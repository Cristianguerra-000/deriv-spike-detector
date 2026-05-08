"""CRASH #5 — Spike Cluster Risk.

Detecta si estamos en una zona de "cluster": varios crashes
ocurrieron en un período muy corto (< 50% del intervalo normal).

Los clusters indican que el mercado está en modo de alta turbulencia.
Después de un cluster, el mercado suele descansar un tiempo largo.
"""
from __future__ import annotations

import re

import pandas as pd

from algorithms._base import AlgorithmBase, AlgorithmResult, register
from algorithms.crash_boom.spike_detector import SPIKE_ATR_MULTIPLIER


@register
class CrashSpikeClusterRisk(AlgorithmBase):
    name = "crash.spike_cluster"
    category = "crash_boom"
    description = "Detecta clusters de crashes y evalúa si el mercado está en fase turbulenta."

    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        if "CRASH" not in symbol.upper():
            return AlgorithmResult(self.name, symbol, None, "N/A", "Solo para índices CRASH.")

        nums = re.findall(r"\d+", symbol)
        declared = int(nums[0]) if nums else 500
        cluster_threshold = declared * 0.4  # < 40% del intervalo = cluster

        window = df.tail(declared * 2).reset_index(drop=True)
        body = (window["close"] - window["open"]).abs()
        normal_body = float(body.quantile(0.75))
        threshold = normal_body * SPIKE_ATR_MULTIPLIER

        wick = window["open"].clip(lower=window["close"]) - window["low"]
        spike_pos = wick[wick > threshold].index.tolist()

        if len(spike_pos) < 2:
            return AlgorithmResult(
                self.name, symbol, 0, "SIN CLUSTER",
                "No hay suficientes spikes para detectar clusters.",
            )

        # Detectar pares de spikes cercanos
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
                f"⚠️ CLUSTER ACTIVO: dos crashes separados solo {gap} velas "
                f"(umbral de cluster: <{cluster_threshold:.0f} velas). "
                f"El mercado está en MODO TURBULENTO. "
                f"Alta volatilidad, los spikes son impredecibles. "
                f"Estrategia conservadora: esperar estabilización antes de operar."
            )
        elif cluster_count > 0:
            signal = "POST-CLUSTER"
            interp = (
                f"Hubo {cluster_count} cluster(s) en la ventana de análisis, "
                f"pero el último cluster fue hace un tiempo. "
                f"Mercado probablemente en fase de normalización. "
                f"Los clusters históricos muestran que este índice puede ser turbulento."
            )
        else:
            signal = "SIN CLUSTER"
            interp = (
                f"No se detectaron clusters en la ventana de {len(window)} velas. "
                f"Los crashes han ocurrido con separación normal (>{cluster_threshold:.0f} velas). "
                f"Mercado en comportamiento estándar. Patrón de spikes regular."
            )

        return AlgorithmResult(
            algorithm=self.name, symbol=symbol,
            value=cluster_count, signal=signal, interpretation=interp,
            metadata={
                "cluster_count": cluster_count,
                "cluster_threshold_bars": round(cluster_threshold, 0),
                "in_recent_cluster": in_recent_cluster,
                "spike_count_in_window": len(spike_pos),
            },
        )
