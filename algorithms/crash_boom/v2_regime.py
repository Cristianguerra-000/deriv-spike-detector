"""v2 · Regime Engine — 3 estados claros, sin heurísticas inventadas.

Estados (humano-legibles):
    POST_SPIKE   → 1..6 velas tras un spike confirmado (mejor zona de entrada)
    OVERDUE      → hazard P(spike en 20 velas) ≥ 30 %
    DRIFT        → cualquier otro caso (mercado calmado entre spikes)

Sin "TENSIÓN" inventada por contar velas alcistas; eso se queda en
el módulo de tensión legacy como métrica auxiliar.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.v2_spike_state import get_state
from algorithms.crash_boom.v2_hazard_model import prob_spike


POST_SPIKE_WINDOW = 6     # velas
OVERDUE_THRESHOLD = 0.30  # P(spike) en 20 velas


def classify_regime(symbol: str, df: pd.DataFrame) -> dict:
    state = get_state(symbol)
    bars_since = None
    if state.last_spike_idx is not None:
        bars_since = (len(df) - 1) - state.last_spike_idx

    if bars_since is not None and bars_since <= POST_SPIKE_WINDOW:
        return {
            "regime": "POST_SPIKE",
            "bars_since": bars_since,
            "hazard_p20": None,
            "reason": f"Han pasado sólo {bars_since} velas tras el spike (ventana ≤ {POST_SPIKE_WINDOW}).",
        }

    if len(state.intervals) >= 5 and bars_since is not None:
        p20 = prob_spike(state.intervals, bars_since, 20)
        if p20["p"] is not None and p20["p"] >= OVERDUE_THRESHOLD:
            return {
                "regime": "OVERDUE",
                "bars_since": bars_since,
                "hazard_p20": p20["p"],
                "reason": f"P(spike en 20 velas) = {p20['p']*100:.1f}% ≥ {OVERDUE_THRESHOLD*100:.0f}%.",
            }
        return {
            "regime": "DRIFT",
            "bars_since": bars_since,
            "hazard_p20": p20["p"],
            "reason": f"Hazard moderada (P20 = {(p20['p'] or 0)*100:.1f}%). Drift normal.",
        }

    return {
        "regime": "DRIFT",
        "bars_since": bars_since,
        "hazard_p20": None,
        "reason": "Datos insuficientes para calcular hazard; se asume drift por defecto.",
    }


@register
class RegimeV2Algo(AlgorithmBase):
    name = "cb.v2.regime"
    category = "crash_boom"
    description = "Régimen del mercado: POST_SPIKE / OVERDUE / DRIFT."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sym = symbol.upper()
        if "CRASH" not in sym and "BOOM" not in sym:
            return AlgorithmResult(self.name, symbol, None, "N/A", "Sólo Crash/Boom.")

        info = classify_regime(symbol, df)
        signal = info["regime"]
        interp = info["reason"]
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=signal, signal=signal, interpretation=interp,
            metadata=info,
        )
