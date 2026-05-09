"""CRASH #34 — Crash Impact Score.

Tamaño × velocidad del crash → score de impacto (0–100).
Crashes grandes y rápidos generan rebotes más agresivos y
un nuevo drift con más momentum. Crashes pequeños = drift débil.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.post_spike_behavior import _find_last_crash


@register
class CrashImpactScore(AlgorithmBase):
    name = "crash.impact"
    category = "crash_boom"
    description = "Tamaño × velocidad del crash. Score 0–100. Impacto alto = rebote potente esperado."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        spike = window.loc[last_idx]
        # Profundidad: wick inferior (mínimo del crash)
        depth_pts = float(max(spike["open"], spike["close"]) - spike["low"])
        ref_price  = float(spike["open"]) or float(spike["close"])
        depth_pct  = (depth_pts / ref_price * 100) if ref_price else 0.0

        # ATR de las 20 velas anteriores al crash (contexto de mercado)
        pre_seg = window.iloc[max(0, last_idx - 20): last_idx]
        atr_pre = float((pre_seg["high"] - pre_seg["low"]).mean()) if len(pre_seg) > 0 else 1.0

        # Velocidad = profundidad relativa al ATR pre-crash
        speed_ratio = depth_pts / atr_pre if atr_pre else 1.0

        # Score compuesto: normalizado a 0–100
        # depth_pct pondera el tamaño absoluto, speed_ratio pondera la violencia
        raw_score = depth_pct * 10 + min(speed_ratio, 20) * 2.5
        score = min(round(raw_score, 1), 100.0)

        # Histórico de crashes para contexto
        body = (window["close"] - window["open"]).abs()
        threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        wick_all = window["open"].clip(lower=window["close"]) - window["low"]
        spike_mask = wick_all > threshold
        all_depths = wick_all[spike_mask].values
        avg_depth = float(all_depths.mean()) if len(all_depths) > 0 else depth_pts
        relative = depth_pts / avg_depth if avg_depth else 1.0

        if score >= 70:
            signal = "IMPACTO EXTREMO"
            interp = (f"Score de impacto: {score}/100. Crash de {depth_pts:.4f} pts ({depth_pct:.3f}%). "
                      f"{relative:.1f}x el promedio histórico ({avg_depth:.4f} pts). "
                      f"Rebote esperado muy agresivo. Drift reiniciará con fuerza.")
        elif score >= 40:
            signal = "IMPACTO ALTO"
            interp = (f"Score de impacto: {score}/100. Crash de {depth_pts:.4f} pts ({depth_pct:.3f}%). "
                      f"Por encima del promedio ({avg_depth:.4f} pts). Rebote moderado-fuerte esperado.")
        elif score >= 20:
            signal = "IMPACTO MODERADO"
            interp = (f"Score de impacto: {score}/100. Crash de {depth_pts:.4f} pts ({depth_pct:.3f}%). "
                      f"Cerca del promedio histórico. Drift normal esperado.")
        else:
            signal = "IMPACTO BAJO"
            interp = (f"Score de impacto: {score}/100. Crash pequeño ({depth_pts:.4f} pts, {depth_pct:.3f}%). "
                      f"Por debajo del promedio. Rebote débil o lento esperado.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=score, signal=signal, interpretation=interp,
            metadata={
                "impact_score": score,
                "depth_pts": round(depth_pts, 5),
                "depth_pct": round(depth_pct, 4),
                "speed_ratio": round(speed_ratio, 2),
                "avg_depth_historical": round(avg_depth, 5),
                "relative_to_avg": round(relative, 2),
            },
        )
