"""CRASH #20 — Recovery Completion.

Calcula qué porcentaje del precio pre-crash ya se ha recuperado.
Indica si el mercado está en fase de recuperación temprana, media o completa.

0% = justo después del crash. 100% = precio recuperado por completo.
>100% = nuevo máximo post-crash = drift activo y en progreso.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashRecoveryCompletion(AlgorithmBase):
    name = "crash.recovery_pct"
    category = "crash_boom"
    description = "% del precio recuperado desde el último crash. 100% = nivel pre-crash alcanzado."

    def __init__(self, lookback: int = 300) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_mask = wick > threshold

        if not spike_mask.any():
            return AlgorithmResult(
                self.name, symbol, 100.0, "SIN CRASHES RECIENTES",
                "No se encontraron crashes en la ventana. El mercado lleva mucho tiempo sin caer.",
            )

        spike_positions = window.index[spike_mask].tolist()
        last_spike_idx = spike_positions[-1]
        spike_row = window.iloc[last_spike_idx]

        pre_crash_price = float(max(spike_row["open"], spike_row["close"]))
        crash_low = float(spike_row["low"])
        crash_depth = pre_crash_price - crash_low
        current_price = float(window.iloc[-1]["close"])

        if crash_depth <= 0:
            return AlgorithmResult(
                self.name, symbol, 100.0, "RECUPERADO",
                "La caída del crash fue mínima.",
            )

        recovered = current_price - crash_low
        recovery_pct = (recovered / crash_depth * 100)
        bars_since = len(window) - 1 - last_spike_idx

        if recovery_pct >= 100:
            signal = "TOTALMENTE RECUPERADO"
            interp = (
                f"Precio actual: {current_price:.4f}. Pre-crash: {pre_crash_price:.4f}. "
                f"Recuperación: {recovery_pct:.1f}% en {bars_since} velas. "
                f"✅ El mercado superó el nivel pre-crash. Drift activo y en progreso hacia el próximo spike."
            )
        elif recovery_pct >= 75:
            signal = "RECUPERACIÓN AVANZADA"
            interp = (
                f"Recuperado el {recovery_pct:.1f}% del crash en {bars_since} velas. "
                f"Precio: {current_price:.4f} | Pre-crash: {pre_crash_price:.4f}. "
                f"Quedan {100 - recovery_pct:.1f}% para completar la recuperación."
            )
        elif recovery_pct >= 40:
            signal = "RECUPERACIÓN MEDIA"
            interp = (
                f"Recuperado el {recovery_pct:.1f}% del crash ({bars_since} velas). "
                f"El mercado aún está en zona de recuperación. "
                f"Quedan {100 - recovery_pct:.1f}% para volver al nivel pre-crash."
            )
        elif recovery_pct >= 10:
            signal = "RECUPERACIÓN TEMPRANA"
            interp = (
                f"Recuperado solo el {recovery_pct:.1f}% del crash ({bars_since} velas). "
                f"El mercado está en la fase inicial del rebote. "
                f"Zona de mayor seguridad estadística para posiciones largas."
            )
        else:
            signal = "CRASH RECIENTE"
            interp = (
                f"Crash muy reciente (hace {bars_since} velas). Recuperado: {recovery_pct:.1f}%. "
                f"El precio está cerca del mínimo del crash. "
                f"Mejor momento estadístico para entrar largo."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(recovery_pct, 2), signal=signal, interpretation=interp,
            metadata={
                "recovery_pct": round(recovery_pct, 2),
                "current_price": round(current_price, 5),
                "pre_crash_price": round(pre_crash_price, 5),
                "crash_low": round(crash_low, 5),
                "bars_since_crash": bars_since,
            },
        )
