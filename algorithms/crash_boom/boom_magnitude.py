"""BOOM #3 — Boom Magnitude Analyzer.

Mide el tamaño promedio de los últimos booms en puntos absolutos.
En BOOM el spike es wick SUPERIOR (disparo alcista violento).
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class BoomSpikeMagnitude(AlgorithmBase):
    name = "boom.spike_magnitude"
    category = "crash_boom"
    description = "Tamaño promedio de spikes BOOM recientes y comparación con el último."

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(self.lookback)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        # Boom = wick superior
        wick = window["high"] - window[["open", "close"]].max(axis=1)
        spikes = wick[wick > threshold]

        if spikes.empty:
            return AlgorithmResult(
                self.name, symbol, 0.0, "SIN BOOMS",
                f"No se detectaron booms en las últimas {self.lookback} velas.",
            )

        avg_mag = float(spikes.mean())
        last_mag = float(spikes.iloc[-1])
        max_mag = float(spikes.max())
        ratio = last_mag / avg_mag if avg_mag else 1.0

        if ratio > 1.8:
            signal = "BOOM EXPLOSIVO"
            interp = (
                f"El último boom fue {ratio:.1f}x más alto que el promedio. "
                f"Último: {last_mag:.4f} pts | Promedio: {avg_mag:.4f} pts | Máx: {max_mag:.4f} pts. "
                f"BOOM EXPLOSIVO. Pico alcista excepcional. "
                f"Corrección post-boom puede ser igualmente pronunciada."
            )
        elif ratio > 1.3:
            signal = "BOOM GRANDE"
            interp = (
                f"Boom por encima del promedio: {last_mag:.4f} pts vs {avg_mag:.4f} pts promedio. "
                f"Disparo alcista fuerte. Corrección esperada puede ser más lenta."
            )
        elif ratio < 0.5:
            signal = "BOOM DÉBIL"
            interp = (
                f"El último boom fue pequeño: {last_mag:.4f} pts (solo {ratio:.1f}x el promedio). "
                f"Boom leve. Señal de posible debilitamiento del patrón."
            )
        else:
            signal = "BOOM NORMAL"
            interp = (
                f"Tamaño del último boom dentro del rango típico ({last_mag:.4f} pts). "
                f"Promedio histórico: {avg_mag:.4f} pts. {len(spikes)} booms en ventana. "
                f"Comportamiento normal del índice."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(avg_mag, 5), signal=signal, interpretation=interp,
            metadata={
                "avg_magnitude": round(avg_mag, 5),
                "last_magnitude": round(last_mag, 5),
                "max_magnitude": round(max_mag, 5),
                "boom_count": len(spikes),
                "ratio_vs_avg": round(ratio, 3),
            },
        )
