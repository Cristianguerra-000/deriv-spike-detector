"""CRASH #4 — Spike Interval Variance.

Mide la regularidad de los intervalos entre crasheos.
Alta varianza = impredecible. Baja varianza = patrón estable y confiable.

Coeficiente de variación (CV) = std / mean. CV < 0.4 = predecible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashSpikeIntervalVariance(AlgorithmBase):
    name = "crash.spike_interval_var"
    category = "crash_boom"
    description = "Regularidad de los intervalos entre crasheos. Bajo CV = más predecible."

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
        spike_positions = wick[wick > threshold].index.tolist()

        if len(spike_positions) < 3:
            return AlgorithmResult(
                self.name, symbol, None, "INSUFICIENTE",
                f"Se necesitan al menos 3 spikes para calcular varianza. Encontrados: {len(spike_positions)}.",
            )

        intervals = np.diff(spike_positions).tolist()
        mean_iv = float(np.mean(intervals))
        std_iv = float(np.std(intervals, ddof=1))
        cv = std_iv / mean_iv if mean_iv else 0.0

        if cv < 0.25:
            signal = "MUY PREDECIBLE"
            interp = (
                f"CV = {cv:.3f} → Los intervalos entre crashes son MUY REGULARES. "
                f"Promedio: {mean_iv:.0f} velas ± {std_iv:.0f}. "
                f"Este índice tiene un patrón de crash muy consistente. "
                f"El spike_overdue_score es altamente confiable aquí."
            )
        elif cv < 0.45:
            signal = "PREDECIBLE"
            interp = (
                f"CV = {cv:.3f} → Intervalos bastante regulares. "
                f"Promedio: {mean_iv:.0f} ± {std_iv:.0f} velas. "
                f"El timing del próximo crash es estimable con razonable confianza."
            )
        elif cv < 0.70:
            signal = "IRREGULAR"
            interp = (
                f"CV = {cv:.3f} → Intervalos con variabilidad moderada-alta. "
                f"Promedio: {mean_iv:.0f} ± {std_iv:.0f} velas. "
                f"El timing de los crashes es incierto. Usar el overdue score con cautela."
            )
        else:
            signal = "MUY IRREGULAR"
            interp = (
                f"CV = {cv:.3f} → Intervalos MUY VARIABLES. "
                f"Promedio: {mean_iv:.0f} ± {std_iv:.0f} velas. "
                f"El patrón de crashes es impredecible en timing. "
                f"Estrategias basadas en countdown tienen baja confianza aquí."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(cv, 4), signal=signal, interpretation=interp,
            metadata={
                "cv": round(cv, 4),
                "mean_interval": round(mean_iv, 1),
                "std_interval": round(std_iv, 1),
                "spike_count": len(spike_positions),
                "intervals_sample": intervals[-5:],
            },
        )
