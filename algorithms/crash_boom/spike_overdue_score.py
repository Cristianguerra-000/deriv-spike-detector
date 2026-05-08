"""CRASH #2 — Spike Overdue Score.

Calcula qué porcentaje del intervalo declarado ya fue consumido desde
el último spike. Es el indicador de "¿cuánto tiempo lleva sin caerse?".

Salida: 0–100 donde 100 = debería haber crasheado ya.
"""
from __future__ import annotations

import re

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


def _find_last_spike_idx(df: pd.DataFrame, symbol: str) -> int | None:
    is_crash = "CRASH" in symbol.upper()
    body = (df["close"] - df["open"]).abs()
    normal_body = float(body.quantile(0.75))
    threshold = normal_body * SPIKE_ATR_MULTIPLIER
    if is_crash:
        wick = df["open"].clip(lower=df["close"]) - df["low"]
    else:
        wick = df["high"] - df[["open", "close"]].max(axis=1)
    spikes = df.index[wick > threshold].tolist()
    return spikes[-1] if spikes else None


@register
class CrashSpikeOverdueScore(AlgorithmBase):
    name = "crash.spike_overdue"
    category = "crash_boom"
    description = "% del intervalo declarado consumido desde el último spike. 100 = máxima sobredosis."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        nums = re.findall(r"\d+", symbol)
        declared = int(nums[0]) if nums else 500

        last_idx = _find_last_spike_idx(df, symbol)
        if last_idx is not None:
            bars_since = len(df) - 1 - df.index.get_loc(last_idx)
        else:
            bars_since = len(df)

        score = min(bars_since / declared * 100, 100)
        urgency = round(score, 1)

        if score >= 100:
            signal = "SOBRETIEMPO MÁXIMO"
            interp = (
                f"⚠️ SOBRETIEMPO: han pasado {bars_since} velas y el intervalo declarado es {declared}. "
                f"Score: {urgency}/100. El próximo crash es estadísticamente INMINENTE. "
                f"MÁXIMO RIESGO. No mantener posiciones largas no protegidas."
            )
        elif score >= 80:
            signal = "RIESGO ALTO"
            interp = (
                f"Han pasado {bars_since}/{declared} velas desde el último crash. "
                f"Score: {urgency}/100. Riesgo ALTO de crash próximo. "
                f"Reducir exposición y ajustar stops."
            )
        elif score >= 60:
            signal = "RIESGO MODERADO"
            interp = (
                f"Han pasado {bars_since}/{declared} velas. Score: {urgency}/100. "
                f"Riesgo moderado. El mercado avanza pero la amenaza de crash crece. "
                f"Seguir con cautela."
            )
        elif score >= 40:
            signal = "RIESGO BAJO-MEDIO"
            interp = (
                f"Han pasado {bars_since}/{declared} velas. Score: {urgency}/100. "
                f"Zona relativamente segura pero ya en la primera mitad del intervalo. "
                f"Momento típico de drift limpio."
            )
        else:
            signal = "ZONA SEGURA"
            interp = (
                f"Recién ocurrió el último crash (hace {bars_since} velas). "
                f"Score: {urgency}/100. Zona de mayor seguridad estadística. "
                f"El drift alcista acaba de reiniciarse. Momento óptimo para estrategias largas."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=urgency, signal=signal, interpretation=interp,
            metadata={"bars_since_spike": bars_since, "declared_interval": declared},
        )
