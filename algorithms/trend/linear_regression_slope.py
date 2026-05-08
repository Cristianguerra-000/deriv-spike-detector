"""Pendiente de regresión lineal sobre cierres — fuerza de tendencia."""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class LinearRegressionSlope(AlgorithmBase):
    name = "trend.lr_slope"
    category = "trend"
    description = "Pendiente normalizada de regresión lineal sobre N cierres."

    def __init__(self, period: int = 50) -> None:
        self.period = period

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        closes = df["close"].tail(self.period).to_numpy()
        if len(closes) < 2:
            return AlgorithmResult(self.name, symbol, None, {"error": "insufficient"})
        x = np.arange(len(closes))
        slope, intercept = np.polyfit(x, closes, 1)
        norm = slope / closes.mean() if closes.mean() else 0.0
        direction = "up" if slope > 0 else ("down" if slope < 0 else "flat")
        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value={"slope": float(slope), "normalized": float(norm), "direction": direction},
            metadata={"period": self.period},
        )
