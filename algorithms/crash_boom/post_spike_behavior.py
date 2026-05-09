"""CRASH #31 — Post Spike Behavior.

Analiza las 5 velas inmediatas tras el último crash:
dirección, momentum y consistencia del rebote inicial.
Es la base de todos los análisis post-evento.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


def _find_last_crash(window: pd.DataFrame) -> int | None:
    body = (window["close"] - window["open"]).abs()
    threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
    wick = window["open"].clip(lower=window["close"]) - window["low"]
    hits = wick[wick > threshold].index.tolist()
    return hits[-1] if hits else None


@register
class CrashPostSpikeBehavior(AlgorithmBase):
    name = "crash.post_spike"
    category = "crash_boom"
    description = "Comportamiento de las 5 velas tras el crash. Mide fuerza y dirección del rebote."

    POST_WINDOW = 5

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        seg = window.iloc[last_idx + 1: last_idx + 1 + self.POST_WINDOW]
        bars_since = len(window) - 1 - last_idx

        if len(seg) < 2:
            return AlgorithmResult(self.name, symbol, None, "MUY RECIENTE",
                                   f"Crash hace {bars_since} vela(s). Aún no hay datos post-spike suficientes.")

        spike_low = float(window.loc[last_idx, "low"])
        spike_open = float(window.loc[last_idx, "open"])

        # Porcentaje de velas alcistas en el rebote
        bull_pct = float((seg["close"] > seg["open"]).mean()) * 100
        # Ganancia total del rebote desde el mínimo del spike
        total_recovery = float(seg["close"].iloc[-1] - spike_low)
        recovery_pct = (total_recovery / spike_low * 100) if spike_low else 0.0
        # Velocidad: ganancia por vela
        speed = total_recovery / len(seg)
        # ATR del segmento post-crash
        post_atr = float((seg["high"] - seg["low"]).mean())
        # Consistencia: % de velas que cierran por encima del open del crash
        above_open = float((seg["close"] > spike_open).mean()) * 100

        if bull_pct >= 80 and recovery_pct > 0.5:
            signal = "REBOTE FUERTE"
            interp = (f"Las {len(seg)} velas post-crash son {bull_pct:.0f}% alcistas. "
                      f"Recuperación de {recovery_pct:.3f}% desde el mínimo. "
                      f"El drift alcista se reanudó agresivamente.")
        elif bull_pct >= 60:
            signal = "REBOTE MODERADO"
            interp = (f"{bull_pct:.0f}% de velas alcistas en las {len(seg)} barras post-crash. "
                      f"Recuperación de {recovery_pct:.3f}%. Rebote en curso pero sin fuerza extrema.")
        elif bull_pct >= 40:
            signal = "REBOTE DÉBIL"
            interp = (f"Solo {bull_pct:.0f}% de velas alcistas tras el crash. "
                      f"El mercado lucha por recuperarse. Posible zona de doble crash.")
        else:
            signal = "PRESIÓN BAJISTA"
            interp = (f"Predominan velas bajistas ({100-bull_pct:.0f}%) en las {len(seg)} barras post-crash. "
                      f"El mercado no rebota. Riesgo de crash consecutivo.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(recovery_pct, 4), signal=signal, interpretation=interp,
            metadata={
                "bars_since_crash": bars_since,
                "bars_analyzed": len(seg),
                "bull_pct": round(bull_pct, 1),
                "recovery_pct": round(recovery_pct, 4),
                "speed_per_bar": round(speed, 5),
                "post_atr": round(post_atr, 5),
                "above_open_pct": round(above_open, 1),
            },
        )
