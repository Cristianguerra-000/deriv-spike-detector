"""BOOM #35 — Post Boom Momentum (RSI).

Calcula el RSI en las 10 velas inmediatas post-boom.
RSI bajo post-boom = el mercado corrigió rápido = drift bajista fuerte.
RSI alto post-boom = resistencia alcista = posible doble boom.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_boom_behavior import _find_last_boom
from algorithms.crash_boom.post_crash_momentum import _rsi


@register
class BoomPostMomentum(AlgorithmBase):
    name = "boom.post_mom"
    category = "crash_boom"
    description = "RSI en las 10 velas post-boom. Bajo = corrección rápida = drift bajista fuerte."

    POST_WINDOW = 10

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        seg = window.iloc[last_idx: last_idx + 1 + self.POST_WINDOW]
        if len(seg) < 4:
            return AlgorithmResult(self.name, symbol, None, "SEGMENTO CORTO",
                                   "No hay suficientes velas post-boom para calcular RSI.")

        closes = seg["close"].values
        rsi_val = _rsi(closes, period=min(7, len(closes) - 1))
        roc = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0.0
        bars_since = len(window) - 1 - last_idx

        if rsi_val <= 35:
            signal = "MOMENTUM BAJISTA FUERTE"
            interp = (f"RSI post-boom: {rsi_val:.1f}. El mercado corrigió con fuerza. "
                      f"ROC: {roc:+.3f}%. Drift bajista activo y con energía.")
        elif rsi_val <= 50:
            signal = "MOMENTUM BAJISTA MODERADO"
            interp = (f"RSI post-boom: {rsi_val:.1f}. Corrección normal. "
                      f"ROC: {roc:+.3f}%. Drift bajista en construcción.")
        elif rsi_val <= 65:
            signal = "CORRECCIÓN DÉBIL"
            interp = (f"RSI post-boom: {rsi_val:.1f}. El mercado resiste la corrección. "
                      f"ROC: {roc:+.3f}%. Drift bajista débil. Posible consolidación.")
        else:
            signal = "RESISTENCIA ALCISTA"
            interp = (f"RSI post-boom: {rsi_val:.1f}. El mercado sigue subiendo tras el boom. "
                      f"ROC: {roc:+.3f}%. Riesgo de boom consecutivo o doble techo.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(rsi_val, 2), signal=signal, interpretation=interp,
            metadata={
                "rsi_post_boom": round(rsi_val, 2),
                "roc_pct": round(roc, 4),
                "bars_analyzed": len(seg),
                "bars_since_boom": bars_since,
            },
        )
