"""ADX — Average Directional Index.

Mide la FUERZA de la tendencia (no la dirección).
+DI vs -DI indica si la presión es compradora o vendedora.
ADX < 20 = rango / ADX 20-40 = tendencia / ADX > 40 = tendencia fuerte.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class ADX(AlgorithmBase):
    name = "trend.adx"
    category = "trend"
    description = "ADX: mide fuerza de tendencia y dominancia compradora/vendedora."

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        high = df["high"]
        low = df["low"]
        close = df["close"]

        prev_high = high.shift(1)
        prev_low = low.shift(1)
        prev_close = close.shift(1)

        tr = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)

        up_move = high - prev_high
        down_move = prev_low - low

        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

        atr = tr.rolling(self.period).mean()
        plus_di = 100 * (plus_dm.rolling(self.period).mean() / atr.replace(0, float("nan")))
        minus_di = 100 * (minus_dm.rolling(self.period).mean() / atr.replace(0, float("nan")))

        di_sum = (plus_di + minus_di).replace(0, float("nan"))
        dx = 100 * (plus_di - minus_di).abs() / di_sum
        adx_val = float(dx.rolling(self.period).mean().iloc[-1])
        plus_val = float(plus_di.iloc[-1])
        minus_val = float(minus_di.iloc[-1])

        if adx_val >= 40:
            strength = "MUY FUERTE"
            strength_text = "Tendencia potente y establecida. Alto riesgo de operar en contra."
        elif adx_val >= 25:
            strength = "FUERTE"
            strength_text = "Tendencia confirmada. Operar a favor de la dirección dominante."
        elif adx_val >= 20:
            strength = "MODERADA"
            strength_text = "Tendencia débil en formación. Confirmar con otros indicadores."
        else:
            strength = "RANGO"
            strength_text = "Sin tendencia definida. El mercado está en rango o lateral. Estrategias de rebote son más efectivas."

        direction = "COMPRADORA (+DI domina)" if plus_val > minus_val else "VENDEDORA (-DI domina)"
        signal = f"{strength}"

        interp = (
            f"ADX = {adx_val:.1f} → Tendencia {strength}. {strength_text} "
            f"Presión dominante: {direction}. "
            f"+DI = {plus_val:.1f} | -DI = {minus_val:.1f}."
        )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(adx_val, 2),
            signal=signal,
            interpretation=interp,
            metadata={
                "period": self.period,
                "plus_di": round(plus_val, 2),
                "minus_di": round(minus_val, 2),
            },
        )
