"""CRASH #47 / BOOM #47 — Optimal Entry.

Determina el momento óptimo para entrar después de un spike.
Score 0–100 de calidad de entrada:
  CRASH → entrada larga (comprar): mejor justo después del crash,
          en zona baja de recuperación, con confirmación de rebote.
  BOOM  → entrada corta (vender):  mejor justo después del boom,
          en zona alta de corrección, con confirmación de caída.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom
from algorithms.crash_boom.post_crash_momentum import _rsi


@register
class CrashOptimalEntry(AlgorithmBase):
    name = "crash.optimal_entry"
    category = "crash_boom"
    description = "Score de entrada post-crash 0–100. Alto = momento óptimo para largo."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN CRASHES",
                                   "No hay crashes recientes. Sin punto de referencia de entrada.")

        crash_low  = float(window.loc[last_idx, "low"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        crash_high = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = crash_high - crash_low
        current = float(window["close"].iloc[-1])
        bars_since = len(window) - 1 - last_idx

        recovery_pct = (current - crash_low) / swing * 100 if swing > 0 else 50.0

        # Factor 1: Timing post-crash (mejor en barras 3–15)
        timing_score = 0.0
        if 3 <= bars_since <= 15:
            timing_score = 40.0
        elif bars_since <= 30:
            timing_score = 25.0
        elif bars_since <= 60:
            timing_score = 10.0

        # Factor 2: Posición en el ciclo (mejor entre 10% y 40% de recuperación)
        if 10 <= recovery_pct <= 40:
            position_score = 35.0
        elif recovery_pct <= 10:
            position_score = 20.0  # muy fresco, puede seguir cayendo
        elif recovery_pct <= 60:
            position_score = 20.0
        else:
            position_score = 0.0   # demasiado recuperado, riesgo alto

        # Factor 3: Momentum alcista (RSI en zona moderada-alta)
        post10 = window.iloc[last_idx: last_idx + min(10, bars_since + 1)]
        rsi = _rsi(post10["close"].values, period=min(6, len(post10) - 1)) if len(post10) > 2 else 50.0
        momentum_score = 0.0
        if 45 <= rsi <= 65:
            momentum_score = 25.0
        elif rsi > 65:
            momentum_score = 10.0  # sobrecomprado
        elif rsi >= 35:
            momentum_score = 15.0

        entry_score = round(timing_score + position_score + momentum_score, 1)

        if entry_score >= 70:
            signal = "ENTRADA ÓPTIMA"
            interp = (f"Score: {entry_score}/100. Condiciones ideales para largo post-crash. "
                      f"Timing: {bars_since} barras, Recuperación: {recovery_pct:.1f}%, RSI: {rsi:.0f}.")
        elif entry_score >= 45:
            signal = "ENTRADA ACEPTABLE"
            interp = (f"Score: {entry_score}/100. Condiciones moderadas. "
                      f"Recuperación: {recovery_pct:.1f}%, RSI: {rsi:.0f}. Vigilar riesgo.")
        elif entry_score >= 20:
            signal = "ENTRADA SUBÓPTIMA"
            interp = (f"Score: {entry_score}/100. No es el mejor momento. "
                      f"Esperar mejor configuración post-crash.")
        else:
            signal = "NO ENTRAR"
            interp = (f"Score: {entry_score}/100. Condiciones desfavorables. "
                      f"Demasiado tarde o muy pronto para entrar. Esperar siguiente crash.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=entry_score, signal=signal, interpretation=interp,
            metadata={
                "entry_score": entry_score,
                "bars_since_crash": bars_since,
                "recovery_pct": round(recovery_pct, 2),
                "rsi_post": round(rsi, 1),
                "timing_score": timing_score,
                "position_score": position_score,
                "momentum_score": momentum_score,
            },
        )


@register
class BoomOptimalEntry(AlgorithmBase):
    name = "boom.optimal_entry"
    category = "crash_boom"
    description = "Score de entrada post-boom 0–100. Alto = momento óptimo para corto."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN BOOMS",
                                   "No hay booms recientes. Sin punto de referencia de entrada.")

        boom_high = float(window.loc[last_idx, "high"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        boom_low  = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = boom_high - boom_low
        current = float(window["close"].iloc[-1])
        bars_since = len(window) - 1 - last_idx
        correction_pct = (boom_high - current) / swing * 100 if swing > 0 else 50.0

        timing_score = 0.0
        if 3 <= bars_since <= 15:
            timing_score = 40.0
        elif bars_since <= 30:
            timing_score = 25.0
        elif bars_since <= 60:
            timing_score = 10.0

        if 10 <= correction_pct <= 40:
            position_score = 35.0
        elif correction_pct <= 10:
            position_score = 20.0
        elif correction_pct <= 60:
            position_score = 20.0
        else:
            position_score = 0.0

        post10 = window.iloc[last_idx: last_idx + min(10, bars_since + 1)]
        rsi = _rsi(post10["close"].values, period=min(6, len(post10) - 1)) if len(post10) > 2 else 50.0
        momentum_score = 0.0
        if 35 <= rsi <= 55:
            momentum_score = 25.0
        elif rsi < 35:
            momentum_score = 10.0
        elif rsi <= 65:
            momentum_score = 15.0

        entry_score = round(timing_score + position_score + momentum_score, 1)

        if entry_score >= 70:
            signal = "ENTRADA ÓPTIMA"
            interp = (f"Score: {entry_score}/100. Condiciones ideales para corto post-boom. "
                      f"Timing: {bars_since} barras, Corrección: {correction_pct:.1f}%, RSI: {rsi:.0f}.")
        elif entry_score >= 45:
            signal = "ENTRADA ACEPTABLE"
            interp = (f"Score: {entry_score}/100. Condiciones moderadas para corto. Vigilar riesgo.")
        elif entry_score >= 20:
            signal = "ENTRADA SUBÓPTIMA"
            interp = (f"Score: {entry_score}/100. Esperar mejor configuración post-boom.")
        else:
            signal = "NO ENTRAR"
            interp = (f"Score: {entry_score}/100. Condiciones desfavorables para corto.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=entry_score, signal=signal, interpretation=interp,
            metadata={
                "entry_score": entry_score,
                "bars_since_boom": bars_since,
                "correction_pct": round(correction_pct, 2),
                "rsi_post": round(rsi, 1),
                "timing_score": timing_score,
                "position_score": position_score,
                "momentum_score": momentum_score,
            },
        )
