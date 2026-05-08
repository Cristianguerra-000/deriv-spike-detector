"""BOOM #9 — Boom Frequency Change.

Analiza si la frecuencia de booms está acelerándose o espaciándose.
Aceleración = mercado en activación. Espaciado = mercado calmado.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class BoomFrequencyChange(AlgorithmBase):
    name = "boom.freq_change"
    category = "crash_boom"
    description = "¿Los booms se están acelerando o espaciando respecto a la norma?"

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["high"] - window[["open", "close"]].max(axis=1)
        spike_pos = wick[wick > threshold].index.tolist()

        if len(spike_pos) < 4:
            return AlgorithmResult(
                self.name, symbol, 0.0, "INSUFICIENTE",
                "Se necesitan al menos 4 booms para analizar cambio de frecuencia.",
            )

        intervals = np.diff(spike_pos).tolist()
        mid = len(intervals) // 2
        early_avg = float(np.mean(intervals[:mid]))
        recent_avg = float(np.mean(intervals[mid:]))
        change_pct = (recent_avg - early_avg) / early_avg * 100

        if change_pct < -25:
            signal = "ACELERACIÓN FUERTE"
            interp = (
                f"Los booms se están ACELERANDO: {recent_avg:.0f} velas entre booms "
                f"vs {early_avg:.0f} antes ({change_pct:+.1f}%). "
                f"⚡ MERCADO EN ACTIVACIÓN. Más booms en menos tiempo. "
                f"Alta volatilidad alcista. Riesgo de booms inesperados."
            )
        elif change_pct < -10:
            signal = "LEVE ACELERACIÓN"
            interp = (
                f"Los booms se aceleran levemente: {recent_avg:.0f} vs {early_avg:.0f} velas "
                f"({change_pct:+.1f}%). Tendencia a mayor frecuencia de booms."
            )
        elif change_pct > 25:
            signal = "ESPACIADO FUERTE"
            interp = (
                f"Los booms se están ESPACIANDO: {recent_avg:.0f} velas entre booms "
                f"vs {early_avg:.0f} antes ({change_pct:+.1f}%). "
                f"El mercado está tranquilo. Más drift bajista disponible entre booms."
            )
        elif change_pct > 10:
            signal = "LEVE ESPACIADO"
            interp = (
                f"Los booms se espacian levemente ({change_pct:+.1f}%). "
                f"Intervalo reciente: {recent_avg:.0f} velas. Mercado algo más tranquilo."
            )
        else:
            signal = "FRECUENCIA ESTABLE"
            interp = (
                f"La frecuencia de booms es estable ({change_pct:+.1f}%). "
                f"Intervalo promedio consistente: ~{recent_avg:.0f} velas. "
                f"Comportamiento predecible del índice."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(change_pct, 2), signal=signal, interpretation=interp,
            metadata={
                "frequency_change_pct": round(change_pct, 2),
                "early_avg_interval": round(early_avg, 1),
                "recent_avg_interval": round(recent_avg, 1),
                "boom_count": len(spike_pos),
            },
        )
