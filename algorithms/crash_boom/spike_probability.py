"""CRASH #41 / BOOM #41 — Spike Probability.

Modelo de probabilidad del próximo spike basado en:
  - % del intervalo histórico ya consumido (sobrevencimiento)
  - Score de tensión pre-spike
  - Riesgo de cluster (spike reciente)
  - Varianza del intervalo (predictibilidad)

Probabilidad estimada en próximas 10, 20 y 50 velas (0–100%).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


def _spike_intervals(window: pd.DataFrame, mode: str) -> list[int]:
    body = (window["close"] - window["open"]).abs()
    threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
    if mode == "crash":
        wick = window["open"].clip(lower=window["close"]) - window["low"]
    else:
        wick = window["high"] - window[["open", "close"]].max(axis=1)
    spike_mask = wick > threshold
    idxs = [i for i in range(len(window)) if spike_mask.iloc[i]]
    if len(idxs) < 2:
        return []
    return [idxs[i + 1] - idxs[i] for i in range(len(idxs) - 1)]


@register
class CrashProbability(AlgorithmBase):
    name = "crash.probability"
    category = "crash_boom"
    description = "Probabilidad de crash en próximas 10/20/50 velas. 0–100%."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(500).reset_index(drop=True)
        intervals = _spike_intervals(window, "crash")

        if len(intervals) < 3:
            return AlgorithmResult(self.name, symbol, None, "SIN DATOS",
                                   "No hay suficientes crashes históricos para estimar probabilidad.")

        avg  = float(np.mean(intervals))
        std  = float(np.std(intervals))
        cv   = std / avg if avg > 0 else 1.0  # coeficiente de variación

        # Barras desde el último spike
        from algorithms.crash_boom.post_spike_behavior import _find_last_crash
        last_idx  = _find_last_crash(window)
        bars_since = (len(window) - 1 - last_idx) if last_idx is not None else int(avg)

        # Función de probabilidad acumulada (exponencial suavizada)
        def prob_next_n(n: int) -> float:
            if avg <= 0:
                return 50.0
            # Modelo: distribución exponencial desplazada
            lam = 1.0 / max(avg - bars_since, 1.0)
            raw = 1.0 - np.exp(-lam * n)
            # Penalizar si la varianza es muy alta (poco predecible)
            reliability = max(0.0, 1.0 - cv * 0.5)
            return min(round(raw * reliability * 100, 1), 99.9)

        p10 = prob_next_n(10)
        p20 = prob_next_n(20)
        p50 = prob_next_n(50)

        # Overdue ratio
        overdue = bars_since / avg * 100 if avg > 0 else 0.0

        if p10 >= 60:
            signal = "CRASH MUY PROBABLE"
            interp = (f"P(crash en 10 velas): {p10}%. El mercado está sobrevencido "
                      f"({overdue:.0f}% del intervalo medio de {avg:.0f} barras). "
                      f"P20={p20}%, P50={p50}%.")
        elif p10 >= 35:
            signal = "CRASH POSIBLE"
            interp = (f"P(crash en 10 velas): {p10}%. Riesgo moderado. "
                      f"Velas transcurridas: {bars_since}/{avg:.0f} (avg). P20={p20}%, P50={p50}%.")
        elif p20 >= 50:
            signal = "CRASH EN HORIZONTE"
            interp = (f"P(crash en 20 velas): {p20}%. Riesgo bajo-moderado en el corto plazo. "
                      f"P10={p10}%, P50={p50}%.")
        else:
            signal = "CRASH LEJANO"
            interp = (f"P(crash en 10 velas): {p10}%. El mercado está lejos del sobrevencimiento. "
                      f"Velas desde crash: {bars_since}. P20={p20}%, P50={p50}%.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=p10, signal=signal, interpretation=interp,
            metadata={
                "prob_10bars": p10,
                "prob_20bars": p20,
                "prob_50bars": p50,
                "bars_since_crash": bars_since,
                "avg_interval": round(avg, 1),
                "std_interval": round(std, 1),
                "overdue_pct": round(overdue, 1),
                "predictability": round(max(0.0, 1.0 - cv) * 100, 1),
            },
        )


@register
class BoomProbability(AlgorithmBase):
    name = "boom.probability"
    category = "crash_boom"
    description = "Probabilidad de boom en próximas 10/20/50 velas. 0–100%."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(500).reset_index(drop=True)
        intervals = _spike_intervals(window, "boom")

        if len(intervals) < 3:
            return AlgorithmResult(self.name, symbol, None, "SIN DATOS",
                                   "No hay suficientes booms históricos para estimar probabilidad.")

        avg  = float(np.mean(intervals))
        std  = float(np.std(intervals))
        cv   = std / avg if avg > 0 else 1.0

        from algorithms.crash_boom.post_boom_behavior import _find_last_boom
        last_idx  = _find_last_boom(window)
        bars_since = (len(window) - 1 - last_idx) if last_idx is not None else int(avg)

        def prob_next_n(n: int) -> float:
            if avg <= 0:
                return 50.0
            lam = 1.0 / max(avg - bars_since, 1.0)
            raw = 1.0 - np.exp(-lam * n)
            reliability = max(0.0, 1.0 - cv * 0.5)
            return min(round(raw * reliability * 100, 1), 99.9)

        p10 = prob_next_n(10)
        p20 = prob_next_n(20)
        p50 = prob_next_n(50)
        overdue = bars_since / avg * 100 if avg > 0 else 0.0

        if p10 >= 60:
            signal = "BOOM MUY PROBABLE"
            interp = (f"P(boom en 10 velas): {p10}%. Mercado sobrevencido "
                      f"({overdue:.0f}% del intervalo medio de {avg:.0f} barras). "
                      f"P20={p20}%, P50={p50}%.")
        elif p10 >= 35:
            signal = "BOOM POSIBLE"
            interp = (f"P(boom en 10 velas): {p10}%. Riesgo moderado. P20={p20}%, P50={p50}%.")
        elif p20 >= 50:
            signal = "BOOM EN HORIZONTE"
            interp = (f"P(boom en 20 velas): {p20}%. Riesgo bajo-moderado. P10={p10}%, P50={p50}%.")
        else:
            signal = "BOOM LEJANO"
            interp = (f"P(boom en 10 velas): {p10}%. Mercado lejos del sobrevencimiento. "
                      f"P20={p20}%, P50={p50}%.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=p10, signal=signal, interpretation=interp,
            metadata={
                "prob_10bars": p10,
                "prob_20bars": p20,
                "prob_50bars": p50,
                "bars_since_boom": bars_since,
                "avg_interval": round(avg, 1),
                "std_interval": round(std, 1),
                "overdue_pct": round(overdue, 1),
                "predictability": round(max(0.0, 1.0 - cv) * 100, 1),
            },
        )
