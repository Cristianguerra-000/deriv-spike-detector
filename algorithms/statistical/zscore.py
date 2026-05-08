"""Z-Score del último cierre respecto a la media móvil."""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class ZScore(AlgorithmBase):
    name = "stat.zscore"
    category = "statistical"
    description = "Z-Score del último cierre."

    def __init__(self, period: int = 50) -> None:
        self.period = period

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        window = df["close"].tail(self.period)
        mean = window.mean()
        std = window.std(ddof=0)
        if not std:
            return AlgorithmResult(self.name, symbol, 0.0, {"period": self.period})
        z = (df["close"].iloc[-1] - mean) / std
        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=float(z),
            metadata={"period": self.period, "mean": float(mean), "std": float(std)},
        )
