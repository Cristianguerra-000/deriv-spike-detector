"""RSI — Relative Strength Index.

Mide la velocidad y magnitud de los cambios de precio.
Identifica condiciones de sobrecompra (>70) y sobreventa (<30).
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class RSI(AlgorithmBase):
    name = "trend.rsi"
    category = "trend"
    description = "RSI: identifica sobrecompra, sobreventa y momentum del precio."

    def __init__(self, period: int = 14) -> None:
        self.period = period

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(self.period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.period).mean()

        rs = gain / loss.replace(0, float("nan"))
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = float(rsi_series.iloc[-1])
        rsi_prev = float(rsi_series.iloc[-2]) if len(rsi_series) > 1 else rsi_val
        direction = "subiendo" if rsi_val > rsi_prev else "bajando"

        if rsi_val >= 80:
            signal = "SOBRECOMPRA EXTREMA"
            interp = (
                f"RSI = {rsi_val:.1f} → ZONA DE SOBRECOMPRA EXTREMA (≥80). "
                f"El activo ha subido demasiado rápido. Alta probabilidad de corrección inminente o reversión bajista. "
                f"Evitar compras nuevas, considerar salida de largos."
            )
        elif rsi_val >= 70:
            signal = "SOBRECOMPRADO"
            interp = (
                f"RSI = {rsi_val:.1f} → SOBRECOMPRA (≥70), {direction}. "
                f"Compradores en control pero el mercado está agotado. "
                f"Posible corrección o consolidación próxima antes de continuar."
            )
        elif rsi_val <= 20:
            signal = "SOBREVENTA EXTREMA"
            interp = (
                f"RSI = {rsi_val:.1f} → ZONA DE SOBREVENTA EXTREMA (≤20). "
                f"El activo ha caído demasiado rápido. Alta probabilidad de rebote técnico inminente. "
                f"Zona de oportunidad para largos con gestión de riesgo."
            )
        elif rsi_val <= 30:
            signal = "SOBREVENDIDO"
            interp = (
                f"RSI = {rsi_val:.1f} → SOBREVENTA (≤30), {direction}. "
                f"Vendedores en control pero el mercado está agotado. "
                f"Monitorear señales de rebote o reversión alcista."
            )
        elif rsi_val >= 55:
            signal = "ALCISTA"
            interp = (
                f"RSI = {rsi_val:.1f} → Momentum ALCISTA activo, {direction}. "
                f"Los compradores dominan sin llegar a sobrecompra. "
                f"Zona saludable para estrategias de seguimiento de tendencia al alza."
            )
        elif rsi_val <= 45:
            signal = "BAJISTA"
            interp = (
                f"RSI = {rsi_val:.1f} → Momentum BAJISTA activo, {direction}. "
                f"Los vendedores dominan sin llegar a sobreventa. "
                f"Zona desfavorable para compras, favorable para cortos controlados."
            )
        else:
            signal = "NEUTRO"
            interp = (
                f"RSI = {rsi_val:.1f} → Zona NEUTRAL (45-55), {direction}. "
                f"Mercado en equilibrio entre compradores y vendedores. "
                f"Sin dirección clara, esperar confirmación antes de tomar posición."
            )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(rsi_val, 2),
            signal=signal,
            interpretation=interp,
            metadata={"period": self.period, "rsi_prev": round(rsi_prev, 2)},
        )
