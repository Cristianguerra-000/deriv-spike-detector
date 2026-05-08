"""Media Móvil Exponencial (EMA).

Detecta si el precio está por encima o debajo de la EMA y cuantifica
el alejamiento porcentual para interpretar la fuerza del movimiento.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class ExponentialMovingAverage(AlgorithmBase):
    name = "math.ema"
    category = "mathematical"
    description = "EMA: detecta dirección y fuerza del momentum respecto al precio."

    def __init__(self, period: int = 20) -> None:
        self.period = period

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        ema = df["close"].ewm(span=self.period, adjust=False).mean().iloc[-1]
        price = float(df["close"].iloc[-1])
        distance_pct = (price - ema) / ema * 100

        if distance_pct > 1.5:
            signal = "ALCISTA"
            interp = (
                f"El precio está {distance_pct:.2f}% POR ENCIMA de la EMA({self.period}). "
                f"Momentum alcista activo y en expansión. Los compradores controlan el mercado."
            )
        elif distance_pct > 0.3:
            signal = "ALCISTA MODERADO"
            interp = (
                f"Precio ligeramente por encima de la EMA({self.period}) (+{distance_pct:.2f}%). "
                f"Sesgo alcista débil. Confirmar con volumen o MACD antes de operar."
            )
        elif distance_pct < -1.5:
            signal = "BAJISTA"
            interp = (
                f"El precio está {abs(distance_pct):.2f}% POR DEBAJO de la EMA({self.period}). "
                f"Presión vendedora dominante. El mercado está en caída sostenida."
            )
        elif distance_pct < -0.3:
            signal = "BAJISTA MODERADO"
            interp = (
                f"Precio ligeramente por debajo de la EMA({self.period}) ({distance_pct:.2f}%). "
                f"Sesgo bajista débil. Posible zona de soporte dinámico."
            )
        else:
            signal = "NEUTRO"
            interp = (
                f"Precio pegado a la EMA({self.period}) (±{abs(distance_pct):.2f}%). "
                f"Mercado indeciso. Esperar ruptura en cualquier dirección."
            )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(ema, 5),
            signal=signal,
            interpretation=interp,
            metadata={
                "period": self.period,
                "price": round(price, 5),
                "distance_pct": round(distance_pct, 4),
            },
        )
