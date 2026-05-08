"""Patrón de Vela Envolvente (Engulfing).

Uno de los patrones de reversión más fiables en análisis técnico.
Una vela envolvente ALCISTA: vela bajista seguida de vela alcista que la absorbe completamente.
Una vela envolvente BAJISTA: vela alcista seguida de vela bajista que la absorbe completamente.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


def _fmt_time(epoch_secs: int) -> str:
    """Convierte epoch Unix a HH:MM UTC legible."""
    try:
        return datetime.fromtimestamp(int(epoch_secs), tz=timezone.utc).strftime("%H:%M UTC")
    except Exception:
        return "—"


@register
class EngulfingPattern(AlgorithmBase):
    name = "micro.engulfing"
    category = "microstructure"
    description = "Engulfing: detecta patrones de vela envolvente alcista o bajista (señal de reversión)."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        # Buscar en las últimas 5 barras (ampliado de 4)
        for i in range(-1, -6, -1):
            if abs(i) + 1 >= len(df):
                break

            curr = df.iloc[i]
            prev = df.iloc[i - 1]
            bars_ago = abs(i)  # 1 = vela más reciente, 2 = anterior, etc.

            curr_bull = curr["close"] > curr["open"]
            curr_bear = curr["close"] < curr["open"]
            prev_bull = prev["close"] > prev["open"]
            prev_bear = prev["close"] < prev["open"]

            # Hora de la vela envolvente (la que absorbió)
            bar_time = _fmt_time(curr.get("time", 0))

            # Envolvente alcista: previa bajista + actual alcista que absorbe
            if prev_bear and curr_bull:
                if curr["open"] <= prev["close"] and curr["close"] >= prev["open"]:
                    body_ratio = abs(curr["close"] - curr["open"]) / max(
                        abs(prev["close"] - prev["open"]), 1e-10
                    )
                    signal = "REVERSIÓN ALCISTA"
                    bars_label = "barra actual" if bars_ago == 1 else f"{bars_ago} barras atrás"
                    interp = (
                        f"⬆️ VELA ENVOLVENTE ALCISTA — {bars_label} ({bar_time}). "
                        f"La vela alcista absorbió completamente a la bajista previa "
                        f"(ratio cuerpo: {body_ratio:.2f}x). "
                        f"Señal de REVERSIÓN ALCISTA: compradores al mando. "
                        f"{'Señal FUERTE: cuerpo grande.' if body_ratio > 1.5 else 'Señal moderada: esperar confirmación.'}"
                    )
                    return AlgorithmResult(
                        algorithm=self.name,
                        symbol=symbol,
                        value=round(body_ratio, 3),
                        signal=signal,
                        interpretation=interp,
                        metadata={"bars_ago": bars_ago, "bar_time": bar_time, "body_ratio": round(body_ratio, 3), "type": "bullish"},
                    )

            # Envolvente bajista: previa alcista + actual bajista que absorbe
            if prev_bull and curr_bear:
                if curr["open"] >= prev["close"] and curr["close"] <= prev["open"]:
                    body_ratio = abs(curr["close"] - curr["open"]) / max(
                        abs(prev["close"] - prev["open"]), 1e-10
                    )
                    signal = "REVERSIÓN BAJISTA"
                    bars_label = "barra actual" if bars_ago == 1 else f"{bars_ago} barras atrás"
                    interp = (
                        f"⬇️ VELA ENVOLVENTE BAJISTA — {bars_label} ({bar_time}). "
                        f"La vela bajista absorbió completamente a la alcista previa "
                        f"(ratio cuerpo: {body_ratio:.2f}x). "
                        f"Señal de REVERSIÓN BAJISTA: vendedores al mando. "
                        f"{'Señal FUERTE: cuerpo grande.' if body_ratio > 1.5 else 'Señal moderada: esperar confirmación.'}"
                    )
                    return AlgorithmResult(
                        algorithm=self.name,
                        symbol=symbol,
                        value=round(body_ratio, 3),
                        signal=signal,
                        interpretation=interp,
                        metadata={"bars_ago": bars_ago, "bar_time": bar_time, "body_ratio": round(body_ratio, 3), "type": "bearish"},
                    )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=0,
            signal="SIN PATRÓN",
            interpretation=(
                "No se detectó vela envolvente en las últimas 5 barras. "
                "El mercado no muestra reversión estructural por este patrón. "
                "Continuar monitoreando la acción del precio."
            ),
        )
