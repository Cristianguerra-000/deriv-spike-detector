"""CRASH #13 — Drift Acceleration.

Mide la segunda derivada del drift: ¿se está acelerando?
Compara la pendiente de la primera mitad del drift con la segunda.

Aceleración positiva = el precio sube cada vez más rápido = crash más cercano.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashDriftAcceleration(AlgorithmBase):
    name = "crash.drift_accel"
    category = "crash_boom"
    description = "¿El drift alcista se acelera? Aceleración = el precio sube cada vez más rápido."

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

        if len(seg) < 12:
            return AlgorithmResult(
                self.name, symbol, 0.0, "SEGMENTO CORTO",
                "Necesario al menos 12 velas post-crash para medir aceleración.",
            )

        prices = seg["close"].values
        mid = len(prices) // 2

        x1 = np.arange(mid)
        x2 = np.arange(mid, len(prices))
        prices1 = prices[:mid]
        prices2 = prices[mid:]

        slope1, _, _, _, _ = stats.linregress(x1, prices1)
        slope2, _, _, _, _ = stats.linregress(np.arange(len(prices2)), prices2)

        price_mean = float(np.mean(prices))
        slope1_pct = (slope1 / price_mean * 100) if price_mean else 0
        slope2_pct = (slope2 / price_mean * 100) if price_mean else 0
        accel = slope2_pct - slope1_pct

        if accel > 0.05:
            signal = "ACELERANDO"
            interp = (
                f"El drift ACELERA: pendiente inicial {slope1_pct:+.4f}% → reciente {slope2_pct:+.4f}% por vela. "
                f"Aceleración: {accel:+.4f}%/vela. "
                f"⚠️ El precio sube cada vez MÁS RÁPIDO. "
                f"Señal de que el mercado se aproxima al límite de tensión pre-crash."
            )
        elif accel < -0.05:
            signal = "DESACELERANDO"
            interp = (
                f"El drift DESACELERA: pendiente inicial {slope1_pct:+.4f}% → reciente {slope2_pct:+.4f}% por vela. "
                f"El precio sube más lentamente. Posible consolidación. "
                f"El crash puede estar más lejos de lo que indica el overdue."
            )
        else:
            signal = "DRIFT ESTABLE"
            interp = (
                f"El drift es estable: pendiente inicial {slope1_pct:+.4f}% ≈ reciente {slope2_pct:+.4f}% por vela. "
                f"El precio sube a ritmo constante. Comportamiento típico del drift CRASH."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(accel, 6), signal=signal, interpretation=interp,
            metadata={
                "acceleration": round(accel, 6),
                "slope_first_half_pct": round(slope1_pct, 6),
                "slope_second_half_pct": round(slope2_pct, 6),
                "drift_bars": len(seg),
            },
        )
