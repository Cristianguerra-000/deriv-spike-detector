"""Autocorrelación de retornos.

Mide si los retornos (cambios porcentuales) tienen inercia serial.
Autocorrelación positiva → momentum (retornos se repiten).
Autocorrelación negativa → reversión (retornos se alternan).
≈ 0 → comportamiento aleatorio (sin patrón serial).
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class ReturnAutocorrelation(AlgorithmBase):
    name = "stat.autocorrelation"
    category = "statistical"
    description = "Autocorrelación de retornos: detecta inercia, reversión o aleatoriedad serial."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        returns = df["close"].pct_change().dropna()

        if len(returns) < 20:
            return AlgorithmResult(
                algorithm=self.name, symbol=symbol, value=None,
                signal="INSUFICIENTE", interpretation="Se necesitan al menos 20 retornos.",
            )

        ac1 = float(returns.autocorr(lag=1))
        ac5 = float(returns.autocorr(lag=5))

        if ac1 > 0.2:
            signal = "MOMENTUM FUERTE"
            interp = (
                f"Autocorrelación(lag-1) = {ac1:.3f} → FUERTE INERCIA SERIAL POSITIVA. "
                f"Los retornos tienden a REPETIRSE barra a barra. "
                f"El mercado tiene momentum: un movimiento al alza tiende a seguirse de otro alza. "
                f"Lag-5 = {ac5:.3f}."
            )
        elif ac1 > 0.1:
            signal = "MOMENTUM LEVE"
            interp = (
                f"Autocorrelación(lag-1) = {ac1:.3f} → Leve inercia positiva. "
                f"Los retornos se repiten con cierta consistencia. "
                f"Tendencia débil pero estadísticamente detectable. Lag-5 = {ac5:.3f}."
            )
        elif ac1 < -0.2:
            signal = "REVERSIÓN FUERTE"
            interp = (
                f"Autocorrelación(lag-1) = {ac1:.3f} → FUERTE REVERSIÓN SERIAL. "
                f"Los retornos tienden a INVERTIRSE cada barra (alza→baja→alza). "
                f"Mercado oscilante: ideal para scalping contra la última vela. Lag-5 = {ac5:.3f}."
            )
        elif ac1 < -0.1:
            signal = "REVERSIÓN LEVE"
            interp = (
                f"Autocorrelación(lag-1) = {ac1:.3f} → Leve tendencia a revertir. "
                f"Los retornos se alternan con cierta consistencia. "
                f"Estrategias de contra-tendencia de corto plazo tienen ligera ventaja. Lag-5 = {ac5:.3f}."
            )
        else:
            signal = "ALEATORIO"
            interp = (
                f"Autocorrelación(lag-1) = {ac1:.3f} ≈ 0 → Sin patrón serial claro. "
                f"Los retornos son prácticamente independientes entre sí. "
                f"Comportamiento cercano al ruido blanco. Ni momentum ni reversión tienen ventaja. "
                f"Lag-5 = {ac5:.3f}."
            )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(ac1, 4),
            signal=signal,
            interpretation=interp,
            metadata={"autocorr_lag1": round(ac1, 4), "autocorr_lag5": round(ac5, 4)},
        )
