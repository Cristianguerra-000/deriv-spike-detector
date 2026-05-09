"""CRASH #38 / BOOM #38 — Echo Spike Detector.

Detecta mini-spikes secundarios después del evento principal.
Un "eco" es un spike de menor magnitud que ocurre dentro de las
30 velas post-evento. Indica debilidad del drift y posible acumulación
para un segundo spike grande.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom

ECHO_RATIO = 0.3   # Un eco es un spike > 30% del threshold normal


@register
class CrashEchoSpike(AlgorithmBase):
    name = "crash.echo"
    category = "crash_boom"
    description = "Detecta mini-crashes secundarios (ecos) en las 30 velas post-crash."

    POST_WINDOW = 30

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        body = (window["close"] - window["open"]).abs()
        threshold_full = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        threshold_echo = threshold_full * ECHO_RATIO  # umbral reducido para ecos

        post = window.iloc[last_idx + 1: last_idx + 1 + self.POST_WINDOW]
        lower_wick = post["open"].clip(lower=post["close"]) - post["low"]
        echo_mask  = lower_wick > threshold_echo
        echo_bars  = list(echo_mask[echo_mask].index - (last_idx + 1) + 1)  # 1-based desde post-crash
        n_echoes   = len(echo_bars)
        bars_since = len(post)

        if n_echoes == 0:
            signal = "SIN ECOS"
            value  = 0.0
            interp = (f"No se detectaron mini-crashes en las {bars_since} velas post-crash. "
                      f"El drift alcista está limpio y sin interferencias.")
        elif n_echoes == 1:
            signal = "ECO ÚNICO"
            value  = 1.0
            interp = (f"1 mini-crash detectado en barra #{echo_bars[0]} post-crash. "
                      f"Eco aislado. El drift puede continuar pero con precaución.")
        elif n_echoes <= 3:
            signal = "ECOS MÚLTIPLES"
            value  = float(n_echoes)
            interp = (f"{n_echoes} mini-crashes en las {bars_since} velas post-crash. "
                      f"En barras: {echo_bars}. El drift tiene turbulencia. "
                      f"Posible acumulación hacia un segundo crash grande.")
        else:
            signal = "ZONA DE ECOS INTENSA"
            value  = float(n_echoes)
            interp = (f"{n_echoes} mini-crashes detectados. Alta densidad de ecos. "
                      f"Mercado inestable. Riesgo de crash consecutivo elevado.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=value, signal=signal, interpretation=interp,
            metadata={
                "echo_count": n_echoes,
                "echo_bars": echo_bars,
                "bars_analyzed": bars_since,
                "echo_threshold": round(threshold_echo, 5),
            },
        )


@register
class BoomEchoSpike(AlgorithmBase):
    name = "boom.echo"
    category = "crash_boom"
    description = "Detecta mini-booms secundarios (ecos) en las 30 velas post-boom."

    POST_WINDOW = 30

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        body = (window["close"] - window["open"]).abs()
        threshold_full = float(body.quantile(0.75)) * SPIKE_ATR_MULTIPLIER
        threshold_echo = threshold_full * ECHO_RATIO

        post = window.iloc[last_idx + 1: last_idx + 1 + self.POST_WINDOW]
        upper_wick = post["high"] - post[["open", "close"]].max(axis=1)
        echo_mask  = upper_wick > threshold_echo
        echo_bars  = list(echo_mask[echo_mask].index - (last_idx + 1) + 1)
        n_echoes   = len(echo_bars)
        bars_since = len(post)

        if n_echoes == 0:
            signal = "SIN ECOS"
            value  = 0.0
            interp = (f"No se detectaron mini-booms en las {bars_since} velas post-boom. "
                      f"El drift bajista está limpio.")
        elif n_echoes == 1:
            signal = "ECO ÚNICO"
            value  = 1.0
            interp = (f"1 mini-boom detectado en barra #{echo_bars[0]} post-boom. "
                      f"Eco aislado. El drift bajista puede continuar con precaución.")
        elif n_echoes <= 3:
            signal = "ECOS MÚLTIPLES"
            value  = float(n_echoes)
            interp = (f"{n_echoes} mini-booms en las {bars_since} velas post-boom. "
                      f"Barras: {echo_bars}. Turbulencia en el drift bajista.")
        else:
            signal = "ZONA DE ECOS INTENSA"
            value  = float(n_echoes)
            interp = (f"{n_echoes} mini-booms. Alta densidad. "
                      f"Riesgo de boom consecutivo elevado.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=value, signal=signal, interpretation=interp,
            metadata={
                "echo_count": n_echoes,
                "echo_bars": echo_bars,
                "bars_analyzed": bars_since,
                "echo_threshold": round(threshold_echo, 5),
            },
        )
