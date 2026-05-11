"""v2 · Position Sizing — tamaño relativo guiado por hazard real.

Regla humana
────────────
size_factor = clamp(1 - hazard_p50, 0.10, 1.00)

  · hazard alta  → tamaño reducido (mercado cerca de un spike contrario)
  · hazard baja  → tamaño normal

Devuelve un porcentaje de la posición base (0..100). No es nominal en USD:
la conversión a USD/lots la hace el ejecutor externo.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.v2_spike_state import get_state
from algorithms.crash_boom.v2_hazard_model import prob_spike


@register
class SizingV2Algo(AlgorithmBase):
    name = "cb.v2.sizing"
    category = "crash_boom"
    description = "Tamaño de posición (% del base) según hazard real."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sym = symbol.upper()
        if "CRASH" not in sym and "BOOM" not in sym:
            return AlgorithmResult(self.name, symbol, None, "N/A", "Sólo Crash/Boom.")

        state = get_state(symbol)
        if len(state.intervals) < 5 or state.last_spike_idx is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN DATOS",
                                   "Sin suficientes intervalos para dimensionar.")

        bars_since = (len(df) - 1) - state.last_spike_idx
        p50 = prob_spike(state.intervals, max(0, bars_since), 50)
        if p50["p"] is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN DATOS",
                                   "Hazard no calculable.")

        factor = max(0.10, min(1.0, 1.0 - p50["p"]))
        pct = round(factor * 100, 1)
        if factor >= 0.8:
            signal = "TAMAÑO PLENO"
        elif factor >= 0.5:
            signal = "TAMAÑO REDUCIDO"
        else:
            signal = "TAMAÑO MÍNIMO"
        interp = (f"Hazard P50={p50['p']*100:.1f}% → usar {pct}% del tamaño base. "
                  "Sizing inverso al riesgo de spike contrario.")
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=pct, signal=signal, interpretation=interp,
            metadata={"size_pct": pct, "hazard_p50": p50["p"]},
        )
