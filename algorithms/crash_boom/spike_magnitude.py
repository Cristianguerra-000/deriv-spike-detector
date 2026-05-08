"""CRASH #3 — Spike Magnitude Analyzer.

Mide el tamaño promedio de los últimos crasheos en puntos absolutos
y compara el último spike con ese promedio histórico.

Spikes grandes = mercado más nervioso / más peligroso en extremos.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashSpikeMagnitude(AlgorithmBase):
    name = "crash.spike_magnitude"
    category = "crash_boom"
    description = "Tamaño promedio de spikes CRASH recientes y comparación con el último."

    def __init__(self, lookback: int = 500) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(self.lookback)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        # En Crash el spike es wick inferior
        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spikes = wick[wick > threshold]

        if spikes.empty:
            return AlgorithmResult(
                self.name, symbol, 0.0, "SIN SPIKES",
                f"No se detectaron crasheos en las últimas {self.lookback} velas. "
                f"Ventana histórica insuficiente o índice muy nuevo.",
            )

        avg_mag = float(spikes.mean())
        last_mag = float(spikes.iloc[-1])
        max_mag = float(spikes.max())
        ratio = last_mag / avg_mag if avg_mag else 1.0

        if ratio > 1.8:
            signal = "SPIKE GIGANTE"
            interp = (
                f"El último crash fue {ratio:.1f}x más grande que el promedio. "
                f"Último: {last_mag:.4f} pts | Promedio: {avg_mag:.4f} pts | Máx histórico: {max_mag:.4f} pts. "
                f"Crash EXCEPCIONAL. El mercado puede estar en régimen de alta volatilidad."
            )
        elif ratio > 1.3:
            signal = "SPIKE GRANDE"
            interp = (
                f"El último crash fue {ratio:.1f}x el promedio ({last_mag:.4f} vs {avg_mag:.4f} pts). "
                f"Spike por encima del tamaño típico. Momentum vendedor inusualmente fuerte."
            )
        elif ratio < 0.5:
            signal = "SPIKE PEQUEÑO"
            interp = (
                f"El último crash fue pequeño: {last_mag:.4f} pts (solo {ratio:.1f}x el promedio). "
                f"Spike de {avg_mag:.4f} pts en promedio. Crash leve, posible señal de debilitamiento del patrón."
            )
        else:
            signal = "SPIKE NORMAL"
            interp = (
                f"Tamaño del último crash dentro del rango típico ({last_mag:.4f} pts). "
                f"Promedio histórico: {avg_mag:.4f} pts. {len(spikes)} crasheos en ventana de {self.lookback} velas. "
                f"Comportamiento normal del índice."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(avg_mag, 5), signal=signal, interpretation=interp,
            metadata={
                "avg_magnitude": round(avg_mag, 5),
                "last_magnitude": round(last_mag, 5),
                "max_magnitude": round(max_mag, 5),
                "spike_count": len(spikes),
                "ratio_vs_avg": round(ratio, 3),
            },
        )
