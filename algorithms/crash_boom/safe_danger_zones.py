"""CRASH #43-44 / BOOM #43-44 — Safe Zone & Danger Zone.

safe_zone  → precio en zona segura para mantener posición.
danger_zone → precio en zona de máximo riesgo de spike.

Zonas calculadas con Fibonacci del ciclo actual:
  CRASH:
    Safe   = precio entre 0% y 50% de recuperación del crash
    Danger = precio entre 80% y 100%+ (cerca del nivel pre-crash)
  BOOM:
    Safe   = precio entre 0% y 50% de corrección del boom
    Danger = precio entre 80% y 100%+ (cerca del nivel pre-boom)
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom


@register
class CrashSafeZone(AlgorithmBase):
    name = "crash.safe_zone"
    category = "crash_boom"
    description = "¿Está el precio en zona segura para largos? Score 0–100."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 50.0, "SIN REFERENCIA",
                                   "Sin crash reciente. Zona de referencia no calculable.")

        crash_low  = float(window.loc[last_idx, "low"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        crash_high = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = crash_high - crash_low
        current = float(window["close"].iloc[-1])
        recovery_pct = (current - crash_low) / swing * 100 if swing > 0 else 50.0

        # Score de seguridad: más alto cuando el precio está lejos del nivel pre-crash
        safe_score = max(0.0, 100.0 - recovery_pct)  # 100 en mínimo, 0 cerca del máximo

        if recovery_pct <= 30:
            signal = "ZONA MUY SEGURA"
            interp = (f"Precio a {recovery_pct:.1f}% del mínimo del crash. "
                      f"Muy lejos del nivel pre-crash ({crash_high:.5f}). "
                      f"Excelente relación riesgo/beneficio para largos.")
        elif recovery_pct <= 50:
            signal = "ZONA SEGURA"
            interp = (f"Precio recuperado {recovery_pct:.1f}%. Zona segura. "
                      f"Alejado del nivel de riesgo máximo ({crash_high:.5f}).")
        elif recovery_pct <= 70:
            signal = "ZONA NEUTRAL"
            interp = (f"Precio en {recovery_pct:.1f}% de recuperación. "
                      f"Zona neutral. Monitorear tensión creciente.")
        elif recovery_pct <= 85:
            signal = "ZONA DE PRECAUCIÓN"
            interp = (f"Precio en {recovery_pct:.1f}% de recuperación. "
                      f"Cerca del nivel pre-crash. Reducir exposición.")
        else:
            signal = "FUERA DE ZONA SEGURA"
            interp = (f"Precio en {recovery_pct:.1f}% (casi en el nivel pre-crash {crash_high:.5f}). "
                      f"Zona de máximo riesgo. NO mantener largos.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(safe_score, 1), signal=signal, interpretation=interp,
            metadata={
                "safe_score": round(safe_score, 1),
                "recovery_pct": round(recovery_pct, 2),
                "crash_low": crash_low,
                "crash_high": crash_high,
                "current_price": current,
            },
        )


@register
class CrashDangerZone(AlgorithmBase):
    name = "crash.danger_zone"
    category = "crash_boom"
    description = "¿Está el precio en zona de peligro? Score 0–100 (100 = máximo peligro)."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN REFERENCIA",
                                   "Sin crash reciente. Zona de referencia no calculable.")

        crash_low  = float(window.loc[last_idx, "low"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        crash_high = float(pre["high"].max()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = crash_high - crash_low
        current = float(window["close"].iloc[-1])
        recovery_pct = (current - crash_low) / swing * 100 if swing > 0 else 0.0

        # Score de peligro: exponencial, se dispara cerca del 100%
        danger_raw = max(0.0, recovery_pct - 50) * 2  # 0 hasta 50%, sube de ahí
        danger_score = min(round(danger_raw, 1), 100.0)

        if danger_score >= 80:
            signal = "ZONA DE PELIGRO MÁXIMO"
            interp = (f"Precio en {recovery_pct:.1f}% de recuperación. "
                      f"Score de peligro: {danger_score}/100. "
                      f"CRASH INMINENTE. Cerrar largos inmediatamente.")
        elif danger_score >= 50:
            signal = "ZONA PELIGROSA"
            interp = (f"Precio en {recovery_pct:.1f}%. Score: {danger_score}/100. "
                      f"Zona de alta probabilidad de crash. Reducir posición.")
        elif danger_score >= 20:
            signal = "ZONA DE ALERTA"
            interp = (f"Precio en {recovery_pct:.1f}%. Score: {danger_score}/100. "
                      f"Comenzando a entrar en zona de riesgo.")
        else:
            signal = "FUERA DE PELIGRO"
            interp = (f"Precio en {recovery_pct:.1f}%. Score: {danger_score}/100. "
                      f"El precio está lejos de la zona de crash.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=danger_score, signal=signal, interpretation=interp,
            metadata={
                "danger_score": danger_score,
                "recovery_pct": round(recovery_pct, 2),
                "crash_low": crash_low,
                "crash_high": crash_high,
                "current_price": current,
            },
        )


@register
class BoomSafeZone(AlgorithmBase):
    name = "boom.safe_zone"
    category = "crash_boom"
    description = "¿Está el precio en zona segura para cortos? Score 0–100."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 50.0, "SIN REFERENCIA",
                                   "Sin boom reciente. Zona de referencia no calculable.")

        boom_high = float(window.loc[last_idx, "high"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        boom_low  = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = boom_high - boom_low
        current = float(window["close"].iloc[-1])
        correction_pct = (boom_high - current) / swing * 100 if swing > 0 else 50.0

        safe_score = max(0.0, 100.0 - correction_pct)
        # Invertido para boom: seguro cuando el precio ya corrigió bastante

        if correction_pct <= 30:
            signal = "ZONA MUY SEGURA"
            interp = (f"Precio a {correction_pct:.1f}% de corrección del boom. "
                      f"Lejos del nivel pre-boom ({boom_low:.5f}). "
                      f"Excelente R/B para cortos.")
        elif correction_pct <= 50:
            signal = "ZONA SEGURA"
            interp = (f"Precio corrigió {correction_pct:.1f}%. Zona segura para cortos.")
        elif correction_pct <= 70:
            signal = "ZONA NEUTRAL"
            interp = (f"Precio en {correction_pct:.1f}% de corrección. Monitorear.")
        elif correction_pct <= 85:
            signal = "ZONA DE PRECAUCIÓN"
            interp = (f"Precio en {correction_pct:.1f}% de corrección. "
                      f"Cerca del nivel pre-boom. Reducir exposición corta.")
        else:
            signal = "FUERA DE ZONA SEGURA"
            interp = (f"Precio en {correction_pct:.1f}% (casi en nivel pre-boom {boom_low:.5f}). "
                      f"Zona de máximo riesgo. NO mantener cortos.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(safe_score, 1), signal=signal, interpretation=interp,
            metadata={
                "safe_score": round(safe_score, 1),
                "correction_pct": round(correction_pct, 2),
                "boom_high": boom_high,
                "boom_low": boom_low,
                "current_price": current,
            },
        )


@register
class BoomDangerZone(AlgorithmBase):
    name = "boom.danger_zone"
    category = "crash_boom"
    description = "¿Está el precio en zona de peligro de boom? Score 0–100."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN REFERENCIA",
                                   "Sin boom reciente. Zona de referencia no calculable.")

        boom_high = float(window.loc[last_idx, "high"])
        pre = window.iloc[max(0, last_idx - 20): last_idx]
        boom_low  = float(pre["low"].min()) if len(pre) > 0 else float(window.loc[last_idx, "open"])
        swing = boom_high - boom_low
        current = float(window["close"].iloc[-1])
        correction_pct = (boom_high - current) / swing * 100 if swing > 0 else 0.0

        danger_raw = max(0.0, correction_pct - 50) * 2
        danger_score = min(round(danger_raw, 1), 100.0)

        if danger_score >= 80:
            signal = "ZONA DE PELIGRO MÁXIMO"
            interp = (f"Precio en {correction_pct:.1f}% de corrección. "
                      f"Score: {danger_score}/100. BOOM INMINENTE. Cerrar cortos.")
        elif danger_score >= 50:
            signal = "ZONA PELIGROSA"
            interp = (f"Precio en {correction_pct:.1f}%. Score: {danger_score}/100. "
                      f"Alta probabilidad de boom. Reducir posición corta.")
        elif danger_score >= 20:
            signal = "ZONA DE ALERTA"
            interp = (f"Precio en {correction_pct:.1f}%. Score: {danger_score}/100. "
                      f"Entrando en zona de riesgo de boom.")
        else:
            signal = "FUERA DE PELIGRO"
            interp = (f"Precio en {correction_pct:.1f}%. Score: {danger_score}/100. "
                      f"Lejos de la zona de boom.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=danger_score, signal=signal, interpretation=interp,
            metadata={
                "danger_score": danger_score,
                "correction_pct": round(correction_pct, 2),
                "boom_high": boom_high,
                "boom_low": boom_low,
                "current_price": current,
            },
        )
