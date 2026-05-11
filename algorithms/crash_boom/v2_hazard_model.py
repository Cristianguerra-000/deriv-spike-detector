"""v2 · Hazard Model — probabilidad REAL del próximo spike.

Idea humana
───────────
"¿Qué probabilidad hay de que ocurra un spike en las próximas N velas,
SABIENDO que ya pasaron T velas sin que ocurriera?"

Eso se llama HAZARD RATE. NO es la misma probabilidad de toda la vida:
cambia con T. Cuanto más tiempo sin spike, más probable es que ocurra ya.

Dos estimadores complementarios (ambos sobre datos REALES del símbolo):

1) Hazard empírica (no-paramétrica):
   Con los intervalos históricos observados, calcula
       P(spike en próximas N | sin spike hasta T)
   contando directamente cuántos intervalos cayeron en (T, T+N].

2) Hazard Weibull (paramétrica):
   Ajusta Weibull(k, λ) por método de momentos sobre los intervalos.
   Para Crash/Boom típicamente k > 1 (hazard creciente con T).
   Útil cuando hay pocos intervalos para extrapolar.

La probabilidad final reportada es el promedio de ambas (cuando hay datos),
acotada a [0, 99] %. NUNCA inventamos: si no hay >= 5 intervalos reales,
devolvemos "DATOS INSUFICIENTES".
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.v2_spike_state import get_state


# ─── Estimador empírico ──────────────────────────────────────────────────────
def empirical_hazard(intervals: Iterable[int], t: int, n: int) -> float:
    """P(spike en (t, t+n] | sin spike hasta t) por conteo directo."""
    arr = np.asarray(list(intervals), dtype=int)
    if arr.size < 5:
        return float("nan")
    at_risk = arr[arr > t]
    if at_risk.size == 0:
        return float("nan")
    events = at_risk[at_risk <= t + n].size
    return events / at_risk.size


# ─── Estimador Weibull ───────────────────────────────────────────────────────
def _weibull_fit_mom(intervals: Iterable[int]) -> tuple[float, float] | None:
    """Ajuste Weibull(k, λ) por método de momentos. Retorna (k, lam) o None."""
    arr = np.asarray(list(intervals), dtype=float)
    if arr.size < 5:
        return None
    mean = float(arr.mean())
    std = float(arr.std(ddof=1))
    if mean <= 0 or std <= 0:
        return None
    cv = std / mean  # coeficiente de variación
    # Aproximación cerrada: k ≈ cv^(-1.086) (Justus et al.)
    k = float(cv ** -1.086)
    k = max(0.5, min(k, 5.0))   # acotar a rango sano
    lam = mean / math.gamma(1.0 + 1.0 / k)
    return k, lam


def weibull_hazard(intervals: Iterable[int], t: int, n: int) -> float:
    """P(T ≤ t+n | T > t) bajo Weibull(k, λ)."""
    fit = _weibull_fit_mom(intervals)
    if fit is None:
        return float("nan")
    k, lam = fit
    if lam <= 0 or t < 0:
        return float("nan")
    # S(t) = exp(-(t/λ)^k)
    s_t = math.exp(-((t / lam) ** k))
    s_tn = math.exp(-(((t + n) / lam) ** k))
    if s_t <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - s_tn / s_t))


# ─── API unificada ───────────────────────────────────────────────────────────
def prob_spike(intervals: Iterable[int], bars_since: int, horizon: int) -> dict:
    """Probabilidad combinada del próximo spike. Devuelve dict completo y honesto."""
    arr = list(intervals)
    if len(arr) < 5 or bars_since < 0:
        return {"p": None, "empirical": None, "weibull": None, "samples": len(arr)}

    p_emp = empirical_hazard(arr, bars_since, horizon)
    p_wb = weibull_hazard(arr, bars_since, horizon)

    values = [v for v in (p_emp, p_wb) if isinstance(v, float) and not math.isnan(v)]
    if not values:
        return {"p": None, "empirical": p_emp, "weibull": p_wb, "samples": len(arr)}
    p = sum(values) / len(values)
    return {
        "p": round(min(p, 0.99), 4),
        "empirical": None if math.isnan(p_emp) else round(p_emp, 4),
        "weibull": None if math.isnan(p_wb) else round(p_wb, 4),
        "samples": len(arr),
    }


@register
class HazardModelAlgo(AlgorithmBase):
    name = "cb.v2.hazard"
    category = "crash_boom"
    description = "Probabilidad REAL del próximo spike (empírica + Weibull)."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sym = symbol.upper()
        if "CRASH" not in sym and "BOOM" not in sym:
            return AlgorithmResult(self.name, symbol, None, "N/A", "Sólo Crash/Boom.")

        state = get_state(symbol)
        if len(state.intervals) < 5 or state.last_spike_idx is None:
            return AlgorithmResult(
                self.name, symbol, None, "DATOS INSUFICIENTES",
                f"Sólo {len(state.intervals)} intervalos observados; se necesitan ≥ 5 para "
                "estimar probabilidades reales. Sin inventos.",
                metadata={"samples": len(state.intervals)},
            )

        bars_since = (len(df) - 1) - state.last_spike_idx
        bars_since = max(0, bars_since)

        p10 = prob_spike(state.intervals, bars_since, 10)
        p20 = prob_spike(state.intervals, bars_since, 20)
        p50 = prob_spike(state.intervals, bars_since, 50)

        p_main = p10["p"] or 0.0
        if p_main >= 0.60:
            signal = "SPIKE MUY PROBABLE"
        elif p_main >= 0.35:
            signal = "SPIKE PROBABLE"
        elif p_main >= 0.15:
            signal = "SPIKE POSIBLE"
        else:
            signal = "SPIKE LEJANO"

        interp = (
            f"Probabilidad real del próximo spike: "
            f"{p10['p']*100:.1f}% en 10 velas, "
            f"{(p20['p'] or 0)*100:.1f}% en 20, "
            f"{(p50['p'] or 0)*100:.1f}% en 50. "
            f"Calculado con {p10['samples']} intervalos observados. "
            f"Han pasado {bars_since} velas desde el último spike."
        )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(p_main * 100, 1), signal=signal, interpretation=interp,
            metadata={
                "bars_since_spike": bars_since,
                "samples": p10["samples"],
                "p10": p10, "p20": p20, "p50": p50,
            },
        )
