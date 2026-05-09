"""CRASH #40 / BOOM #40 — Reversal Confirmation.

Señal final de confirmación de reanudación del drift.
Combina: precio sobre/bajo EMA20, RSI en zona de tendencia,
y dirección dominante de velas en las últimas 10 barras.
Confirma que el drift se reanudó con solidez después del spike.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.post_spike_behavior import _find_last_crash
from algorithms.crash_boom.post_boom_behavior import _find_last_boom
from algorithms.crash_boom.post_crash_momentum import _rsi


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


@register
class CrashReversalConfirmation(AlgorithmBase):
    name = "crash.reversal"
    category = "crash_boom"
    description = "Confirma que el drift alcista se reanudó tras el crash. Score 0–3."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_crash(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN CRASHES",
                                   "No se detectaron crashes en las últimas 300 velas.")

        post = window.iloc[last_idx + 1:]
        if len(post) < 5:
            return AlgorithmResult(self.name, symbol, None, "ESPERANDO",
                                   "Sin suficientes velas post-crash para confirmar.")

        current = float(post["close"].iloc[-1])
        score = 0
        details = []

        # 1. Precio sobre EMA20 (tendencia alcista)
        ema20 = _ema(window["close"], 20)
        ema_now = float(ema20.iloc[-1])
        if current > ema_now:
            score += 1
            details.append(f"✓ Precio ({current:.5f}) > EMA20 ({ema_now:.5f})")
        else:
            details.append(f"✗ Precio ({current:.5f}) < EMA20 ({ema_now:.5f})")

        # 2. RSI en zona alcista (>50)
        last10 = post.tail(10)
        rsi_val = _rsi(last10["close"].values, period=min(7, len(last10) - 1))
        if rsi_val > 50:
            score += 1
            details.append(f"✓ RSI={rsi_val:.1f} > 50 (zona alcista)")
        else:
            details.append(f"✗ RSI={rsi_val:.1f} ≤ 50")

        # 3. Mayoría de velas alcistas en las últimas 10 barras
        bull_count = int((last10["close"] > last10["open"]).sum())
        if bull_count >= 6:
            score += 1
            details.append(f"✓ {bull_count}/10 velas alcistas")
        else:
            details.append(f"✗ {bull_count}/10 velas alcistas (insuficiente)")

        bars_since = len(post)

        if score == 3:
            signal = "DRIFT CONFIRMADO"
            interp = (f"3/3 condiciones cumplidas. Drift alcista post-crash plenamente restablecido. "
                      f"({bars_since} barras desde crash). " + " | ".join(details))
        elif score == 2:
            signal = "DRIFT PROBABLE"
            interp = (f"2/3 condiciones. Drift alcista probable pero sin confirmación total. "
                      f"| ".join(details))
        elif score == 1:
            signal = "DRIFT DÉBIL"
            interp = (f"1/3 condiciones. El mercado aún no confirma el drift alcista. "
                      f"| ".join(details))
        else:
            signal = "SIN REVERSAL"
            interp = (f"0/3 condiciones. El mercado no ha confirmado la reanudación del drift. "
                      f"Alta incertidumbre post-crash. | ".join(details))

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=float(score), signal=signal, interpretation=interp,
            metadata={
                "score": score,
                "price_above_ema20": current > ema_now,
                "rsi_post": round(rsi_val, 2),
                "bull_candles_10": bull_count,
                "bars_since_crash": bars_since,
            },
        )


@register
class BoomReversalConfirmation(AlgorithmBase):
    name = "boom.reversal"
    category = "crash_boom"
    description = "Confirma que el drift bajista se reanudó tras el boom. Score 0–3."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        window = df.tail(300).reset_index(drop=True)
        last_idx = _find_last_boom(window)

        if last_idx is None:
            return AlgorithmResult(self.name, symbol, None, "SIN BOOMS",
                                   "No se detectaron booms en las últimas 300 velas.")

        post = window.iloc[last_idx + 1:]
        if len(post) < 5:
            return AlgorithmResult(self.name, symbol, None, "ESPERANDO",
                                   "Sin suficientes velas post-boom para confirmar.")

        current = float(post["close"].iloc[-1])
        score = 0
        details = []

        # 1. Precio bajo EMA20 (tendencia bajista)
        ema20 = _ema(window["close"], 20)
        ema_now = float(ema20.iloc[-1])
        if current < ema_now:
            score += 1
            details.append(f"✓ Precio ({current:.5f}) < EMA20 ({ema_now:.5f})")
        else:
            details.append(f"✗ Precio ({current:.5f}) > EMA20 ({ema_now:.5f})")

        # 2. RSI en zona bajista (<50)
        last10 = post.tail(10)
        rsi_val = _rsi(last10["close"].values, period=min(7, len(last10) - 1))
        if rsi_val < 50:
            score += 1
            details.append(f"✓ RSI={rsi_val:.1f} < 50 (zona bajista)")
        else:
            details.append(f"✗ RSI={rsi_val:.1f} ≥ 50")

        # 3. Mayoría de velas bajistas en las últimas 10 barras
        bear_count = int((last10["close"] < last10["open"]).sum())
        if bear_count >= 6:
            score += 1
            details.append(f"✓ {bear_count}/10 velas bajistas")
        else:
            details.append(f"✗ {bear_count}/10 velas bajistas (insuficiente)")

        bars_since = len(post)

        if score == 3:
            signal = "DRIFT CONFIRMADO"
            interp = (f"3/3 condiciones cumplidas. Drift bajista post-boom plenamente restablecido. "
                      f"({bars_since} barras desde boom). " + " | ".join(details))
        elif score == 2:
            signal = "DRIFT PROBABLE"
            interp = (f"2/3 condiciones. Drift bajista probable. | ".join(details))
        elif score == 1:
            signal = "DRIFT DÉBIL"
            interp = (f"1/3 condiciones. El mercado no confirma el drift bajista aún. | ".join(details))
        else:
            signal = "SIN REVERSAL"
            interp = (f"0/3 condiciones. Sin confirmación de reanudación del drift bajista. "
                      f"| ".join(details))

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=float(score), signal=signal, interpretation=interp,
            metadata={
                "score": score,
                "price_below_ema20": current < ema_now,
                "rsi_post": round(rsi_val, 2),
                "bear_candles_10": bear_count,
                "bars_since_boom": bars_since,
            },
        )
