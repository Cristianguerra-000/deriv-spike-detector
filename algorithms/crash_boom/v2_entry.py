"""v2 · Entry Engine — Crash → SELL, Boom → BUY (jamás al revés).

Regla simple y humana
─────────────────────
Operamos a favor del evento, no contra él:

   CRASH 1000/500/300 → SELL (apuesta a la baja del spike)
   BOOM  1000/500/300 → BUY  (apuesta al alza del spike)

Condiciones para emitir entrada:
  1. data_quality.ok == True
  2. regime == POST_SPIKE  → entrada óptima: drift apenas reanudado
     · bars_since_spike entre 1 y 6
     · hazard_p50 < 25 %  (riesgo bajo de spike inminente contra nosotros)
     · al menos 5 spikes históricos para confiar en hazard
  3. (Opcional) similitud pre-spike < 0.7  (evita meternos en patrón pre-spike)

Si no se cumple TODO → WAIT (no se entra).
"""
from __future__ import annotations

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.v2_spike_state import get_state
from algorithms.crash_boom.v2_regime import classify_regime
from algorithms.crash_boom.v2_hazard_model import prob_spike
from algorithms.crash_boom.v2_pre_spike_capture import similarity_to_memory
from algorithms.crash_boom.v2_quality import check_quality


MIN_HISTORICAL_SPIKES = 5
MAX_HAZARD_P50_FOR_ENTRY = 0.25
MAX_SIMILARITY_FOR_ENTRY = 0.70
ENTRY_WINDOW = (1, 6)  # bars_since_spike permitido


def decide_entry(df: pd.DataFrame, symbol: str) -> dict:
    qual = check_quality(df, symbol)
    if not qual["ok"]:
        return {"action": "WAIT", "reason": f"Datos no aptos: {qual['reason']}"}

    state = get_state(symbol)
    if len(state.intervals) < MIN_HISTORICAL_SPIKES:
        return {"action": "WAIT",
                "reason": f"Sólo {len(state.intervals)} intervalos observados; se necesitan ≥ {MIN_HISTORICAL_SPIKES}."}

    info = classify_regime(symbol, df)
    if info["regime"] != "POST_SPIKE":
        return {"action": "WAIT",
                "reason": f"Régimen {info['regime']}: no es ventana de entrada óptima."}

    bs = info["bars_since"] or 0
    if not (ENTRY_WINDOW[0] <= bs <= ENTRY_WINDOW[1]):
        return {"action": "WAIT",
                "reason": f"Velas tras spike = {bs}; fuera de ventana {ENTRY_WINDOW}."}

    p50 = prob_spike(state.intervals, bs, 50)
    if p50["p"] is None or p50["p"] > MAX_HAZARD_P50_FOR_ENTRY:
        return {"action": "WAIT",
                "reason": f"Hazard P50 = {(p50['p'] or 1)*100:.1f}% supera {MAX_HAZARD_P50_FOR_ENTRY*100:.0f}%."}

    sim = similarity_to_memory(symbol, df)
    if sim["matches"] >= 3 and sim["best"] > MAX_SIMILARITY_FOR_ENTRY:
        return {"action": "WAIT",
                "reason": f"Estado actual similar ({sim['best']*100:.0f}%) a patrón pre-spike."}

    side = state.side
    action = "SELL" if side == "crash" else "BUY"
    reason = (
        f"{side.upper()}: régimen POST_SPIKE ({bs} velas desde spike), "
        f"hazard P50={p50['p']*100:.1f}% bajo, similitud pre-spike "
        f"{sim['best']*100 if sim['matches']>=3 else 0:.0f}%. "
        f"Entrada a favor del drift {'bajista' if side=='boom' else 'alcista'}."
    )
    return {
        "action": action, "reason": reason,
        "bars_since_spike": bs, "p50": p50["p"],
        "similarity": sim.get("best", 0.0), "side": side,
    }


@register
class EntryV2Algo(AlgorithmBase):
    name = "cb.v2.entry"
    category = "crash_boom"
    description = "Entry engine v2 — Crash→SELL, Boom→BUY, sólo en condiciones óptimas."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        sym = symbol.upper()
        if "CRASH" not in sym and "BOOM" not in sym:
            return AlgorithmResult(self.name, symbol, None, "N/A", "Sólo Crash/Boom.")

        d = decide_entry(df, symbol)
        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=d["action"], signal=d["action"], interpretation=d["reason"],
            metadata=d,
        )
