"""CRASH #9 — Spike Frequency Change.

Analiza si la frecuencia de crashes está acelerándose o espaciándose
en comparación con el promedio histórico del índice.

Aceleración = mercado inestable. Espaciado = mercado en calma.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashFrequencyChange(AlgorithmBase):
    name = "crash.freq_change"
    category = "crash_boom"
    description = "¿Los crashes se están acelerando o espaciando respecto a la norma?"

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_pos = wick[wick > threshold].index.tolist()

        if len(spike_pos) < 4:
            return AlgorithmResult(
                self.name, symbol, 0.0, "INSUFICIENTE",
                "Se necesitan al menos 4 spikes para analizar cambio de frecuencia.",
            )

        intervals = np.diff(spike_pos).tolist()

        # Primera mitad vs segunda mitad
        mid = len(intervals) // 2
        early_avg = float(np.mean(intervals[:mid]))
        recent_avg = float(np.mean(intervals[mid:]))

        change_pct = (recent_avg - early_avg) / early_avg * 100

        if change_pct < -25:
            signal = "ACELERACIÓN FUERTE"
            interp = (
                f"Los crashes se están ACELERANDO: intervalo reciente {recent_avg:.0f} velas "
                f"vs {early_avg:.0f} velas antes ({change_pct:+.1f}%). "
                f"⚠️ MERCADO INESTABLE. Más crashes en menos tiempo. "
                f"El riesgo de operar posiciones largas está elevado."
            )
        elif change_pct < -10:
            signal = "LEVE ACELERACIÓN"
            interp = (
                f"Los crashes se están acelerando levemente: {recent_avg:.0f} vs {early_avg:.0f} velas "
                f"({change_pct:+.1f}%). Tendencia a mayor frecuencia. Ser cauteloso."
            )
        elif change_pct > 25:
            signal = "ESPACIADO FUERTE"
            interp = (
                f"Los crashes se están ESPACIANDO: {recent_avg:.0f} velas entre crashes "
                f"vs {early_avg:.0f} velas antes ({change_pct:+.1f}%). "
                f"El mercado está en fase tranquila. Intervalos más largos = más drift disponible."
            )
        elif change_pct > 10:
            signal = "LEVE ESPACIADO"
            interp = (
                f"Los crashes se están espaciando levemente ({change_pct:+.1f}%). "
                f"Intervalo reciente: {recent_avg:.0f} velas. Mercado algo más tranquilo."
            )
        else:
            signal = "FRECUENCIA ESTABLE"
            interp = (
                f"La frecuencia de crashes es estable ({change_pct:+.1f}%). "
                f"Intervalo promedio consistente: ~{recent_avg:.0f} velas. "
                f"El índice se comporta de forma predecible."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(change_pct, 2), signal=signal, interpretation=interp,
            metadata={
                "frequency_change_pct": round(change_pct, 2),
                "early_avg_interval": round(early_avg, 1),
                "recent_avg_interval": round(recent_avg, 1),
                "spike_count": len(spike_pos),
            },
        )
