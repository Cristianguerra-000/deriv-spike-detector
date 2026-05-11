"""v2 · Data Quality Gate — bloquea señales si los datos no son confiables.

Sin esto, los demás módulos pueden producir resultados absurdos cuando:
  · hay gaps en el feed
  · el histórico es demasiado corto
  · el símbolo no es Crash/Boom (regex estricto)
  · todas las velas son idénticas (feed congelado)
"""
from __future__ import annotations

import re

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register


SYMBOL_RE = re.compile(r"^(?:CRASH|BOOM)\s?\d+(?:\s?INDEX)?$", re.IGNORECASE)
MIN_BARS = 100


def check_quality(df: pd.DataFrame, symbol: str) -> dict:
    s = symbol.strip()
    if not SYMBOL_RE.match(s):
        return {"ok": False, "reason": f"Símbolo «{symbol}» no es Crash/Boom válido."}
    if len(df) < MIN_BARS:
        return {"ok": False, "reason": f"Sólo {len(df)} velas; se necesitan ≥ {MIN_BARS}."}
    last_50 = df.tail(50)
    if last_50["close"].nunique() <= 2:
        return {"ok": False, "reason": "Feed sospechoso: precio casi constante en las últimas 50 velas."}
    if "time" in df.columns:
        try:
            diffs = pd.to_numeric(df["time"]).diff().dropna()
            # M1: paso normal 60s. Toleramos hasta 90s
            big_gaps = int((diffs > 90).sum())
            if big_gaps > 5:
                return {"ok": False, "reason": f"{big_gaps} gaps grandes en el feed (>90s)."}
        except Exception:
            pass
    return {"ok": True, "reason": "Datos íntegros."}


@register
class DataQualityAlgo(AlgorithmBase):
    name = "cb.v2.quality"
    category = "crash_boom"
    description = "Data quality gate. Si falla, ninguna señal v2 debe operarse."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        info = check_quality(df, symbol)
        signal = "OK" if info["ok"] else "BLOQUEADO"
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=info["ok"], signal=signal, interpretation=info["reason"],
            metadata=info,
        )
