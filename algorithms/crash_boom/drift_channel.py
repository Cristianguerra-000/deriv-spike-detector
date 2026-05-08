"""CRASH #12 — Drift Channel.

Calcula el canal de precios del drift alcista entre crasheos:
banda superior, banda inferior y línea media.
Indica si el precio está en la parte alta o baja del canal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashDriftChannel(AlgorithmBase):
    name = "crash.drift_channel"
    category = "crash_boom"
    description = "Canal del drift alcista. ¿Está el precio en la parte alta o baja del canal?"

    def __init__(self, lookback: int = 80) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_positions = wick[wick > threshold].index.tolist()

        start = spike_positions[-1] + 1 if spike_positions else 0
        seg = window.iloc[start:]

        if len(seg) < 8:
            return AlgorithmResult(
                self.name, symbol, None, "SEGMENTO CORTO",
                "Insuficiente histórico post-crash para construir canal.",
            )

        prices = seg["close"].values
        x = np.arange(len(prices))
        coeffs = np.polyfit(x, prices, 1)
        trend_line = np.polyval(coeffs, x)
        residuals = prices - trend_line
        std_res = float(np.std(residuals))

        current_price = float(prices[-1])
        current_trend = float(trend_line[-1])
        upper = current_trend + 2 * std_res
        lower = current_trend - 2 * std_res

        channel_width = upper - lower
        if channel_width > 0:
            position = (current_price - lower) / channel_width  # 0=bottom, 1=top
        else:
            position = 0.5

        pos_pct = round(position * 100, 1)

        if position > 0.85:
            signal = "TECHO DEL CANAL"
            interp = (
                f"El precio está en el TECHO del canal de drift ({pos_pct}% del canal). "
                f"Canal: [{lower:.4f} – {upper:.4f}]. Precio actual: {current_price:.4f}. "
                f"⚠️ El precio está sobreextendido. Alta probabilidad de crash inminente o corrección."
            )
        elif position > 0.65:
            signal = "PARTE ALTA DEL CANAL"
            interp = (
                f"Precio en parte alta del canal ({pos_pct}%). "
                f"Canal: [{lower:.4f} – {upper:.4f}]. El drift sigue activo pero empieza a tensionarse. "
                f"Zona de precaución."
            )
        elif position > 0.35:
            signal = "CENTRO DEL CANAL"
            interp = (
                f"Precio centrado en el canal de drift ({pos_pct}%). "
                f"Canal: [{lower:.4f} – {upper:.4f}]. Zona equilibrada. "
                f"El drift avanza normalmente, sin tensión extrema."
            )
        else:
            signal = "PARTE BAJA DEL CANAL"
            interp = (
                f"Precio en parte baja del canal ({pos_pct}%). "
                f"Canal: [{lower:.4f} – {upper:.4f}]. "
                f"Posible micro-corrección en el drift. Zona de mayor seguridad relativa."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(pos_pct, 1), signal=signal, interpretation=interp,
            metadata={
                "channel_position_pct": round(pos_pct, 1),
                "upper_band": round(upper, 5),
                "lower_band": round(lower, 5),
                "trend_mid": round(current_trend, 5),
                "current_price": round(current_price, 5),
                "drift_bars": len(seg),
            },
        )
