"""CRASH #17 — Micro Drift Slope.

Versión de ventana ultracorta: analiza solo las últimas 10 velas para
capturar el momentum inmediato del drift. Más reactivo que crash.drift_slope.

Ideal para detectar cambios de ritmo en tiempo real.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class CrashMicroDriftSlope(AlgorithmBase):
    name = "crash.micro_drift"
    category = "crash_boom"
    description = "Pendiente inmediata del precio (últimas 10 velas). Captura el momentum en tiempo real."

    def __init__(self, window: int = 10) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        recent = df.tail(self.window)
        if len(recent) < 4:
            return AlgorithmResult(
                self.name, symbol, 0.0, "INSUFICIENTE",
                "Insuficiente data para calcular micro-drift.",
            )

        prices = recent["close"].values
        x = np.arange(len(prices))
        slope, _, r_value, _, _ = stats.linregress(x, prices)

        price_mean = float(np.mean(prices))
        slope_pct = (slope / price_mean * 100) if price_mean else 0.0
        r2 = r_value ** 2

        if slope_pct > 0.2:
            signal = "IMPULSO ALCISTA FUERTE"
            interp = (
                f"Las últimas {self.window} velas suben con fuerza: {slope_pct:+.4f}%/vela (R²={r2:.2f}). "
                f"Momentum alcista inmediato muy fuerte. "
                f"En CRASH: señal de aceleración del drift hacia el techo."
            )
        elif slope_pct > 0.05:
            signal = "IMPULSO ALCISTA"
            interp = (
                f"Micro-drift alcista: {slope_pct:+.4f}%/vela (R²={r2:.2f}). "
                f"El precio sube en el corto plazo. Drift activo."
            )
        elif slope_pct < -0.2:
            signal = "CORRECCIÓN FUERTE"
            interp = (
                f"Caída inmediata pronunciada: {slope_pct:+.4f}%/vela (R²={r2:.2f}). "
                f"El precio baja en el corto plazo. Podría ser un crash reciente o corrección del drift."
            )
        elif slope_pct < -0.05:
            signal = "CORRECCIÓN LEVE"
            interp = (
                f"Micro-corrección: {slope_pct:+.4f}%/vela (R²={r2:.2f}). "
                f"El drift pierde momentum momentáneamente."
            )
        else:
            signal = "CONSOLIDACIÓN"
            interp = (
                f"Precio consolidando: pendiente {slope_pct:+.4f}%/vela (R²={r2:.2f}). "
                f"Sin momentum claro en el muy corto plazo."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(slope_pct, 6), signal=signal, interpretation=interp,
            metadata={
                "slope_pct_per_bar": round(slope_pct, 6),
                "r_squared": round(r2, 4),
                "window_bars": self.window,
            },
        )
