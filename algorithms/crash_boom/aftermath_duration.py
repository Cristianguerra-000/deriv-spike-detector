"""CRASH #37 / BOOM #37 — Aftermath Duration.

Mide cuántas velas tarda el ATR post-evento en regresar al
nivel de ATR pre-evento (normalización de volatilidad).
Rápido = el mercado absorbió el shock. Lento = volatilidad persistente.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom


def _rolling_atr(df: pd.DataFrame, window: int = 5) -> pd.Series:
    return (df["high"] - df["low"]).rolling(window).mean()


@register
class CrashAftermathDuration(AlgorithmBase):
    name = "crash.aftermath"
    category = "crash_boom"
    description = "Velas hasta que el ATR vuelve al nivel pre-crash. Rápido = shock absorbido."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        atr_series = _rolling_atr(window, 5)
        pre_atr = float(atr_series.iloc[max(0, last_idx - 20): last_idx].mean())
        if pre_atr <= 0:
            return AlgorithmResult(self.name, symbol, None, "ATR INVÁLIDO", "ATR pre-crash no calculable.")

        threshold = pre_atr * 1.1  # Tolerar hasta 10% sobre el ATR base
        post = atr_series.iloc[last_idx + 1:]
        bars_to_normalize = None
        current_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else pre_atr

        for i, val in enumerate(post, start=1):
            if pd.isna(val):
                continue
            if val <= threshold:
                bars_to_normalize = i
                break

        bars_since = len(post)

        if bars_to_normalize is not None:
            value = float(bars_to_normalize)
            if bars_to_normalize <= 5:
                signal = "NORMALIZACIÓN RÁPIDA"
                interp = (f"ATR normalizó en {bars_to_normalize} velas post-crash. "
                          f"Shock absorbido rápidamente. Drift estable.")
            elif bars_to_normalize <= 15:
                signal = "NORMALIZACIÓN MEDIA"
                interp = (f"ATR normalizó en {bars_to_normalize} velas. "
                          f"Volatilidad post-crash moderada. Drift en estabilización.")
            else:
                signal = "NORMALIZACIÓN LENTA"
                interp = (f"ATR tardó {bars_to_normalize} velas en normalizarse. "
                          f"Volatilidad persistente. Drift errático hasta estabilizar.")
        else:
            value = float(bars_since)
            signal = "SIN NORMALIZACIÓN"
            interp = (f"ATR aún elevado tras {bars_since} velas post-crash. "
                      f"ATR actual: {current_atr:.5f} vs pre-crash: {pre_atr:.5f}. "
                      f"Alta volatilidad en curso.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=value, signal=signal, interpretation=interp,
            metadata={
                "bars_to_normalize": bars_to_normalize,
                "bars_since_crash": bars_since,
                "pre_crash_atr": round(pre_atr, 5),
                "current_atr": round(current_atr, 5),
                "atr_ratio": round(current_atr / pre_atr, 2) if pre_atr else None,
            },
        )


@register
class BoomAftermathDuration(AlgorithmBase):
    name = "boom.aftermath"
    category = "crash_boom"
    description = "Velas hasta que el ATR vuelve al nivel pre-boom. Rápido = shock absorbido."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        atr_series = _rolling_atr(window, 5)
        pre_atr = float(atr_series.iloc[max(0, last_idx - 20): last_idx].mean())
        if pre_atr <= 0:
            return AlgorithmResult(self.name, symbol, None, "ATR INVÁLIDO", "ATR pre-boom no calculable.")

        threshold = pre_atr * 1.1
        post = atr_series.iloc[last_idx + 1:]
        bars_to_normalize = None
        current_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else pre_atr

        for i, val in enumerate(post, start=1):
            if pd.isna(val):
                continue
            if val <= threshold:
                bars_to_normalize = i
                break

        bars_since = len(post)

        if bars_to_normalize is not None:
            value = float(bars_to_normalize)
            if bars_to_normalize <= 5:
                signal = "NORMALIZACIÓN RÁPIDA"
                interp = (f"ATR normalizó en {bars_to_normalize} velas post-boom. "
                          f"Shock absorbido. Drift bajista estable.")
            elif bars_to_normalize <= 15:
                signal = "NORMALIZACIÓN MEDIA"
                interp = (f"ATR normalizó en {bars_to_normalize} velas. "
                          f"Volatilidad post-boom moderada.")
            else:
                signal = "NORMALIZACIÓN LENTA"
                interp = (f"ATR tardó {bars_to_normalize} velas en normalizarse. "
                          f"Volatilidad persistente post-boom.")
        else:
            value = float(bars_since)
            signal = "SIN NORMALIZACIÓN"
            interp = (f"ATR aún elevado tras {bars_since} velas post-boom. "
                      f"ATR actual: {current_atr:.5f} vs pre-boom: {pre_atr:.5f}.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=value, signal=signal, interpretation=interp,
            metadata={
                "bars_to_normalize": bars_to_normalize,
                "bars_since_boom": bars_since,
                "pre_boom_atr": round(pre_atr, 5),
                "current_atr": round(current_atr, 5),
                "atr_ratio": round(current_atr / pre_atr, 2) if pre_atr else None,
            },
        )
