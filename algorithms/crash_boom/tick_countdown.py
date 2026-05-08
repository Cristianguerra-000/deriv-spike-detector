"""CRASH #6 — Tick Countdown Estimator.

Estima cuántas velas más quedan hasta el próximo crash, basándose
en el intervalo promedio observado y las velas ya transcurridas.

Combina: intervalo declarado + intervalo observado (ponderados).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashTickCountdown(AlgorithmBase):
    name = "crash.tick_countdown"
    category = "crash_boom"
    description = "Estimación de velas restantes hasta el próximo crash."

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        nums = re.findall(r"\d+", symbol)
        declared = int(nums[0]) if nums else 500

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_pos = wick[wick > threshold].index.tolist()

        if spike_pos:
            bars_since = len(window) - 1 - spike_pos[-1]
        else:
            bars_since = len(window)

        if len(spike_pos) >= 2:
            intervals = np.diff(spike_pos)
            observed_avg = float(np.mean(intervals))
        else:
            observed_avg = declared

        # Estimado ponderado: 60% observado + 40% declarado
        expected = observed_avg * 0.6 + declared * 0.4
        remaining = max(0, expected - bars_since)

        pct_done = min(bars_since / expected * 100, 100)

        if remaining <= 0:
            signal = "COUNTDOWN = 0"
            interp = (
                f"Estimación: el crash ya debería haber ocurrido. "
                f"Pasaron {bars_since} velas vs {expected:.0f} esperadas. "
                f"⚡ MÁXIMA ALERTA. Cualquier vela puede ser el crash."
            )
        elif remaining <= expected * 0.15:
            signal = "INMINENTE"
            interp = (
                f"Estimación: ~{remaining:.0f} velas restantes hasta el próximo crash. "
                f"({pct_done:.0f}% del intervalo consumido). "
                f"Zona de ALTA PROBABILIDAD de crash próximo. Ajustar posiciones."
            )
        elif remaining <= expected * 0.35:
            signal = "PRÓXIMO"
            interp = (
                f"Estimación: ~{remaining:.0f} velas restantes. "
                f"({pct_done:.0f}% consumido). El crash se aproxima. "
                f"Comenzar a reducir exposición gradualmente."
            )
        else:
            signal = "LEJANO"
            interp = (
                f"Estimación: ~{remaining:.0f} velas restantes hasta el próximo crash. "
                f"({pct_done:.0f}% consumido). Aún hay margen de drift seguro. "
                f"Intervalo esperado: {expected:.0f} velas (declarado: {declared}, observado: {observed_avg:.0f})."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(remaining, 0), signal=signal, interpretation=interp,
            metadata={
                "estimated_remaining_bars": round(remaining, 0),
                "bars_since_last_spike": bars_since,
                "expected_interval": round(expected, 1),
                "declared_interval": declared,
                "observed_avg_interval": round(observed_avg, 1),
            },
        )
