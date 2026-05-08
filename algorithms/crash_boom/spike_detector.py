"""Detector de Spikes — exclusivo para Crash y Boom Index.

Un spike en Crash es una vela con caída súbita enorme (la wick inferior
es muchas veces el ATR normal). En Boom es la wick superior.

Este algoritmo detecta:
1. Si la última vela ES un spike
2. Cuántas velas han pasado desde el último spike (zona de riesgo)
3. Si estamos en zona de alta probabilidad de spike próximo
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register

# Umbral: una vela es spike si su wick extrema es > N veces el ATR promedio
SPIKE_ATR_MULTIPLIER = 4.0


@register
class SpikeDetector(AlgorithmBase):
    name = "cb.spike_detector"
    category = "crash_boom"
    description = "Detecta spikes reales en Crash/Boom y mide riesgo acumulado."

    def __init__(self, atr_period: int = 14, lookback: int = 200) -> None:
        self.atr_period = atr_period
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        is_crash = "CRASH" in symbol.upper()
        is_boom = "BOOM" in symbol.upper()

        if not (is_crash or is_boom):
            return AlgorithmResult(
                algorithm=self.name, symbol=symbol, value=None,
                signal="N/A",
                interpretation="Este algoritmo es exclusivo para índices Crash y Boom.",
            )

        window = df.tail(self.lookback).copy()

        # ATR promedio de velas "normales" (excluye spikes para no contaminarse)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))  # percentil 75, ignora extremos

        # Detectar spikes: velas donde la wick extrema >> cuerpo normal
        if is_crash:
            # En Crash: el spike es caída enorme → wick inferior grande
            extreme_wick = window["open"].clip(lower=window["close"]) - window["low"]
        else:
            # En Boom: el spike es subida enorme → wick superior grande
            extreme_wick = window["high"] - window[["open", "close"]].max(axis=1)

        spike_threshold = normal_body * SPIKE_ATR_MULTIPLIER
        spike_mask = extreme_wick > spike_threshold
        spike_indices = window.index[spike_mask].tolist()

        # ¿La última vela es un spike?
        last_is_spike = bool(spike_mask.iloc[-1])

        # Velas desde el último spike
        if spike_indices:
            last_spike_pos = window.index.get_loc(spike_indices[-1])
            bars_since_spike = len(window) - 1 - last_spike_pos
        else:
            bars_since_spike = len(window)  # no se encontró spike → máximo riesgo

        total_spikes = int(spike_mask.sum())
        avg_interval = len(window) / total_spikes if total_spikes > 0 else len(window)

        # Extraer el número del símbolo (ej: CRASH500 → 500, BOOM1000 → 1000)
        import re
        nums = re.findall(r"\d+", symbol)
        declared_interval = int(nums[0]) if nums else 500

        # Riesgo relativo: cuánto del intervalo esperado ya ha pasado
        risk_pct = min(bars_since_spike / declared_interval * 100, 100)

        if last_is_spike:
            signal = "SPIKE DETECTADO"
            interp = (
                f"⚡ SPIKE {'BAJISTA' if is_crash else 'ALCISTA'} DETECTADO en la última vela. "
                f"La wick extrema ({float(extreme_wick.iloc[-1]):.5f}) es "
                f"{float(extreme_wick.iloc[-1]) / max(normal_body, 1e-10):.1f}x el cuerpo normal. "
                f"Después de un spike, el mercado suele retomar el drift anterior. "
                f"Oportunidad de entrada a favor del drift en los próximos ticks."
            )
        elif risk_pct >= 85:
            signal = "RIESGO ALTO DE SPIKE"
            interp = (
                f"⚠️ Han pasado {bars_since_spike} velas sin spike ({risk_pct:.0f}% del intervalo declarado {declared_interval}). "
                f"ZONA DE ALTO RIESGO: el próximo spike puede ocurrir en cualquier momento. "
                f"Reducir exposición en la dirección del spike ({'bajista' if is_crash else 'alcista'}). "
                f"Intervalo promedio histórico observado: {avg_interval:.0f} velas."
            )
        elif risk_pct >= 60:
            signal = "RIESGO MODERADO"
            interp = (
                f"Han pasado {bars_since_spike} velas desde el último spike ({risk_pct:.0f}% del intervalo). "
                f"Riesgo moderado de spike próximo. Gestionar posiciones con precaución. "
                f"Intervalo promedio observado: {avg_interval:.0f} velas | Declarado: {declared_interval}."
            )
        else:
            signal = "RIESGO BAJO"
            interp = (
                f"Último spike hace {bars_since_spike} velas ({risk_pct:.0f}% del intervalo). "
                f"Zona de bajo riesgo inmediato de spike. "
                f"El mercado debería moverse con su drift normal por un tiempo. "
                f"Total spikes detectados en ventana de {self.lookback} velas: {total_spikes}."
            )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=bars_since_spike,
            signal=signal,
            interpretation=interp,
            metadata={
                "bars_since_spike": bars_since_spike,
                "risk_pct": round(risk_pct, 1),
                "total_spikes_in_window": total_spikes,
                "avg_interval_observed": round(avg_interval, 1),
                "declared_interval": declared_interval,
                "last_is_spike": last_is_spike,
            },
        )
