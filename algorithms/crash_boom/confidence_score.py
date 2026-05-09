"""CRASH #48 / BOOM #48 — Confidence Score.

Mide la confianza estadística en la señal actual basada en:
  - Consistencia de señales entre algoritmos afines
  - Calidad del dato histórico (cantidad de spikes disponibles)
  - Predictibilidad del índice (coeficiente de variación de intervalos)
  - Acuerdo entre ciclo temporal y ciclo de precio

Score 0–100: 100 = señal de máxima confianza estadística.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom


def _get_spike_data(window: pd.DataFrame, mode: str):
    body = (window["close"] - window["open"]).abs()
    threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
    if mode == "crash":
        wick = window["open"].clip(lower=window["close"]) - window["low"]
    else:
        wick = window["high"] - window[["open", "close"]].max(axis=1)
    mask = wick > threshold
    idxs = [i for i in range(len(window)) if mask.iloc[i]]
    return idxs, threshold


@register
class CrashConfidence(AlgorithmBase):
    name = "crash.confidence"
    category = "crash_boom"
    description = "Confianza estadística en la señal CRASH 0–100. Alto = señal fiable."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(600).reset_index(drop=True)
        spike_idxs, _ = _get_spike_data(window, "crash")
        n_spikes = len(spike_idxs)

        # Factor 1: Cantidad de datos históricos (más spikes = más confianza)
        data_score = min(n_spikes / 20 * 40, 40.0)  # max 40 pts con 20+ spikes

        # Factor 2: Predictibilidad (bajo CV = intervalos regulares = más confiable)
        if n_spikes >= 3:
            intervals = [spike_idxs[i + 1] - spike_idxs[i] for i in range(n_spikes - 1)]
            avg = float(np.mean(intervals))
            std = float(np.std(intervals))
            cv = std / avg if avg > 0 else 1.0
            predictability = max(0.0, (1.0 - min(cv, 1.0)) * 35)  # max 35 pts
        else:
            predictability = 5.0
            avg = 0.0
            cv = 1.0

        # Factor 3: Acuerdo precio-tiempo
        last_idx = _find_last_crash(window)
        if last_idx is not None and n_spikes >= 2:
            bars_since = len(window) - 1 - last_idx
            crash_low  = float(window.loc[last_idx, "low"])
            pre = window.iloc[max(0, last_idx - 20): last_idx]
            crash_high = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
            swing = crash_high - crash_low
            current = float(window["close"].iloc[-1])
            price_cycle = (current - crash_low) / swing * 100 if swing > 0 else 50.0
            time_cycle  = min(bars_since / avg * 100, 100.0) if avg > 0 else 50.0
            agreement   = 100.0 - abs(price_cycle - time_cycle)
            agreement_score = max(0.0, agreement * 0.25)  # max 25 pts
        else:
            agreement_score = 5.0

        confidence = round(data_score + predictability + agreement_score, 1)
        confidence = min(confidence, 100.0)

        if confidence >= 75:
            signal = "ALTA CONFIANZA"
            interp = (f"Score: {confidence}/100. Señal fiable. "
                      f"{n_spikes} crashes históricos. CV={cv:.2f} (predictibilidad {'alta' if cv < 0.3 else 'media'}).")
        elif confidence >= 50:
            signal = "CONFIANZA MODERADA"
            interp = (f"Score: {confidence}/100. Señal razonablemente confiable. "
                      f"{n_spikes} crashes históricos, CV={cv:.2f}.")
        elif confidence >= 25:
            signal = "BAJA CONFIANZA"
            interp = (f"Score: {confidence}/100. Pocos datos o alta varianza. "
                      f"Solo {n_spikes} crashes disponibles. Usar con precaución.")
        else:
            signal = "SIN CONFIANZA"
            interp = (f"Score: {confidence}/100. Datos insuficientes o índice muy impredecible. "
                      f"No operar basándose en señales actuales.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=confidence, signal=signal, interpretation=interp,
            metadata={
                "confidence_score": confidence,
                "n_historical_crashes": n_spikes,
                "avg_interval": round(avg, 1) if avg else None,
                "cv_predictability": round(cv, 3) if n_spikes >= 3 else None,
                "data_score": round(data_score, 1),
                "predictability_score": round(predictability, 1),
                "agreement_score": round(agreement_score, 1),
            },
        )


@register
class BoomConfidence(AlgorithmBase):
    name = "boom.confidence"
    category = "crash_boom"
    description = "Confianza estadística en la señal BOOM 0–100. Alto = señal fiable."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(600).reset_index(drop=True)
        spike_idxs, _ = _get_spike_data(window, "boom")
        n_spikes = len(spike_idxs)

        data_score = min(n_spikes / 20 * 40, 40.0)

        if n_spikes >= 3:
            intervals = [spike_idxs[i + 1] - spike_idxs[i] for i in range(n_spikes - 1)]
            avg = float(np.mean(intervals))
            std = float(np.std(intervals))
            cv = std / avg if avg > 0 else 1.0
            predictability = max(0.0, (1.0 - min(cv, 1.0)) * 35)
        else:
            predictability = 5.0
            avg = 0.0
            cv = 1.0

        last_idx = _find_last_boom(window)
        if last_idx is not None and n_spikes >= 2:
            bars_since = len(window) - 1 - last_idx
            boom_high = float(window.loc[last_idx, "high"])
            pre = window.iloc[max(0, last_idx - 20): last_idx]
            boom_low  = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
            swing = boom_high - boom_low
            current = float(window["close"].iloc[-1])
            price_cycle = (boom_high - current) / swing * 100 if swing > 0 else 50.0
            time_cycle  = min(bars_since / avg * 100, 100.0) if avg > 0 else 50.0
            agreement   = 100.0 - abs(price_cycle - time_cycle)
            agreement_score = max(0.0, agreement * 0.25)
        else:
            agreement_score = 5.0

        confidence = round(min(data_score + predictability + agreement_score, 100.0), 1)

        if confidence >= 75:
            signal = "ALTA CONFIANZA"
            interp = (f"Score: {confidence}/100. Señal fiable. "
                      f"{n_spikes} booms históricos, CV={cv:.2f}.")
        elif confidence >= 50:
            signal = "CONFIANZA MODERADA"
            interp = (f"Score: {confidence}/100. Señal razonablemente confiable. "
                      f"{n_spikes} booms, CV={cv:.2f}.")
        elif confidence >= 25:
            signal = "BAJA CONFIANZA"
            interp = (f"Score: {confidence}/100. Datos limitados o alta varianza. "
                      f"Solo {n_spikes} booms disponibles.")
        else:
            signal = "SIN CONFIANZA"
            interp = (f"Score: {confidence}/100. Insuficientes datos históricos.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=confidence, signal=signal, interpretation=interp,
            metadata={
                "confidence_score": confidence,
                "n_historical_booms": n_spikes,
                "avg_interval": round(avg, 1) if avg else None,
                "cv_predictability": round(cv, 3) if n_spikes >= 3 else None,
                "data_score": round(data_score, 1),
                "predictability_score": round(predictability, 1),
                "agreement_score": round(agreement_score, 1),
            },
        )
