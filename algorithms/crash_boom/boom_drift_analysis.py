"""BOOM #11–20 — Drift Analysis (versiones espejo para BOOM).

En BOOM el drift es BAJISTA entre booms (wick superior).
Este módulo implementa los 10 algoritmos del Bloque B para BOOM,
mirroreando la lógica de los algoritmos crash.drift_* pero con dirección invertida.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.drift_exhaustion import _rsi_of_series


def _atr(window: pd.DataFrame, period: int = 14) -> float:
    """ATR clásico de Wilder simplificado (sobre OHLC)."""
    h, l, c = window["high"], window["low"], window["close"]
    tr = pd.concat([(h - l).abs(),
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.tail(period).mean())


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _find_boom_spikes(df: pd.DataFrame, lookback: int = 100):
    window = df.tail(lookback).reset_index(drop=True)
    body = (window["close"] - window["open"]).abs()
    normal_body = float(body.quantile(0.75))
    threshold = normal_body * SPIKE_ATR_MULTIPLIER
    wick = window["high"] - window[["open", "close"]].max(axis=1)
    spike_positions = wick[wick > threshold].index.tolist()
    return window, spike_positions


# ─── BOOM #11 — Drift Slope ───────────────────────────────────────────────────

@register
class BoomDriftSlope(AlgorithmBase):
    name = "boom.drift_slope"
    category = "crash_boom"
    description = "Pendiente del drift BAJISTA entre booms. Pendiente negativa = drift activo."

    def __init__(self, lookback: int = 100) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        window, spike_pos = _find_boom_spikes(df, self.lookback)
        start = spike_pos[-1] + 1 if spike_pos else 0
        seg = window.iloc[start:]
        if len(seg) < 5:
            return AlgorithmResult(self.name, symbol, 0.0, "SEGMENTO CORTO",
                f"Solo {len(seg)} velas desde el último boom.")
        prices = seg["close"].values
        x = np.arange(len(prices))
        slope, _, r_value, _, _ = stats.linregress(x, prices)
        price_mean = float(np.mean(prices))
        slope_pct = (slope / price_mean * 100) if price_mean else 0
        r2 = r_value ** 2

        if slope_pct < -0.15:
            signal = "DRIFT BAJISTA AGRESIVO"
            interp = (
                f"El drift bajista post-boom es AGRESIVO: {slope_pct:+.4f}%/vela (R²={r2:.3f}). "
                f"El precio baja rápidamente. Excelente para estrategias cortas. "
                f"El mercado se acerca velozmente al siguiente boom."
            )
        elif slope_pct < -0.05:
            signal = "DRIFT BAJISTA NORMAL"
            interp = (
                f"Drift bajista estable: {slope_pct:+.4f}%/vela (R²={r2:.3f}). "
                f"Comportamiento típico post-boom. Buenas condiciones para cortos."
            )
        elif slope_pct < 0:
            signal = "DRIFT BAJISTA LENTO"
            interp = (
                f"Drift bajista muy lento: {slope_pct:+.4f}%/vela. "
                f"El precio baja poco. Posible resistencia al drift o consolidación. R²={r2:.3f}."
            )
        elif slope_pct > 0.05:
            signal = "DRIFT INVERTIDO"
            interp = (
                f"⚠️ El precio SUBE post-boom: {slope_pct:+.4f}%/vela. "
                f"Comportamiento atípico para BOOM. Posible régimen de doble boom. R²={r2:.3f}."
            )
        else:
            signal = "NEUTRO"
            interp = f"Drift prácticamente plano post-boom: {slope_pct:+.4f}%/vela. R²={r2:.3f}."

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(slope_pct, 6), signal=signal, interpretation=interp,
            metadata={"slope_pct_per_bar": round(slope_pct, 6), "r_squared": round(r2, 4),
                      "drift_bars": len(seg)},
        )


# ─── BOOM #12 — Drift Channel ─────────────────────────────────────────────────

@register
class BoomDriftChannel(AlgorithmBase):
    name = "boom.drift_channel"
    category = "crash_boom"
    description = "Canal del drift bajista post-boom. Precio en zona baja = boom próximo."

    def __init__(self, lookback: int = 80) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        window, spike_pos = _find_boom_spikes(df, self.lookback)
        start = spike_pos[-1] + 1 if spike_pos else 0
        seg = window.iloc[start:]
        if len(seg) < 8:
            return AlgorithmResult(self.name, symbol, None, "SEGMENTO CORTO",
                "Insuficiente histórico post-boom para construir canal.")
        prices = seg["close"].values
        x = np.arange(len(prices))
        coeffs = np.polyfit(x, prices, 1)
        trend_line = np.polyval(coeffs, x)
        residuals = prices - trend_line
        std_res = float(np.std(residuals))
        current_price = float(prices[-1])
        current_trend = float(trend_line[-1])
        upper = current_trend + 2 * std_res
        lower = current_trend - 2 * std_res
        channel_width = upper - lower
        position = (current_price - lower) / channel_width if channel_width > 0 else 0.5
        pos_pct = round(position * 100, 1)

        if position < 0.15:
            signal = "PISO DEL CANAL"
            interp = (
                f"El precio está en el PISO del canal de drift bajista ({pos_pct}%). "
                f"Canal: [{lower:.4f} – {upper:.4f}]. ⚡ Zona de máxima presión vendedora. "
                f"Alta probabilidad de boom inminente."
            )
        elif position < 0.35:
            signal = "PARTE BAJA DEL CANAL"
            interp = (
                f"Precio en parte baja del canal ({pos_pct}%). "
                f"Canal: [{lower:.4f} – {upper:.4f}]. Tensión compradora creciente. Zona de alerta."
            )
        elif position < 0.65:
            signal = "CENTRO DEL CANAL"
            interp = (
                f"Precio centrado en el canal de drift bajista ({pos_pct}%). "
                f"Canal: [{lower:.4f} – {upper:.4f}]. Drift activo y equilibrado."
            )
        else:
            signal = "PARTE ALTA DEL CANAL"
            interp = (
                f"Precio en parte alta del canal ({pos_pct}%). "
                f"Canal: [{lower:.4f} – {upper:.4f}]. El drift bajista tiene más margen disponible."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=pos_pct, signal=signal, interpretation=interp,
            metadata={"channel_position_pct": pos_pct, "upper_band": round(upper, 5),
                      "lower_band": round(lower, 5), "current_price": round(current_price, 5),
                      "drift_bars": len(seg)},
        )


# ─── BOOM #13 — Drift Deceleration ───────────────────────────────────────────

@register
class BoomDriftDeceleration(AlgorithmBase):
    name = "boom.drift_decel"
    category = "crash_boom"
    description = "¿El drift bajista se desacelera? Desaceleración = boom próximo."

    def __init__(self, lookback: int = 100) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        window, spike_pos = _find_boom_spikes(df, self.lookback)
        start = spike_pos[-1] + 1 if spike_pos else 0
        seg = window.iloc[start:]
        if len(seg) < 12:
            return AlgorithmResult(self.name, symbol, 0.0, "SEGMENTO CORTO",
                "Necesario al menos 12 velas post-boom.")
        prices = seg["close"].values
        mid = len(prices) // 2
        slope1, _, _, _, _ = stats.linregress(np.arange(mid), prices[:mid])
        slope2, _, _, _, _ = stats.linregress(np.arange(len(prices) - mid), prices[mid:])
        price_mean = float(np.mean(prices))
        slope1_pct = (slope1 / price_mean * 100) if price_mean else 0
        slope2_pct = (slope2 / price_mean * 100) if price_mean else 0
        # En BOOM, el drift es bajista, así que "aceleración" significa más negativo
        accel = slope2_pct - slope1_pct  # negativo = más caída = aceleración bajista

        if accel < -0.05:
            signal = "ACELERANDO A LA BAJA"
            interp = (
                f"El drift bajista ACELERA: {slope1_pct:+.4f}% → {slope2_pct:+.4f}%/vela. "
                f"El precio cae cada vez más rápido. Boom puede estar más lejos aún."
            )
        elif accel > 0.05:
            signal = "DESACELERANDO"
            interp = (
                f"El drift bajista DESACELERA: {slope1_pct:+.4f}% → {slope2_pct:+.4f}%/vela. "
                f"⚡ El precio ya no baja tan rápido. "
                f"Señal de que la presión compradora crece. Boom puede estar próximo."
            )
        else:
            signal = "DRIFT ESTABLE"
            interp = (
                f"Drift bajista estable: {slope1_pct:+.4f}% ≈ {slope2_pct:+.4f}%/vela. "
                f"El precio baja a ritmo constante."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(accel, 6), signal=signal, interpretation=interp,
            metadata={"deceleration": round(accel, 6),
                      "slope_first_half_pct": round(slope1_pct, 6),
                      "slope_second_half_pct": round(slope2_pct, 6),
                      "drift_bars": len(seg)},
        )


# ─── BOOM #14 — Drift Exhaustion ─────────────────────────────────────────────

@register
class BoomDriftExhaustion(AlgorithmBase):
    name = "boom.drift_exhaust"
    category = "crash_boom"
    description = "Signos de agotamiento del drift bajista. Agotamiento = tensión máxima pre-boom."

    def __init__(self, lookback: int = 80) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        window, spike_pos = _find_boom_spikes(df, self.lookback)
        start = spike_pos[-1] + 1 if spike_pos else 0
        seg = window.iloc[start:]
        if len(seg) < 10:
            return AlgorithmResult(self.name, symbol, 0, "SEGMENTO CORTO",
                "Insuficiente para detectar agotamiento.")
        prices = seg["close"].values
        rsi_val = _rsi_of_series(prices, 7)
        roc = (prices[-1] - prices[-6]) / prices[-6] * 100 if len(prices) >= 6 and prices[-6] else 0
        recent_slope_pct = 0.0
        if len(prices) >= 5:
            coeffs = np.polyfit(np.arange(5), prices[-5:], 1)
            recent_slope_pct = coeffs[0] / float(np.mean(prices[-5:])) * 100 if np.mean(prices[-5:]) else 0

        # En BOOM el drift es bajista, agotamiento = RSI muy bajo + slope plano
        exhaustion_components = []
        if rsi_val < 30:
            exhaustion_components.append(30)
        elif rsi_val < 40:
            exhaustion_components.append(15)
        if abs(recent_slope_pct) < 0.01:
            exhaustion_components.append(35)
        elif abs(recent_slope_pct) < 0.05:
            exhaustion_components.append(15)
        if abs(roc) < 0.01:
            exhaustion_components.append(35)
        elif abs(roc) < 0.1:
            exhaustion_components.append(15)

        exhaustion_score = min(sum(exhaustion_components), 100)

        if exhaustion_score >= 60:
            signal = "DRIFT AGOTADO"
            interp = (
                f"El drift bajista muestra signos de AGOTAMIENTO (score: {exhaustion_score}/100). "
                f"RSI: {rsi_val:.1f} | ROC: {roc:+.4f}% | Pendiente reciente: {recent_slope_pct:+.4f}%/vela. "
                f"⚡ La caída pierde fuerza. Tensión compradora creciendo. Boom puede llegar pronto."
            )
        elif exhaustion_score >= 30:
            signal = "DRIFT DEBILITANDO"
            interp = (
                f"El drift bajista se debilita (score: {exhaustion_score}/100). "
                f"RSI: {rsi_val:.1f} | ROC: {roc:+.4f}%. Aumentar monitoreo de boom."
            )
        else:
            signal = "DRIFT ACTIVO"
            interp = (
                f"El drift bajista está activo y saludable (agotamiento: {exhaustion_score}/100). "
                f"RSI: {rsi_val:.1f} | ROC: {roc:+.4f}%."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=exhaustion_score, signal=signal, interpretation=interp,
            metadata={"exhaustion_score": exhaustion_score, "drift_rsi": round(rsi_val, 2),
                      "drift_roc_pct": round(roc, 4), "recent_slope_pct": round(recent_slope_pct, 6),
                      "drift_bars": len(seg)},
        )


# ─── BOOM #15 — Drift Linearity ──────────────────────────────────────────────

@register
class BoomDriftLinearity(AlgorithmBase):
    name = "boom.drift_linear"
    category = "crash_boom"
    description = "R² del drift bajista post-boom. Alto R² = drift limpio y predecible."

    def __init__(self, lookback: int = 100) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        window, spike_pos = _find_boom_spikes(df, self.lookback)
        start = spike_pos[-1] + 1 if spike_pos else 0
        seg = window.iloc[start:]
        if len(seg) < 6:
            return AlgorithmResult(self.name, symbol, 0.0, "SEGMENTO CORTO", "Insuficiente para R².")
        prices = seg["close"].values
        _, _, r_value, _, _ = stats.linregress(np.arange(len(prices)), prices)
        r2 = float(r_value ** 2)
        if r2 >= 0.90:
            signal = "DRIFT MUY LIMPIO"
            interp = (f"R² = {r2:.4f} → Drift bajista muy lineal y predecible. "
                      f"Condiciones ideales para estrategias de seguimiento del drift BOOM.")
        elif r2 >= 0.75:
            signal = "DRIFT LIMPIO"
            interp = f"R² = {r2:.4f} → Drift bajista ordenado. Buena confianza en indicadores de timing."
        elif r2 >= 0.50:
            signal = "DRIFT RUIDOSO"
            interp = f"R² = {r2:.4f} → Drift bajista con ruido. Micro-correcciones frecuentes."
        else:
            signal = "DRIFT CAÓTICO"
            interp = f"R² = {r2:.4f} → Drift post-boom muy irregular. Baja confianza en timing."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(r2, 4), signal=signal, interpretation=interp,
            metadata={"r_squared": round(r2, 4), "drift_bars": len(seg)},
        )


# ─── BOOM #16 — Drift Volatility ─────────────────────────────────────────────

@register
class BoomDriftVolatility(AlgorithmBase):
    name = "boom.drift_vol"
    category = "crash_boom"
    description = "Volatilidad interna (ATR) del drift bajista post-boom."

    def __init__(self, lookback: int = 80) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        global_atr = _atr(df.tail(30), 14)
        window, spike_pos = _find_boom_spikes(df, self.lookback)
        start = spike_pos[-1] + 1 if spike_pos else 0
        seg = window.iloc[start:]
        if len(seg) < 5:
            return AlgorithmResult(self.name, symbol, 0.0, "SEGMENTO CORTO",
                "Insuficiente para calcular ATR del drift.")
        drift_atr = _atr(seg, min(7, len(seg) - 1))
        ratio = drift_atr / global_atr if global_atr else 1.0
        if ratio < 0.5:
            signal = "DRIFT MUY SUAVE"
            interp = f"ATR del drift: {drift_atr:.5f} ({ratio:.2f}x global). Drift muy tranquilo. Ideal para cortos."
        elif ratio < 0.8:
            signal = "DRIFT SUAVE"
            interp = f"ATR del drift: {drift_atr:.5f} ({ratio:.2f}x global). Baja volatilidad en el drift."
        elif ratio < 1.2:
            signal = "DRIFT NORMAL"
            interp = f"ATR del drift: {drift_atr:.5f} ({ratio:.2f}x global). Volatilidad normal."
        else:
            signal = "DRIFT TURBULENTO"
            interp = (f"ATR del drift: {drift_atr:.5f} ({ratio:.2f}x global). "
                      f"Mucho ruido en el drift bajista. Ampliar stops.")
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(drift_atr, 6), signal=signal, interpretation=interp,
            metadata={"drift_atr": round(drift_atr, 6), "global_atr": round(global_atr, 6),
                      "ratio_vs_global": round(ratio, 3), "drift_bars": len(seg)},
        )


# ─── BOOM #17 — Micro Drift ───────────────────────────────────────────────────

@register
class BoomMicroDrift(AlgorithmBase):
    name = "boom.micro_drift"
    category = "crash_boom"
    description = "Pendiente inmediata del precio (últimas 10 velas). Momentum real en tiempo real."

    def __init__(self, window: int = 10) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        recent = df.tail(self.window)
        if len(recent) < 4:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        prices = recent["close"].values
        slope, _, r_value, _, _ = stats.linregress(np.arange(len(prices)), prices)
        price_mean = float(np.mean(prices))
        slope_pct = (slope / price_mean * 100) if price_mean else 0
        r2 = r_value ** 2
        if slope_pct < -0.2:
            signal = "IMPULSO BAJISTA FUERTE"
            interp = (f"Últimas {self.window} velas bajan con fuerza: {slope_pct:+.4f}%/vela (R²={r2:.2f}). "
                      f"En BOOM: drift bajista agresivo. Boom puede estar más lejos aún.")
        elif slope_pct < -0.05:
            signal = "IMPULSO BAJISTA"
            interp = f"Micro-drift bajista: {slope_pct:+.4f}%/vela (R²={r2:.2f}). Drift activo."
        elif slope_pct > 0.2:
            signal = "CORRECCIÓN FUERTE"
            interp = (f"El precio sube en el corto plazo: {slope_pct:+.4f}%/vela (R²={r2:.2f}). "
                      f"Posible boom reciente o corrección del drift bajista.")
        elif slope_pct > 0.05:
            signal = "CORRECCIÓN LEVE"
            interp = f"Micro-corrección alcista: {slope_pct:+.4f}%/vela. El drift pierde momentum."
        else:
            signal = "CONSOLIDACIÓN"
            interp = f"Precio consolidando: {slope_pct:+.4f}%/vela (R²={r2:.2f})."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(slope_pct, 6), signal=signal, interpretation=interp,
            metadata={"slope_pct_per_bar": round(slope_pct, 6), "r_squared": round(r2, 4),
                      "window_bars": self.window},
        )


# ─── BOOM #18 — Drift Consistency ────────────────────────────────────────────

@register
class BoomDriftConsistency(AlgorithmBase):
    name = "boom.drift_consist"
    category = "crash_boom"
    description = "Consistencia del drift bajista: % velas bajistas y uniformidad de cuerpos."

    def __init__(self, lookback: int = 80) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        window, spike_pos = _find_boom_spikes(df, self.lookback)
        start = spike_pos[-1] + 1 if spike_pos else 0
        seg = window.iloc[start:]
        if len(seg) < 6:
            return AlgorithmResult(self.name, symbol, 0.0, "SEGMENTO CORTO",
                "Insuficiente para analizar consistencia.")
        is_bearish = seg["close"] < seg["open"]
        pct_bearish = float(is_bearish.mean() * 100)
        bodies = (seg["close"] - seg["open"]).abs()
        normal_mask = bodies < bodies.quantile(0.9)
        if normal_mask.sum() > 2:
            cv_body = float(bodies[normal_mask].std() / bodies[normal_mask].mean()) if bodies[normal_mask].mean() > 0 else 1.0
        else:
            cv_body = 1.0
        bear_score = max(0, (pct_bearish - 50) / 50 * 50)
        cv_score = max(0, (1 - min(cv_body, 1)) * 50)
        consistency = bear_score + cv_score
        if consistency >= 70:
            signal = "DRIFT MUY CONSISTENTE"
            interp = (f"Score: {consistency:.0f}/100. Bajistas: {pct_bearish:.1f}% | CV: {cv_body:.3f}. "
                      f"Drift bajista muy regular. Ideal para estrategias cortas.")
        elif consistency >= 45:
            signal = "DRIFT CONSISTENTE"
            interp = f"Score: {consistency:.0f}/100. Bajistas: {pct_bearish:.1f}%. Drift ordenado."
        elif consistency >= 25:
            signal = "DRIFT IRREGULAR"
            interp = f"Score: {consistency:.0f}/100. Mezcla de velas bajistas/alcistas."
        else:
            signal = "DRIFT ERRÁTICO"
            interp = f"Score: {consistency:.0f}/100. Drift muy irregular. Difícil operar."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(consistency, 1), signal=signal, interpretation=interp,
            metadata={"consistency_score": round(consistency, 1),
                      "pct_bearish_candles": round(pct_bearish, 2),
                      "body_cv": round(cv_body, 4), "drift_bars": len(seg)},
        )


# ─── BOOM #19 — Correction Trajectory ───────────────────────────────────────

@register
class BoomCorrectionTrajectory(AlgorithmBase):
    name = "boom.correction_traj"
    category = "crash_boom"
    description = "Velocidad y ángulo de la corrección post-boom. Rápida = nuevo drift bajista activo."

    def __init__(self, correction_window: int = 20) -> None:
        self.correction_window = correction_window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        window, spike_pos = _find_boom_spikes(df, 200)
        if not spike_pos:
            return AlgorithmResult(self.name, symbol, 0.0, "SIN BOOMS",
                "No se encontraron booms en las últimas 200 velas.")
        last_spike_idx = spike_pos[-1]
        corr_seg = window.iloc[last_spike_idx + 1: last_spike_idx + 1 + self.correction_window]
        if len(corr_seg) < 4:
            return AlgorithmResult(self.name, symbol, 0.0, "CORRECCIÓN ACTIVA",
                f"El boom fue muy reciente. La corrección está en curso.")
        boom_high = float(window.iloc[last_spike_idx]["high"])
        boom_close = float(window.iloc[last_spike_idx]["close"])
        correction_prices = corr_seg["close"].values
        slope, _, r_value, _, _ = stats.linregress(np.arange(len(correction_prices)), correction_prices)
        price_mean = float(np.mean(correction_prices))
        slope_pct = (slope / price_mean * 100) if price_mean else 0
        boom_gain = boom_high - boom_close
        current_price = float(correction_prices[-1])
        corrected = max(0, boom_high - current_price)
        correction_pct = (corrected / boom_gain * 100) if boom_gain > 0 else 100.0
        if slope_pct < -0.15 and r_value < -0.7:
            signal = "CORRECCIÓN FUERTE"
            interp = (f"Corrección post-boom RÁPIDA: {slope_pct:+.4f}%/vela (R²={r_value**2:.3f}). "
                      f"Corregido {correction_pct:.1f}% del boom en {len(corr_seg)} velas. "
                      f"El nuevo drift bajista se estableció sólidamente.")
        elif slope_pct < -0.05:
            signal = "CORRECCIÓN MODERADA"
            interp = (f"Corrección gradual: {slope_pct:+.4f}%/vela. "
                      f"Corregido {correction_pct:.1f}% del boom. Drift re-estableciéndose.")
        elif slope_pct > 0.05:
            signal = "CORRECCIÓN FALLIDA"
            interp = (f"⚠️ El precio SIGUE SUBIENDO post-boom: {slope_pct:+.4f}%/vela. "
                      f"Solo corregido {correction_pct:.1f}%. Posible doble boom.")
        else:
            signal = "CORRECCIÓN PLANA"
            interp = (f"Precio plano post-boom. Corregido: {correction_pct:.1f}%. "
                      f"El nuevo drift aún no se estableció.")
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(correction_pct, 2), signal=signal, interpretation=interp,
            metadata={"correction_pct": round(correction_pct, 2),
                      "correction_slope_pct": round(slope_pct, 6),
                      "r_squared": round(r_value ** 2, 4),
                      "correction_bars": len(corr_seg)},
        )


# ─── BOOM #20 — Correction Completion ───────────────────────────────────────

@register
class BoomCorrectionCompletion(AlgorithmBase):
    name = "boom.correction_pct"
    category = "crash_boom"
    description = "% corregido desde el último boom. 100% = precio bajó de vuelta al nivel pre-boom."

    def __init__(self, lookback: int = 300) -> None:
        self.lookback = lookback

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        window = df.tail(self.lookback).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER
        wick = window["high"] - window[["open", "close"]].max(axis=1)
        spike_mask = wick > threshold
        if not spike_mask.any():
            return AlgorithmResult(self.name, symbol, 100.0, "SIN BOOMS RECIENTES",
                "No se encontraron booms en la ventana.")
        spike_positions = window.index[spike_mask].tolist()
        last_spike_idx = spike_positions[-1]
        spike_row = window.iloc[last_spike_idx]
        boom_high = float(spike_row["high"])
        post_boom_price = float(min(spike_row["open"], spike_row["close"]))
        boom_gain = boom_high - post_boom_price
        current_price = float(window.iloc[-1]["close"])
        bars_since = len(window) - 1 - last_spike_idx
        if boom_gain <= 0:
            return AlgorithmResult(self.name, symbol, 100.0, "CORREGIDO", "Ganancia del boom fue mínima.")
        corrected = max(0, boom_high - current_price)
        correction_pct = (corrected / boom_gain * 100)
        if correction_pct >= 100:
            signal = "TOTALMENTE CORREGIDO"
            interp = (f"El precio bajó de vuelta al nivel pre-boom. Corrección: {correction_pct:.1f}% "
                      f"en {bars_since} velas. ✅ Nuevo drift bajista activo y avanzado.")
        elif correction_pct >= 75:
            signal = "CORRECCIÓN AVANZADA"
            interp = (f"Corregido el {correction_pct:.1f}% del boom en {bars_since} velas. "
                      f"Drift bajista bien establecido.")
        elif correction_pct >= 40:
            signal = "CORRECCIÓN MEDIA"
            interp = (f"Corregido el {correction_pct:.1f}% del boom ({bars_since} velas). "
                      f"El mercado aún en zona de corrección.")
        elif correction_pct >= 10:
            signal = "CORRECCIÓN TEMPRANA"
            interp = (f"Corregido solo el {correction_pct:.1f}% del boom ({bars_since} velas). "
                      f"Zona de mayor seguridad para estrategias cortas.")
        else:
            signal = "BOOM RECIENTE"
            interp = (f"Boom muy reciente (hace {bars_since} velas). Corregido: {correction_pct:.1f}%. "
                      f"El precio está cerca del máximo del boom. "
                      f"Mejor momento estadístico para entrar corto.")
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(correction_pct, 2), signal=signal, interpretation=interp,
            metadata={"correction_pct": round(correction_pct, 2),
                      "current_price": round(current_price, 5),
                      "boom_high": round(boom_high, 5),
                      "bars_since_boom": bars_since},
        )
