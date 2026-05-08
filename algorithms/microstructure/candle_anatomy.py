"""Tamaño promedio de cuerpo y mecha — microestructura básica."""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class CandleAnatomy(AlgorithmBase):
    name = "micro.candle_anatomy"
    category = "microstructure"
    description = "Cuerpo, mecha superior e inferior promedio."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        body = (df["close"] - df["open"]).abs()
        upper = df["high"] - df[["open", "close"]].max(axis=1)
        lower = df[["open", "close"]].min(axis=1) - df["low"]
        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value={
                "avg_body": float(body.mean()),
                "avg_upper_wick": float(upper.mean()),
                "avg_lower_wick": float(lower.mean()),
            },
        )
