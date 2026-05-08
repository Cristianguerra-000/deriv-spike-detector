"""Exponente de Hurst — memoria del mercado.

H > 0.6 → mercado TENDENCIAL (los movimientos tienden a continuar).
H < 0.4 → mercado ANTIPERSISTENTE o MEAN-REVERTING (los movimientos tienden a revertir).
H ≈ 0.5 → movimiento aleatorio (sin memoria estadística).

Usa análisis R/S (Rango Reescalado) clásico.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register

_LAGS = [8, 16, 32, 64, 128]


@register
class HurstExponent(AlgorithmBase):
    name = "stat.hurst"
    category = "statistical"
    description = "Hurst: detecta si el mercado es tendencial, aleatorio o mean-reverting."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        prices = df["close"].dropna().to_numpy(dtype=float)
        if len(prices) < _LAGS[-1]:
            return AlgorithmResult(
                algorithm=self.name,
                symbol=symbol,
                value=None,
                signal="INSUFICIENTE",
                interpretation=f"Se necesitan al menos {_LAGS[-1]} velas. Solo hay {len(prices)}.",
            )

        rs_vals, lag_vals = [], []
        for lag in _LAGS:
            sub = prices[-lag:]
            mean = sub.mean()
            dev = np.cumsum(sub - mean)
            r = dev.max() - dev.min()
            s = sub.std(ddof=1)
            if s > 0:
                rs_vals.append(r / s)
                lag_vals.append(lag)

        if len(rs_vals) < 2:
            return AlgorithmResult(
                algorithm=self.name, symbol=symbol, value=None,
                signal="ERROR", interpretation="No se pudo calcular R/S.",
            )

        h, _ = np.polyfit(np.log(lag_vals), np.log(rs_vals), 1)
        h = float(h)

        if h > 0.65:
            signal = "TENDENCIAL FUERTE"
            interp = (
                f"Hurst = {h:.3f} (>0.65) → El mercado tiene MEMORIA POSITIVA FUERTE. "
                f"Los movimientos actuales tienden a CONTINUAR en la misma dirección. "
                f"Estrategias de seguimiento de tendencia tienen ventaja estadística aquí."
            )
        elif h > 0.55:
            signal = "TENDENCIAL"
            interp = (
                f"Hurst = {h:.3f} → Mercado con tendencia leve. "
                f"Los movimientos tienden a persistir más de lo aleatorio. "
                f"Estrategias de trend-following tienen ligera ventaja."
            )
        elif h < 0.35:
            signal = "MEAN-REVERTING FUERTE"
            interp = (
                f"Hurst = {h:.3f} (<0.35) → El mercado es ANTIPERSISTENTE FUERTE. "
                f"Después de un movimiento grande, hay alta probabilidad de REVERSIÓN. "
                f"Estrategias de reversión a la media o contra-tendencia son más efectivas."
            )
        elif h < 0.45:
            signal = "MEAN-REVERTING"
            interp = (
                f"Hurst = {h:.3f} → Mercado con tendencia a revertir leve. "
                f"Los extremos tienden a corregirse. "
                f"Estrategias de oscilador tienen ligera ventaja."
            )
        else:
            signal = "ALEATORIO"
            interp = (
                f"Hurst = {h:.3f} (~0.5) → Movimiento CASI ALEATORIO. "
                f"No hay memoria estadística clara. "
                f"Ni tendencia ni reversión tiene ventaja, el mercado está en fase de ruido."
            )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(h, 4),
            signal=signal,
            interpretation=interp,
            metadata={"lags_used": lag_vals},
        )
