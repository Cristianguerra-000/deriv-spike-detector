"""ATR (Average True Range) — volatilidad."""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class AverageTrueRange(AlgorithmBase):
    name = "vol.atr"
    category = "volatility"
    description = "Average True Range de N períodos."

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        high, low, close = df["high"], df["low"], df["close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(self.period).mean().iloc[-1]
        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=float(atr) if pd.notna(atr) else None,
            metadata={"period": self.period},
        )
