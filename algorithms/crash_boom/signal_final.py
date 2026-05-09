"""CRASH #50 / BOOM #50 — Signal Final. ★ SEÑAL MAESTRA ★

Señal de decisión final que consolida todos los bloques:
  CRASH: BUY / WAIT / AVOID / EXIT
  BOOM:  SELL / WAIT / AVOID / EXIT

Lógica de decisión (4 estados):
─────────────────────────────────────────────────────────────────
CRASH:
  BUY   → Régimen=RECUPERACIÓN/DRIFT + Ciclo<50% + Riesgo<40 + Confianza>40
  WAIT  → Régimen=DRIFT + Ciclo 50–70% (zona intermedia)
  AVOID → Régimen=TENSIÓN o Ciclo>80% o Riesgo>60 (crash cercano)
  EXIT  → Régimen=SPIKE (crash ocurrió, salir)

BOOM:
  SELL  → Régimen=CORRECCIÓN/DRIFT + Ciclo<50% + Riesgo<40 + Confianza>40
  WAIT  → Régimen=DRIFT + Ciclo 50–70%
  AVOID → Régimen=TENSIÓN o Ciclo>80% o Riesgo>60 (boom cercano)
  EXIT  → Régimen=SPIKE (boom ocurrió, salir)
─────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom
from algorithms.crash_boom.post_crash_momentum import _rsi


def _quick_regime(window: pd.DataFrame, mode: str, last_idx, bars_since: int) -> str:
    """Clasifica rápidamente el régimen sin importar el clasificador completo."""
    if last_idx is not None and bars_since <= 2:
        return "SPIKE"
    if last_idx is not None and bars_since <= 40:
        return "RECUPERACIÓN" if mode == "crash" else "CORRECCIÓN"
    last10 = window.tail(10)
    if mode == "crash":
        dir_pct = float((last10["close"] > last10["open"]).mean() * 100)
    else:
        dir_pct = float((last10["close"] < last10["open"]).mean() * 100)
    bodies = (last10["close"] - last10["open"]).abs()
    body_trend = float(bodies.iloc[-3:].mean()) - float(bodies.iloc[:3].mean())
    tension = dir_pct * 0.6 + (min(body_trend / bodies.mean() * 50, 40) if bodies.mean() > 0 else 0)
    return "TENSIÓN" if tension >= 60 else "DRIFT"


def _quick_risk(window: pd.DataFrame, mode: str, last_idx) -> float:
    """Score de riesgo simplificado 0–100."""
    body = (window["close"] - window["open"]).abs()
    thr  = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
    if mode == "crash":
        wick = window["open"].clip(lower=window["close"]) - window["low"]
    else:
        wick = window["high"] - window[["open", "close"]].max(axis=1)
    mask = wick > thr
    idxs = [i for i in range(len(window)) if mask.iloc[i]]
    if len(idxs) < 2:
        return 30.0
    intervals = [idxs[i + 1] - idxs[i] for i in range(len(idxs) - 1)]
    avg = float(np.mean(intervals))
    bars_since = (len(window) - 1 - last_idx) if last_idx is not None else avg
    overdue = min(bars_since / avg * 100, 100.0) if avg > 0 else 50.0
    last10 = window.tail(10)
    if mode == "crash":
        dir_pct = float((last10["close"] > last10["open"]).mean() * 100)
    else:
        dir_pct = float((last10["close"] < last10["open"]).mean() * 100)
    return round(overdue * 0.5 + dir_pct * 0.5, 1)


def _quick_cycle(window: pd.DataFrame, mode: str, last_idx) -> float:
    """% del ciclo completado (precio)."""
    if last_idx is None:
        return 50.0
    if mode == "crash":
        low_val  = float(window.loc[last_idx, "low"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        high_val = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        current  = float(window["close"].iloc[-1])
        return min((current - low_val) / (high_val - low_val) * 100, 100.0) if high_val != low_val else 50.0
    else:
        high_val = float(window.loc[last_idx, "high"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        low_val  = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        current  = float(window["close"].iloc[-1])
        return min((high_val - current) / (high_val - low_val) * 100, 100.0) if high_val != low_val else 50.0


def _quick_confidence(window: pd.DataFrame, mode: str) -> float:
    body = (window["close"] - window["open"]).abs()
    thr  = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
    if mode == "crash":
        wick = window["open"].clip(lower=window["close"]) - window["low"]
    else:
        wick = window["high"] - window[["open", "close"]].max(axis=1)
    n = int((wick > thr).sum())
    return min(n / 15 * 100, 100.0)


@register
class CrashSignalFinal(AlgorithmBase):
    name = "crash.signal_final"
    category = "crash_boom"
    description = "★ SEÑAL FINAL CRASH: BUY / WAIT / AVOID / EXIT."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(500).reset_index(drop=True)
        last_idx   = _find_last_crash(window)
        bars_since = (len(window) - 1 - last_idx) if last_idx is not None else 999

        regime     = _quick_regime(window, "crash", last_idx, bars_since)
        risk       = _quick_risk(window, "crash", last_idx)
        cycle_pct  = _quick_cycle(window, "crash", last_idx)
        confidence = _quick_confidence(window, "crash")

        # RSI de las últimas 14 velas como factor secundario
        rsi = _rsi(window["close"].values[-14:], period=7)

        # ── Lógica de decisión ──────────────────────────────────────
        if regime == "SPIKE":
            action = "EXIT"
            score  = 0.0
            reason = (f"Crash detectado hace {bars_since} vela(s). "
                      f"SALIR inmediatamente de posiciones largas. "
                      f"Esperar estabilización (régimen RECUPERACIÓN).")

        elif regime in ("RECUPERACIÓN",) and cycle_pct < 30 and risk < 50:
            action = "BUY"
            score  = round(100 - risk + confidence * 0.3, 1)
            reason = (f"Régimen: {regime}. Ciclo: {cycle_pct:.0f}%. Riesgo: {risk:.0f}. "
                      f"ZONA ÓPTIMA DE ENTRADA. El crash ocurrió, el drift alcista comienza. "
                      f"RSI={rsi:.0f}. Confianza: {confidence:.0f}%.")

        elif regime == "DRIFT" and cycle_pct < 50 and risk < 40:
            action = "BUY"
            score  = round(80 - risk, 1)
            reason = (f"Régimen: DRIFT. Ciclo: {cycle_pct:.0f}%. Riesgo bajo ({risk:.0f}). "
                      f"Drift activo y estable. Buena relación R/B para largos. RSI={rsi:.0f}.")

        elif regime == "DRIFT" and 50 <= cycle_pct <= 75 and risk < 60:
            action = "WAIT"
            score  = 50.0
            reason = (f"Régimen: DRIFT. Ciclo: {cycle_pct:.0f}% (zona media). "
                      f"Riesgo: {risk:.0f}. El drift continúa pero la relación R/B se reduce. "
                      f"Esperar corrección o continuar con stop ajustado.")

        elif regime == "TENSIÓN" or cycle_pct > 80 or risk > 65:
            action = "AVOID"
            score  = round(risk, 1)
            reason = (f"Régimen: {regime}. Ciclo: {cycle_pct:.0f}%. Riesgo: {risk:.0f}. "
                      f"El crash está próximo. EVITAR nuevas posiciones largas. "
                      f"Si ya hay posición, considerar cerrar o poner stop muy ajustado.")

        else:
            action = "WAIT"
            score  = 50.0
            reason = (f"Régimen: {regime}. Ciclo: {cycle_pct:.0f}%. Riesgo: {risk:.0f}. "
                      f"Señal ambigua. Monitorear. No actuar hasta confirmación.")

        # Ajustar score si confianza es baja
        if confidence < 30 and action in ("BUY",):
            action = "WAIT"
            reason += f" [REBAJADO a WAIT: confianza insuficiente ({confidence:.0f}%)]"

        score = min(max(score, 0.0), 100.0)

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=score, signal=action, interpretation=reason,
            metadata={
                "action": action,
                "score": round(score, 1),
                "regime": regime,
                "cycle_pct": round(cycle_pct, 1),
                "risk_score": round(risk, 1),
                "confidence": round(confidence, 1),
                "rsi": round(rsi, 1),
                "bars_since_crash": bars_since,
            },
        )


@register
class BoomSignalFinal(AlgorithmBase):
    name = "boom.signal_final"
    category = "crash_boom"
    description = "★ SEÑAL FINAL BOOM: SELL / WAIT / AVOID / EXIT."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(500).reset_index(drop=True)
        last_idx   = _find_last_boom(window)
        bars_since = (len(window) - 1 - last_idx) if last_idx is not None else 999

        regime     = _quick_regime(window, "boom", last_idx, bars_since)
        risk       = _quick_risk(window, "boom", last_idx)
        cycle_pct  = _quick_cycle(window, "boom", last_idx)
        confidence = _quick_confidence(window, "boom")
        rsi = _rsi(window["close"].values[-14:], period=7)

        if regime == "SPIKE":
            action = "EXIT"
            score  = 0.0
            reason = (f"Boom detectado hace {bars_since} vela(s). "
                      f"SALIR inmediatamente de posiciones cortas. "
                      f"Esperar estabilización (régimen CORRECCIÓN).")

        elif regime == "CORRECCIÓN" and cycle_pct < 30 and risk < 50:
            action = "SELL"
            score  = round(100 - risk + confidence * 0.3, 1)
            reason = (f"Régimen: {regime}. Ciclo: {cycle_pct:.0f}%. Riesgo: {risk:.0f}. "
                      f"ZONA ÓPTIMA DE ENTRADA. El boom ocurrió, el drift bajista comienza. "
                      f"RSI={rsi:.0f}. Confianza: {confidence:.0f}%.")

        elif regime == "DRIFT" and cycle_pct < 50 and risk < 40:
            action = "SELL"
            score  = round(80 - risk, 1)
            reason = (f"Régimen: DRIFT. Ciclo: {cycle_pct:.0f}%. Riesgo bajo ({risk:.0f}). "
                      f"Drift bajista activo. Buena R/B para cortos. RSI={rsi:.0f}.")

        elif regime == "DRIFT" and 50 <= cycle_pct <= 75 and risk < 60:
            action = "WAIT"
            score  = 50.0
            reason = (f"Régimen: DRIFT. Ciclo: {cycle_pct:.0f}% (zona media). "
                      f"Riesgo: {risk:.0f}. Esperar corrección o continuar con stop ajustado.")

        elif regime == "TENSIÓN" or cycle_pct > 80 or risk > 65:
            action = "AVOID"
            score  = round(risk, 1)
            reason = (f"Régimen: {regime}. Ciclo: {cycle_pct:.0f}%. Riesgo: {risk:.0f}. "
                      f"El boom está próximo. EVITAR nuevas posiciones cortas.")

        else:
            action = "WAIT"
            score  = 50.0
            reason = (f"Régimen: {regime}. Ciclo: {cycle_pct:.0f}%. Riesgo: {risk:.0f}. "
                      f"Señal ambigua. Monitorear.")

        if confidence < 30 and action in ("SELL",):
            action = "WAIT"
            reason += f" [REBAJADO a WAIT: confianza insuficiente ({confidence:.0f}%)]"

        score = min(max(score, 0.0), 100.0)

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=score, signal=action, interpretation=reason,
            metadata={
                "action": action,
                "score": round(score, 1),
                "regime": regime,
                "cycle_pct": round(cycle_pct, 1),
                "risk_score": round(risk, 1),
                "confidence": round(confidence, 1),
                "rsi": round(rsi, 1),
                "bars_since_boom": bars_since,
            },
        )
