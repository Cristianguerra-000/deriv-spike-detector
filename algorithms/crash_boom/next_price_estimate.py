"""CRASH #49 / BOOM #49 — Next Price Estimate.

Estima el precio aproximado cuando ocurra el próximo spike,
extrapolando el drift actual hacia adelante.

Usa:
  - Pendiente del drift (regresión lineal de los últimos 50 cierres)
  - Tiempo estimado hasta el próximo spike (basado en intervalos históricos)
  - Proyección lineal: precio_actual + pendiente × barras_restantes
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom


def _linear_slope(series: np.ndarray) -> float:
    """Pendiente de regresión lineal sobre la serie dada."""
    n = len(series)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    slope = float(np.polyfit(x, series, 1)[0])
    return slope


@register
class CrashNextPriceEstimate(AlgorithmBase):
    name = "crash.next_price"
    category = "crash_boom"
    description = "Precio estimado del mercado cuando ocurra el próximo crash."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(500).reset_index(drop=True)

        # Historial de spikes para estimar cuándo vendrá el próximo
        body = (window["close"] - window["open"]).abs()
        threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        lower_wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_mask = lower_wick > threshold
        spike_idxs = [i for i in range(len(window)) if spike_mask.iloc[i]]

        if len(spike_idxs) < 3:
            return AlgorithmResult(self.name, symbol, None, "SIN DATOS",
                                   "No hay suficientes crashes para estimar el próximo precio.")

        intervals = [spike_idxs[i + 1] - spike_idxs[i] for i in range(len(spike_idxs) - 1)]
        avg_interval = float(np.mean(intervals))

        last_idx = _find_last_crash(window)
        bars_since = (len(window) - 1 - last_idx) if last_idx is not None else 0
        bars_remaining = max(int(avg_interval - bars_since), 1)

        # Pendiente del drift (últimas 50 velas post-crash)
        post_start = (last_idx + 1) if last_idx is not None else max(0, len(window) - 50)
        post_seg   = window.iloc[post_start:]["close"].values[-50:]
        slope = _linear_slope(post_seg)  # puntos por vela

        current_price = float(window["close"].iloc[-1])
        estimated_price = current_price + slope * bars_remaining

        # Nivel de confianza de la estimación
        std_interval = float(np.std(intervals))
        cv = std_interval / avg_interval if avg_interval > 0 else 1.0
        confidence_pct = round(max(0.0, (1.0 - min(cv, 1.0)) * 100), 1)

        if estimated_price > current_price:
            direction = "más alto"
        else:
            direction = "más bajo"

        interp = (f"Próximo crash estimado en ~{bars_remaining} velas. "
                  f"Precio actual: {current_price:.5f}. "
                  f"Precio estimado al crash: {estimated_price:.5f} ({direction}). "
                  f"Pendiente drift: {slope:+.5f}/vela. "
                  f"Confianza: {confidence_pct}% (CV={cv:.2f}).")

        if confidence_pct >= 70:
            signal = "ESTIMACIÓN FIABLE"
        elif confidence_pct >= 40:
            signal = "ESTIMACIÓN MODERADA"
        else:
            signal = "ESTIMACIÓN BAJA CONFIANZA"

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(estimated_price, 5), signal=signal, interpretation=interp,
            metadata={
                "estimated_price_at_crash": round(estimated_price, 5),
                "current_price": round(current_price, 5),
                "bars_remaining": bars_remaining,
                "drift_slope_per_bar": round(slope, 6),
                "avg_interval": round(avg_interval, 1),
                "confidence_pct": confidence_pct,
            },
        )


@register
class BoomNextPriceEstimate(AlgorithmBase):
    name = "boom.next_price"
    category = "crash_boom"
    description = "Precio estimado del mercado cuando ocurra el próximo boom."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(500).reset_index(drop=True)

        body = (window["close"] - window["open"]).abs()
        threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        upper_wick = window["high"] - window[["open", "close"]].max(axis=1)
        spike_mask = upper_wick > threshold
        spike_idxs = [i for i in range(len(window)) if spike_mask.iloc[i]]

        if len(spike_idxs) < 3:
            return AlgorithmResult(self.name, symbol, None, "SIN DATOS",
                                   "No hay suficientes booms para estimar el próximo precio.")

        intervals = [spike_idxs[i + 1] - spike_idxs[i] for i in range(len(spike_idxs) - 1)]
        avg_interval = float(np.mean(intervals))

        last_idx = _find_last_boom(window)
        bars_since = (len(window) - 1 - last_idx) if last_idx is not None else 0
        bars_remaining = max(int(avg_interval - bars_since), 1)

        post_start = (last_idx + 1) if last_idx is not None else max(0, len(window) - 50)
        post_seg   = window.iloc[post_start:]["close"].values[-50:]
        slope = _linear_slope(post_seg)

        current_price = float(window["close"].iloc[-1])
        estimated_price = current_price + slope * bars_remaining

        std_interval = float(np.std(intervals))
        cv = std_interval / avg_interval if avg_interval > 0 else 1.0
        confidence_pct = round(max(0.0, (1.0 - min(cv, 1.0)) * 100), 1)

        direction = "más alto" if estimated_price > current_price else "más bajo"

        interp = (f"Próximo boom estimado en ~{bars_remaining} velas. "
                  f"Precio actual: {current_price:.5f}. "
                  f"Precio estimado al boom: {estimated_price:.5f} ({direction}). "
                  f"Pendiente drift bajista: {slope:+.5f}/vela. "
                  f"Confianza: {confidence_pct}% (CV={cv:.2f}).")

        if confidence_pct >= 70:
            signal = "ESTIMACIÓN FIABLE"
        elif confidence_pct >= 40:
            signal = "ESTIMACIÓN MODERADA"
        else:
            signal = "ESTIMACIÓN BAJA CONFIANZA"

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(estimated_price, 5), signal=signal, interpretation=interp,
            metadata={
                "estimated_price_at_boom": round(estimated_price, 5),
                "current_price": round(current_price, 5),
                "bars_remaining": bars_remaining,
                "drift_slope_per_bar": round(slope, 6),
                "avg_interval": round(avg_interval, 1),
                "confidence_pct": confidence_pct,
            },
        )
