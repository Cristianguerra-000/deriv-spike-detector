"""BOOM #7 — Boom Consecutive Detector.

Detecta múltiples booms en ventana corta.
Múltiples booms consecutivos = euforia compradora extrema = alto riesgo para cortos.
"""
from __future__ import annotations

import re

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class BoomConsecutiveSpikes(AlgorithmBase):
    name = "boom.consec_spikes"
    category = "crash_boom"
    description = "Detecta múltiples booms en ventana corta → señal de euforia compradora."

    def __init__(self, window_bars: int = 30) -> None:
        self.window_bars = window_bars

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        recent = df.tail(self.window_bars)
        normal_body = float((df["close"] - df["open"]).abs().quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = recent["high"] - recent[["open", "close"]].max(axis=1)
        boom_count = int((wick > threshold).sum())

        nums = re.findall(r"\d+", symbol)
        declared = int(nums[0]) if nums else 500

        if boom_count >= 3:
            signal = "EUFORIA EXTREMA"
            interp = (
                f"🚀 {boom_count} booms en solo {self.window_bars} velas. "
                f"EUFORIA EXTREMA DE MERCADO. "
                f"Múltiples disparos alcistas en ventana corta = régimen excepcional. "
                f"Evitar posiciones cortas hasta estabilización."
            )
        elif boom_count == 2:
            signal = "DOBLE BOOM"
            interp = (
                f"⚡ 2 booms en {self.window_bars} velas. "
                f"Mercado en estado de activación doble. "
                f"Riesgo elevado para estrategias que anticipan el boom. "
                f"Esperar al menos {declared // 4} velas sin boom para normalizar."
            )
        elif boom_count == 1:
            signal = "BOOM RECIENTE"
            interp = (
                f"1 boom en las últimas {self.window_bars} velas. Normal. "
                f"El mercado debería estar en fase de corrección y drift bajista."
            )
        else:
            signal = "SIN BOOMS RECIENTES"
            interp = (
                f"No se detectaron booms en las últimas {self.window_bars} velas. "
                f"El mercado lleva al menos {self.window_bars} velas en drift puro bajista. "
                f"Monitorear el boom_overdue_score."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=boom_count, signal=signal, interpretation=interp,
            metadata={
                "booms_in_window": boom_count,
                "window_bars": self.window_bars,
            },
        )
