"""Carga centralizada de configuración desde variables de entorno."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class DerivConfig:
    api_token: str
    app_id: str
    ws_url: str

    @property
    def ws_endpoint(self) -> str:
        return f"{self.ws_url}?app_id={self.app_id}"


@dataclass(frozen=True)
class FirebaseConfig:
    credentials_path: str
    project_id: str


@dataclass(frozen=True)
class LabConfig:
    env: str
    log_level: str
    deriv: DerivConfig
    firebase: FirebaseConfig


def _require(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None or value == "" or value.startswith("tu_"):
        raise RuntimeError(
            f"Falta la variable de entorno '{key}'. "
            f"Cópiala desde .env.example a .env y rellénala."
        )
    return value


def load_config() -> LabConfig:
    return LabConfig(
        env=os.getenv("LAB_ENV", "development"),
        log_level=os.getenv("LAB_LOG_LEVEL", "INFO"),
        deriv=DerivConfig(
            api_token=_require("DERIV_API_TOKEN"),
            app_id=os.getenv("DERIV_APP_ID", "1089"),
            ws_url=os.getenv("DERIV_WS_URL", "wss://ws.derivws.com/websockets/v3"),
        ),
        firebase=FirebaseConfig(
            credentials_path=os.getenv("FIREBASE_CREDENTIALS", "./serviceAccountKey.json"),
            project_id=os.getenv("FIREBASE_PROJECT_ID", ""),
        ),
    )
