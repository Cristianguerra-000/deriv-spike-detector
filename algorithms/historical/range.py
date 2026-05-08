"""Detecta máximo y mínimo histórico en la ventana cargada."""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


@register
class HistoricalRange(AlgorithmBase):
    name = "hist.range"
    category = "historical"
    description = "Máximo, mínimo y rango total del histórico recibido."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        hi = float(df["high"].max())
        lo = float(df["low"].min())
        rng = hi - lo
        mid = (hi + lo) / 2
        last = float(df["close"].iloc[-1])

        # Rango como % del precio actual
        range_pct = (rng / lo * 100) if lo > 0 else 0
        # Posición del último precio dentro del rango (0%=fondo, 100%=techo)
        pos_pct = ((last - lo) / rng * 100) if rng > 0 else 50

        if range_pct > 8:
            signal = "RANGO AMPLIO"
            rango_label = "muy amplio"
        elif range_pct > 3:
            signal = "RANGO NORMAL"
            rango_label = "normal"
        else:
            signal = "RANGO ESTRECHO"
            rango_label = "comprimido"

        pos_label = "cerca del TECHO" if pos_pct > 70 else ("cerca del PISO" if pos_pct < 30 else "en zona MEDIA")

        interp = (
            f"Rango histórico {rango_label}: {rng:.3f} pts ({range_pct:.1f}% del precio). "
            f"Máx: {hi:.3f} | Mín: {lo:.3f} | Medio: {mid:.3f}. "
            f"Precio actual {pos_label} del rango ({pos_pct:.0f}%). "
            f"{'Zona de riesgo: precio en extremo superior.' if pos_pct > 85 else 'Zona de oportunidad: precio en extremo inferior.' if pos_pct < 15 else ''}"
        )

        return AlgorithmResult(
            algorithm=self.name,
            symbol=symbol,
            value=round(rng, 3),
            signal=signal,
            interpretation=interp,
            metadata={"high": hi, "low": lo, "range": round(rng, 3), "range_pct": round(range_pct, 2), "pos_pct": round(pos_pct, 1), "bars": len(df)},
        )
