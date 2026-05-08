"""CRASH #15 — Drift Linearity (R²).

Mide qué tan "limpio" y lineal es el drift alcista entre crasheos.
R² alto = drift muy ordenado y predecible.
R² bajo = drift ruidoso, con reversiones.

Un drift muy lineal es el ideal para estrategias de seguimiento de tendencia en Crash.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashDriftLinearity(AlgorithmBase):
    name = "crash.drift_linear"
    category = "crash_boom"
    description = "R² del drift alcista. Alto R² = drift limpio y predecible."

    def __init__(self, lookback: int = 100) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_positions = wick[wick > threshold].index.tolist()

        start = spike_positions[-1] + 1 if spike_positions else 0
        seg = window.iloc[start:]

        if len(seg) < 6:
            return AlgorithmResult(
                self.name, symbol, 0.0, "SEGMENTO CORTO",
                "Insuficiente para calcular R².",
            )

        prices = seg["close"].values
        x = np.arange(len(prices))
        _, _, r_value, _, _ = stats.linregress(x, prices)
        r2 = float(r_value ** 2)

        if r2 >= 0.90:
            signal = "DRIFT MUY LIMPIO"
            interp = (
                f"R² = {r2:.4f} → El drift es MUY LINEAL y predecible. "
                f"El precio sigue casi perfectamente una línea recta ascendente. "
                f"Condiciones ideales para estrategias de seguimiento del drift. "
                f"El análisis de timing (overdue/calendar) es muy confiable aquí."
            )
        elif r2 >= 0.75:
            signal = "DRIFT LIMPIO"
            interp = (
                f"R² = {r2:.4f} → Drift bastante lineal. "
                f"El precio sube ordenadamente con poco ruido. "
                f"Los indicadores de timing tienen buena confianza."
            )
        elif r2 >= 0.50:
            signal = "DRIFT RUIDOSO"
            interp = (
                f"R² = {r2:.4f} → El drift tiene bastante ruido. "
                f"El precio no sigue una línea limpia. "
                f"Hay micro-correcciones frecuentes. Estrategias de timing menos precisas."
            )
        else:
            signal = "DRIFT CAÓTICO"
            interp = (
                f"R² = {r2:.4f} → El drift post-crash es muy caótico. "
                f"El precio no tiene dirección clara. Posible transición de régimen "
                f"o segmento demasiado corto. Los indicadores de timing tienen baja confianza."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(r2, 4), signal=signal, interpretation=interp,
            metadata={
                "r_squared": round(r2, 4),
                "drift_bars": len(seg),
            },
        )
