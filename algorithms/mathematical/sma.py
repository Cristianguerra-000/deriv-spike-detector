"""Media móvil simple (SMA) — algoritmo matemático básico."""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class SimpleMovingAverage(AlgorithmBase):
    name = "math.sma"
    category = "mathematical"
    description = "Media móvil simple sobre cierre."

    def __init__(self, period: int = 20) -> None:
        self.period = period

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sma = df["close"].rolling(self.period).mean().iloc[-1]
        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=float(sma) if pd.notna(sma) else None,
            metadata={"period": self.period},
        )
