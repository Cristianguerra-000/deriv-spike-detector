"""CRASH #46 / BOOM #46 — Cycle Phase.

Clasifica en qué fase del ciclo de drift se encuentra el mercado:
  INICIO DRIFT   → 0–25% de recuperación/corrección post-spike
  DRIFT ACTIVO   → 25–70% del ciclo completado
  DRIFT MADURO   → 70–90% completado (zona de precaución)
  ZONA CRÍTICA   → >90% del ciclo (spike inminente)

El "ciclo" se mide entre el último spike y el siguiente estimado,
usando la distancia recorrida desde el mínimo/máximo del spike.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom


@register
class CrashCyclePhase(AlgorithmBase):
    name = "crash.cycle_phase"
    category = "crash_boom"
    description = "Fase del ciclo CRASH: INICIO / ACTIVO / MADURO / CRÍTICO."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN DATOS",
                                   "No hay crashes recientes para calcular la fase del ciclo.")

        crash_low  = float(window.loc[last_idx, "low"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        crash_high = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = crash_high - crash_low
        current = float(window["close"].iloc[-1])
        bars_since = len(window) - 1 - last_idx

        # Progreso del ciclo: 0% = precio en el mínimo, 100% = precio recuperó el nivel pre-crash
        cycle_pct = (current - crash_low) / swing * 100 if swing > 0 else 0.0
        cycle_pct = max(0.0, min(cycle_pct, 100.0))

        # Factor tiempo: cuánto del intervalo típico ha transcurrido
        # Usar duración histórica media entre crashes como referencia
        from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
        body = (window["close"] - window["open"]).abs()
        threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        lower_wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_mask = lower_wick > threshold
        spike_idxs = [i for i in range(len(window)) if spike_mask.iloc[i]]

        if len(spike_idxs) >= 2:
            intervals = [spike_idxs[i + 1] - spike_idxs[i] for i in range(len(spike_idxs) - 1)]
            avg_interval = float(np.mean(intervals))
            time_pct = min(bars_since / avg_interval * 100, 100.0) if avg_interval > 0 else 50.0
        else:
            time_pct = 50.0
            avg_interval = None

        # Fase compuesta: precio + tiempo
        combined = cycle_pct * 0.6 + time_pct * 0.4

        if combined >= 90:
            phase = "ZONA CRÍTICA"
            interp = (f"Ciclo {combined:.0f}% completado. Precio recuperó {cycle_pct:.1f}% del swing. "
                      f"Tiempo: {bars_since} barras ({time_pct:.0f}% del intervalo medio). "
                      f"CRASH INMINENTE. Máximo riesgo para largos.")
        elif combined >= 70:
            phase = "DRIFT MADURO"
            interp = (f"Ciclo {combined:.0f}% completado. Precio recuperó {cycle_pct:.1f}%. "
                      f"Fase de madurez. Reducir exposición en largos. Monitorear tensión.")
        elif combined >= 25:
            phase = "DRIFT ACTIVO"
            interp = (f"Ciclo {combined:.0f}% completado. Precio recuperó {cycle_pct:.1f}%. "
                      f"Drift alcista en plena actividad. Condiciones favorables.")
        else:
            phase = "INICIO DRIFT"
            interp = (f"Ciclo {combined:.0f}% completado. {bars_since} barras post-crash. "
                      f"Precio recuperó {cycle_pct:.1f}%. Inicio del drift. Momento óptimo de entrada.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(combined, 1), signal=phase, interpretation=interp,
            metadata={
                "cycle_pct_combined": round(combined, 1),
                "price_recovery_pct": round(cycle_pct, 2),
                "time_elapsed_pct": round(time_pct, 2),
                "bars_since_crash": bars_since,
                "avg_interval_bars": round(avg_interval, 1) if avg_interval else None,
            },
        )


@register
class BoomCyclePhase(AlgorithmBase):
    name = "boom.cycle_phase"
    category = "crash_boom"
    description = "Fase del ciclo BOOM: INICIO / ACTIVO / MADURO / CRÍTICO."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN DATOS",
                                   "No hay booms recientes para calcular la fase del ciclo.")

        boom_high = float(window.loc[last_idx, "high"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        boom_low  = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = boom_high - boom_low
        current = float(window["close"].iloc[-1])
        bars_since = len(window) - 1 - last_idx

        cycle_pct = (boom_high - current) / swing * 100 if swing > 0 else 0.0
        cycle_pct = max(0.0, min(cycle_pct, 100.0))

        from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
        body = (window["close"] - window["open"]).abs()
        threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        upper_wick = window["high"] - window[["open", "close"]].max(axis=1)
        spike_mask = upper_wick > threshold
        spike_idxs = [i for i in range(len(window)) if spike_mask.iloc[i]]

        if len(spike_idxs) >= 2:
            intervals = [spike_idxs[i + 1] - spike_idxs[i] for i in range(len(spike_idxs) - 1)]
            avg_interval = float(np.mean(intervals))
            time_pct = min(bars_since / avg_interval * 100, 100.0) if avg_interval > 0 else 50.0
        else:
            time_pct = 50.0
            avg_interval = None

        combined = cycle_pct * 0.6 + time_pct * 0.4

        if combined >= 90:
            phase = "ZONA CRÍTICA"
            interp = (f"Ciclo {combined:.0f}% completado. Precio corrigió {cycle_pct:.1f}% del swing. "
                      f"BOOM INMINENTE. Máximo riesgo para cortos.")
        elif combined >= 70:
            phase = "DRIFT MADURO"
            interp = (f"Ciclo {combined:.0f}% completado. Precio corrigió {cycle_pct:.1f}%. "
                      f"Fase de madurez. Reducir exposición en cortos.")
        elif combined >= 25:
            phase = "DRIFT ACTIVO"
            interp = (f"Ciclo {combined:.0f}% completado. Drift bajista activo. Condiciones favorables.")
        else:
            phase = "INICIO DRIFT"
            interp = (f"Ciclo {combined:.0f}% completado. {bars_since} barras post-boom. "
                      f"Inicio del drift bajista. Momento óptimo de entrada en cortos.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(combined, 1), signal=phase, interpretation=interp,
            metadata={
                "cycle_pct_combined": round(combined, 1),
                "price_correction_pct": round(cycle_pct, 2),
                "time_elapsed_pct": round(time_pct, 2),
                "bars_since_boom": bars_since,
                "avg_interval_bars": round(avg_interval, 1) if avg_interval else None,
            },
        )
