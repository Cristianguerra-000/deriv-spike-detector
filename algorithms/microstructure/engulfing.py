"""Patrón de Vela Envolvente (Engulfing).

Uno de los patrones de reversión más fiables en análisis técnico.
Una vela envolvente ALCISTA: vela bajista seguida de vela alcista que la absorbe completamente.
Una vela envolvente BAJISTA: vela alcista seguida de vela bajista que la absorbe completamente.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class EngulfingPattern(AlgorithmBase):
    name = "micro.engulfing"
    category = "microstructure"
    description = "Engulfing: detecta patrones de vela envolvente alcista o bajista (señal de reversión)."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        # Buscar en las últimas 4 barras
        for i in range(-1, -5, -1):
            if abs(i) + 1 >= len(df):
                break

            curr = df.iloc[i]
            prev = df.iloc[i - 1]
            bars_ago = abs(i)

            curr_bull = curr["close"] > curr["open"]
            curr_bear = curr["close"] < curr["open"]
            prev_bull = prev["close"] > prev["open"]
            prev_bear = prev["close"] < prev["open"]

            # Envolvente alcista: previa bajista + actual alcista que absorbe
            if prev_bear and curr_bull:
                if curr["open"] <= prev["close"] and curr["close"] >= prev["open"]:
                    body_ratio = abs(curr["close"] - curr["open"]) / max(
                        abs(prev["close"] - prev["open"]), 1e-10
                    )
                    signal = "REVERSIÓN ALCISTA"
                    interp = (
                        f"⬆️ VELA ENVOLVENTE ALCISTA detectada hace {bars_ago} barra(s). "
                        f"La vela actual ALCISTA absorbió completamente a la vela bajista previa "
                        f"(ratio de cuerpo: {body_ratio:.2f}x). "
                        f"Señal de REVERSIÓN ALCISTA: los compradores tomaron el control. "
                        f"{'Señal fuerte: cuerpo grande.' if body_ratio > 1.5 else 'Señal moderada: confirmar con siguiente vela.'}"
                    )
                    return AlgorithmResult(
                        algorithm=self.name,
                        symbol=symbol,
                        value=round(body_ratio, 3),
                        signal=signal,
                        interpretation=interp,
                        metadata={"bars_ago": bars_ago, "body_ratio": round(body_ratio, 3), "type": "bullish"},
                    )

            # Envolvente bajista: previa alcista + actual bajista que absorbe
            if prev_bull and curr_bear:
                if curr["open"] >= prev["close"] and curr["close"] <= prev["open"]:
                    body_ratio = abs(curr["close"] - curr["open"]) / max(
                        abs(prev["close"] - prev["open"]), 1e-10
                    )
                    signal = "REVERSIÓN BAJISTA"
                    interp = (
                        f"⬇️ VELA ENVOLVENTE BAJISTA detectada hace {bars_ago} barra(s). "
                        f"La vela actual BAJISTA absorbió completamente a la vela alcista previa "
                        f"(ratio de cuerpo: {body_ratio:.2f}x). "
                        f"Señal de REVERSIÓN BAJISTA: los vendedores tomaron el control. "
                        f"{'Señal fuerte: cuerpo grande.' if body_ratio > 1.5 else 'Señal moderada: confirmar con siguiente vela.'}"
                    )
                    return AlgorithmResult(
                        algorithm=self.name,
                        symbol=symbol,
                        value=round(body_ratio, 3),
                        signal=signal,
                        interpretation=interp,
                        metadata={"bars_ago": bars_ago, "body_ratio": round(body_ratio, 3), "type": "bearish"},
                    )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=0,
            signal="SIN PATRÓN",
            interpretation=(
                "No se detectó vela envolvente en las últimas 4 barras. "
                "El mercado no muestra señal de reversión estructural por este patrón. "
                "Continuar monitoreando la acción del precio."
            ),
        )
