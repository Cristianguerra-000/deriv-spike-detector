"""BOOM #6 — Boom Tick Countdown.

Estima cuántas velas más faltan hasta el próximo boom.
El boom interrumpe el drift bajista con un disparo alcista súbito.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class BoomTickCountdown(AlgorithmBase):
    name = "boom.tick_countdown"
    category = "crash_boom"
    description = "Estimación de velas restantes hasta el próximo boom."

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        nums = re.findall(r"\d+", symbol)
        declared = int(nums[0]) if nums else 500

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["high"] - window[["open", "close"]].max(axis=1)
        spike_pos = wick[wick > threshold].index.tolist()

        bars_since = len(window) - 1 - spike_pos[-1] if spike_pos else len(window)

        if len(spike_pos) >= 2:
            intervals = np.diff(spike_pos)
            observed_avg = float(np.mean(intervals))
        else:
            observed_avg = declared

        expected = observed_avg * 0.6 + declared * 0.4
        remaining = max(0, expected - bars_since)
        pct_done = min(bars_since / expected * 100, 100)

        if remaining <= 0:
            signal = "COUNTDOWN = 0"
            interp = (
                f"El boom ya debería haber ocurrido. "
                f"Pasaron {bars_since} velas vs {expected:.0f} esperadas. "
                f"⚡ MÁXIMA ALERTA. Cualquier vela puede ser el boom."
            )
        elif remaining <= expected * 0.15:
            signal = "INMINENTE"
            interp = (
                f"~{remaining:.0f} velas para el próximo boom ({pct_done:.0f}% consumido). "
                f"Zona de ALTA PROBABILIDAD. Preparar estrategia: aguardar el boom para vender el pico."
            )
        elif remaining <= expected * 0.35:
            signal = "PRÓXIMO"
            interp = (
                f"~{remaining:.0f} velas para el próximo boom ({pct_done:.0f}% consumido). "
                f"Acercándose. Comenzar a monitorear señales de tensión pre-boom."
            )
        else:
            signal = "LEJANO"
            interp = (
                f"~{remaining:.0f} velas restantes para el próximo boom ({pct_done:.0f}% consumido). "
                f"Aún hay margen de drift bajista disponible. "
                f"Intervalo esperado: {expected:.0f} velas (declarado: {declared}, observado: {observed_avg:.0f})."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(remaining, 0), signal=signal, interpretation=interp,
            metadata={
                "estimated_remaining_bars": round(remaining, 0),
                "bars_since_last_boom": bars_since,
                "expected_interval": round(expected, 1),
                "declared_interval": declared,
                "observed_avg_interval": round(observed_avg, 1),
            },
        )
