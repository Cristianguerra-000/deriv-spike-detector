"""BOOM #10 — Boom Spike Calendar.

Distribución estadística de los intervalos entre booms.
Percentiles P25/P50/P75/P90 para saber dónde estamos en la distribución.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class BoomSpikeCalendar(AlgorithmBase):
    name = "boom.spike_calendar"
    category = "crash_boom"
    description = "Distribución histórica de intervalos entre booms. ¿En qué percentil estamos?"

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["high"] - window[["open", "close"]].max(axis=1)
        spike_pos = wick[wick > threshold].index.tolist()

        if len(spike_pos) < 3:
            return AlgorithmResult(
                self.name, symbol, 0, "INSUFICIENTE",
                "Se necesitan al menos 3 booms para construir la distribución.",
            )

        intervals = np.diff(spike_pos)
        p25 = float(np.percentile(intervals, 25))
        p50 = float(np.percentile(intervals, 50))
        p75 = float(np.percentile(intervals, 75))
        p90 = float(np.percentile(intervals, 90))

        bars_since = len(window) - 1 - spike_pos[-1]
        current_pct = float(np.sum(intervals <= bars_since) / len(intervals) * 100)

        if bars_since > p90:
            signal = "PERCENTIL >90"
            interp = (
                f"Llevas {bars_since} velas desde el último boom. "
                f"ENCIMA del percentil 90 de la distribución histórica. "
                f"Solo el 10% de los intervalos han durado más. "
                f"MÁXIMA PROBABILIDAD de boom inminente. "
                f"P50={p50:.0f} | P75={p75:.0f} | P90={p90:.0f} velas."
            )
        elif bars_since > p75:
            signal = "PERCENTIL >75"
            interp = (
                f"Llevas {bars_since} velas. Superaste el percentil 75 ({p75:.0f} velas). "
                f"75% de los booms ya habrían ocurrido. "
                f"Alta probabilidad de boom próximo. Preparar estrategia."
            )
        elif bars_since > p50:
            signal = "PERCENTIL >50"
            interp = (
                f"Llevas {bars_since} velas. Superaste la mediana ({p50:.0f} velas). "
                f"Más de la mitad de los booms habrían ocurrido ya. "
                f"Zona de atención moderada-alta."
            )
        else:
            signal = "PERCENTIL BAJO"
            interp = (
                f"Llevas {bars_since} velas (percentil ~{current_pct:.0f}% de la distribución). "
                f"Por debajo de la mediana ({p50:.0f} velas). "
                f"Zona estadísticamente segura para el drift bajista."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(current_pct, 1), signal=signal, interpretation=interp,
            metadata={
                "current_percentile": round(current_pct, 1),
                "bars_since_last_boom": bars_since,
                "p25": round(p25, 0),
                "p50": round(p50, 0),
                "p75": round(p75, 0),
                "p90": round(p90, 0),
                "boom_count": len(spike_pos),
            },
        )
