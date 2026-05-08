"""CRASH #10 — Spike Calendar (Distribución de Intervalos).

Analiza la distribución estadística de los intervalos entre crashes:
percentiles, moda del intervalo, y dónde cae el intervalo actual
dentro de la distribución histórica.

Permite saber si ya pasamos el percentil 50, 75, o 90 de la distribución.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashSpikeCalendar(AlgorithmBase):
    name = "crash.spike_calendar"
    category = "crash_boom"
    description = "Distribución histórica de intervalos. ¿En qué percentil estamos ahora?"

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_pos = wick[wick > threshold].index.tolist()

        if len(spike_pos) < 3:
            return AlgorithmResult(
                self.name, symbol, 0, "INSUFICIENTE",
                "Se necesitan al menos 3 spikes para construir la distribución.",
            )

        intervals = np.diff(spike_pos)
        p25 = float(np.percentile(intervals, 25))
        p50 = float(np.percentile(intervals, 50))
        p75 = float(np.percentile(intervals, 75))
        p90 = float(np.percentile(intervals, 90))

        # Barras desde el último spike
        bars_since = len(window) - 1 - spike_pos[-1]

        # Percentil actual
        current_pct = float(
            np.sum(intervals <= bars_since) / len(intervals) * 100
        )

        if bars_since > p90:
            signal = "PERCENTIL >90"
            interp = (
                f"Llevas {bars_since} velas desde el último crash. "
                f"Estás por ENCIMA del percentil 90 de la distribución histórica. "
                f"Solo el 10% de los intervalos han durado más que esto. "
                f"Zona de MÁXIMO RIESGO estadístico. "
                f"P50={p50:.0f} | P75={p75:.0f} | P90={p90:.0f} velas."
            )
        elif bars_since > p75:
            signal = "PERCENTIL >75"
            interp = (
                f"Llevas {bars_since} velas. Superaste el percentil 75 ({p75:.0f} velas). "
                f"75% de los crashes han ocurrido antes de este punto. "
                f"Riesgo ALTO. Zona de alta probabilidad de crash inminente."
            )
        elif bars_since > p50:
            signal = "PERCENTIL >50"
            interp = (
                f"Llevas {bars_since} velas. Superaste la mediana ({p50:.0f} velas). "
                f"Más de la mitad de los crashes ya habrían ocurrido. "
                f"Riesgo moderado-alto. Zona de atención activa."
            )
        else:
            signal = "PERCENTIL BAJO"
            interp = (
                f"Llevas {bars_since} velas (percentil ~{current_pct:.0f}% de la distribución). "
                f"Aún por debajo de la mediana ({p50:.0f} velas). "
                f"Zona estadísticamente segura. El drift tiene margen de continuación."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(current_pct, 1), signal=signal, interpretation=interp,
            metadata={
                "current_percentile": round(current_pct, 1),
                "bars_since_last_spike": bars_since,
                "p25": round(p25, 0),
                "p50": round(p50, 0),
                "p75": round(p75, 0),
                "p90": round(p90, 0),
                "spike_count": len(spike_pos),
            },
        )
