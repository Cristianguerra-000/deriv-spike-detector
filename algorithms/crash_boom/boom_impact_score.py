"""BOOM #34 — Boom Impact Score.

Tamaño × velocidad del boom → score de impacto (0–100).
Booms grandes y rápidos generan correcciones más profundas y
un nuevo drift bajista con más momentum.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.post_boom_behavior import _find_last_boom


@register
class BoomImpactScore(AlgorithmBase):
    name = "boom.impact"
    category = "crash_boom"
    description = "Tamaño × velocidad del boom. Score 0–100. Impacto alto = corrección potente esperada."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        spike = window.loc[last_idx]
        # Altura: wick superior del boom
        height_pts = float(spike["high"] - max(spike["open"], spike["close"]))
        ref_price   = float(spike["open"]) or float(spike["close"])
        height_pct  = (height_pts / ref_price * 100) if ref_price else 0.0

        # ATR de las 20 velas anteriores al boom (contexto)
        pre_seg = window.iloc[max(0, last_idx - 20): last_idx]
        atr_pre = float((pre_seg["high"] - pre_seg["low"]).mean()) if len(pre_seg) > 0 else 1.0

        speed_ratio = height_pts / atr_pre if atr_pre else 1.0

        raw_score = height_pct * 10 + min(speed_ratio, 20) * 2.5
        score = min(round(raw_score, 1), 100.0)

        body = (window["close"] - window["open"]).abs()
        threshold = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        wick_all = window["high"] - window[["open", "close"]].max(axis=1)
        spike_mask = wick_all > threshold
        all_heights = wick_all[spike_mask].values
        avg_height = float(all_heights.mean()) if len(all_heights) > 0 else height_pts
        relative = height_pts / avg_height if avg_height else 1.0

        if score >= 70:
            signal = "IMPACTO EXTREMO"
            interp = (f"Score de impacto: {score}/100. Boom de {height_pts:.4f} pts ({height_pct:.3f}%). "
                      f"{relative:.1f}x el promedio histórico ({avg_height:.4f} pts). "
                      f"Corrección bajista muy agresiva esperada.")
        elif score >= 40:
            signal = "IMPACTO ALTO"
            interp = (f"Score de impacto: {score}/100. Boom de {height_pts:.4f} pts ({height_pct:.3f}%). "
                      f"Por encima del promedio ({avg_height:.4f} pts). Corrección moderada-fuerte esperada.")
        elif score >= 20:
            signal = "IMPACTO MODERADO"
            interp = (f"Score de impacto: {score}/100. Boom de {height_pts:.4f} pts ({height_pct:.3f}%). "
                      f"Cerca del promedio histórico. Drift bajista normal esperado.")
        else:
            signal = "IMPACTO BAJO"
            interp = (f"Score de impacto: {score}/100. Boom pequeño ({height_pts:.4f} pts, {height_pct:.3f}%). "
                      f"Por debajo del promedio. Corrección leve o lenta esperada.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=score, signal=signal, interpretation=interp,
            metadata={
                "impact_score": score,
                "height_pts": round(height_pts, 5),
                "height_pct": round(height_pct, 4),
                "speed_ratio": round(speed_ratio, 2),
                "avg_height_historical": round(avg_height, 5),
                "relative_to_avg": round(relative, 2),
            },
        )
