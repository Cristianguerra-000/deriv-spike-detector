"""BOOM #31 — Post Boom Behavior.

Analiza las 5 velas inmediatas tras el último boom:
dirección, momentum y consistencia de la corrección inicial.
Es la base de todos los análisis post-evento para Boom.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


def _find_last_boom(window: pd.DataFrame) -> int | None:
    body = (window["close"] - window["open"]).abs()
    threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
    wick = window["high"] - window[["open", "close"]].max(axis=1)
    hits = wick[wick > threshold].index.tolist()
    return hits[-1] if hits else None


@register
class BoomPostSpikeBehavior(AlgorithmBase):
    name = "boom.post_spike"
    category = "crash_boom"
    description = "Comportamiento de las 5 velas tras el boom. Mide fuerza y dirección de la corrección."

    POST_WINDOW = 5

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        seg = window.iloc[last_idx + 1: last_idx + 1 + self.POST_WINDOW]
        bars_since = len(window) - 1 - last_idx

        if len(seg) < 2:
            return AlgorithmResult(self.name, symbol, None, "MUY RECIENTE",
                                   f"Boom hace {bars_since} vela(s). Aún no hay datos post-boom suficientes.")

        spike_high = float(window.loc[last_idx, "high"])
        spike_open = float(window.loc[last_idx, "open"])

        # Porcentaje de velas bajistas en la corrección
        bear_pct = float((seg["close"] < seg["open"]).mean()) * 100
        # Caída total desde el máximo del boom
        total_correction = float(spike_high - seg["close"].iloc[-1])
        correction_pct = (total_correction / spike_high * 100) if spike_high else 0.0
        # Velocidad: caída por vela
        speed = total_correction / len(seg)
        # ATR del segmento post-boom
        post_atr = float((seg["high"] - seg["low"]).mean())
        # Consistencia: % de velas que cierran por debajo del open del boom
        below_open = float((seg["close"] < spike_open).mean()) * 100

        if bear_pct >= 80 and correction_pct > 0.5:
            signal = "CORRECCIÓN FUERTE"
            interp = (f"Las {len(seg)} velas post-boom son {bear_pct:.0f}% bajistas. "
                      f"Corrección de {correction_pct:.3f}% desde el máximo. "
                      f"El drift bajista se reanudó agresivamente.")
        elif bear_pct >= 60:
            signal = "CORRECCIÓN MODERADA"
            interp = (f"{bear_pct:.0f}% de velas bajistas en las {len(seg)} barras post-boom. "
                      f"Corrección de {correction_pct:.3f}%. Drift bajista en curso sin fuerza extrema.")
        elif bear_pct >= 40:
            signal = "CORRECCIÓN DÉBIL"
            interp = (f"Solo {bear_pct:.0f}% de velas bajistas tras el boom. "
                      f"El mercado resiste la corrección. Posible zona de doble boom.")
        else:
            signal = "PRESIÓN ALCISTA"
            interp = (f"Predominan velas alcistas ({100-bear_pct:.0f}%) en las {len(seg)} barras post-boom. "
                      f"El mercado no corrige. Riesgo de boom consecutivo.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(correction_pct, 4), signal=signal, interpretation=interp,
            metadata={
                "bars_since_boom": bars_since,
                "bars_analyzed": len(seg),
                "bear_pct": round(bear_pct, 1),
                "correction_pct": round(correction_pct, 4),
                "speed_per_bar": round(speed, 5),
                "post_atr": round(post_atr, 5),
                "below_open_pct": round(below_open, 1),
            },
        )
