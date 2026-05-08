"""CRASH #19 — Recovery Trajectory.

Analiza el rebote inmediato post-crash: velocidad de recuperación
y ángulo en las primeras N velas después de un crash.

Rebote rápido = el mercado vuelve a subir agresivamente = nuevo drift activo.
Rebote lento = posible debilidad o doble crash próximo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashRecoveryTrajectory(AlgorithmBase):
    name = "crash.recovery_traj"
    category = "crash_boom"
    description = "Velocidad y ángulo del rebote post-crash. Rápido = nuevo drift activo."

    def __init__(self, recovery_window: int = 20) -> None:
        self.recovery_window = recovery_window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(200).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_positions = wick[wick > threshold].index.tolist()

        if not spike_positions:
            return AlgorithmResult(
                self.name, symbol, 0.0, "SIN CRASHES",
                "No se encontraron crashes en las últimas 200 velas.",
            )

        last_spike_idx = spike_positions[-1]
        recovery_seg = window.iloc[last_spike_idx + 1: last_spike_idx + 1 + self.recovery_window]

        if len(recovery_seg) < 4:
            return AlgorithmResult(
                self.name, symbol, 0.0, "RECUPERACIÓN ACTIVA",
                f"El crash fue muy reciente (hace {len(window) - 1 - last_spike_idx} velas). "
                f"La recuperación está en curso.",
            )

        crash_low = float(window.iloc[last_spike_idx]["low"])
        crash_open = float(window.iloc[last_spike_idx]["open"])
        recovery_prices = recovery_seg["close"].values

        x = np.arange(len(recovery_prices))
        slope, _, r_value, _, _ = stats.linregress(x, recovery_prices)
        price_mean = float(np.mean(recovery_prices))
        slope_pct = (slope / price_mean * 100) if price_mean else 0

        # % recuperado
        current_price = float(recovery_prices[-1])
        crash_drop = crash_open - crash_low
        recovered = max(0, current_price - crash_low)
        recovery_pct = (recovered / crash_drop * 100) if crash_drop > 0 else 100.0

        if slope_pct > 0.15 and r_value > 0.7:
            signal = "REBOTE FUERTE"
            interp = (
                f"Recuperación post-crash RÁPIDA y LINEAL: {slope_pct:+.4f}%/vela (R²={r_value**2:.3f}). "
                f"Precio recuperó {recovery_pct:.1f}% del crash en {len(recovery_seg)} velas. "
                f"El nuevo drift alcista se estableció sólidamente."
            )
        elif slope_pct > 0.05:
            signal = "REBOTE MODERADO"
            interp = (
                f"Recuperación gradual: {slope_pct:+.4f}%/vela. "
                f"Recuperó {recovery_pct:.1f}% del crash en {len(recovery_seg)} velas. "
                f"Drift re-estableciéndose a ritmo normal."
            )
        elif slope_pct < -0.05:
            signal = "REBOTE FALLIDO"
            interp = (
                f"⚠️ El precio SIGUE BAJANDO post-crash: {slope_pct:+.4f}%/vela. "
                f"Recuperado solo {recovery_pct:.1f}%. "
                f"Posible doble crash o debilidad estructural. Alto riesgo."
            )
        else:
            signal = "REBOTE PLANO"
            interp = (
                f"El precio está plano post-crash: {slope_pct:+.4f}%/vela. "
                f"Recuperado: {recovery_pct:.1f}%. "
                f"Consolidación. El drift aún no se estableció."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(recovery_pct, 2), signal=signal, interpretation=interp,
            metadata={
                "recovery_pct": round(recovery_pct, 2),
                "recovery_slope_pct": round(slope_pct, 6),
                "r_squared": round(r_value ** 2, 4),
                "recovery_bars": len(recovery_seg),
                "bars_since_crash": len(window) - 1 - last_spike_idx,
            },
        )
