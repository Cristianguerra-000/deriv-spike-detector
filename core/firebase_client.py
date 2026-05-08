"""Cliente Firebase / Firestore para persistencia del laboratorio."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore
from loguru import logger

from config.settings import FirebaseConfig


class FirebaseClient:
    """Wrapper sobre Firestore con métodos de alto nivel."""

    def __init__(self, config: FirebaseConfig) -> None:
        self._config = config
        if not firebase_admin._apps:
            # Soporte para credenciales inline (Railway/CI) via FIREBASE_CREDENTIALS_JSON
            creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
            if creds_json:
                cred = credentials.Certificate(json.loads(creds_json))
            else:
                cred = credentials.Certificate(config.credentials_path)
            firebase_admin.initialize_app(cred, {"projectId": config.project_id})
            logger.info("Firebase inicializado: proyecto={}", config.project_id)
        self._db = firestore.client()

    @property
    def db(self):  # noqa: ANN201
        return self._db

    # ------------------------------------------------------------------
    def save_market_catalog(self, symbols: list[dict[str, Any]]) -> None:
        batch = self._db.batch()
        col = self._db.collection("markets")
        for s in symbols:
            ref = col.document(s["symbol"])
            batch.set(ref, s, merge=True)
        batch.commit()
        logger.info("Catálogo guardado: {} símbolos", len(symbols))

    def save_candles(self, symbol: str, granularity: int, candles: list[dict[str, Any]]) -> None:
        doc = (
            self._db.collection("candles")
            .document(symbol)
            .collection(str(granularity))
            .document("latest")
        )
        doc.set({"candles": candles, "count": len(candles)}, merge=True)

    def save_algorithm_result(
        self,
        algorithm: str,
        symbol: str,
        result: dict[str, Any],
    ) -> None:
        payload = dict(result)
        meta = dict(payload.get("metadata") or {})
        meta["ts"] = datetime.now(timezone.utc).isoformat()
        payload["metadata"] = meta
        # Escribe/sobreescribe en ruta fija: results/{algorithm}/symbols/{symbol}
        # Esto evita documentos implícitos y la necesidad de índices compuestos.
        (
            self._db
            .collection("results")
            .document(algorithm)
            .collection("symbols")
            .document(symbol)
            .set(payload)
        )
        # Stub en el doc padre para que getDocs("results") devuelva los algoritmos.
        self._db.collection("results").document(algorithm).set(
            {"name": algorithm}, merge=True
        )
