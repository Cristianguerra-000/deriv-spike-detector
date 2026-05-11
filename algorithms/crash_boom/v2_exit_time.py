"""v2 · Exit Time-Stop — sal ANTES del próximo spike, no en él.

Regla humana
────────────
Calculamos el cuantil 10 de los intervalos históricos:
  → "el 10 % de los spikes ocurre antes de Q10 velas".

El time-stop es:
  exit_at = Q10 - SAFETY_BUFFER    (mínimo 3 velas)

Cuando bars_since_spike alcanza ese valor → señal EXIT.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.v2_spike_state import get_state


SAFETY_BUFFER = 3


def time_stop_bar(intervals) -> int | None:
    arr = list(intervals)
    if len(arr) < 5:
        return None
    q10 = float(np.quantile(arr, 0.10))
    return max(3, int(q10 - SAFETY_BUFFER))


@register
class ExitTimeStopAlgo(AlgorithmBase):
    name = "cb.v2.exit_time"
    category = "crash_boom"
    description = "Time-stop: indica EXIT antes del cuantil-10 de intervalos."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sym = symbol.upper()
        if "CRASH" not in sym and "BOOM" not in sym:
            return AlgorithmResult(self.name, symbol, None, "N/A", "Sólo Crash/Boom.")

        state = get_state(symbol)
        stop_bar = time_stop_bar(state.intervals)
        if stop_bar is None or state.last_spike_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN DATOS",
                                   "Aún no hay suficientes intervalos para calcular time-stop.")

        bars_since = (len(df) - 1) - state.last_spike_idx
        remaining = stop_bar - bars_since

        if bars_since >= stop_bar:
            signal = "EXIT YA"
            interp = (f"Se alcanzó el time-stop ({stop_bar} velas tras spike). "
                      f"Cerrar posición antes de que entre el 10% de los spikes más rápidos.")
        elif remaining <= 2:
            signal = "EXIT INMINENTE"
            interp = (f"Sólo quedan {remaining} velas hasta el time-stop. Prepararse para cerrar.")
        else:
            signal = "MANTENER"
            interp = (f"Time-stop a {stop_bar} velas tras spike. Faltan {remaining} velas.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=remaining, signal=signal, interpretation=interp,
            metadata={"stop_bar": stop_bar, "bars_since_spike": bars_since,
                      "remaining": remaining, "samples": len(state.intervals)},
        )
