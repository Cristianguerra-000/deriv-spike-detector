"""BOOM #8 — Boom Height Score.

Mide la altura del último boom: cuántos puntos y qué % subió
el precio en la vela del spike alcista.

Booms altos = mercado con mucha fuerza compradora latente.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class BoomHeightScore(AlgorithmBase):
    name = "boom.spike_height"
    category = "crash_boom"
    description = "Altura del último boom en puntos y %. Booms altos = mercado agresivo al alza."

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(self.lookback)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["high"] - window[["open", "close"]].max(axis=1)
        spike_mask = wick > threshold

        if not spike_mask.any():
            return AlgorithmResult(
                self.name, symbol, 0.0, "SIN BOOMS",
                "No se detectaron booms en la ventana de análisis.",
            )

        spike_rows = window[spike_mask]
        last_spike = spike_rows.iloc[-1]

        # Altura = wick superior del boom
        height_pts = float(last_spike["high"] - max(last_spike["open"], last_spike["close"]))
        ref_price = float(last_spike["open"]) or float(last_spike["close"])
        height_pct = (height_pts / ref_price * 100) if ref_price else 0.0

        all_heights = wick[spike_mask].values
        avg_height = float(all_heights.mean())
        max_height = float(all_heights.max())
        relative = height_pts / avg_height if avg_height else 1.0

        if height_pct > 3.0:
            signal = "BOOM EXPLOSIVO"
            interp = (
                f"El último boom subió {height_pts:.4f} pts ({height_pct:.2f}% del precio). "
                f"BOOM EXPLOSIVO: muy superior al promedio ({avg_height:.4f} pts). "
                f"Fuerza compradora excepcional. La corrección post-boom puede ser violenta."
            )
        elif height_pct > 1.5 or relative > 1.5:
            signal = "BOOM ALTO"
            interp = (
                f"Boom de {height_pts:.4f} pts ({height_pct:.2f}%). "
                f"Por encima del promedio de {avg_height:.4f} pts. "
                f"Boom significativo. Corrección esperada."
            )
        elif relative < 0.5:
            signal = "BOOM BAJO"
            interp = (
                f"El último boom fue pequeño: {height_pts:.4f} pts ({height_pct:.2f}%). "
                f"Muy por debajo del promedio ({avg_height:.4f} pts). "
                f"Boom débil, posible señal de agotamiento del patrón."
            )
        else:
            signal = "BOOM NORMAL"
            interp = (
                f"Altura del último boom: {height_pts:.4f} pts ({height_pct:.2f}%). "
                f"Dentro del rango histórico normal (promedio: {avg_height:.4f} pts, máx: {max_height:.4f} pts). "
                f"Comportamiento estándar del índice."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(height_pts, 5), signal=signal, interpretation=interp,
            metadata={
                "last_boom_height_pts": round(height_pts, 5),
                "last_boom_height_pct": round(height_pct, 3),
                "avg_height": round(avg_height, 5),
                "max_height": round(max_height, 5),
                "relative_vs_avg": round(relative, 3),
            },
        )
