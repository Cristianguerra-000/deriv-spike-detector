"""CRASH #32 — Crash Retracement Levels.

Calcula niveles de retroceso Fibonacci desde el último crash.
Precio mínimo del crash = 0%, precio pre-crash = 100%.
Los niveles actúan como soporte/resistencia durante el rebote y el drift.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash

FIB_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


@register
class CrashRetracementLevels(AlgorithmBase):
    name = "crash.retracement"
    category = "crash_boom"
    description = "Niveles Fibonacci del crash. Indica en qué zona Fibonacci está el precio actual."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        crash_low  = float(window.loc[last_idx, "low"])
        # Precio de referencia pre-crash: máximo de las 20 velas anteriores
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        crash_high = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        current = float(window["close"].iloc[-1])

        swing = crash_high - crash_low
        if swing <= 0:
            return AlgorithmResult(self.name, symbol, None, "SWING INVÁLIDO",
                                   "El rango del crash es demasiado pequeño para calcular Fibonacci.")

        # Niveles Fib: el precio sube desde el mínimo (retroceso alcista)
        levels = {f"fib_{int(r*1000):04d}": round(crash_low + r * swing, 5) for r in FIB_RATIOS}

        # ¿En qué zona Fibonacci está el precio actual?
        retracement_pct = (current - crash_low) / swing * 100

        if retracement_pct >= 100:
            zone = "SOBRE 100%"
            signal = "DRIFT PLENO"
            interp = (f"Precio ({current:.5f}) superó el nivel pre-crash ({crash_high:.5f}). "
                      f"Retroceso: {retracement_pct:.1f}%. Drift alcista completamente restablecido.")
        elif retracement_pct >= 78.6:
            zone = "78.6% – 100%"
            signal = "RECUPERACIÓN ALTA"
            interp = (f"Retroceso del {retracement_pct:.1f}%. Precio cerca del nivel pre-crash. "
                      f"Zona de resistencia. La tensión pre-crash comienza a acumularse de nuevo.")
        elif retracement_pct >= 61.8:
            zone = "61.8% – 78.6%"
            signal = "RECUPERACIÓN MODERADA"
            interp = (f"Retroceso del {retracement_pct:.1f}%. Entre Fib 61.8 y 78.6. "
                      f"Zona de equilibrio del drift. Sin presión extrema aún.")
        elif retracement_pct >= 38.2:
            zone = "38.2% – 61.8%"
            signal = "REBOTE MEDIO"
            interp = (f"Retroceso del {retracement_pct:.1f}%. Entre Fib 38.2 y 61.8. "
                      f"El precio aún está en la zona baja del rango crash-precrash. "
                      f"Drift alcista en etapa inicial.")
        elif retracement_pct >= 23.6:
            zone = "23.6% – 38.2%"
            signal = "REBOTE BAJO"
            interp = (f"Retroceso del {retracement_pct:.1f}%. Muy cerca del mínimo del crash. "
                      f"El precio apenas despegó. Riesgo de caída de vuelta al mínimo.")
        else:
            zone = "0% – 23.6%"
            signal = "ZONA DE MÍNIMO"
            interp = (f"Retroceso del {retracement_pct:.1f}%. El precio está casi en el mínimo del crash. "
                      f"Alta volatilidad post-crash. Zona de máxima incertidumbre.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(retracement_pct, 2), signal=signal, interpretation=interp,
            metadata={
                "retracement_pct": round(retracement_pct, 2),
                "zone": zone,
                "crash_low": crash_low,
                "crash_high": crash_high,
                "current_price": current,
                **levels,
            },
        )
