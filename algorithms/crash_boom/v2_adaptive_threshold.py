"""v2 · Adaptive Threshold — umbral MAD-robusto, recalibrado en cada spike.

Idea humana
───────────
El detector viejo usaba `body.quantile(0.75) * 6.0`. Problema:
los propios spikes inflaban el percentil y dejaban de detectarse los siguientes.

Aquí usamos MAD (Median Absolute Deviation) sobre las WICKS extremas,
que es robusto a outliers (los spikes mismos no contaminan la mediana).

Fórmula:
    median_wick = mediana(wicks)
    mad         = mediana(|wick - median_wick|)
    threshold   = median_wick + k * 1.4826 * mad      (k=4 por defecto)

El 1.4826 convierte MAD en estimador consistente de desviación estándar
para distribución normal. Un spike es por definición >> 4·σ.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


K_SIGMA = 4.0   # un spike = > 4σ por encima de la mediana de wicks


def _wick_series(df: pd.DataFrame, side: str) -> pd.Series:
    if side == "crash":
        body_top = df[["open", "close"]].max(axis=1)
        return body_top - df["low"]
    else:  # boom
        body_top = df[["open", "close"]].max(axis=1)
        return df["high"] - body_top


def robust_threshold(df: pd.DataFrame, side: str, lookback: int = 500) -> float:
    """Umbral MAD-robusto en puntos absolutos para detectar wicks tipo spike."""
    window = df.tail(lookback)
    wicks = _wick_series(window, side).dropna()
    if len(wicks) < 30:
        return float(wicks.max()) if len(wicks) else 0.0
    med = float(wicks.median())
    mad = float((wicks - med).abs().median())
    if mad <= 0:
        # Fallback al percentil si MAD se anula (datos casi constantes)
        return float(wicks.quantile(0.99))
    return med + K_SIGMA * 1.4826 * mad


@register
class AdaptiveThresholdAlgo(AlgorithmBase):
    name = "cb.v2.threshold"
    category = "crash_boom"
    description = "Umbral MAD-robusto para spikes (recalibrado en cada vela)."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sym = symbol.upper()
        side = "crash" if "CRASH" in sym else ("boom" if "BOOM" in sym else None)
        if side is None:
            return AlgorithmResult(self.name, symbol, None, "N/A",
                                   "Sólo Crash/Boom.")
        if len(df) < 50:
            return AlgorithmResult(self.name, symbol, None, "SIN DATOS",
                                   "Se necesitan al menos 50 velas.")

        thr = robust_threshold(df, side)
        wicks = _wick_series(df.tail(500), side)
        last_wick = float(wicks.iloc[-1])
        ratio = last_wick / thr if thr > 0 else 0.0

        if ratio >= 1.0:
            signal = "WICK DE SPIKE"
            interp = (f"La wick {('inferior' if side=='crash' else 'superior')} "
                      f"de la última vela ({last_wick:.2f} pts) supera el umbral "
                      f"robusto ({thr:.2f} pts). Es {ratio:.1f}× el umbral.")
        elif ratio >= 0.6:
            signal = "WICK ELEVADA"
            interp = (f"Wick {last_wick:.2f} pts vs umbral {thr:.2f}. "
                      f"No es spike, pero hay tensión.")
        else:
            signal = "NORMAL"
            interp = (f"Wick {last_wick:.2f} pts vs umbral {thr:.2f}. "
                      f"Mercado en comportamiento normal.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(thr, 4), signal=signal, interpretation=interp,
            metadata={
                "threshold_pts": round(thr, 4),
                "last_wick_pts": round(last_wick, 4),
                "ratio": round(ratio, 3),
                "side": side,
                "k_sigma": K_SIGMA,
            },
        )
