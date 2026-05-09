"""CRASH #45 / BOOM #45 — Regime Classifier.

Clasifica el estado actual del mercado en uno de 4 regímenes:
  DRIFT      → el mercado sube/baja establemente entre spikes
  TENSIÓN    → el precio se acerca al nivel pre-spike, riesgo alto
  SPIKE      → spike ocurrió en las últimas 2 velas
  RECUPERACIÓN → 3–40 velas post-spike, precio rebotando/corrigiendo
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom

TENSION_THRESHOLD = 60      # % de recuperación que ya empieza a ser tensión
SPIKE_FRESH_BARS  = 2       # velas donde el spike se considera "activo"
RECOVERY_MAX_BARS = 40      # máximo de barras en fase de recuperación


def _is_spike_bar(row: pd.Series, threshold: float, mode: str) -> bool:
    if mode == "crash":
        wick = float(max(row["open"], row["close"]) - row["low"])
    else:
        wick = float(row["high"] - max(row["open"], row["close"]))
    return wick > threshold


@register
class CrashRegimeClassifier(AlgorithmBase):
    name = "crash.regime"
    category = "crash_boom"
    description = "Régimen del mercado: DRIFT / TENSIÓN / SPIKE / RECUPERACIÓN."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        last_idx = _find_last_crash(window)
        bars_since = (len(window) - 1 - last_idx) if last_idx is not None else 999

        # ── Régimen SPIKE (spike en última vela o penúltima) ──
        if last_idx is not None and bars_since <= SPIKE_FRESH_BARS:
            regime = "SPIKE"
            value  = 0.0
            interp = (f"Crash detectado hace {bars_since} vela(s). "
                      f"El mercado está en shock. No entrar hasta estabilizar.")
            return AlgorithmResult(self.name, symbol, value, regime, interp,
                                   {"bars_since_spike": bars_since})

        # ── Régimen RECUPERACIÓN ──
        if last_idx is not None and bars_since <= RECOVERY_MAX_BARS:
            crash_low  = float(window.loc[last_idx, "low"])
            pre = window.iloc[max(0, last_idx - 20): last_idx]
            crash_high = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
            swing = crash_high - crash_low
            current = float(window["close"].iloc[-1])
            recovery_pct = (current - crash_low) / swing * 100 if swing > 0 else 0.0

            regime = "RECUPERACIÓN"
            value  = round(recovery_pct, 1)
            interp = (f"Post-crash: {bars_since} barras. Recuperado {recovery_pct:.1f}% del swing. "
                      f"Drift alcista en construcción. Presión de venta reducida.")
            return AlgorithmResult(self.name, symbol, value, regime, interp,
                                   {"bars_since_crash": bars_since, "recovery_pct": round(recovery_pct, 2)})

        # ── Régimen TENSIÓN o DRIFT ──
        # Tensión: últimas 10 velas mayoritariamente alcistas + precio en zona alta
        last10 = window.tail(10)
        bull_pct = float((last10["close"] > last10["open"]).mean() * 100)
        # Cuerpos crecientes (proxy de tensión)
        bodies = (last10["close"] - last10["open"]).abs()
        body_trend = float(bodies.iloc[-3:].mean()) - float(bodies.iloc[:3].mean())
        tension_score = (bull_pct * 0.6) + (min(body_trend / bodies.mean() * 50, 40) if bodies.mean() > 0 else 0)

        if tension_score >= TENSION_THRESHOLD:
            regime = "TENSIÓN"
            value  = round(tension_score, 1)
            interp = (f"Score de tensión: {tension_score:.1f}/100. {bull_pct:.0f}% velas alcistas recientes. "
                      f"El drift está maduro y el crash podría estar cerca.")
        else:
            regime = "DRIFT"
            value  = round(tension_score, 1)
            interp = (f"Score de tensión: {tension_score:.1f}/100. Drift alcista estable. "
                      f"Presión de crash baja. Condiciones favorables para mantener largos.")

        return AlgorithmResult(self.name, symbol, value, regime, interp,
                               {"tension_score": round(tension_score, 1),
                                "bull_pct_10": round(bull_pct, 1),
                                "bars_since_last_crash": bars_since})


@register
class BoomRegimeClassifier(AlgorithmBase):
    name = "boom.regime"
    category = "crash_boom"
    description = "Régimen del mercado: DRIFT / TENSIÓN / SPIKE / CORRECCIÓN."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        last_idx = _find_last_boom(window)
        bars_since = (len(window) - 1 - last_idx) if last_idx is not None else 999

        if last_idx is not None and bars_since <= SPIKE_FRESH_BARS:
            regime = "SPIKE"
            value  = 0.0
            interp = (f"Boom detectado hace {bars_since} vela(s). "
                      f"El mercado está en shock alcista. No entrar shorts hasta estabilizar.")
            return AlgorithmResult(self.name, symbol, value, regime, interp,
                                   {"bars_since_spike": bars_since})

        if last_idx is not None and bars_since <= RECOVERY_MAX_BARS:
            boom_high = float(window.loc[last_idx, "high"])
            pre = window.iloc[max(0, last_idx - 20): last_idx]
            boom_low  = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
            swing = boom_high - boom_low
            current = float(window["close"].iloc[-1])
            correction_pct = (boom_high - current) / swing * 100 if swing > 0 else 0.0

            regime = "CORRECCIÓN"
            value  = round(correction_pct, 1)
            interp = (f"Post-boom: {bars_since} barras. Corregido {correction_pct:.1f}% del swing. "
                      f"Drift bajista en construcción.")
            return AlgorithmResult(self.name, symbol, value, regime, interp,
                                   {"bars_since_boom": bars_since, "correction_pct": round(correction_pct, 2)})

        last10 = window.tail(10)
        bear_pct = float((last10["close"] < last10["open"]).mean() * 100)
        bodies = (last10["close"] - last10["open"]).abs()
        body_trend = float(bodies.iloc[-3:].mean()) - float(bodies.iloc[:3].mean())
        tension_score = (bear_pct * 0.6) + (min(body_trend / bodies.mean() * 50, 40) if bodies.mean() > 0 else 0)

        if tension_score >= TENSION_THRESHOLD:
            regime = "TENSIÓN"
            value  = round(tension_score, 1)
            interp = (f"Score de tensión: {tension_score:.1f}/100. {bear_pct:.0f}% velas bajistas recientes. "
                      f"El drift bajista está maduro y el boom podría estar cerca.")
        else:
            regime = "DRIFT"
            value  = round(tension_score, 1)
            interp = (f"Score de tensión: {tension_score:.1f}/100. Drift bajista estable. "
                      f"Presión de boom baja. Condiciones favorables para mantener cortos.")

        return AlgorithmResult(self.name, symbol, value, regime, interp,
                               {"tension_score": round(tension_score, 1),
                                "bear_pct_10": round(bear_pct, 1),
                                "bars_since_last_boom": bars_since})
