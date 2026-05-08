"""BOOM #2 — Boom Overdue Score.

Idéntico al crash.spike_overdue pero para BOOM:
calcula qué % del intervalo declarado ya fue consumido desde el último boom.

En BOOM el spike es ALCISTA (wick superior), el drift es BAJISTA.
"""
from __future__ import annotations

import re

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


def _find_last_boom_idx(df: pd.DataFrame) -> int | None:
    body = (df["close"] - df["open"]).abs()
    normal_body = float(body.quantile(0.75))
    threshold = normal_body * SPIKE_ATR_MULTIPLIER
    # Boom = wick superior
    wick = df["high"] - df[["open", "close"]].max(axis=1)
    spikes = df.index[wick > threshold].tolist()
    return spikes[-1] if spikes else None


@register
class BoomSpikeOverdueScore(AlgorithmBase):
    name = "boom.spike_overdue"
    category = "crash_boom"
    description = "% del intervalo BOOM consumido. 100 = el próximo boom es estadísticamente inminente."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        nums = re.findall(r"\d+", symbol)
        declared = int(nums[0]) if nums else 500

        last_idx = _find_last_boom_idx(df)
        if last_idx is not None:
            bars_since = len(df) - 1 - df.index.get_loc(last_idx)
        else:
            bars_since = len(df)

        score = min(bars_since / declared * 100, 100)
        urgency = round(score, 1)

        if score >= 100:
            signal = "SOBRETIEMPO MÁXIMO"
            interp = (
                f"⚡ SOBRETIEMPO: {bars_since} velas desde el último boom (intervalo: {declared}). "
                f"Score: {urgency}/100. El próximo BOOM es estadísticamente INMINENTE. "
                f"MÁXIMA OPORTUNIDAD de entrada en corto pre-boom."
            )
        elif score >= 80:
            signal = "BOOM INMINENTE"
            interp = (
                f"Han pasado {bars_since}/{declared} velas desde el último boom. "
                f"Score: {urgency}/100. Alta probabilidad de boom próximo. "
                f"Preparar estrategia de entrada: esperar el boom para vender en el pico."
            )
        elif score >= 60:
            signal = "RIESGO MODERADO"
            interp = (
                f"Han pasado {bars_since}/{declared} velas. Score: {urgency}/100. "
                f"Zona de alerta media. El drift bajista continúa pero el boom se acerca."
            )
        elif score >= 40:
            signal = "MARGEN MEDIO"
            interp = (
                f"Han pasado {bars_since}/{declared} velas. Score: {urgency}/100. "
                f"Primera mitad del intervalo superada. Drift bajista probable pero boom lejano aún."
            )
        else:
            signal = "ZONA SEGURA"
            interp = (
                f"Recién ocurrió el último boom (hace {bars_since} velas). "
                f"Score: {urgency}/100. Zona de mayor seguridad estadística. "
                f"El drift bajista acaba de reiniciarse. Momento óptimo para estrategias cortas."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=urgency, signal=signal, interpretation=interp,
            metadata={"bars_since_spike": bars_since, "declared_interval": declared},
        )
