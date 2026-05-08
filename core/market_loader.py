"""Descarga el catálogo completo de mercados de Deriv y los clasifica."""
from __future__ import annotations

from typing import Any

from loguru import logger

from core.deriv_client import DerivClient


# Categorías sintéticas relevantes
SYNTHETIC_GROUPS = {
    "crash_boom": lambda s: s.startswith(("CRASH", "BOOM")),
    "volatility": lambda s: s.startswith("R_") or s.startswith("1HZ"),
    "jump": lambda s: s.startswith("JD"),
    "step": lambda s: "STPRNG" in s,
    "range_break": lambda s: s.startswith("RDB"),
}


def classify(symbol: str, market: str) -> str:
    for tag, pred in SYNTHETIC_GROUPS.items():
        if pred(symbol):
            return tag
    return market  # forex, indices, commodities, cryptocurrency, stocks…


async def fetch_all_markets(client: DerivClient) -> list[dict[str, Any]]:
    symbols = await client.active_symbols("basic")
    enriched: list[dict[str, Any]] = []
    for s in symbols:
        enriched.append({
            "symbol": s["symbol"],
            "display_name": s.get("display_name"),
            "market": s.get("market"),
            "submarket": s.get("submarket"),
            "category": classify(s["symbol"], s.get("market", "")),
            "pip": s.get("pip"),
            "exchange_is_open": s.get("exchange_is_open"),
        })
    logger.info("Mercados Deriv cargados: {}", len(enriched))
    return enriched
