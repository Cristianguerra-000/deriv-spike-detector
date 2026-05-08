"""Canal de Keltner.

Similar a Bollinger pero usa ATR en vez de desviación estándar.
Más robusto ante picos de volatilidad. La ruptura del canal confirma
breakouts reales con alta probabilidad de continuación.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class KeltnerChannel(AlgorithmBase):
    name = "vol.keltner"
    category = "volatility"
    description = "Keltner Channel: detecta breakouts reales usando EMA + ATR."

    def __init__(self, period: int = 20, multiplier: float = 2.0) -> None:
        self.period = period
        self.multiplier = multiplier

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        ema = df["close"].ewm(span=self.period, adjust=False).mean()
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [(df["high"] - df["low"]),
             (df["high"] - prev_close).abs(),
             (df["low"] - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(self.period).mean()

        upper = ema + self.multiplier * atr
        lower = ema - self.multiplier * atr

        price = float(df["close"].iloc[-1])
        upper_val = float(upper.iloc[-1])
        lower_val = float(lower.iloc[-1])
        mid_val = float(ema.iloc[-1])
        atr_val = float(atr.iloc[-1])

        # Comparar con Bollinger para detectar squeeze de Bollinger dentro de Keltner
        bb_std = df["close"].rolling(self.period).std().iloc[-1]
        bb_upper = mid_val + 2 * bb_std
        bb_lower = mid_val - 2 * bb_std
        squeeze = bool(bb_upper < upper_val and bb_lower > lower_val)

        if price > upper_val:
            signal = "BREAKOUT ALCISTA"
            interp = (
                f"Precio ({price:.5f}) ROMPIÓ la banda superior del Keltner ({upper_val:.5f}). "
                f"BREAKOUT ALCISTA confirmado con alta probabilidad de continuación al alza. "
                f"{'⚠️ SQUEEZE activo: explosión de volatilidad en curso.' if squeeze else ''}"
            )
        elif price < lower_val:
            signal = "BREAKOUT BAJISTA"
            interp = (
                f"Precio ({price:.5f}) ROMPIÓ la banda inferior del Keltner ({lower_val:.5f}). "
                f"BREAKOUT BAJISTA confirmado con alta probabilidad de continuación a la baja. "
                f"{'⚠️ SQUEEZE activo: explosión de volatilidad en curso.' if squeeze else ''}"
            )
        elif price > mid_val:
            signal = "ALCISTA EN CANAL"
            interp = (
                f"Precio en mitad SUPERIOR del canal Keltner (EMA={mid_val:.5f}). "
                f"Dentro del rango normal con sesgo alcista. Sin breakout confirmado aún. "
                f"ATR = {atr_val:.5f}. {'⚠️ SQUEEZE activo: posible ruptura próxima.' if squeeze else ''}"
            )
        else:
            signal = "BAJISTA EN CANAL"
            interp = (
                f"Precio en mitad INFERIOR del canal Keltner (EMA={mid_val:.5f}). "
                f"Dentro del rango normal con sesgo bajista. Sin breakout confirmado aún. "
                f"ATR = {atr_val:.5f}. {'⚠️ SQUEEZE activo: posible ruptura próxima.' if squeeze else ''}"
            )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(price, 5),
            signal=signal,
            interpretation=interp,
            metadata={
                "upper": round(upper_val, 5),
                "ema": round(mid_val, 5),
                "lower": round(lower_val, 5),
                "atr": round(atr_val, 5),
                "squeeze": squeeze,
            },
        )
