"""v2 · Signal Final — la única señal que el humano debe leer.

Salida (un humano sin saber estadística puede entenderla):

  action          : SELL / BUY / WAIT / EXIT
  confidence_pct  : 0..100 — basada en cantidad de datos reales
  hazard_p10/20/50: probabilidad real del próximo spike
  size_pct        : tamaño recomendado relativo al base
  reason          : una frase corta que explica POR QUÉ
  warnings        : lista de cosas que el humano debe saber

NUNCA emite SELL en Boom ni BUY en Crash. Punto.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.v2_spike_state import get_state
from algorithms.crash_boom.v2_regime import classify_regime
from algorithms.crash_boom.v2_hazard_model import prob_spike
from algorithms.crash_boom.v2_pre_spike_capture import similarity_to_memory
from algorithms.crash_boom.v2_entry import decide_entry
from algorithms.crash_boom.v2_exit_time import time_stop_bar
from algorithms.crash_boom.v2_sizing import SizingV2Algo
from algorithms.crash_boom.v2_quality import check_quality


def _confidence(num_intervals: int, samples_similarity: int, quality_ok: bool) -> float:
    """Confianza honesta: depende de la cantidad de datos reales."""
    if not quality_ok:
        return 0.0
    base = min(num_intervals / 30.0, 1.0) * 70.0   # hasta 70% por hazard
    extra = min(samples_similarity / 50.0, 1.0) * 30.0  # +30% por aprendiz
    return round(base + extra, 1)


def build_signal(df: pd.DataFrame, symbol: str) -> dict:
    sym = symbol.upper()
    if "CRASH" not in sym and "BOOM" not in sym:
        return {"action": "N/A", "reason": "Símbolo no es Crash/Boom."}

    qual = check_quality(df, symbol)
    state = get_state(symbol)
    side = state.side

    warnings: list[str] = []
    if not qual["ok"]:
        warnings.append(qual["reason"])

    bars_since = None
    if state.last_spike_idx is not None:
        bars_since = (len(df) - 1) - state.last_spike_idx

    intervals = list(state.intervals)
    if len(intervals) < 5:
        warnings.append(f"Sólo {len(intervals)} intervalos observados (< 5). Sin probabilidad fiable.")

    p10 = prob_spike(intervals, max(0, bars_since or 0), 10) if intervals else {"p": None}
    p20 = prob_spike(intervals, max(0, bars_since or 0), 20) if intervals else {"p": None}
    p50 = prob_spike(intervals, max(0, bars_since or 0), 50) if intervals else {"p": None}

    regime_info = classify_regime(symbol, df)
    sim = similarity_to_memory(symbol, df)
    stop_bar = time_stop_bar(state.intervals)

    # Decisión
    if not qual["ok"] or len(intervals) < 5:
        action, reason = "WAIT", "Datos insuficientes o feed no apto. No se opera."
    else:
        # ¿Hay que salir?
        if (stop_bar is not None and bars_since is not None
                and bars_since >= stop_bar):
            action = "EXIT"
            reason = (f"Time-stop alcanzado ({bars_since} ≥ {stop_bar} velas). "
                      f"Salir antes del próximo spike contrario.")
        else:
            entry = decide_entry(df, symbol)
            action = entry["action"]
            reason = entry["reason"]

    # Tamaño
    size_algo = SizingV2Algo()
    size_res = size_algo.run(df, symbol)
    size_pct = size_res.metadata.get("size_pct", 0.0) if size_res.metadata else 0.0

    confidence = _confidence(len(intervals), sim.get("matches", 0), qual["ok"])

    if sim.get("matches", 0) >= 3 and sim.get("best", 0) > 0.85:
        warnings.append("Patrón actual MUY similar a pre-spike. Riesgo elevado.")

    return {
        "action": action,
        "side": side,
        "reason": reason,
        "confidence_pct": confidence,
        "hazard": {
            "p10_pct": None if p10["p"] is None else round(p10["p"] * 100, 1),
            "p20_pct": None if p20["p"] is None else round(p20["p"] * 100, 1),
            "p50_pct": None if p50["p"] is None else round(p50["p"] * 100, 1),
            "samples": len(intervals),
        },
        "regime": regime_info["regime"],
        "bars_since_spike": bars_since,
        "pre_spike_similarity_pct": round(sim.get("best", 0.0) * 100, 1),
        "patterns_learned": sim.get("matches", 0),
        "size_pct": size_pct,
        "time_stop_bar": stop_bar,
        "warnings": warnings,
        "quality_ok": qual["ok"],
    }


@register
class SignalFinalV2Algo(AlgorithmBase):
    name = "cb.v2.signal"
    category = "crash_boom"
    description = "★ Señal final v2 — Crash→SELL, Boom→BUY, basada en probabilidades reales."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sig = build_signal(df, symbol)
        if sig["action"] == "N/A":
            return AlgorithmResult(self.name, symbol, None, "N/A", sig["reason"])

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=sig["action"], signal=sig["action"],
            interpretation=sig["reason"],
            metadata=sig,
        )
