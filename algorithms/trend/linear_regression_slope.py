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
            return AlgorithmResult(self.name, symbol, None, "NEUTRO", "Datos insuficientes.")
        x = np.arange(len(closes))
        slope, _ = np.polyfit(x, closes, 1)
        norm = slope / closes.mean() if closes.mean() else 0.0
        direction = "up" if slope > 0 else ("down" if slope < 0 else "flat")

        abs_norm = abs(norm)
        if abs_norm < 0.000005:
            signal = "LATERAL"
            strength = "sin tendencia clara"
        elif abs_norm < 0.00005:
            strength = "tendencia débil"
            signal = "ALCISTA DÉBIL" if direction == "up" else "BAJISTA DÉBIL"
        else:
            strength = "tendencia fuerte"
            signal = "TENDENCIA ALCISTA" if direction == "up" else "TENDENCIA BAJISTA"

        dir_emoji = "⬆️" if direction == "up" else ("⬇️" if direction == "down" else "↔️")
        interp = (
            f"{dir_emoji} Pendiente de regresión lineal ({self.period} barras): {slope:+.4f} pts/barra. "
            f"Normalizada: {norm:.2e} — {strength}. "
            f"{'El precio sube en promedio cada barra.' if direction == 'up' else 'El precio baja en promedio cada barra.' if direction == 'down' else 'Sin dirección definida.'}"
        )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(slope, 6),
            signal=signal,
            interpretation=interp,
            metadata={"period": self.period, "slope": float(slope), "normalized": float(norm), "direction": direction},
        )
