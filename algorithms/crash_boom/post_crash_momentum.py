"""CRASH #35 — Post Crash Momentum (RSI).

Calcula el RSI en las 10 velas inmediatas post-crash.
RSI alto post-crash = el mercado absorbió el crash rápido = drift fuerte.
RSI bajo post-crash = debilidad = posible doble crash.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash


def _rsi(series: np.ndarray, period: int = 7) -> float:
    if len(series) < period + 1:
        return 50.0
    deltas = np.diff(series)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g  = np.mean(gains[-period:])
    avg_l  = np.mean(losses[-period:])
    if avg_l == 0:
        return 100.0
    return 100 - 100 / (1 + avg_g / avg_l)


@register
class CrashPostMomentum(AlgorithmBase):
    name = "crash.post_mom"
    category = "crash_boom"
    description = "RSI en las 10 velas post-crash. Alto = absorción rápida = drift fuerte."

    POST_WINDOW = 10

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        seg = window.iloc[last_idx: last_idx + 1 + self.POST_WINDOW]
        if len(seg) < 4:
            return AlgorithmResult(self.name, symbol, None, "SEGMENTO CORTO",
                                   "No hay suficientes velas post-crash para calcular RSI.")

        closes = seg["close"].values
        rsi_val = _rsi(closes, period=min(7, len(closes) - 1))

        # También calcula ROC (Rate of Change) del segmento
        roc = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0.0

        bars_since = len(window) - 1 - last_idx

        if rsi_val >= 65:
            signal = "MOMENTUM FUERTE"
            interp = (f"RSI post-crash: {rsi_val:.1f}. El mercado absorbió el crash con fuerza. "
                      f"ROC del segmento: {roc:+.3f}%. Drift alcista activo y con energía.")
        elif rsi_val >= 50:
            signal = "MOMENTUM MODERADO"
            interp = (f"RSI post-crash: {rsi_val:.1f}. Recuperación normal. "
                      f"ROC: {roc:+.3f}%. Drift en construcción sin señales de debilidad.")
        elif rsi_val >= 35:
            signal = "MOMENTUM DÉBIL"
            interp = (f"RSI post-crash: {rsi_val:.1f}. El mercado lucha por recuperarse. "
                      f"ROC: {roc:+.3f}%. Drift débil. Posible consolidación larga.")
        else:
            signal = "MOMENTUM NEGATIVO"
            interp = (f"RSI post-crash: {rsi_val:.1f}. El mercado sigue bajando tras el crash. "
                      f"ROC: {roc:+.3f}%. Riesgo de crash consecutivo o doble suelo.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(rsi_val, 2), signal=signal, interpretation=interp,
            metadata={
                "rsi_post_crash": round(rsi_val, 2),
                "roc_pct": round(roc, 4),
                "bars_analyzed": len(seg),
                "bars_since_crash": bars_since,
            },
        )
