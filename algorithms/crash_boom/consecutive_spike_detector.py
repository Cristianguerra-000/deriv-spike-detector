"""CRASH #7 — Consecutive Spike Detector.

Detecta si ocurrieron 2 o más crashes dentro de una ventana pequeña.
Esto es una señal de que el mercado está en estado de "shock" o pánico.
"""
from __future__ import annotations

import re

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashConsecutiveSpikes(AlgorithmBase):
    name = "crash.consec_spikes"
    category = "crash_boom"
    description = "Detecta múltiples crashes en ventana corta → señal de mercado en pánico."

    def __init__(self, window_bars: int = 30) -> None:
        self.window_bars = window_bars

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        recent = df.tail(self.window_bars)
        body = (recent["close"] - recent["open"]).abs()
        normal_body = float((df["close"] - df["open"]).abs().quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = recent["open"].clip(lower=recent["close"]) - recent["low"]
        spike_count = int((wick > threshold).sum())

        nums = re.findall(r"\d+", symbol)
        declared = int(nums[0]) if nums else 500

        if spike_count >= 3:
            signal = "PÁNICO DE MERCADO"
            interp = (
                f"🚨 {spike_count} crashes en solo {self.window_bars} velas. "
                f"El mercado está en MODO PÁNICO. "
                f"Múltiples spikes en ventana corta = disfunción del índice o régimen excepcional. "
                f"Evitar operar hasta que el mercado se estabilice."
            )
        elif spike_count == 2:
            signal = "DOBLE CRASH"
            interp = (
                f"⚠️ 2 crashes en {self.window_bars} velas. "
                f"Doble crash = mercado inestable. "
                f"Posiblemente en fase de transición o corrección acelerada. "
                f"Esperar normalización (al menos {declared // 4} velas sin crash)."
            )
        elif spike_count == 1:
            signal = "CRASH RECIENTE"
            interp = (
                f"1 crash en las últimas {self.window_bars} velas. Comportamiento normal. "
                f"El mercado debería estar en fase de recuperación y drift ascendente."
            )
        else:
            signal = "SIN CRASHES RECIENTES"
            interp = (
                f"No se detectaron crashes en las últimas {self.window_bars} velas. "
                f"El mercado lleva al menos {self.window_bars} velas en drift puro. "
                f"Monitorear el overdue score."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=spike_count, signal=signal, interpretation=interp,
            metadata={
                "spikes_in_window": spike_count,
                "window_bars": self.window_bars,
            },
        )
