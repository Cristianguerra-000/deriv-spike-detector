"""BOOM #33 — Boom Correction Speed.

Mide cuántas velas tarda el precio en corregir el 50% y el 100%
del rango subido durante el boom.
Corrección rápida = mercado débil, drift bajista reanudado con energía.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_boom_behavior import _find_last_boom


@register
class BoomCorrectionSpeed(AlgorithmBase):
    name = "boom.correction_speed"
    category = "crash_boom"
    description = "Velas necesarias para corregir 50% y 100% del boom. Rápido = drift bajista fuerte."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        boom_high = float(window.loc[last_idx, "high"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        boom_low  = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = boom_high - boom_low
        if swing <= 0:
            return AlgorithmResult(self.name, symbol, None, "SWING INVÁLIDO", "Rango inválido.")

        target_50  = boom_high - swing * 0.5
        target_100 = boom_low

        post = window.iloc[last_idx + 1:]
        bars_to_50 = bars_to_100 = None

        for i, (_, row) in enumerate(post.iterrows(), start=1):
            if bars_to_50 is None and row["close"] <= target_50:
                bars_to_50 = i
            if bars_to_100 is None and row["close"] <= target_100:
                bars_to_100 = i
            if bars_to_50 is not None and bars_to_100 is not None:
                break

        bars_since = len(post)
        current = float(window["close"].iloc[-1])
        current_pct = (boom_high - current) / swing * 100

        if bars_to_100 is not None:
            signal = "CORRECCIÓN TOTAL"
            interp = (f"Corrigió el 100% en {bars_to_100} velas, el 50% en {bars_to_50} velas. "
                      f"Drift bajista completamente restablecido con rapidez.")
            value = float(bars_to_100)
        elif bars_to_50 is not None:
            signal = "CORRECCIÓN MEDIA"
            interp = (f"Corrigió el 50% en {bars_to_50} velas ({bars_since} barras desde el boom). "
                      f"Aún no alcanzó el nivel pre-boom ({current_pct:.1f}% corregido). "
                      f"Drift bajista en construcción.")
            value = float(bars_to_50)
        else:
            signal = "CORRECCIÓN LENTA"
            interp = (f"Tras {bars_since} velas aún no se corrigió el 50% del boom. "
                      f"Corregido: {current_pct:.1f}%. Posible doble boom inminente.")
            value = float(bars_since)

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=value, signal=signal, interpretation=interp,
            metadata={
                "bars_to_50pct": bars_to_50,
                "bars_to_100pct": bars_to_100,
                "bars_since_boom": bars_since,
                "current_correction_pct": round(current_pct, 2),
                "boom_high": boom_high,
                "boom_low": boom_low,
            },
        )
