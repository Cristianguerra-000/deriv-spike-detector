"""CRASH Bloque C (#21–30) + BOOM Bloque C (#21–30) — Tensión Pre-Spike.

Estos algoritmos detectan la tensión que se acumula ANTES de que ocurra un crash o boom.
En CRASH: la tensión es alcista (precio sube → tensión para el crash).
En BOOM: la tensión es bajista (precio baja → tensión para el boom).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER
from algorithms.crash_boom.boom_drift_analysis import _find_boom_spikes


# ─── Helper ─────────────────────────────────────────────────────────────────

def _find_crash_spikes_recent(df: pd.DataFrame, lookback: int = 200):
    window = df.tail(lookback).reset_index(drop=True)
    body = (window["close"] - window["open"]).abs()
    normal_body = float(body.quantile(0.75))
    threshold = normal_body * SPIKE_ATR_MULTIPLIER
    wick = window["open"].clip(lower=window["close"]) - window["low"]
    return window, wick[wick > threshold].index.tolist()


# ═══════════════════════════════════════════════════════════════════════
# CRASH #21 — Bull Candle Streak
# ═══════════════════════════════════════════════════════════════════════

@register
class CrashBullCandleStreak(AlgorithmBase):
    name = "crash.bull_streak"
    category = "crash_boom"
    description = "Racha de velas alcistas consecutivas. Racha alta = tensión pre-crash acumulada."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")
        closes = df["close"].values
        opens = df["open"].values
        streak = 0
        for i in range(len(closes) - 1, -1, -1):
            if closes[i] > opens[i]:
                streak += 1
            else:
                break
        if streak >= 15:
            signal = "RACHA EXTREMA"
            interp = (f"¡{streak} velas alcistas consecutivas! "
                      f"Tensión pre-crash EXTREMA. El mercado lleva mucho tiempo subiendo sin parar. "
                      f"⚠️ Alta probabilidad de crash inminente.")
        elif streak >= 8:
            signal = "RACHA ALTA"
            interp = (f"{streak} velas alcistas seguidas. Tensión pre-crash ALTA. "
                      f"El drift alcista está sobreextendido. Zona de alerta.")
        elif streak >= 4:
            signal = "RACHA MEDIA"
            interp = (f"{streak} velas alcistas consecutivas. Tensión moderada. "
                      f"El drift avanza normalmente.")
        elif streak >= 1:
            signal = "RACHA BAJA"
            interp = f"{streak} vela(s) alcista(s) seguidas. Tensión baja."
        else:
            signal = "SIN RACHA"
            interp = "La última vela fue bajista. Sin racha alcista activa."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=streak, signal=signal, interpretation=interp,
            metadata={"bull_streak": streak},
        )


# ═══════════════════════════════════════════════════════════════════════
# CRASH #22 — Body Expansion Detector
# ═══════════════════════════════════════════════════════════════════════

@register
class CrashBodyExpansion(AlgorithmBase):
    name = "crash.body_expand"
    category = "crash_boom"
    description = "¿Los cuerpos de las velas crecen? Cuerpos creciendo = tensión compradora acumulando."

    def __init__(self, window: int = 10) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")
        recent = df.tail(self.window)
        bodies = (recent["close"] - recent["open"]).abs().values
        if len(bodies) < 4:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        x = np.arange(len(bodies))
        slope, _, r_value, _, _ = stats.linregress(x, bodies)
        body_mean = float(np.mean(bodies))
        slope_pct = (slope / body_mean * 100) if body_mean else 0
        r2 = r_value ** 2
        if slope_pct > 5 and r2 > 0.5:
            signal = "EXPANSIÓN FUERTE"
            interp = (f"Los cuerpos de las velas crecen rápidamente: {slope_pct:+.2f}%/vela (R²={r2:.2f}). "
                      f"⚠️ Los compradores son cada vez más agresivos. "
                      f"Señal clásica de tensión pre-crash.")
        elif slope_pct > 2:
            signal = "EXPANSIÓN LEVE"
            interp = (f"Expansión moderada de cuerpos: {slope_pct:+.2f}%/vela. "
                      f"Tensión compradora creciendo gradualmente.")
        elif slope_pct < -5:
            signal = "CONTRACCIÓN"
            interp = (f"Los cuerpos se contraen: {slope_pct:+.2f}%/vela. "
                      f"El momentum comprador se debilita. Posible consolidación o agotamiento.")
        else:
            signal = "TAMAÑO ESTABLE"
            interp = (f"Tamaño de cuerpos estable ({slope_pct:+.2f}%/vela). "
                      f"Sin señal de expansión o contracción notable.")
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(slope_pct, 3), signal=signal, interpretation=interp,
            metadata={"body_slope_pct": round(slope_pct, 3), "r_squared": round(r2, 4),
                      "avg_body": round(body_mean, 6)},
        )


# ═══════════════════════════════════════════════════════════════════════
# CRASH #23 — Wick Compression
# ═══════════════════════════════════════════════════════════════════════

@register
class CrashWickCompression(AlgorithmBase):
    name = "crash.wick_compress"
    category = "crash_boom"
    description = "Mechas superiores reduciéndose = compradores eufóricos. Señal pre-crash."

    def __init__(self, window: int = 15) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")
        recent = df.tail(self.window)
        upper_wicks = (recent["high"] - recent[["open", "close"]].max(axis=1)).values
        if len(upper_wicks) < 5:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        x = np.arange(len(upper_wicks))
        slope, _, r_value, _, _ = stats.linregress(x, upper_wicks)
        wick_mean = float(np.mean(upper_wicks))
        slope_pct = (slope / wick_mean * 100) if wick_mean else 0
        r2 = r_value ** 2
        if slope_pct < -5 and r2 > 0.4:
            signal = "COMPRESIÓN FUERTE"
            interp = (f"Las mechas superiores se comprimen: {slope_pct:+.2f}%/vela (R²={r2:.2f}). "
                      f"Los compradores ya no dejan coletas. Euforia compradora. "
                      f"⚠️ Señal clásica de tensión extrema pre-crash.")
        elif slope_pct < -2:
            signal = "COMPRESIÓN LEVE"
            interp = (f"Leve reducción de mechas superiores: {slope_pct:+.2f}%/vela. "
                      f"Compradores ganando confianza. Tensión aumentando.")
        elif slope_pct > 5:
            signal = "EXPANSIÓN DE MECHAS"
            interp = (f"Las mechas superiores crecen: {slope_pct:+.2f}%/vela. "
                      f"Hay presión vendedora en los máximos. Menos tensión pre-crash.")
        else:
            signal = "MECHAS ESTABLES"
            interp = f"Mechas superiores estables ({slope_pct:+.2f}%/vela). Sin señal de compresión."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(slope_pct, 3), signal=signal, interpretation=interp,
            metadata={"wick_slope_pct": round(slope_pct, 3), "r_squared": round(r2, 4),
                      "avg_upper_wick": round(wick_mean, 6)},
        )


# ═══════════════════════════════════════════════════════════════════════
# CRASH #24 — Price Velocity
# ═══════════════════════════════════════════════════════════════════════

@register
class CrashPriceVelocity(AlgorithmBase):
    name = "crash.price_vel"
    category = "crash_boom"
    description = "Velocidad de subida del precio. Alta velocidad = drift agresivo = crash más cerca."

    def __init__(self, periods: int = 5) -> None:
        self.periods = periods

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")
        if len(df) < self.periods + 1:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        price_now = float(df["close"].iloc[-1])
        price_then = float(df["close"].iloc[-(self.periods + 1)])
        velocity_pct = (price_now - price_then) / price_then * 100 if price_then else 0
        if velocity_pct > 0.5:
            signal = "VELOCIDAD ALTA"
            interp = (f"El precio subió {velocity_pct:+.4f}% en las últimas {self.periods} velas. "
                      f"Alta velocidad de drift alcista. "
                      f"⚠️ El mercado se aproxima rápidamente al umbral de crash.")
        elif velocity_pct > 0.15:
            signal = "VELOCIDAD NORMAL"
            interp = (f"Velocidad normal de drift: +{velocity_pct:.4f}% en {self.periods} velas. "
                      f"Comportamiento estándar.")
        elif velocity_pct > 0:
            signal = "VELOCIDAD BAJA"
            interp = (f"Drift muy lento: +{velocity_pct:.4f}% en {self.periods} velas. "
                      f"El mercado sube a paso muy lento.")
        else:
            signal = "RETROCESO"
            interp = (f"El precio bajó {velocity_pct:+.4f}% en {self.periods} velas. "
                      f"Corrección o post-crash reciente.")
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(velocity_pct, 4), signal=signal, interpretation=interp,
            metadata={"velocity_pct": round(velocity_pct, 4), "periods": self.periods,
                      "price_now": round(price_now, 5), "price_then": round(price_then, 5)},
        )


# ═══════════════════════════════════════════════════════════════════════
# CRASH #25 — Momentum Divergence
# ═══════════════════════════════════════════════════════════════════════

def _rsi_quick(prices: np.ndarray, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g = np.mean(gains[-period:])
    avg_l = np.mean(losses[-period:])
    if avg_l == 0:
        return 100.0
    return 100 - 100 / (1 + avg_g / avg_l)


@register
class CrashMomentumDivergence(AlgorithmBase):
    name = "crash.mom_div"
    category = "crash_boom"
    description = "Divergencia bajista: precio sube pero RSI baja. Señal de techo inminente en el drift."

    def __init__(self, window: int = 20) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")
        recent = df.tail(self.window)
        if len(recent) < 10:
            return AlgorithmResult(self.name, symbol, 0, "INSUFICIENTE", "Insuficiente data.")
        prices = recent["close"].values
        mid = len(prices) // 2
        price_trend = prices[-1] - prices[mid]
        rsi_now = _rsi_quick(prices, min(14, len(prices) - 1))
        rsi_mid = _rsi_quick(prices[:mid + 1], min(14, mid))
        rsi_trend = rsi_now - rsi_mid
        if price_trend > 0 and rsi_trend < -5:
            signal = "DIVERGENCIA BAJISTA"
            interp = (f"DIVERGENCIA BAJISTA CLÁSICA: precio sube ({price_trend:+.4f}) "
                      f"pero RSI baja ({rsi_mid:.1f} → {rsi_now:.1f}). "
                      f"⚠️ El momentum no confirma la subida. Señal de techo próximo y posible crash.")
        elif price_trend > 0 and rsi_trend > 5:
            signal = "MOMENTUM CONFIRMADO"
            interp = (f"El precio sube Y el RSI confirma: {rsi_mid:.1f} → {rsi_now:.1f}. "
                      f"No hay divergencia. El drift está saludable.")
        elif price_trend < 0:
            signal = "PRECIO BAJANDO"
            interp = f"El precio bajó en la ventana. Posible post-crash o corrección del drift."
        else:
            signal = "NEUTRO"
            interp = f"Sin divergencia clara. RSI: {rsi_now:.1f}."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(rsi_trend, 2), signal=signal, interpretation=interp,
            metadata={"rsi_now": round(rsi_now, 2), "rsi_mid": round(rsi_mid, 2),
                      "rsi_delta": round(rsi_trend, 2), "price_trend": round(price_trend, 5)},
        )


# ═══════════════════════════════════════════════════════════════════════
# CRASH #26 — Pre-Crash Consolidation
# ═══════════════════════════════════════════════════════════════════════

@register
class CrashPreConsolidation(AlgorithmBase):
    name = "crash.consolidation"
    category = "crash_boom"
    description = "Rango estrecho antes del crash. Consolidación = acumulación de energía."

    def __init__(self, window: int = 10) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")
        recent = df.tail(self.window)
        historical = df.tail(self.window * 5)
        recent_range = float(recent["high"].max() - recent["low"].min())
        hist_range = float(historical["high"].max() - historical["low"].min()) / 5
        ratio = recent_range / hist_range if hist_range else 1.0
        ref_price = float(recent["close"].iloc[-1])
        range_pct = (recent_range / ref_price * 100) if ref_price else 0
        if ratio < 0.3:
            signal = "CONSOLIDACIÓN FUERTE"
            interp = (f"Rango de {self.window} velas: {recent_range:.5f} ({range_pct:.3f}% del precio). "
                      f"Solo el {ratio:.1%} del rango histórico. "
                      f"⚠️ COMPRESIÓN EXTREMA. Alta energía acumulada. Ruptura violenta inminente → probable crash.")
        elif ratio < 0.5:
            signal = "CONSOLIDACIÓN LEVE"
            interp = (f"Rango de {self.window} velas ({range_pct:.3f}%) es {ratio:.1%} del histórico. "
                      f"El mercado está comprimiendo. Zona de acumulación de tensión.")
        elif ratio > 1.5:
            signal = "ALTA VOLATILIDAD"
            interp = (f"Rango amplio ({range_pct:.3f}%). El mercado está en alta volatilidad. "
                      f"Sin consolidación activa.")
        else:
            signal = "RANGO NORMAL"
            interp = f"Rango dentro de los niveles normales. Sin consolidación ni expansión notable."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(ratio, 4), signal=signal, interpretation=interp,
            metadata={"range_ratio_vs_hist": round(ratio, 4), "recent_range": round(recent_range, 6),
                      "range_pct": round(range_pct, 4)},
        )


# ═══════════════════════════════════════════════════════════════════════
# CRASH #27 — Tension Score (Compuesto)
# ═══════════════════════════════════════════════════════════════════════

@register
class CrashTensionScore(AlgorithmBase):
    name = "crash.tension"
    category = "crash_boom"
    description = "Score compuesto de tensión pre-crash (0–100). 100 = máxima tensión. Usar con overdue."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        points = []
        window = df.tail(20)

        # 1. Racha alcista
        streak = 0
        for i in range(len(df) - 1, -1, -1):
            if df["close"].iloc[i] > df["open"].iloc[i]:
                streak += 1
            else:
                break
        if streak >= 12:
            points.append(25)
        elif streak >= 6:
            points.append(15)
        elif streak >= 3:
            points.append(5)

        # 2. RSI alto
        prices = df["close"].values
        rsi = _rsi_quick(prices, 14)
        if rsi > 75:
            points.append(25)
        elif rsi > 65:
            points.append(15)
        elif rsi > 55:
            points.append(5)

        # 3. Velocidad alta
        if len(df) >= 6:
            vel = (float(df["close"].iloc[-1]) - float(df["close"].iloc[-6])) / float(df["close"].iloc[-6]) * 100
            if vel > 0.5:
                points.append(25)
            elif vel > 0.2:
                points.append(15)
            elif vel > 0.05:
                points.append(5)

        # 4. Compresión de mechas
        upper_wicks = (window["high"] - window[["open", "close"]].max(axis=1))
        wick_trend_slope = float(np.polyfit(np.arange(len(upper_wicks)), upper_wicks.values, 1)[0])
        if wick_trend_slope < 0:
            points.append(25)

        tension = min(sum(points), 100)

        if tension >= 75:
            signal = "TENSIÓN EXTREMA"
            interp = (f"Score de tensión pre-crash: {tension}/100. CONDICIONES EXTREMAS. "
                      f"RSI: {rsi:.1f} | Racha alcista: {streak} | Mechas comprimidas. "
                      f"⚠️ Múltiples señales alineadas. Alto riesgo de crash inminente.")
        elif tension >= 50:
            signal = "TENSIÓN ALTA"
            interp = (f"Score de tensión: {tension}/100. Múltiples indicadores de tensión activos. "
                      f"RSI: {rsi:.1f} | Racha: {streak} velas.")
        elif tension >= 25:
            signal = "TENSIÓN MEDIA"
            interp = (f"Score de tensión: {tension}/100. Algunos indicadores de tensión detectados. "
                      f"RSI: {rsi:.1f}.")
        else:
            signal = "TENSIÓN BAJA"
            interp = (f"Score de tensión: {tension}/100. Mercado sin señales de tensión fuerte. "
                      f"RSI: {rsi:.1f}. Momento de relativa calma.")

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=tension, signal=signal, interpretation=interp,
            metadata={"tension_score": tension, "rsi": round(rsi, 2), "bull_streak": streak},
        )


# ═══════════════════════════════════════════════════════════════════════
# CRASH #28 — Upper Wick Ratio
# ═══════════════════════════════════════════════════════════════════════

@register
class CrashUpperWickRatio(AlgorithmBase):
    name = "crash.upper_wick"
    category = "crash_boom"
    description = "Ratio mecha superior / cuerpo. Alto = presión vendedora latente en máximos."

    def __init__(self, window: int = 10) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")
        recent = df.tail(self.window)
        upper_wicks = (recent["high"] - recent[["open", "close"]].max(axis=1)).values
        bodies = (recent["close"] - recent["open"]).abs().values
        valid = bodies > 0
        if not valid.any():
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Cuerpos cero.")
        ratios = upper_wicks[valid] / bodies[valid]
        avg_ratio = float(np.mean(ratios))
        if avg_ratio > 1.5:
            signal = "PRESIÓN VENDEDORA ALTA"
            interp = (f"Mecha superior promedio = {avg_ratio:.2f}x el cuerpo. "
                      f"Los vendedores rechazan activamente los máximos. "
                      f"Presión vendedora alta en el drift. Señal mixta: sube pero con resistencia.")
        elif avg_ratio > 0.7:
            signal = "PRESIÓN VENDEDORA LEVE"
            interp = (f"Ratio mecha/cuerpo = {avg_ratio:.2f}. "
                      f"Algo de rechazo en máximos pero no dominante.")
        elif avg_ratio < 0.2:
            signal = "SIN PRESIÓN VENDEDORA"
            interp = (f"Ratio mecha/cuerpo = {avg_ratio:.2f}. "
                      f"Mechas superiores casi inexistentes. Los compradores dominan sin resistencia. "
                      f"Tensión alcista elevada.")
        else:
            signal = "NORMAL"
            interp = f"Ratio mecha/cuerpo = {avg_ratio:.2f}. Estructura normal de velas."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(avg_ratio, 4), signal=signal, interpretation=interp,
            metadata={"avg_wick_body_ratio": round(avg_ratio, 4), "window": self.window},
        )


# ═══════════════════════════════════════════════════════════════════════
# CRASH #29 — Range Compression Score
# ═══════════════════════════════════════════════════════════════════════

@register
class CrashRangeCompression(AlgorithmBase):
    name = "crash.range_compress"
    category = "crash_boom"
    description = "ATR contrayéndose → explosión próxima. Compresión fuerte = crash o gap inminente."

    def __init__(self, fast: int = 5, slow: int = 20) -> None:
        self.fast = fast
        self.slow = slow

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")
        if len(df) < self.slow + 1:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]),
                                   np.abs(low[1:] - close[:-1])))
        atr_fast = float(np.mean(tr[-self.fast:]))
        atr_slow = float(np.mean(tr[-self.slow:]))
        ratio = atr_fast / atr_slow if atr_slow else 1.0
        compression_pct = (1 - ratio) * 100
        if ratio < 0.5:
            signal = "COMPRESIÓN EXTREMA"
            interp = (f"ATR rápido ({atr_fast:.5f}) es solo {ratio:.2f}x el ATR lento ({atr_slow:.5f}). "
                      f"Compresión del {compression_pct:.1f}%. "
                      f"⚠️ La volatilidad está colapsada. Ruptura explosiva inminente. "
                      f"En CRASH: muy probable que el próximo movimiento sea un crash violento.")
        elif ratio < 0.7:
            signal = "COMPRESIÓN FUERTE"
            interp = (f"ATR rápido = {ratio:.2f}x ATR lento. Compresión del {compression_pct:.1f}%. "
                      f"Mercado acumulando energía. Alta probabilidad de movimiento brusco próximo.")
        elif ratio < 0.85:
            signal = "COMPRESIÓN LEVE"
            interp = (f"ATR rápido = {ratio:.2f}x ATR lento. Leve compresión ({compression_pct:.1f}%). "
                      f"El mercado se calma un poco. Monitorear.")
        else:
            signal = "SIN COMPRESIÓN"
            interp = (f"ATR rápido = {ratio:.2f}x ATR lento. Sin compresión. "
                      f"La volatilidad es normal.")
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(ratio, 4), signal=signal, interpretation=interp,
            metadata={"atr_ratio": round(ratio, 4), "atr_fast": round(atr_fast, 6),
                      "atr_slow": round(atr_slow, 6), "compression_pct": round(compression_pct, 2)},
        )


# ═══════════════════════════════════════════════════════════════════════
# CRASH #30 — Candle Body Sequence
# ═══════════════════════════════════════════════════════════════════════

@register
class CrashCandleBodySequence(AlgorithmBase):
    name = "crash.body_seq"
    category = "crash_boom"
    description = "Patrón de tamaño de cuerpos en últimas 5 velas. Cuerpos crecientes = momentum fuerte."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")
        recent = df.tail(5)
        if len(recent) < 5:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        bodies = (recent["close"] - recent["open"]).abs().values
        is_bullish = (recent["close"].values > recent["open"].values)
        growing = all(bodies[i] < bodies[i + 1] for i in range(len(bodies) - 1))
        shrinking = all(bodies[i] > bodies[i + 1] for i in range(len(bodies) - 1))
        all_bull = all(is_bullish)
        body_sequence = [round(float(b), 6) for b in bodies]
        if growing and all_bull:
            signal = "IMPULSO CRECIENTE"
            interp = (f"5 velas alcistas con cuerpos crecientes: {body_sequence}. "
                      f"⚡ IMPULSO ALCISTA EN ESCALADA. Máxima tensión pre-crash. "
                      f"El momentum comprador se acelera vela a vela.")
        elif growing:
            signal = "CUERPOS CRECIENTES"
            interp = (f"Cuerpos en crecimiento: {body_sequence}. "
                      f"El momentum se acelera (mezclando alcistas y bajistas).")
        elif shrinking and all_bull:
            signal = "IMPULSO DEBILITANDO"
            interp = (f"Velas alcistas pero cuerpos decrecientes: {body_sequence}. "
                      f"Los compradores pierden fuerza. Posible agotamiento del drift.")
        elif shrinking:
            signal = "CUERPOS DECRECIENTES"
            interp = (f"Cuerpos decrecientes: {body_sequence}. Momentum general debilitando.")
        else:
            signal = "SECUENCIA MIXTA"
            interp = (f"Cuerpos sin patrón claro: {body_sequence}. "
                      f"El mercado está en transición o consolidación.")
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=float(bodies[-1]), signal=signal, interpretation=interp,
            metadata={"body_sequence": body_sequence, "all_bullish": bool(all_bull)},
        )


# ═══════════════════════════════════════════════════════════════════════
# BOOM BLOQUE C — Tensión Pre-Boom (#21–30)
# ═══════════════════════════════════════════════════════════════════════

@register
class BoomBearCandleStreak(AlgorithmBase):
    name = "boom.bear_streak"
    category = "crash_boom"
    description = "Racha de velas bajistas consecutivas. Racha alta = tensión pre-boom acumulada."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        closes = df["close"].values
        opens = df["open"].values
        streak = 0
        for i in range(len(closes) - 1, -1, -1):
            if closes[i] < opens[i]:
                streak += 1
            else:
                break
        if streak >= 15:
            signal = "RACHA EXTREMA"
            interp = (f"¡{streak} velas bajistas consecutivas! "
                      f"Tensión pre-boom EXTREMA. El mercado cae sin parar. "
                      f"⚡ Alta probabilidad de boom inminente.")
        elif streak >= 8:
            signal = "RACHA ALTA"
            interp = (f"{streak} velas bajistas seguidas. Tensión pre-boom ALTA. "
                      f"El drift bajista está sobreextendido.")
        elif streak >= 4:
            signal = "RACHA MEDIA"
            interp = f"{streak} velas bajistas consecutivas. Tensión moderada."
        elif streak >= 1:
            signal = "RACHA BAJA"
            interp = f"{streak} vela(s) bajista(s) seguidas. Tensión baja."
        else:
            signal = "SIN RACHA"
            interp = "La última vela fue alcista. Sin racha bajista activa."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=streak, signal=signal, interpretation=interp,
            metadata={"bear_streak": streak},
        )


@register
class BoomBodyExpansion(AlgorithmBase):
    name = "boom.body_expand"
    category = "crash_boom"
    description = "¿Los cuerpos bajistas crecen? Cuerpos creciendo = tensión vendedora acumulando."

    def __init__(self, window: int = 10) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        recent = df.tail(self.window)
        bodies = (recent["close"] - recent["open"]).abs().values
        if len(bodies) < 4:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        slope, _, r_value, _, _ = stats.linregress(np.arange(len(bodies)), bodies)
        body_mean = float(np.mean(bodies))
        slope_pct = (slope / body_mean * 100) if body_mean else 0
        r2 = r_value ** 2
        if slope_pct > 5 and r2 > 0.5:
            signal = "EXPANSIÓN FUERTE"
            interp = (f"Los cuerpos de las velas crecen: {slope_pct:+.2f}%/vela (R²={r2:.2f}). "
                      f"⚡ Los vendedores son cada vez más agresivos. Tensión pre-boom.")
        elif slope_pct > 2:
            signal = "EXPANSIÓN LEVE"
            interp = f"Expansión moderada de cuerpos: {slope_pct:+.2f}%/vela. Tensión creciendo."
        elif slope_pct < -5:
            signal = "CONTRACCIÓN"
            interp = f"Los cuerpos se contraen: {slope_pct:+.2f}%/vela. Momentum vendedor debilitando."
        else:
            signal = "TAMAÑO ESTABLE"
            interp = f"Tamaño de cuerpos estable ({slope_pct:+.2f}%/vela)."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(slope_pct, 3), signal=signal, interpretation=interp,
            metadata={"body_slope_pct": round(slope_pct, 3), "r_squared": round(r2, 4)},
        )


@register
class BoomWickCompression(AlgorithmBase):
    name = "boom.wick_compress"
    category = "crash_boom"
    description = "Mechas inferiores reduciéndose = vendedores capitulando. Señal pre-boom."

    def __init__(self, window: int = 15) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        recent = df.tail(self.window)
        lower_wicks = (recent[["open", "close"]].min(axis=1) - recent["low"]).values
        if len(lower_wicks) < 5:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        slope, _, r_value, _, _ = stats.linregress(np.arange(len(lower_wicks)), lower_wicks)
        wick_mean = float(np.mean(lower_wicks))
        slope_pct = (slope / wick_mean * 100) if wick_mean else 0
        r2 = r_value ** 2
        if slope_pct < -5 and r2 > 0.4:
            signal = "COMPRESIÓN FUERTE"
            interp = (f"Mechas inferiores comprimiéndose: {slope_pct:+.2f}%/vela (R²={r2:.2f}). "
                      f"Los vendedores ya no dejan mechas abajo. Capitulación bajista. "
                      f"⚡ Señal pre-boom clásica.")
        elif slope_pct < -2:
            signal = "COMPRESIÓN LEVE"
            interp = (f"Reducción de mechas inferiores: {slope_pct:+.2f}%/vela. "
                      f"Vendedores perdiendo confianza. Tensión pre-boom aumentando.")
        elif slope_pct > 5:
            signal = "EXPANSIÓN DE MECHAS"
            interp = f"Las mechas inferiores crecen: {slope_pct:+.2f}%/vela. Compradores resistiendo."
        else:
            signal = "MECHAS ESTABLES"
            interp = f"Mechas inferiores estables. Sin señal de compresión."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(slope_pct, 3), signal=signal, interpretation=interp,
            metadata={"wick_slope_pct": round(slope_pct, 3), "r_squared": round(r2, 4)},
        )


@register
class BoomPriceVelocity(AlgorithmBase):
    name = "boom.price_vel"
    category = "crash_boom"
    description = "Velocidad de caída del precio. Caída rápida = drift agresivo = boom más cerca."

    def __init__(self, periods: int = 5) -> None:
        self.periods = periods

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        if len(df) < self.periods + 1:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        price_now = float(df["close"].iloc[-1])
        price_then = float(df["close"].iloc[-(self.periods + 1)])
        velocity_pct = (price_now - price_then) / price_then * 100 if price_then else 0
        if velocity_pct < -0.5:
            signal = "CAÍDA RÁPIDA"
            interp = (f"El precio bajó {velocity_pct:+.4f}% en {self.periods} velas. "
                      f"⚡ Drift bajista AGRESIVO. El mercado se acerca rápidamente al boom.")
        elif velocity_pct < -0.15:
            signal = "CAÍDA NORMAL"
            interp = f"Caída normal: {velocity_pct:+.4f}% en {self.periods} velas. Drift activo."
        elif velocity_pct < 0:
            signal = "CAÍDA LENTA"
            interp = f"Caída muy lenta: {velocity_pct:+.4f}% en {self.periods} velas."
        else:
            signal = "REBOTE"
            interp = f"El precio subió {velocity_pct:+.4f}% en {self.periods} velas. Post-boom o corrección del drift."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(velocity_pct, 4), signal=signal, interpretation=interp,
            metadata={"velocity_pct": round(velocity_pct, 4), "periods": self.periods},
        )


@register
class BoomMomentumDivergence(AlgorithmBase):
    name = "boom.mom_div"
    category = "crash_boom"
    description = "Divergencia alcista: precio baja pero RSI sube. Señal de suelo inminente → boom."

    def __init__(self, window: int = 20) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        recent = df.tail(self.window)
        if len(recent) < 10:
            return AlgorithmResult(self.name, symbol, 0, "INSUFICIENTE", "Insuficiente data.")
        prices = recent["close"].values
        mid = len(prices) // 2
        price_trend = prices[-1] - prices[mid]
        rsi_now = _rsi_quick(prices, min(14, len(prices) - 1))
        rsi_mid = _rsi_quick(prices[:mid + 1], min(14, mid))
        rsi_trend = rsi_now - rsi_mid
        if price_trend < 0 and rsi_trend > 5:
            signal = "DIVERGENCIA ALCISTA"
            interp = (f"DIVERGENCIA ALCISTA: precio baja ({price_trend:+.4f}) "
                      f"pero RSI sube ({rsi_mid:.1f} → {rsi_now:.1f}). "
                      f"⚡ El momentum no confirma la caída. Señal de suelo próximo y posible boom.")
        elif price_trend < 0 and rsi_trend < -5:
            signal = "MOMENTUM BAJISTA CONFIRMADO"
            interp = f"Precio baja Y RSI confirma. Drift bajista saludable. No hay divergencia."
        elif price_trend > 0:
            signal = "PRECIO SUBIENDO"
            interp = f"El precio subió. Posible post-boom o corrección del drift."
        else:
            signal = "NEUTRO"
            interp = f"Sin divergencia clara. RSI: {rsi_now:.1f}."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(rsi_trend, 2), signal=signal, interpretation=interp,
            metadata={"rsi_now": round(rsi_now, 2), "rsi_mid": round(rsi_mid, 2),
                      "rsi_delta": round(rsi_trend, 2), "price_trend": round(price_trend, 5)},
        )


@register
class BoomPreConsolidation(AlgorithmBase):
    name = "boom.consolidation"
    category = "crash_boom"
    description = "Rango estrecho antes del boom. Compresión = acumulación de energía compradora."

    def __init__(self, window: int = 10) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        recent = df.tail(self.window)
        historical = df.tail(self.window * 5)
        recent_range = float(recent["high"].max() - recent["low"].min())
        hist_range = float(historical["high"].max() - historical["low"].min()) / 5
        ratio = recent_range / hist_range if hist_range else 1.0
        ref_price = float(recent["close"].iloc[-1])
        range_pct = (recent_range / ref_price * 100) if ref_price else 0
        if ratio < 0.3:
            signal = "CONSOLIDACIÓN FUERTE"
            interp = (f"Rango comprimido al {ratio:.1%} del histórico ({range_pct:.3f}%). "
                      f"⚡ COMPRESIÓN EXTREMA. Ruptura violenta inminente → probable boom explosivo.")
        elif ratio < 0.5:
            signal = "CONSOLIDACIÓN LEVE"
            interp = f"Rango = {ratio:.1%} del histórico. El mercado comprime. Energía acumulándose."
        elif ratio > 1.5:
            signal = "ALTA VOLATILIDAD"
            interp = f"Rango amplio. Sin consolidación activa."
        else:
            signal = "RANGO NORMAL"
            interp = f"Rango dentro de los niveles normales."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(ratio, 4), signal=signal, interpretation=interp,
            metadata={"range_ratio_vs_hist": round(ratio, 4), "range_pct": round(range_pct, 4)},
        )


@register
class BoomTensionScore(AlgorithmBase):
    name = "boom.tension"
    category = "crash_boom"
    description = "Score compuesto de tensión pre-boom (0–100). 100 = máxima tensión bajista."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        points = []
        window = df.tail(20)
        # 1. Racha bajista
        streak = 0
        for i in range(len(df) - 1, -1, -1):
            if df["close"].iloc[i] < df["open"].iloc[i]:
                streak += 1
            else:
                break
        if streak >= 12:
            points.append(25)
        elif streak >= 6:
            points.append(15)
        elif streak >= 3:
            points.append(5)
        # 2. RSI bajo
        prices = df["close"].values
        rsi = _rsi_quick(prices, 14)
        if rsi < 25:
            points.append(25)
        elif rsi < 35:
            points.append(15)
        elif rsi < 45:
            points.append(5)
        # 3. Velocidad de caída
        if len(df) >= 6:
            vel = (float(df["close"].iloc[-1]) - float(df["close"].iloc[-6])) / float(df["close"].iloc[-6]) * 100
            if vel < -0.5:
                points.append(25)
            elif vel < -0.2:
                points.append(15)
            elif vel < -0.05:
                points.append(5)
        # 4. Compresión de mechas inferiores
        lower_wicks = (window[["open", "close"]].min(axis=1) - window["low"])
        wick_slope = float(np.polyfit(np.arange(len(lower_wicks)), lower_wicks.values, 1)[0])
        if wick_slope < 0:
            points.append(25)
        tension = min(sum(points), 100)
        if tension >= 75:
            signal = "TENSIÓN EXTREMA"
            interp = (f"Score de tensión pre-boom: {tension}/100. "
                      f"RSI: {rsi:.1f} | Racha bajista: {streak} | Mechas inferiores comprimidas. "
                      f"⚡ Múltiples señales alineadas. Alto riesgo de boom inminente.")
        elif tension >= 50:
            signal = "TENSIÓN ALTA"
            interp = (f"Score: {tension}/100. Varios indicadores de tensión bajista activos. RSI: {rsi:.1f}.")
        elif tension >= 25:
            signal = "TENSIÓN MEDIA"
            interp = (f"Score: {tension}/100. Algunos indicadores activos. RSI: {rsi:.1f}.")
        else:
            signal = "TENSIÓN BAJA"
            interp = (f"Score: {tension}/100. Sin señales fuertes de tensión pre-boom. RSI: {rsi:.1f}.")
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=tension, signal=signal, interpretation=interp,
            metadata={"tension_score": tension, "rsi": round(rsi, 2), "bear_streak": streak},
        )


@register
class BoomLowerWickRatio(AlgorithmBase):
    name = "boom.lower_wick"
    category = "crash_boom"
    description = "Ratio mecha inferior / cuerpo. Alto = presión compradora latente en mínimos."

    def __init__(self, window: int = 10) -> None:
        self.window = window

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        recent = df.tail(self.window)
        lower_wicks = (recent[["open", "close"]].min(axis=1) - recent["low"]).values
        bodies = (recent["close"] - recent["open"]).abs().values
        valid = bodies > 0
        if not valid.any():
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Cuerpos cero.")
        ratios = lower_wicks[valid] / bodies[valid]
        avg_ratio = float(np.mean(ratios))
        if avg_ratio > 1.5:
            signal = "PRESIÓN COMPRADORA ALTA"
            interp = (f"Mecha inferior promedio = {avg_ratio:.2f}x el cuerpo. "
                      f"Los compradores rechazan activamente los mínimos. "
                      f"⚡ Presión compradora creciente. Tensión pre-boom alta.")
        elif avg_ratio > 0.7:
            signal = "PRESIÓN COMPRADORA LEVE"
            interp = f"Ratio mecha/cuerpo = {avg_ratio:.2f}. Algo de soporte en mínimos."
        elif avg_ratio < 0.2:
            signal = "SIN SOPORTE"
            interp = (f"Ratio mecha/cuerpo = {avg_ratio:.2f}. Casi sin mechas inferiores. "
                      f"Los vendedores dominan sin resistencia. Tensión pre-boom alta.")
        else:
            signal = "NORMAL"
            interp = f"Ratio mecha/cuerpo = {avg_ratio:.2f}. Estructura normal."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(avg_ratio, 4), signal=signal, interpretation=interp,
            metadata={"avg_wick_body_ratio": round(avg_ratio, 4)},
        )


@register
class BoomRangeCompression(AlgorithmBase):
    name = "boom.range_compress"
    category = "crash_boom"
    description = "ATR contrayéndose → explosión próxima. En BOOM la ruptura es alcista."

    def __init__(self, fast: int = 5, slow: int = 20) -> None:
        self.fast = fast
        self.slow = slow

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        if len(df) < self.slow + 1:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]),
                                   np.abs(low[1:] - close[:-1])))
        atr_fast = float(np.mean(tr[-self.fast:]))
        atr_slow = float(np.mean(tr[-self.slow:]))
        ratio = atr_fast / atr_slow if atr_slow else 1.0
        compression_pct = (1 - ratio) * 100
        if ratio < 0.5:
            signal = "COMPRESIÓN EXTREMA"
            interp = (f"ATR rápido ({atr_fast:.5f}) es solo {ratio:.2f}x el ATR lento. "
                      f"Compresión del {compression_pct:.1f}%. "
                      f"⚡ Volatilidad colapsada. En BOOM: la ruptura será alcista explosiva.")
        elif ratio < 0.7:
            signal = "COMPRESIÓN FUERTE"
            interp = (f"ATR rápido = {ratio:.2f}x ATR lento. Mercado comprimido. Boom explosivo esperado.")
        elif ratio < 0.85:
            signal = "COMPRESIÓN LEVE"
            interp = f"Leve compresión ({compression_pct:.1f}%). Monitorear."
        else:
            signal = "SIN COMPRESIÓN"
            interp = "Volatilidad normal. Sin compresión."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=round(ratio, 4), signal=signal, interpretation=interp,
            metadata={"atr_ratio": round(ratio, 4), "atr_fast": round(atr_fast, 6),
                      "atr_slow": round(atr_slow, 6), "compression_pct": round(compression_pct, 2)},
        )


@register
class BoomCandleBodySequence(AlgorithmBase):
    name = "boom.body_seq"
    category = "crash_boom"
    description = "Patrón de cuerpos en últimas 5 velas. Cuerpos bajistas crecientes = tensión pre-boom."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")
        recent = df.tail(5)
        if len(recent) < 5:
            return AlgorithmResult(self.name, symbol, 0.0, "INSUFICIENTE", "Insuficiente data.")
        bodies = (recent["close"] - recent["open"]).abs().values
        is_bearish = (recent["close"].values < recent["open"].values)
        growing = all(bodies[i] < bodies[i + 1] for i in range(len(bodies) - 1))
        shrinking = all(bodies[i] > bodies[i + 1] for i in range(len(bodies) - 1))
        all_bear = all(is_bearish)
        body_sequence = [round(float(b), 6) for b in bodies]
        if growing and all_bear:
            signal = "IMPULSO BAJISTA CRECIENTE"
            interp = (f"5 velas bajistas con cuerpos crecientes: {body_sequence}. "
                      f"⚡ IMPULSO BAJISTA EN ESCALADA. Máxima tensión pre-boom.")
        elif growing:
            signal = "CUERPOS CRECIENTES"
            interp = f"Cuerpos en crecimiento: {body_sequence}. Momentum acelerando."
        elif shrinking and all_bear:
            signal = "IMPULSO DEBILITANDO"
            interp = f"Velas bajistas pero cuerpos decrecientes: {body_sequence}. Vendedores perdiendo fuerza."
        elif shrinking:
            signal = "CUERPOS DECRECIENTES"
            interp = f"Momentum general debilitando: {body_sequence}."
        else:
            signal = "SECUENCIA MIXTA"
            interp = f"Cuerpos sin patrón claro: {body_sequence}."
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=float(bodies[-1]), signal=signal, interpretation=interp,
            metadata={"body_sequence": body_sequence, "all_bearish": bool(all_bear)},
        )
