"""CRASH #39 — Double Bottom Detector.

Detecta patrón de doble suelo en las velas post-crash.
Un doble suelo = el precio vuelve cerca del mínimo del crash,
luego rebota → señal de soporte fuerte y reanudación del drift.
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash

PROXIMITY_PCT = 0.005   # Considerar "cerca" al mínimo si está dentro del 0.5%
LOOKBACK      = 50      # Velas post-crash a analizar


@register
class CrashDoubleBottom(AlgorithmBase):
    name = "crash.double_bot"
    category = "crash_boom"
    description = "Doble suelo post-crash. Detecta retesteo del mínimo y confirmación de soporte."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        crash_low = float(window.loc[last_idx, "low"])
        proximity_band = crash_low * (1 + PROXIMITY_PCT)  # zona ≤ crash_low * 1.005

        post = window.iloc[last_idx + 1: last_idx + 1 + LOOKBACK]
        current = float(window["close"].iloc[-1])
        bars_since = len(post)

        # Detectar toque del mínimo (retesteo)
        touches = post[post["low"] <= proximity_band]
        n_touches = len(touches)

        # Verificar que después del retesteo el precio subió (confirmación)
        confirmed = False
        confirm_bar = None
        if n_touches > 0:
            last_touch_idx = int(touches.index[-1])
            after_touch = post.iloc[last_touch_idx - (last_idx + 1):]
            if len(after_touch) > 2:
                bounce = float(after_touch["close"].iloc[-1]) - float(after_touch["low"].min())
                swing  = float(post["high"].max()) - crash_low
                if swing > 0 and bounce / swing >= 0.3:
                    confirmed = True
                    confirm_bar = last_touch_idx - last_idx

        if confirmed and n_touches >= 1:
            signal = "DOBLE SUELO CONFIRMADO"
            value  = 100.0
            interp = (f"Doble suelo detectado. Crash mínimo: {crash_low:.5f}. "
                      f"Retesteos: {n_touches}. Confirmado en barra #{confirm_bar} post-crash. "
                      f"Precio actual ({current:.5f}) por encima. Soporte fuerte. Drift alcista.")
        elif n_touches >= 1:
            signal = "RETESTEO SIN CONFIRMAR"
            value  = 50.0
            interp = (f"El precio tocó la zona del mínimo ({n_touches} vez/veces) pero "
                      f"no confirmó rebote significativo. Vigilar si respeta el soporte.")
        elif bars_since > 10:
            signal = "SIN RETESTEO"
            value  = 0.0
            interp = (f"En {bars_since} velas post-crash, el precio no volvió al mínimo ({crash_low:.5f}). "
                      f"Drift alcista limpio, sin patrón de doble suelo.")
        else:
            signal = "ESPERANDO"
            value  = 0.0
            interp = (f"Solo {bars_since} velas post-crash. Aún no hay datos suficientes "
                      f"para evaluar patrón de doble suelo.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=value, signal=signal, interpretation=interp,
            metadata={
                "crash_low": crash_low,
                "n_touches": n_touches,
                "confirmed": confirmed,
                "confirm_bar": confirm_bar,
                "bars_since_crash": bars_since,
                "current_price": current,
            },
        )


@register
class BoomDoubleTop(AlgorithmBase):
    name = "boom.double_top"
    category = "crash_boom"
    description = "Doble techo post-boom. Detecta retesteo del máximo y confirmación de resistencia."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        from algorithms.crash_boom.post_boom_behavior import _find_last_boom
        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        boom_high = float(window.loc[last_idx, "high"])
        proximity_band = boom_high * (1 - PROXIMITY_PCT)  # zona ≥ boom_high * 0.995

        post = window.iloc[last_idx + 1: last_idx + 1 + LOOKBACK]
        current = float(window["close"].iloc[-1])
        bars_since = len(post)

        touches = post[post["high"] >= proximity_band]
        n_touches = len(touches)

        confirmed = False
        confirm_bar = None
        if n_touches > 0:
            last_touch_idx = int(touches.index[-1])
            after_touch = post.iloc[last_touch_idx - (last_idx + 1):]
            if len(after_touch) > 2:
                drop  = float(after_touch["high"].max()) - float(after_touch["close"].iloc[-1])
                swing = boom_high - float(post["low"].min())
                if swing > 0 and drop / swing >= 0.3:
                    confirmed = True
                    confirm_bar = last_touch_idx - last_idx

        if confirmed and n_touches >= 1:
            signal = "DOBLE TECHO CONFIRMADO"
            value  = 100.0
            interp = (f"Doble techo detectado. Boom máximo: {boom_high:.5f}. "
                      f"Retesteos: {n_touches}. Confirmado en barra #{confirm_bar} post-boom. "
                      f"Resistencia fuerte. Drift bajista reanudado.")
        elif n_touches >= 1:
            signal = "RETESTEO SIN CONFIRMAR"
            value  = 50.0
            interp = (f"El precio tocó la zona del máximo ({n_touches} vez/veces) sin "
                      f"confirmar caída significativa. Vigilar si respeta la resistencia.")
        elif bars_since > 10:
            signal = "SIN RETESTEO"
            value  = 0.0
            interp = (f"En {bars_since} velas post-boom, el precio no volvió al máximo ({boom_high:.5f}). "
                      f"Drift bajista limpio.")
        else:
            signal = "ESPERANDO"
            value  = 0.0
            interp = (f"Solo {bars_since} velas post-boom. Sin datos suficientes.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=value, signal=signal, interpretation=interp,
            metadata={
                "boom_high": boom_high,
                "n_touches": n_touches,
                "confirmed": confirmed,
                "confirm_bar": confirm_bar,
                "bars_since_boom": bars_since,
                "current_price": current,
            },
        )
