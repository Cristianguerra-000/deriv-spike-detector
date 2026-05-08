"""Buffer deslizante de velas por símbolo.

Mantiene las últimas N velas en memoria. Cuando llega una vela nueva
(de la suscripción live), la agrega y descarta la más antigua.
Los algoritmos siempre leen desde aquí → ventana siempre actualizada.
"""
from __future__ import annotations

from collections import deque
from typing import Any

import pandas as pd


class CandleBuffer:
    """Ventana deslizante de velas OHLC para un símbolo."""

    def __init__(self, symbol: str, max_size: int = 600) -> None:
        self.symbol = symbol
        self.max_size = max_size
        self._buf: deque[dict[str, Any]] = deque(maxlen=max_size)
        self._last_epoch: int = 0

    def load_history(self, candles: list[dict[str, Any]]) -> None:
        """Carga el histórico inicial (llamada única al arrancar)."""
        self._buf.clear()
        for c in candles:
            self._buf.append(self._normalize(c))
        if self._buf:
            self._last_epoch = int(self._buf[-1]["time"])

    def update(self, ohlc: dict[str, Any]) -> bool:
        """Agrega o actualiza la vela más reciente.

        Devuelve True si es una vela NUEVA (cierre de vela anterior).
        Devuelve False si es una actualización de la vela abierta actual.
        """
        epoch = int(ohlc.get("open_time") or ohlc.get("epoch") or 0)
        if epoch > self._last_epoch:
            # Vela nueva: la anterior ya cerró → momento de ejecutar algoritmos
            self._buf.append(self._normalize(ohlc))
            self._last_epoch = epoch
            return True
        else:
            # Actualización de la vela actual (aún abierta)
            if self._buf:
                self._buf[-1] = self._normalize(ohlc)
            return False

    def to_dataframe(self) -> pd.DataFrame:
        df = pd.DataFrame(list(self._buf))
        for col in ("open", "high", "low", "close"):
            df[col] = df[col].astype(float)
        return df

    def ready(self, min_bars: int = 30) -> bool:
        return len(self._buf) >= min_bars

    @staticmethod
    def _normalize(c: dict[str, Any]) -> dict[str, Any]:
        return {
            "time": int(c.get("open_time") or c.get("epoch") or 0),
            "open":  float(c.get("open",  0)),
            "high":  float(c.get("high",  0)),
            "low":   float(c.get("low",   0)),
            "close": float(c.get("close", 0)),
        }

    def __len__(self) -> int:
        return len(self._buf)
