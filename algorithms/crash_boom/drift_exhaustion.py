"""CRASH #14 — Drift Exhaustion.

Detecta signos de agotamiento en el drift alcista:
RSI del drift, ROC (rate of change) y ángulo de la pendiente reciente.

Cuando el drift se agota, la tensión para el crash es máxima.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


def _rsi_of_series(series: np.ndarray, period: int = 7) -> float:
    if len(series) < period + 1:
        return 50.0
    deltas = np.diff(series)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


@register
class CrashDriftExhaustion(AlgorithmBase):
    name = "crash.drift_exhaust"
    category = "crash_boom"
    description = "Señales de agotamiento del drift alcista. Agotamiento = tensión máxima pre-crash."

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

        if len(seg) < 10:
            return AlgorithmResult(
                self.name, symbol, 0, "SEGMENTO CORTO",
                "Insuficiente histórico post-crash para detectar agotamiento.",
            )

        prices = seg["close"].values

        # RSI del drift (¿el drift mismo está sobrecomprado?)
        rsi_val = _rsi_of_series(prices, 7)

        # Rate of change: últimas 5 velas vs las 5 anteriores
        if len(prices) >= 10:
            roc = (prices[-1] - prices[-6]) / prices[-6] * 100 if prices[-6] else 0
        else:
            roc = 0.0

        # Slope reciente (últimas 5 velas)
        if len(prices) >= 5:
            recent_prices = prices[-5:]
            x = np.arange(5)
            coeffs = np.polyfit(x, recent_prices, 1)
            recent_slope_pct = coeffs[0] / float(np.mean(recent_prices)) * 100
        else:
            recent_slope_pct = 0.0

        # Score de agotamiento: 0 = fresco, 100 = agotado
        exhaustion_components = []
        if rsi_val > 70:
            exhaustion_components.append(30)
        elif rsi_val > 60:
            exhaustion_components.append(15)
        if recent_slope_pct < 0.01:  # pendiente casi plana o negativa
            exhaustion_components.append(35)
        elif recent_slope_pct < 0.05:
            exhaustion_components.append(15)
        if roc < 0.01:  # sin momentum reciente
            exhaustion_components.append(35)
        elif roc < 0.1:
            exhaustion_components.append(15)

        exhaustion_score = min(sum(exhaustion_components), 100)

        if exhaustion_score >= 60:
            signal = "AGOTADO"
            interp = (
                f"El drift muestra signos de AGOTAMIENTO (score: {exhaustion_score}/100). "
                f"RSI del drift: {rsi_val:.1f} | ROC reciente: {roc:+.4f}% | "
                f"Pendiente última velas: {recent_slope_pct:+.4f}%/vela. "
                f"⚠️ El drift pierde fuerza. Zona de máxima tensión pre-crash. "
                f"El crash puede estar próximo incluso si el overdue no lo indica aún."
            )
        elif exhaustion_score >= 30:
            signal = "DRIFT DEBILITANDO"
            interp = (
                f"El drift empieza a debilitarse (score: {exhaustion_score}/100). "
                f"RSI: {rsi_val:.1f} | ROC: {roc:+.4f}%. "
                f"El momentum alcista del drift disminuye. Aumentar el monitoreo."
            )
        else:
            signal = "DRIFT ACTIVO"
            interp = (
                f"El drift está activo y saludable (score de agotamiento: {exhaustion_score}/100). "
                f"RSI: {rsi_val:.1f} | ROC: {roc:+.4f}% | Pendiente: {recent_slope_pct:+.4f}%/vela. "
                f"El momentum alcista del drift sigue vigente."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=exhaustion_score, signal=signal, interpretation=interp,
            metadata={
                "exhaustion_score": exhaustion_score,
                "drift_rsi": round(rsi_val, 2),
                "drift_roc_pct": round(roc, 4),
                "recent_slope_pct": round(recent_slope_pct, 6),
                "drift_bars": len(seg),
            },
        )
