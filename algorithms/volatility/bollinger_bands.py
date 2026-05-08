"""Bandas de Bollinger.

El precio en banda superior = sobrecompra / inferior = sobreventa.
Squeeze (bandas estrechas) → explosión de volatilidad próxima.
%B indica posición relativa del precio dentro de las bandas.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class BollingerBands(AlgorithmBase):
    name = "vol.bollinger"
    category = "volatility"
    description = "Bollinger Bands: posición del precio y estado de volatilidad (squeeze/expansión)."

    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        self.period = period
        self.std_dev = std_dev

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sma = df["close"].rolling(self.period).mean()
        std = df["close"].rolling(self.period).std()
        upper = sma + self.std_dev * std
        lower = sma - self.std_dev * std

        price = float(df["close"].iloc[-1])
        upper_val = float(upper.iloc[-1])
        lower_val = float(lower.iloc[-1])
        mid_val = float(sma.iloc[-1])
        band_range = upper_val - lower_val

        pct_b = (price - lower_val) / band_range if band_range else 0.5
        bandwidth = (band_range / mid_val * 100) if mid_val else 0.0

        # Tendencia del ancho (squeeze o expansión)
        bw_5ago = float(
            ((upper.iloc[-6] - lower.iloc[-6]) / sma.iloc[-6] * 100)
            if len(df) > 6 and sma.iloc[-6] else bandwidth
        )
        if bandwidth < bw_5ago * 0.75:
            vol_state = "SQUEEZE (compresión fuerte)"
            vol_text = "Las bandas se están CERRANDO → se acumula energía. Esperar una ruptura explosiva próxima."
        elif bandwidth < bw_5ago * 0.9:
            vol_state = "CONTRAYÉNDOSE"
            vol_text = "Volatilidad bajando. El mercado se consolida antes de un movimiento mayor."
        elif bandwidth > bw_5ago * 1.25:
            vol_state = "EXPANDIÉNDOSE"
            vol_text = "Las bandas se están ABRIENDO → volatilidad en aumento, movimiento activo."
        else:
            vol_state = "ESTABLE"
            vol_text = "Volatilidad sin cambios significativos."

        if pct_b >= 1.0:
            signal = "RUPTURA ALCISTA"
            pos_text = f"precio ({price:.5f}) FUERA de la banda SUPERIOR → ruptura alcista o sobrecompra extrema"
        elif pct_b <= 0.0:
            signal = "RUPTURA BAJISTA"
            pos_text = f"precio ({price:.5f}) FUERA de la banda INFERIOR → ruptura bajista o sobreventa extrema"
        elif pct_b > 0.6:
            signal = "ALCISTA"
            pos_text = f"precio en mitad SUPERIOR (%.B={pct_b:.2f}) → presión compradora"
        elif pct_b < 0.4:
            signal = "BAJISTA"
            pos_text = f"precio en mitad INFERIOR (%B={pct_b:.2f}) → presión vendedora"
        else:
            signal = "NEUTRO"
            pos_text = f"precio en zona MEDIA (%B={pct_b:.2f}) → equilibrio, sin dirección"

        interp = (
            f"Bollinger Bands: {pos_text}. "
            f"Banda superior={upper_val:.5f} | Media={mid_val:.5f} | Inferior={lower_val:.5f}. "
            f"Estado de volatilidad: {vol_state}. {vol_text}"
        )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(pct_b, 4),
            signal=signal,
            interpretation=interp,
            metadata={
                "upper": round(upper_val, 5),
                "middle": round(mid_val, 5),
                "lower": round(lower_val, 5),
                "pct_b": round(pct_b, 4),
                "bandwidth_pct": round(bandwidth, 4),
                "vol_state": vol_state,
            },
        )
