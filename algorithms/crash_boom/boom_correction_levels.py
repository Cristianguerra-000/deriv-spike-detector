"""BOOM #32 — Boom Correction Levels.

Calcula niveles de corrección Fibonacci desde el último boom.
Precio máximo del boom = 0%, precio pre-boom = 100% (hacia abajo).
Los niveles actúan como soporte/resistencia durante la corrección y el drift bajista.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_boom_behavior import _find_last_boom

FIB_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


@register
class BoomCorrectionLevels(AlgorithmBase):
    name = "boom.correction_lvl"
    category = "crash_boom"
    description = "Niveles Fibonacci del boom. Indica en qué zona de corrección está el precio actual."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        boom_high = float(window.loc[last_idx, "high"])
        # Precio de referencia pre-boom: mínimo de las 20 velas anteriores
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        boom_low = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        current  = float(window["close"].iloc[-1])

        swing = boom_high - boom_low
        if swing <= 0:
            return AlgorithmResult(self.name, symbol, None, "SWING INVÁLIDO",
                                   "El rango del boom es demasiado pequeño para calcular Fibonacci.")

        # Niveles Fib: el precio cae desde el máximo (corrección bajista)
        levels = {f"fib_{int(r*1000):04d}": round(boom_high - r * swing, 5) for r in FIB_RATIOS}

        # ¿Cuánto ha corregido el precio desde el máximo?
        correction_pct = (boom_high - current) / swing * 100

        if correction_pct >= 100:
            zone = "SOBRE 100%"
            signal = "DRIFT PLENO"
            interp = (f"Precio ({current:.5f}) bajó del nivel pre-boom ({boom_low:.5f}). "
                      f"Corrección: {correction_pct:.1f}%. Drift bajista completamente restablecido.")
        elif correction_pct >= 78.6:
            zone = "78.6% – 100%"
            signal = "CORRECCIÓN ALTA"
            interp = (f"Corrección del {correction_pct:.1f}%. Precio cerca del nivel pre-boom. "
                      f"Zona de soporte. La tensión pre-boom comienza a acumularse de nuevo.")
        elif correction_pct >= 61.8:
            zone = "61.8% – 78.6%"
            signal = "CORRECCIÓN MODERADA"
            interp = (f"Corrección del {correction_pct:.1f}%. Entre Fib 61.8 y 78.6. "
                      f"Zona de equilibrio del drift bajista. Sin presión extrema aún.")
        elif correction_pct >= 38.2:
            zone = "38.2% – 61.8%"
            signal = "CORRECCIÓN MEDIA"
            interp = (f"Corrección del {correction_pct:.1f}%. Entre Fib 38.2 y 61.8. "
                      f"El precio aún está en la zona alta del rango boom-preboom. "
                      f"Drift bajista en etapa inicial.")
        elif correction_pct >= 23.6:
            zone = "23.6% – 38.2%"
            signal = "CORRECCIÓN BAJA"
            interp = (f"Corrección del {correction_pct:.1f}%. Muy cerca del máximo del boom. "
                      f"El precio apenas cayó. Riesgo de subida de vuelta al máximo.")
        else:
            zone = "0% – 23.6%"
            signal = "ZONA DE MÁXIMO"
            interp = (f"Corrección del {correction_pct:.1f}%. El precio está casi en el máximo del boom. "
                      f"Alta volatilidad post-boom. Zona de máxima incertidumbre.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(correction_pct, 2), signal=signal, interpretation=interp,
            metadata={
                "correction_pct": round(correction_pct, 2),
                "zone": zone,
                "boom_high": boom_high,
                "boom_low": boom_low,
                "current_price": current,
                **levels,
            },
        )
