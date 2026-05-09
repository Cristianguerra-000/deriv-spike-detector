"""CRASH #33 — Recovery Speed.

Mide cuántas velas tarda el precio en recuperar el 50% y el 100%
del rango caído durante el crash.
Recuperación rápida = mercado fuerte, drift reanudado con energía.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash


@register
class CrashRecoverySpeed(AlgorithmBase):
    name = "crash.recovery_speed"
    category = "crash_boom"
    description = "Velas necesarias para recuperar 50% y 100% del crash. Rápido = drift fuerte."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        crash_low  = float(window.loc[last_idx, "low"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        crash_high = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = crash_high - crash_low
        if swing <= 0:
            return AlgorithmResult(self.name, symbol, None, "SWING INVÁLIDO", "Rango inválido.")

        target_50  = crash_low + swing * 0.5
        target_100 = crash_high

        post = window.iloc[last_idx + 1:]
        bars_to_50 = bars_to_100 = None

        for i, (_, row) in enumerate(post.iterrows(), start=1):
            if bars_to_50 is None and row["close"] >= target_50:
                bars_to_50 = i
            if bars_to_100 is None and row["close"] >= target_100:
                bars_to_100 = i
            if bars_to_50 is not None and bars_to_100 is not None:
                break

        bars_since = len(post)
        current = float(window["close"].iloc[-1])
        current_pct = (current - crash_low) / swing * 100

        if bars_to_100 is not None:
            signal = "RECUPERACIÓN TOTAL"
            interp = (f"Recuperó el 100% en {bars_to_100} velas, el 50% en {bars_to_50} velas. "
                      f"Drift completamente restablecido con rapidez.")
            value = float(bars_to_100)
        elif bars_to_50 is not None:
            signal = "RECUPERACIÓN MEDIA"
            interp = (f"Recuperó el 50% en {bars_to_50} velas ({bars_since} barras desde el crash). "
                      f"Aún no alcanzó el nivel pre-crash ({current_pct:.1f}% recuperado). "
                      f"Drift en construcción.")
            value = float(bars_to_50)
        else:
            signal = "RECUPERACIÓN LENTA"
            interp = (f"Tras {bars_since} velas aún no se recuperó el 50% del crash. "
                      f"Recuperado: {current_pct:.1f}%. Posible debilidad del drift o doble crash.")
            value = float(bars_since)

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=value, signal=signal, interpretation=interp,
            metadata={
                "bars_to_50pct": bars_to_50,
                "bars_to_100pct": bars_to_100,
                "bars_since_crash": bars_since,
                "current_recovery_pct": round(current_pct, 2),
                "crash_low": crash_low,
                "crash_high": crash_high,
            },
        )
