"""Tamaño promedio de cuerpo y mecha — microestructura básica."""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class CandleAnatomy(AlgorithmBase):
    name = "micro.candle_anatomy"
    category = "microstructure"
    description = "Cuerpo, mecha superior e inferior promedio."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        body  = (df["close"] - df["open"]).abs()
        upper = df["high"] - df[["open", "close"]].max(axis=1)
        lower = df[["open", "close"]].min(axis=1) - df["low"]

        avg_body  = float(body.mean())
        avg_upper = float(upper.mean())
        avg_lower = float(lower.mean())
        total = avg_body + avg_upper + avg_lower or 1e-10

        body_pct  = avg_body / total
        wick_pct  = (avg_upper + avg_lower) / total

        if body_pct > 0.65:
            signal = "CUERPOS DOMINANTES"
            interp = (
                f"Las velas tienen cuerpos grandes ({body_pct:.0%} del rango promedio). "
                f"El mercado se mueve con decisión: presión direccional clara. "
                f"Cuerpo medio: {avg_body:.4f} pts. Mechas pequeñas indican poca indecisión."
            )
        elif wick_pct > 0.60:
            signal = "MECHAS DOMINANTES"
            interp = (
                f"Las mechas superan al cuerpo ({wick_pct:.0%} del rango). "
                f"Alta indecisión y rechazo de precios extremos. "
                f"Mecha sup: {avg_upper:.4f} | Mecha inf: {avg_lower:.4f}. "
                f"Zona de acumulación/distribución activa."
            )
        else:
            signal = "EQUILIBRADO"
            interp = (
                f"Estructura equilibrada entre cuerpo ({body_pct:.0%}) y mechas ({wick_pct:.0%}). "
                f"Mercado sin presión dominante clara. Esperar señal de ruptura."
            )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(avg_body, 5),
            signal=signal,
            interpretation=interp,
            metadata={
                "avg_body": round(avg_body, 5),
                "avg_upper_wick": round(avg_upper, 5),
                "avg_lower_wick": round(avg_lower, 5),
                "body_pct": round(body_pct, 3),
            },
        )
