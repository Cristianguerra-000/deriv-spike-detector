"""CRASH #18 — Drift Consistency.

Mide si las velas del drift son consistentes en tamaño (% de velas alcistas
y relación entre cuerpos de velas consecutivas).

Un drift consistente = más confiable. Un drift errático = menos predecible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashDriftConsistency(AlgorithmBase):
    name = "crash.drift_consist"
    category = "crash_boom"
    description = "Consistencia de las velas en el drift: % alcistas y uniformidad de tamaños."

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

        if len(seg) < 6:
            return AlgorithmResult(
                self.name, symbol, 0.0, "SEGMENTO CORTO",
                "Insuficiente para analizar consistencia del drift.",
            )

        # % de velas alcistas
        is_bullish = seg["close"] > seg["open"]
        pct_bullish = float(is_bullish.mean() * 100)

        # Coeficiente de variación de los cuerpos (sin spikes)
        bodies = (seg["close"] - seg["open"]).abs()
        # Excluir spike bars del cálculo de consistencia
        normal_mask = bodies < (bodies.quantile(0.9))
        if normal_mask.sum() > 2:
            cv_body = float(bodies[normal_mask].std() / bodies[normal_mask].mean())
        else:
            cv_body = 1.0

        # Score compuesto de consistencia (0 = errático, 100 = perfecto)
        # Bonus por alto % alcista, penalización por alta variación de cuerpos
        bull_score = max(0, (pct_bullish - 50) / 50 * 50)  # 0-50 pts
        cv_score = max(0, (1 - min(cv_body, 1)) * 50)  # 0-50 pts
        consistency = bull_score + cv_score

        if consistency >= 70:
            signal = "DRIFT MUY CONSISTENTE"
            interp = (
                f"Score de consistencia: {consistency:.0f}/100. "
                f"Velas alcistas: {pct_bullish:.1f}% | CV de cuerpos: {cv_body:.3f}. "
                f"El drift es muy regular: velas alcistas dominantes y tamaños uniformes. "
                f"Condiciones ideales para estrategias largas en el drift."
            )
        elif consistency >= 45:
            signal = "DRIFT CONSISTENTE"
            interp = (
                f"Score de consistencia: {consistency:.0f}/100. "
                f"Velas alcistas: {pct_bullish:.1f}% | CV: {cv_body:.3f}. "
                f"Drift bastante ordenado. Adecuado para estrategias de tendencia."
            )
        elif consistency >= 25:
            signal = "DRIFT IRREGULAR"
            interp = (
                f"Score de consistencia: {consistency:.0f}/100. "
                f"Velas alcistas: {pct_bullish:.1f}% | CV: {cv_body:.3f}. "
                f"El drift tiene mezcla de velas alcistas y bajistas. Patrón menos predecible."
            )
        else:
            signal = "DRIFT ERRÁTICO"
            interp = (
                f"Score de consistencia: {consistency:.0f}/100. "
                f"Velas alcistas: {pct_bullish:.1f}% | CV: {cv_body:.3f}. "
                f"Drift muy irregular. Muchas velas bajistas mezcladas o tamaños muy variables. "
                f"Difícil operar este drift con confianza."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(consistency, 1), signal=signal, interpretation=interp,
            metadata={
                "consistency_score": round(consistency, 1),
                "pct_bullish_candles": round(pct_bullish, 2),
                "body_cv": round(cv_body, 4),
                "drift_bars": len(seg),
            },
        )
