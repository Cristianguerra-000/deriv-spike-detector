"""Clase base para todos los algoritmos del laboratorio.

Convención: 1 algoritmo por archivo. Cada archivo expone una subclase de
`AlgorithmBase` y la registra automáticamente vía `@register`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar

import pandas as pd


@dataclass
class AlgorithmResult:
    algorithm: str
    symbol: str
    value: Any
    # Etiqueta corta legible: ALCISTA, BAJISTA, NEUTRO, SOBRECOMPRADO, etc.
    signal: str = "NEUTRO"
    # Frase completa que explica qué está pasando en el mercado
    interpretation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "symbol": self.symbol,
            "value": self.value,
            "signal": self.signal,
            "interpretation": self.interpretation,
            "metadata": self.metadata,
        }


class AlgorithmBase(ABC):
    name: ClassVar[str] = ""
    category: ClassVar[str] = ""
    description: ClassVar[str] = ""

    @abstractmethod
    def run(self, df: pd.DataFrame, symbol: str) -> AlgorithmResult:
        """Recibe DataFrame con columnas: time, open, high, low, close, volume?."""


# ---------------------------------------------------------------------------
# Registro global
# ---------------------------------------------------------------------------
REGISTRY: dict[str, type[AlgorithmBase]] = {}


def register(cls: type[AlgorithmBase]) -> type[AlgorithmBase]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} debe definir 'name'")
    if cls.name in REGISTRY:
        raise ValueError(f"Algoritmo duplicado: {cls.name}")
    REGISTRY[cls.name] = cls
    return cls
