"""CRASH #42 / BOOM #42 — Risk Composite Score.

Score compuesto ponderado (0–100) que agrega las señales más críticas:
  - Sobrevencimiento (spike_overdue)           → 30%
  - Tensión pre-spike                          → 25%
  - Fase del ciclo                             → 20%
  - Probabilidad de spike (10 barras)          → 15%
  - Ecos detectados                            → 10%

Score alto → acercarse al spike, riesgo elevado.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom
import numpy as np


def _overdue_score(window: pd.DataFrame, mode: str) -> float:
    """Retorna el % del intervalo histórico consumido (0–100)."""
    body = (window["close"] - window["open"]).abs()
    thr  = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
    if mode == "crash":
        wick = window["open"].clip(lower=window["close"]) - window["low"]
        last_fn = _find_last_crash
    else:
        wick = window["high"] - window[["open", "close"]].max(axis=1)
        last_fn = _find_last_boom
    spike_mask = wick > thr
    idxs = [i for i in range(len(window)) if spike_mask.iloc[i]]
    if len(idxs) < 2:
        return 50.0
    intervals = [idxs[i + 1] - idxs[i] for i in range(len(idxs) - 1)]
    avg = float(np.mean(intervals))
    last_idx = last_fn(window)
    bars_since = (len(window) - 1 - last_idx) if last_idx is not None else avg
    return min(bars_since / avg * 100, 100.0) if avg > 0 else 50.0


def _tension_score(window: pd.DataFrame, mode: str) -> float:
    last10 = window.tail(10)
    if mode == "crash":
        dir_pct = float((last10["close"] > last10["open"]).mean() * 100)
    else:
        dir_pct = float((last10["close"] < last10["open"]).mean() * 100)
    bodies = (last10["close"] - last10["open"]).abs()
    body_mean = float(bodies.mean())
    body_trend = float(bodies.iloc[-3:].mean()) - float(bodies.iloc[:3].mean())
    expansion = min(body_trend / body_mean * 50, 40) if body_mean > 0 else 0
    return min(dir_pct * 0.6 + expansion, 100.0)


def _echo_count(window: pd.DataFrame, mode: str, last_idx) -> int:
    if last_idx is None:
        return 0
    body = (window["close"] - window["open"]).abs()
    thr  = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER * 0.3
    post = window.iloc[last_idx + 1: last_idx + 31]
    if mode == "crash":
        wick = post["open"].clip(lower=post["close"]) - post["low"]
    else:
        wick = post["high"] - post[["open", "close"]].max(axis=1)
    return int((wick > thr).sum())


@register
class CrashRiskComposite(AlgorithmBase):
    name = "crash.risk_composite"
    category = "crash_boom"
    description = "Score compuesto de riesgo de crash 0–100. Alto = crash cerca."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(500).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        overdue  = _overdue_score(window, "crash")
        tension  = _tension_score(window, "crash")
        n_echoes = _echo_count(window, "crash", last_idx)

        # Fase del ciclo (precio)
        if last_idx is not None:
            crash_low  = float(window.loc[last_idx, "low"])
            pre = window.iloc[max(0, last_idx - 20): last_idx]
            crash_high = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
            swing = crash_high - crash_low
            current = float(window["close"].iloc[-1])
            cycle_pct = min((current - crash_low) / swing * 100, 100.0) if swing > 0 else 50.0
        else:
            cycle_pct = 50.0

        # Probabilidad (modelo simplificado)
        from algorithms.crash_boom.spike_probability import _spike_intervals
        intervals = _spike_intervals(window, "crash")
        if len(intervals) >= 2:
            avg = float(np.mean(intervals))
            bars_since = (len(window) - 1 - last_idx) if last_idx is not None else avg
            lam = 1.0 / max(avg - bars_since, 1.0)
            prob10 = min((1.0 - np.exp(-lam * 10)) * 100, 99.0)
        else:
            prob10 = 30.0

        echo_score = min(n_echoes * 15, 30.0)

        composite = (
            overdue  * 0.30 +
            tension  * 0.25 +
            cycle_pct * 0.20 +
            prob10   * 0.15 +
            echo_score * 0.10
        )
        composite = round(min(composite, 100.0), 1)

        if composite >= 75:
            signal = "RIESGO EXTREMO"
            interp = (f"Score: {composite}/100. Overdue={overdue:.0f}%, Tensión={tension:.0f}%, "
                      f"Ciclo={cycle_pct:.0f}%, P10={prob10:.0f}%. CRASH MUY CERCA.")
        elif composite >= 55:
            signal = "RIESGO ALTO"
            interp = (f"Score: {composite}/100. Múltiples señales convergentes. "
                      f"Overdue={overdue:.0f}%, Tensión={tension:.0f}%, Ciclo={cycle_pct:.0f}%.")
        elif composite >= 35:
            signal = "RIESGO MODERADO"
            interp = (f"Score: {composite}/100. Algunas señales de alerta. Monitorear.")
        else:
            signal = "RIESGO BAJO"
            interp = (f"Score: {composite}/100. El mercado está en zona segura. "
                      f"Overdue={overdue:.0f}%, Tensión={tension:.0f}%.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=composite, signal=signal, interpretation=interp,
            metadata={
                "composite_score": composite,
                "overdue_pct": round(overdue, 1),
                "tension_score": round(tension, 1),
                "cycle_pct": round(cycle_pct, 1),
                "prob_10bars": round(prob10, 1),
                "echo_count": n_echoes,
            },
        )


@register
class BoomRiskComposite(AlgorithmBase):
    name = "boom.risk_composite"
    category = "crash_boom"
    description = "Score compuesto de riesgo de boom 0–100. Alto = boom cerca."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(500).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        overdue  = _overdue_score(window, "boom")
        tension  = _tension_score(window, "boom")
        n_echoes = _echo_count(window, "boom", last_idx)

        if last_idx is not None:
            boom_high = float(window.loc[last_idx, "high"])
            pre = window.iloc[max(0, last_idx - 20): last_idx]
            boom_low  = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
            swing = boom_high - boom_low
            current = float(window["close"].iloc[-1])
            cycle_pct = min((boom_high - current) / swing * 100, 100.0) if swing > 0 else 50.0
        else:
            cycle_pct = 50.0

        from algorithms.crash_boom.spike_probability import _spike_intervals
        intervals = _spike_intervals(window, "boom")
        if len(intervals) >= 2:
            avg = float(np.mean(intervals))
            bars_since = (len(window) - 1 - last_idx) if last_idx is not None else avg
            lam = 1.0 / max(avg - bars_since, 1.0)
            prob10 = min((1.0 - np.exp(-lam * 10)) * 100, 99.0)
        else:
            prob10 = 30.0

        echo_score = min(n_echoes * 15, 30.0)

        composite = (
            overdue  * 0.30 +
            tension  * 0.25 +
            cycle_pct * 0.20 +
            prob10   * 0.15 +
            echo_score * 0.10
        )
        composite = round(min(composite, 100.0), 1)

        if composite >= 75:
            signal = "RIESGO EXTREMO"
            interp = (f"Score: {composite}/100. BOOM MUY CERCA. "
                      f"Overdue={overdue:.0f}%, Tensión={tension:.0f}%, Ciclo={cycle_pct:.0f}%.")
        elif composite >= 55:
            signal = "RIESGO ALTO"
            interp = (f"Score: {composite}/100. Señales convergentes de boom próximo.")
        elif composite >= 35:
            signal = "RIESGO MODERADO"
            interp = (f"Score: {composite}/100. Algunas señales de alerta. Monitorear.")
        else:
            signal = "RIESGO BAJO"
            interp = (f"Score: {composite}/100. Zona segura para cortos. "
                      f"Overdue={overdue:.0f}%, Tensión={tension:.0f}%.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=composite, signal=signal, interpretation=interp,
            metadata={
                "composite_score": composite,
                "overdue_pct": round(overdue, 1),
                "tension_score": round(tension, 1),
                "cycle_pct": round(cycle_pct, 1),
                "prob_10bars": round(prob10, 1),
                "echo_count": n_echoes,
            },
        )
