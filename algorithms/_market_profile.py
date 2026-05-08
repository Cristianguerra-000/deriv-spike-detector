"""Clasifica cada símbolo Deriv en un perfil de mercado.

El perfil determina qué conjunto de algoritmos se le aplica.
"""
from __future__ import annotations

from enum import Enum


class MarketProfile(str, Enum):
    CRASH_BOOM = "crash_boom"       # Crash 500, Boom 1000, etc.
    VOLATILITY = "volatility"       # R_10, R_25, R_50, R_75, R_100, 1HZ*
    FOREX = "forex"                 # EUR/USD, GBP/USD, etc.
    INDICES = "indices"             # US30, SPX500, etc.
    CRYPTO = "crypto"               # BTC/USD, ETH/USD, etc.
    STEP = "step"                   # Step Index
    JUMP = "jump"                   # Jump Index 10-100
    RANGE_BREAK = "range_break"     # Range Break 100/200
    UNKNOWN = "unknown"


def get_profile(symbol: str, market: str = "") -> MarketProfile:
    s = symbol.upper()

    if s.startswith("CRASH") or s.startswith("BOOM"):
        return MarketProfile.CRASH_BOOM
    if s.startswith("R_") or s.startswith("1HZ"):
        return MarketProfile.VOLATILITY
    if "STPRNG" in s:
        return MarketProfile.STEP
    if s.startswith("JD"):
        return MarketProfile.JUMP
    if s.startswith("RDB"):
        return MarketProfile.RANGE_BREAK
    if market == "forex":
        return MarketProfile.FOREX
    if market == "cryptocurrency":
        return MarketProfile.CRYPTO
    if market in ("indices", "stocks"):
        return MarketProfile.INDICES

    return MarketProfile.UNKNOWN
