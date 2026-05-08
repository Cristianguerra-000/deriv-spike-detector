"""BOOM #4 — Boom Interval Variance.

Mide la regularidad de los intervalos entre booms.
Mismo concepto que crash.spike_interval_var pero para BOOM (wick superior).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class BoomIntervalVariance(AlgorithmBase):
    name = "boom.spike_interval_var"
    category = "crash_boom"
    description = "Regularidad de los intervalos entre booms. Bajo CV = más predecible."

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
        spike_positions = wick[wick > threshold].index.tolist()

        if len(spike_positions) < 3:
            return AlgorithmResult(
                self.name, symbol, None, "INSUFICIENTE",
                f"Necesario mínimo 3 booms. Encontrados: {len(spike_positions)}.",
            )

        intervals = np.diff(spike_positions).tolist()
        mean_iv = float(np.mean(intervals))
        std_iv = float(np.std(intervals, ddof=1))
        cv = std_iv / mean_iv if mean_iv else 0.0

        if cv < 0.25:
            signal = "MUY PREDECIBLE"
            interp = (
                f"CV = {cv:.3f} → Los intervalos entre booms son MUY REGULARES. "
                f"Promedio: {mean_iv:.0f} velas ± {std_iv:.0f}. "
                f"Excelente para estrategias de timing de boom."
            )
        elif cv < 0.45:
            signal = "PREDECIBLE"
            interp = (
                f"CV = {cv:.3f} → Intervalos bastante regulares. "
                f"Promedio: {mean_iv:.0f} ± {std_iv:.0f} velas. "
                f"El boom_overdue_score es confiable aquí."
            )
        elif cv < 0.70:
            signal = "IRREGULAR"
            interp = (
                f"CV = {cv:.3f} → Variabilidad moderada-alta en intervalos. "
                f"Promedio: {mean_iv:.0f} ± {std_iv:.0f} velas. "
                f"El timing es incierto. Combinar con otros indicadores."
            )
        else:
            signal = "MUY IRREGULAR"
            interp = (
                f"CV = {cv:.3f} → Los intervalos entre booms son MUY VARIABLES. "
                f"Promedio: {mean_iv:.0f} ± {std_iv:.0f} velas. "
                f"El timing de los booms es impredecible. Usar indicadores de tensión pre-boom."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(cv, 4), signal=signal, interpretation=interp,
            metadata={
                "cv": round(cv, 4),
                "mean_interval": round(mean_iv, 1),
                "std_interval": round(std_iv, 1),
                "boom_count": len(spike_positions),
                "intervals_sample": intervals[-5:],
            },
        )
