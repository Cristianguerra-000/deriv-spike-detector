"""Detecta máximo y mínimo histórico en la ventana cargada."""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class HistoricalRange(AlgorithmBase):
    name = "hist.range"
    category = "historical"
    description = "Máximo, mínimo y rango total del histórico recibido."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        hi = float(df["high"].max())
        lo = float(df["low"].min())
        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value={"high": hi, "low": lo, "range": hi - lo},
            metadata={"bars": len(df)},
        )
