"""BOOM #5 — Boom Cluster Risk.

Detecta si ocurrieron varios booms en un período corto.
Clusters de booms = mercado en euforia compradora extrema → peligroso para cortos.
"""
from __future__ import annotations

import re

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class BoomClusterRisk(AlgorithmBase):
    name = "boom.spike_cluster"
    category = "crash_boom"
    description = "Detecta clusters de booms. Clusters = mercado en euforia → peligroso para cortos."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "BOOM" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices BOOM.")

        nums = re.findall(r"\d+", symbol)
        declared = int(nums[0]) if nums else 500
        cluster_threshold = declared * 0.4

        window = df.tail(declared * 2).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["high"] - window[["open", "close"]].max(axis=1)
        spike_pos = wick[wick > threshold].index.tolist()

        if len(spike_pos) < 2:
            return AlgorithmResult(
                self.name, symbol, 0, "SIN CLUSTER",
                "No hay suficientes booms para detectar clusters.",
            )

        cluster_pairs = [
            (spike_pos[i], spike_pos[i + 1])
            for i in range(len(spike_pos) - 1)
            if (spike_pos[i + 1] - spike_pos[i]) < cluster_threshold
        ]

        in_recent_cluster = (
            cluster_pairs and
            len(window) - 1 - cluster_pairs[-1][1] < declared
        )

        cluster_count = len(cluster_pairs)

        if in_recent_cluster:
            last_pair = cluster_pairs[-1]
            gap = last_pair[1] - last_pair[0]
            signal = "CLUSTER ACTIVO"
            interp = (
                f"⚡ CLUSTER DE BOOMS ACTIVO: dos booms separados solo {gap} velas "
                f"(umbral de cluster: <{cluster_threshold:.0f} velas). "
                f"Mercado en EUFORIA COMPRADORA. Los booms son impredecibles. "
                f"Estrategia conservadora: esperar estabilización antes de entrar en corto."
            )
        elif cluster_count > 0:
            signal = "POST-CLUSTER"
            interp = (
                f"Hubo {cluster_count} cluster(s) de booms en la ventana, pero fue hace un tiempo. "
                f"Mercado en normalización post-euforia. "
                f"El drift bajista debería estar restablecido."
            )
        else:
            signal = "SIN CLUSTER"
            interp = (
                f"No se detectaron clusters de booms en {len(window)} velas analizadas. "
                f"Los booms tienen separación normal. Mercado en comportamiento estándar."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=cluster_count, signal=signal, interpretation=interp,
            metadata={
                "cluster_count": cluster_count,
                "cluster_threshold_bars": round(cluster_threshold, 0),
                "in_recent_cluster": in_recent_cluster,
                "boom_count_in_window": len(spike_pos),
            },
        )
