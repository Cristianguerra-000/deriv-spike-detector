"""Auto-importa todos los algoritmos para que se registren."""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from algorithms._base import REGISTRY, AlgorithmBase, AlgorithmResult, register

_PKG_DIR = Path(__file__).parent

for sub in _PKG_DIR.iterdir():
    if sub.is_dir() and not sub.name.startswith("_"):
        for mod in pkgutil.iter_modules([str(sub)]):
            if not mod.name.startswith("_"):
                importlib.import_module(f"algorithms.{sub.name}.{mod.name}")

__all__ = ["REGISTRY", "AlgorithmBase", "AlgorithmResult", "register"]
