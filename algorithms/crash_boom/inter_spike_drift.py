"""CRASH #11 — Inter-Spike Drift Slope.

Mide la pendiente del drift ALCISTA entre crasheos.
En Crash, el precio sube lentamente entre spikes (drift alcista).
Este algoritmo captura la velocidad y dirección de ese drift.

Una pendiente alta = drift agresivo = el mercado corre hacia el próximo crash.
Una pendiente baja = drift lento = hay más tiempo de drift disponible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashInterSpikeDrift(AlgorithmBase):
    name = "crash.drift_slope"
    category = "crash_boom"
    description = "Pendiente y velocidad del drift alcista entre crasheos. Alta pendiente = drift agresivo."

    def __init__(self, lookback: int = 100) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_positions = wick[wick > threshold].index.tolist()

        # Usar el segmento post-último spike
        if spike_positions:
            start = spike_positions[-1] + 1
        else:
            start = 0
        drift_segment = window.iloc[start:]

        if len(drift_segment) < 5:
            return AlgorithmResult(
                self.name, symbol, 0.0, "SEGMENTO CORTO",
                f"Solo {len(drift_segment)} velas desde el último crash. Insuficiente para calcular drift.",
            )

        prices = drift_segment["close"].values
        x = np.arange(len(prices))
        slope, intercept, r_value, p_value, _ = stats.linregress(x, prices)

        # Normalizar la pendiente como % diario del precio medio
        price_mean = float(np.mean(prices))
        slope_pct = (slope / price_mean * 100) if price_mean else 0.0
        r2 = r_value ** 2

        if slope_pct > 0.15:
            signal = "DRIFT AGRESIVO"
            interp = (
                f"El drift alcista post-crash tiene una pendiente alta: {slope_pct:+.4f}% por vela. "
                f"R²={r2:.3f}. El precio sube rápidamente después del último crash. "
                f"Drift agresivo = el mercado se acerca velozmente al siguiente crash. "
                f"Segmento de {len(drift_segment)} velas desde el último spike."
            )
        elif slope_pct > 0.05:
            signal = "DRIFT NORMAL"
            interp = (
                f"Drift alcista estable: {slope_pct:+.4f}% por vela. "
                f"R²={r2:.3f}. El precio sube gradualmente. Comportamiento típico. "
                f"Segmento de {len(drift_segment)} velas."
            )
        elif slope_pct > 0:
            signal = "DRIFT LENTO"
            interp = (
                f"Drift alcista muy lento: {slope_pct:+.4f}% por vela. "
                f"El precio sube muy poco. Puede indicar que el mercado no ha consolidado "
                f"el rebote post-crash o hay fuerza vendedora. R²={r2:.3f}."
            )
        elif slope_pct < -0.05:
            signal = "DRIFT NEGATIVO"
            interp = (
                f"⚠️ El precio está BAJANDO post-crash: {slope_pct:+.4f}% por vela. "
                f"Comportamiento atípico para CRASH. Posible régimen de doble crash o "
                f"segmento de análisis muy corto. R²={r2:.3f}."
            )
        else:
            signal = "NEUTRO"
            interp = (
                f"Drift prácticamente plano: {slope_pct:+.4f}% por vela. "
                f"El mercado está consolidando post-crash. R²={r2:.3f}."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(slope_pct, 6), signal=signal, interpretation=interp,
            metadata={
                "slope_pct_per_bar": round(slope_pct, 6),
                "r_squared": round(r2, 4),
                "drift_bars": len(drift_segment),
                "bars_since_last_crash": len(window) - 1 - (spike_positions[-1] if spike_positions else -1),
            },
        )
