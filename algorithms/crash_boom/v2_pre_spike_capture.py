"""v2 · Pre-Spike Capture — el "aprendiz" event-driven.

Idea humana
───────────
Cuando ocurre un spike, este módulo MIRA HACIA ATRÁS las últimas 10 velas
y guarda una "huella digital" del estado del mercado justo antes del
evento (la pre-condición). Con el tiempo acumulamos muchas huellas y
podemos preguntarle al mercado actual:

   "¿Te pareces a alguna situación previa al spike?"

Si la respuesta es SÍ → estamos en una zona de riesgo / oportunidad.
Si la respuesta es NO → mercado en estado normal.

Las "huellas" se almacenan en memoria del proceso (in-process) y se
pueden persistir en Firestore en su metadata. Sin invenciones:
los features son simples, transparentes y reproducibles.

Features capturados (todos en unidades adimensionales):
    f1  streak             racha direccional pre-spike
    f2  body_growth        crecimiento de cuerpos (últimos 3 vs primeros 3 de 10)
    f3  range_compress     ATR(últimas 5) / ATR(últimas 20)
    f4  drift_slope_norm   pendiente normalizada de cierres
    f5  wick_ratio         wick promedio / cuerpo promedio (presión)
    f6  bars_since_prev    velas desde el spike anterior / promedio histórico
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Optional

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.v2_spike_state import get_state, SymbolState


# ─── Memoria de patrones por símbolo (huellas pre-spike) ────────────────────
_MEMORY: dict[str, Deque[dict]] = {}
_MAX_MEMORY = 500


def _features(window: pd.DataFrame, side: str, bars_since_prev: Optional[int],
              avg_interval: Optional[float]) -> dict:
    """Calcula 6 features explicables de las últimas 10 velas."""
    w = window.tail(10).reset_index(drop=True)
    if len(w) < 10:
        return {}

    bodies = (w["close"] - w["open"])
    abs_bodies = bodies.abs()

    if side == "crash":
        directional = (w["close"] > w["open"]).astype(int)  # alcistas antes del crash
    else:
        directional = (w["close"] < w["open"]).astype(int)  # bajistas antes del boom

    streak = int(directional.tail(5).sum())  # 0..5
    body_growth = float(abs_bodies.iloc[-3:].mean() / max(abs_bodies.iloc[:3].mean(), 1e-9))
    atr5 = float((w["high"] - w["low"]).iloc[-5:].mean())
    atr20 = float((w["high"] - w["low"]).mean())
    range_compress = atr5 / max(atr20, 1e-9)
    slope = float(np.polyfit(range(10), w["close"].values, 1)[0])
    drift_slope_norm = slope / max(float(w["close"].mean()), 1e-9) * 1000

    if side == "crash":
        wicks = w[["open", "close"]].max(axis=1) - w["low"]
    else:
        wicks = w["high"] - w[["open", "close"]].max(axis=1)
    wick_ratio = float(wicks.mean() / max(abs_bodies.mean(), 1e-9))

    overdue_ratio = (bars_since_prev / avg_interval) if (bars_since_prev and avg_interval) else 0.0

    return {
        "streak": streak,
        "body_growth": round(body_growth, 3),
        "range_compress": round(range_compress, 3),
        "drift_slope_norm": round(drift_slope_norm, 3),
        "wick_ratio": round(wick_ratio, 3),
        "overdue_ratio": round(overdue_ratio, 3),
    }


def on_spike_event(symbol: str, df: pd.DataFrame, state: SymbolState) -> None:
    """Llamado por v2_spike_state cuando se confirma un NUEVO spike."""
    s = symbol.upper()
    if s not in _MEMORY:
        _MEMORY[s] = deque(maxlen=_MAX_MEMORY)

    # Tomar las 10 velas ANTERIORES al spike (no incluyen la del spike)
    pre = df.iloc[:-1].tail(10)
    if len(pre) < 10:
        return

    prev_interval = state.intervals[-1] if state.intervals else None
    avg = (sum(state.intervals) / len(state.intervals)) if state.intervals else None
    feats = _features(pre, state.side, prev_interval, avg)
    if not feats:
        return

    _MEMORY[s].append(feats)


def _similarity(current: dict, snapshot: dict) -> float:
    """Distancia 0..1 (1 = idéntico) entre dos huellas."""
    keys = ["streak", "body_growth", "range_compress",
            "drift_slope_norm", "wick_ratio", "overdue_ratio"]
    # Distancia euclidiana sobre features estandarizados toscamente
    diffs = []
    for k in keys:
        a, b = float(current.get(k, 0)), float(snapshot.get(k, 0))
        # Normalización suave (rango típico observado en sintéticos)
        scale = {"streak": 5, "body_growth": 3, "range_compress": 3,
                 "drift_slope_norm": 10, "wick_ratio": 5, "overdue_ratio": 2}[k]
        diffs.append(((a - b) / scale) ** 2)
    d = math_sqrt(sum(diffs))
    return max(0.0, 1.0 - d)


def math_sqrt(x: float) -> float:  # evitamos import por una sola llamada
    return float(np.sqrt(max(x, 0.0)))


def similarity_to_memory(symbol: str, df: pd.DataFrame) -> dict:
    """¿Qué tanto se parece el estado actual a huellas pre-spike pasadas?"""
    s = symbol.upper()
    mem = _MEMORY.get(s)
    state = get_state(symbol)
    if state.side == "other" or not mem or len(mem) < 3:
        return {"matches": 0, "best": 0.0, "avg_top3": 0.0}

    prev_interval = state.intervals[-1] if state.intervals else None
    avg = (sum(state.intervals) / len(state.intervals)) if state.intervals else None
    bars_since = (len(df) - 1 - state.last_spike_idx) if state.last_spike_idx else None
    feats = _features(df, state.side, bars_since, avg)
    if not feats:
        return {"matches": 0, "best": 0.0, "avg_top3": 0.0}

    sims = sorted([_similarity(feats, snap) for snap in mem], reverse=True)
    top3 = sims[:3]
    return {
        "matches": len(mem),
        "best": round(top3[0], 3),
        "avg_top3": round(float(np.mean(top3)), 3),
        "features": feats,
    }


@register
class PreSpikeCaptureAlgo(AlgorithmBase):
    name = "cb.v2.pre_capture"
    category = "crash_boom"
    description = "Aprende patrones pre-spike y mide similitud del estado actual."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sym = symbol.upper()
        if "CRASH" not in sym and "BOOM" not in sym:
            return AlgorithmResult(self.name, symbol, None, "N/A", "Sólo Crash/Boom.")

        sim = similarity_to_memory(symbol, df)
        n = sim["matches"]

        if n < 3:
            return AlgorithmResult(
                self.name, symbol, 0.0, "APRENDIENDO",
                f"Sólo {n} huellas pre-spike registradas. Aún no se puede estimar similitud. "
                "Cada nuevo spike se incorpora automáticamente al expediente.",
                metadata={"matches": n, "features": sim.get("features", {})},
            )

        best = sim["best"]
        avg3 = sim["avg_top3"]

        if best >= 0.85 and avg3 >= 0.75:
            signal = "PATRÓN PRE-SPIKE FUERTE"
            interp = (f"El estado actual se parece mucho ({best*100:.0f}% al mejor match) "
                      f"a patrones que precedieron a {n} spikes anteriores.")
        elif best >= 0.70:
            signal = "PATRÓN PRE-SPIKE MODERADO"
            interp = (f"Similitud moderada con históricos pre-spike "
                      f"(best={best*100:.0f}%, top3={avg3*100:.0f}%).")
        else:
            signal = "SIN PATRÓN PRE-SPIKE"
            interp = (f"El estado actual NO se parece a patrones pre-spike "
                      f"(best={best*100:.0f}%). Comportamiento ordinario.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(best * 100, 1), signal=signal, interpretation=interp,
            metadata=sim,
        )
