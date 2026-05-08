"""Media Móvil Ponderada (WMA).

Compara WMA vs SMA del mismo período para detectar aceleración:
si WMA > SMA, los precios recientes (mayor peso) están más altos → inercia compradora.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class WeightedMovingAverage(AlgorithmBase):
    name = "math.wma"
    category = "mathematical"
    description = "WMA: detecta aceleración del precio comparando con SMA del mismo período."

    def __init__(self, period: int = 20) -> None:
        self.period = period

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        n = min(self.period, len(df))
        weights = np.arange(1, n + 1, dtype=float)
        closes = df["close"].tail(n).to_numpy(dtype=float)

        wma = float(np.dot(closes, weights) / weights.sum())
        sma = float(closes.mean())
        diff = wma - sma
        diff_pct = (diff / sma * 100) if sma else 0.0

        if diff_pct > 0.05:
            signal = "ACELERACIÓN ALCISTA"
            interp = (
                f"WMA({n}) = {wma:.5f} supera a SMA({n}) = {sma:.5f} en {diff_pct:.3f}%. "
                f"Las velas RECIENTES tienen mayor peso → los compradores están acelerando. "
                f"Buena señal de entrada en la dirección del impulso."
            )
        elif diff_pct < -0.05:
            signal = "ACELERACIÓN BAJISTA"
            interp = (
                f"WMA({n}) = {wma:.5f} por debajo de SMA({n}) = {sma:.5f} en {abs(diff_pct):.3f}%. "
                f"Las velas RECIENTES tienen mayor peso → los vendedores están acelerando. "
                f"Cuidado: el impulso bajista se está intensificando."
            )
        else:
            signal = "NEUTRO"
            interp = (
                f"WMA({n}) y SMA({n}) prácticamente iguales (diferencia {diff_pct:.4f}%). "
                f"No hay aceleración en ninguna dirección. Mercado en equilibrio, sin inercia clara."
            )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(wma, 5),
            signal=signal,
            interpretation=interp,
            metadata={
                "period": n,
                "wma": round(wma, 5),
                "sma": round(sma, 5),
                "diff_pct": round(diff_pct, 4),
            },
        )
