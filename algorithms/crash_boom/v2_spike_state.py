"""v2 · Spike State — memoria persistente del símbolo.

Idea humana
───────────
Cada símbolo Crash/Boom tiene un "expediente médico" en memoria:
  · cuándo ocurrió cada spike pasado (índice de vela)
  · qué tamaño tuvo (magnitud en puntos)
  · qué intervalo lo separó del anterior
  · cuál es el umbral robusto vigente (recalibrado en cada spike)

Este expediente se RECALCULA sólo cuando ocurre un evento nuevo
(spike confirmado al cierre de vela). El resto del tiempo se LEE.
Esto evita recomputar 500 velas cada minuto.

Una vela = un minuto. No se usan ticks intra-vela.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


# ─── Estado en memoria (por símbolo) ────────────────────────────────────────
@dataclass
class SymbolState:
    symbol: str
    side: str                            # "crash" | "boom"
    last_spike_idx: Optional[int] = None # índice (en df) del último spike confirmado
    intervals: Deque[int] = field(default_factory=lambda: deque(maxlen=200))
    magnitudes: Deque[float] = field(default_factory=lambda: deque(maxlen=200))
    threshold: float = 0.0               # umbral MAD vigente
    bars_seen: int = 0                   # total de velas procesadas
    last_processed_time: Optional[int] = None  # timestamp de la última vela vista


# Diccionario global keyed por símbolo
_STATE: dict[str, SymbolState] = {}


def get_state(symbol: str) -> SymbolState:
    """Devuelve (creando si hace falta) el estado del símbolo."""
    s = symbol.upper()
    if s not in _STATE:
        side = "crash" if "CRASH" in s else ("boom" if "BOOM" in s else "other")
        _STATE[s] = SymbolState(symbol=s, side=side)
    return _STATE[s]


def reset_state(symbol: str) -> None:
    """Reinicia el expediente del símbolo (útil en test)."""
    _STATE.pop(symbol.upper(), None)


def _detect_spike_in_last_candle(df: pd.DataFrame, side: str, threshold: float) -> tuple[bool, float]:
    """¿La última vela cerrada es un spike? Devuelve (es_spike, magnitud_pts)."""
    last = df.iloc[-1]
    if side == "crash":
        wick = float(last["open"] if last["open"] > last["close"] else last["close"]) - float(last["low"])
    elif side == "boom":
        wick = float(last["high"]) - float(last["open"] if last["open"] > last["close"] else last["close"])
    else:
        return False, 0.0
    return wick > threshold, wick


def _refresh(state: SymbolState, df: pd.DataFrame) -> dict:
    """Actualiza el expediente con la última vela. Detecta spike si lo hubo.

    Retorna info legible para el AlgorithmResult.
    """
    from algorithms.crash_boom.v2_adaptive_threshold import robust_threshold

    if state.side == "other":
        return {"ok": False, "reason": "símbolo no es Crash/Boom"}

    # Umbral robusto (excluye outliers que ya son spikes)
    state.threshold = robust_threshold(df, state.side)

    is_spike, mag = _detect_spike_in_last_candle(df, state.side, state.threshold)
    current_idx = len(df) - 1
    state.bars_seen += 1
    new_event = False

    if is_spike:
        # ¿Es un spike nuevo (no el mismo ya registrado)?
        if state.last_spike_idx is None or current_idx != state.last_spike_idx:
            if state.last_spike_idx is not None:
                interval = current_idx - state.last_spike_idx
                if interval > 0:
                    state.intervals.append(interval)
            state.magnitudes.append(mag)
            state.last_spike_idx = current_idx
            new_event = True

    bars_since = (current_idx - state.last_spike_idx) if state.last_spike_idx is not None else None

    return {
        "ok": True,
        "side": state.side,
        "is_spike": is_spike,
        "new_event": new_event,
        "last_spike_idx": state.last_spike_idx,
        "bars_since_spike": bars_since,
        "num_spikes": len(state.magnitudes),
        "avg_interval": (sum(state.intervals) / len(state.intervals)) if state.intervals else None,
        "avg_magnitude": (sum(state.magnitudes) / len(state.magnitudes)) if state.magnitudes else None,
        "threshold": state.threshold,
    }


@register
class SpikeStateAlgo(AlgorithmBase):
    name = "cb.v2.state"
    category = "crash_boom"
    description = "Mantiene expediente del símbolo (spikes, intervalos, magnitudes). Solo Crash/Boom."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sym = symbol.upper()
        if "CRASH" not in sym and "BOOM" not in sym:
            return AlgorithmResult(self.name, symbol, None, "N/A",
                                   "Sólo aplica a índices Crash/Boom.")
        if len(df) < 30:
            return AlgorithmResult(self.name, symbol, None, "SIN DATOS",
                                   "Se necesitan al menos 30 velas para inicializar el expediente.")

        state = get_state(symbol)
        info = _refresh(state, df)

        if info["is_spike"] and info["new_event"]:
            # Notifica al capturador pre-spike (event-driven)
            try:
                from algorithms.crash_boom.v2_pre_spike_capture import on_spike_event
                on_spike_event(symbol, df, state)
            except Exception:
                pass
            signal = "NUEVO SPIKE"
            interp = (
                f"⚡ Spike confirmado en la última vela "
                f"(magnitud {info['avg_magnitude']:.2f} pts promedio). "
                f"Total registrados: {info['num_spikes']}. "
                f"Intervalo promedio: {info['avg_interval']:.0f} velas."
                if info['avg_interval'] else
                "⚡ Primer spike registrado; aún no hay intervalos para estimar frecuencia."
            )
        elif info["bars_since_spike"] is not None:
            signal = "EN SEGUIMIENTO"
            interp = (
                f"Han pasado {info['bars_since_spike']} velas desde el último spike. "
                f"Histórico: {info['num_spikes']} spikes, intervalo promedio "
                f"{info['avg_interval']:.0f} velas."
                if info['avg_interval'] else
                f"Han pasado {info['bars_since_spike']} velas desde el primer spike registrado."
            )
        else:
            signal = "SIN HISTORIAL"
            interp = "Aún no se ha registrado ningún spike en este símbolo."

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=info["num_spikes"], signal=signal, interpretation=interp,
            metadata={
                "side": info["side"],
                "is_spike": info["is_spike"],
                "new_event": info["new_event"],
                "bars_since_spike": info["bars_since_spike"],
                "num_spikes": info["num_spikes"],
                "avg_interval": info["avg_interval"],
                "avg_magnitude": info["avg_magnitude"],
                "threshold_pts": info["threshold"],
            },
        )
