"""MACD — Moving Average Convergence Divergence.

Detecta cruces de línea MACD/señal, divergencias y fuerza del histograma.
Indica cambios de momentum antes de que el precio los confirme.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class MACD(AlgorithmBase):
    name = "trend.macd"
    category = "trend"
    description = "MACD: detecta cambios de momentum y cruces de señal."

    def __init__(self, fast: int = 12, slow: int = 26, signal_period: int = 9) -> None:
        self.fast = fast
        self.slow = slow
        self.signal_period = signal_period

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        ema_fast = df["close"].ewm(span=self.fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal_period, adjust=False).mean()
        histogram = macd_line - signal_line

        m_now = float(macd_line.iloc[-1])
        s_now = float(signal_line.iloc[-1])
        m_prev = float(macd_line.iloc[-2])
        s_prev = float(signal_line.iloc[-2])
        h_now = float(histogram.iloc[-1])
        h_prev = float(histogram.iloc[-2])

        # Detectar cruce
        bullish_cross = m_prev < s_prev and m_now > s_now
        bearish_cross = m_prev > s_prev and m_now < s_now
        hist_growing = h_now > h_prev

        if bullish_cross:
            signal = "CRUCE ALCISTA"
            cross_text = "⚡ CRUCE ALCISTA recién confirmado (MACD cruzó por ENCIMA de la señal)"
        elif bearish_cross:
            signal = "CRUCE BAJISTA"
            cross_text = "⚡ CRUCE BAJISTA recién confirmado (MACD cruzó por DEBAJO de la señal)"
        elif h_now > 0:
            signal = "ALCISTA"
            cross_text = "Histograma POSITIVO (MACD por encima de la señal)"
        else:
            signal = "BAJISTA"
            cross_text = "Histograma NEGATIVO (MACD por debajo de la señal)"

        momentum_text = (
            "fortaleciéndose" if (h_now > 0 and hist_growing) or (h_now < 0 and not hist_growing)
            else "debilitándose"
        )

        interp = (
            f"{cross_text}. "
            f"MACD = {m_now:.5f} | Señal = {s_now:.5f} | Histograma = {h_now:.5f}. "
            f"El impulso se está {momentum_text}. "
            f"{'Buena zona de entrada en largo.' if signal in ('CRUCE ALCISTA','ALCISTA') else 'Precaución o buscar cortos.'}"
        )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(h_now, 6),
            signal=signal,
            interpretation=interp,
            metadata={
                "macd": round(m_now, 6),
                "signal_line": round(s_now, 6),
                "histogram": round(h_now, 6),
                "bullish_cross": bullish_cross,
                "bearish_cross": bearish_cross,
            },
        )
