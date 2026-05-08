"""CRASH #16 — Drift Volatility (ATR del drift).

Mide el ruido o volatilidad interna del drift entre crasheos.
ATR alto en el drift = mucho ruido = mayor riesgo de ser parado en posiciones largas.
ATR bajo = drift suave = ideal para seguir la tendencia con stops ajustados.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


def _atr(df: pd.DataFrame, period: int = 7) -> float:
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])),
    )
    if len(tr) < period:
        return float(np.mean(tr)) if len(tr) else 0.0
    return float(np.mean(tr[-period:]))


@register
class CrashDriftVolatility(AlgorithmBase):
    name = "crash.drift_vol"
    category = "crash_boom"
    description = "Volatilidad interna (ATR) del drift. Baja = drift suave. Alta = drift ruidoso."

    def __init__(self, lookback: int = 80) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        # ATR global para referencia
        global_atr = _atr(df.tail(30), 14)

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_positions = wick[wick > threshold].index.tolist()

        start = spike_positions[-1] + 1 if spike_positions else 0
        seg = window.iloc[start:]

        if len(seg) < 5:
            return AlgorithmResult(
                self.name, symbol, 0.0, "SEGMENTO CORTO",
                "Insuficiente para calcular ATR del drift.",
            )

        drift_atr = _atr(seg, min(7, len(seg) - 1))
        ratio = drift_atr / global_atr if global_atr else 1.0

        if ratio < 0.5:
            signal = "DRIFT MUY SUAVE"
            interp = (
                f"ATR del drift: {drift_atr:.5f} (solo {ratio:.2f}x el ATR global). "
                f"El drift es excepcionalmente suave. Ideal para seguir la tendencia. "
                f"Stops ajustados son viables. Bajo riesgo de sacudidas antes del crash."
            )
        elif ratio < 0.8:
            signal = "DRIFT SUAVE"
            interp = (
                f"ATR del drift: {drift_atr:.5f} ({ratio:.2f}x el ATR global). "
                f"Drift con baja volatilidad. Buenas condiciones para seguimiento."
            )
        elif ratio < 1.2:
            signal = "DRIFT NORMAL"
            interp = (
                f"ATR del drift: {drift_atr:.5f} ({ratio:.2f}x el ATR global). "
                f"Volatilidad del drift dentro de lo normal. Comportamiento estándar."
            )
        else:
            signal = "DRIFT TURBULENTO"
            interp = (
                f"ATR del drift: {drift_atr:.5f} ({ratio:.2f}x el ATR global). "
                f"El drift tiene MUCHO RUIDO. Alto riesgo de sacudidas. "
                f"Ampliar stops si se opera en este drift."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(drift_atr, 6), signal=signal, interpretation=interp,
            metadata={
                "drift_atr": round(drift_atr, 6),
                "global_atr": round(global_atr, 6),
                "ratio_vs_global": round(ratio, 3),
                "drift_bars": len(seg),
            },
        )
