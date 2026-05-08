"""CRASH #8 — Spike Depth Score.

Mide la profundidad del último crash: cuántos puntos y qué % cayó
el precio en la vela del spike.

Un crash profundo = movimiento más dramático = mercado más agresivo.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashSpikeDepthScore(AlgorithmBase):
    name = "crash.spike_depth"
    category = "crash_boom"
    description = "Profundidad del último crash en puntos y %. Crashes profundos = mercado agresivo."

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(self.lookback)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        # Wick inferior = profundidad del crash
        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_mask = wick > threshold

        if not spike_mask.any():
            return AlgorithmResult(
                self.name, symbol, 0.0, "SIN SPIKES",
                "No se detectaron crasheos en la ventana de análisis.",
            )

        spike_rows = window[spike_mask]
        last_spike = spike_rows.iloc[-1]

        # Profundidad = wick inferior del spike
        depth_pts = float(
            max(last_spike["open"], last_spike["close"]) - last_spike["low"]
        )
        ref_price = float(last_spike["open"]) or float(last_spike["close"])
        depth_pct = (depth_pts / ref_price * 100) if ref_price else 0.0

        # Promedio histórico de profundidades
        all_depths = wick[spike_mask].values
        avg_depth = float(all_depths.mean())
        max_depth = float(all_depths.max())
        relative = depth_pts / avg_depth if avg_depth else 1.0

        if depth_pct > 3.0:
            signal = "CRASH BRUTAL"
            interp = (
                f"El último crash bajó {depth_pts:.4f} pts ({depth_pct:.2f}% del precio). "
                f"CRASH BRUTAL: muy superior al promedio ({avg_depth:.4f} pts). "
                f"El mercado descargó con extrema agresividad. "
                f"Después de crashes muy profundos, el rebote puede ser igualmente violento."
            )
        elif depth_pct > 1.5 or relative > 1.5:
            signal = "CRASH PROFUNDO"
            interp = (
                f"Crash de {depth_pts:.4f} pts ({depth_pct:.2f}%). "
                f"Por encima del promedio de {avg_depth:.4f} pts. "
                f"Crash significativo. Recuperación puede tardar más de lo normal."
            )
        elif relative < 0.5:
            signal = "CRASH SUPERFICIAL"
            interp = (
                f"El último crash fue pequeño: {depth_pts:.4f} pts ({depth_pct:.2f}%). "
                f"Muy por debajo del promedio ({avg_depth:.4f} pts). "
                f"Spike débil. Podría indicar que el mecanismo de crash está moderado actualmente."
            )
        else:
            signal = "CRASH NORMAL"
            interp = (
                f"Profundidad del último crash: {depth_pts:.4f} pts ({depth_pct:.2f}%). "
                f"Dentro del rango histórico normal (promedio: {avg_depth:.4f} pts, máx: {max_depth:.4f} pts). "
                f"Comportamiento estándar del índice."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(depth_pts, 5), signal=signal, interpretation=interp,
            metadata={
                "last_spike_depth_pts": round(depth_pts, 5),
                "last_spike_depth_pct": round(depth_pct, 3),
                "avg_depth": round(avg_depth, 5),
                "max_depth": round(max_depth, 5),
                "relative_vs_avg": round(relative, 3),
            },
        )
