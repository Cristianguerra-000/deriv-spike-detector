"""CRASH #36 — Volume Proxy (Post-Crash).

Sin volumen real en Deriv Crash/Boom. Usa el tamaño del cuerpo
de las velas como proxy de actividad/presión.
Cuerpos grandes post-crash = alta actividad = drift fuerte.
Cuerpos pequeños = mercado indeciso.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash


@register
class CrashVolProxy(AlgorithmBase):
    name = "crash.vol_proxy"
    category = "crash_boom"
    description = "Cuerpos de velas post-crash como proxy de actividad. Alto = drift activo."

    POST_WINDOW = 10

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        # Tamaño de cuerpo como proxy de volumen
        body = (window["close"] - window["open"]).abs()
        # Baseline: mediana histórica de cuerpos (últimas 100 velas antes del crash)
        baseline_seg = window.iloc[max(0, last_idx - 100): last_idx]
        baseline = float(baseline_seg["close"].sub(baseline_seg["open"]).abs().median()) if len(baseline_seg) > 0 else 0.0

        post = window.iloc[last_idx + 1: last_idx + 1 + self.POST_WINDOW]
        if len(post) == 0:
            return AlgorithmResult(self.name, symbol, None, "SIN POST-CRASH", "Sin datos post-crash.")

        post_body = (post["close"] - post["open"]).abs()
        avg_post   = float(post_body.mean())
        ratio      = avg_post / baseline if baseline > 0 else 1.0

        # Dirección dominante
        bull_bodies = float((post["close"] > post["open"]).sum())
        bull_pct    = bull_bodies / len(post) * 100

        if ratio >= 1.5 and bull_pct >= 60:
            signal = "ACTIVIDAD ALCISTA ALTA"
            interp = (f"Cuerpos post-crash {ratio:.1f}x el promedio histórico. "
                      f"{bull_pct:.0f}% de velas alcistas. Fuerte presión compradora, drift activo.")
        elif ratio >= 1.2:
            signal = "ACTIVIDAD MODERADA"
            interp = (f"Cuerpos {ratio:.1f}x el promedio. Actividad moderada post-crash. "
                      f"Drift formándose sin presión extrema.")
        elif ratio >= 0.8:
            signal = "ACTIVIDAD NORMAL"
            interp = (f"Cuerpos {ratio:.1f}x el promedio. Mercado en modo normal post-crash. "
                      f"Esperar confirmación de dirección.")
        else:
            signal = "ACTIVIDAD BAJA"
            interp = (f"Cuerpos solo {ratio:.1f}x el promedio. Mercado letárgico post-crash. "
                      f"Drift lento o consolidación lateral probable.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(ratio, 3), signal=signal, interpretation=interp,
            metadata={
                "body_ratio_vs_baseline": round(ratio, 3),
                "avg_post_body": round(avg_post, 5),
                "baseline_body": round(baseline, 5),
                "bull_pct": round(bull_pct, 1),
                "bars_analyzed": len(post),
            },
        )


@register
class BoomVolProxy(AlgorithmBase):
    name = "boom.vol_proxy"
    category = "crash_boom"
    description = "Cuerpos de velas post-boom como proxy de actividad. Alto = drift activo."

    POST_WINDOW = 10

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        from algorithms.crash_boom.post_boom_behavior import _find_last_boom
        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        baseline_seg = window.iloc[max(0, last_idx - 100): last_idx]
        baseline = float(baseline_seg["close"].sub(baseline_seg["open"]).abs().median()) if len(baseline_seg) > 0 else 0.0

        post = window.iloc[last_idx + 1: last_idx + 1 + self.POST_WINDOW]
        if len(post) == 0:
            return AlgorithmResult(self.name, symbol, None, "SIN POST-BOOM", "Sin datos post-boom.")

        post_body = (post["close"] - post["open"]).abs()
        avg_post  = float(post_body.mean())
        ratio     = avg_post / baseline if baseline > 0 else 1.0

        bear_bodies = float((post["close"] < post["open"]).sum())
        bear_pct    = bear_bodies / len(post) * 100

        if ratio >= 1.5 and bear_pct >= 60:
            signal = "ACTIVIDAD BAJISTA ALTA"
            interp = (f"Cuerpos post-boom {ratio:.1f}x el promedio histórico. "
                      f"{bear_pct:.0f}% de velas bajistas. Fuerte presión vendedora, corrección activa.")
        elif ratio >= 1.2:
            signal = "ACTIVIDAD MODERADA"
            interp = (f"Cuerpos {ratio:.1f}x el promedio. Actividad moderada post-boom. "
                      f"Corrección formándose sin presión extrema.")
        elif ratio >= 0.8:
            signal = "ACTIVIDAD NORMAL"
            interp = (f"Cuerpos {ratio:.1f}x el promedio. Mercado en modo normal post-boom.")
        else:
            signal = "ACTIVIDAD BAJA"
            interp = (f"Cuerpos solo {ratio:.1f}x el promedio. Mercado letárgico post-boom. "
                      f"Corrección lenta o nuevo boom posible.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(ratio, 3), signal=signal, interpretation=interp,
            metadata={
                "body_ratio_vs_baseline": round(ratio, 3),
                "avg_post_body": round(avg_post, 5),
                "baseline_body": round(baseline, 5),
                "bear_pct": round(bear_pct, 1),
                "bars_analyzed": len(post),
            },
        )
