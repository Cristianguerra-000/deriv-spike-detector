"""Cliente WebSocket asíncrono para la API de Deriv.

Documentación: https://developers.deriv.com/docs/websockets
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import websockets
from loguru import logger

from config.settings import DerivConfig


class DerivClient:
    """Cliente WebSocket ligero para Deriv con request/response por req_id."""

    def __init__(self, config: DerivConfig) -> None:
        self._config = config
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._req_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._listener_task: asyncio.Task[None] | None = None
        self._subscriptions: dict[str, asyncio.Queue[dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        logger.info("Conectando a Deriv WS: {}", self._config.ws_url)
        self._ws = await websockets.connect(self._config.ws_endpoint)
        self._listener_task = asyncio.create_task(self._listen())
        await self.authorize()

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._ws:
            await self._ws.close()
        logger.info("Conexión Deriv cerrada")

    async def __aenter__(self) -> "DerivClient":
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Mensajería
    # ------------------------------------------------------------------
    async def _listen(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                req_id = msg.get("req_id")
                sub_id = msg.get("subscription", {}).get("id") if isinstance(msg.get("subscription"), dict) else None

                # Entrega a suscripción si corresponde
                if sub_id and sub_id in self._subscriptions:
                    await self._subscriptions[sub_id].put(msg)

                if req_id in self._pending:
                    fut = self._pending.pop(req_id)
                    if not fut.done():
                        fut.set_result(msg)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover
            logger.exception("Listener Deriv falló: {}", exc)

    async def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self._ws is not None, "Llama a connect() primero"
        self._req_id += 1
        payload = {**payload, "req_id": self._req_id}
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_event_loop().create_future()
        self._pending[self._req_id] = fut
        await self._ws.send(json.dumps(payload))
        response = await asyncio.wait_for(fut, timeout=30)
        if "error" in response:
            raise RuntimeError(f"Deriv error: {response['error']}")
        return response

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------
    async def authorize(self) -> dict[str, Any]:
        return await self.send({"authorize": self._config.api_token})

    async def active_symbols(self, product_type: str = "basic") -> list[dict[str, Any]]:
        resp = await self.send({"active_symbols": "brief", "product_type": product_type})
        return resp.get("active_symbols", [])

    async def ticks_history(
        self,
        symbol: str,
        count: int = 1000,
        granularity: int = 60,
        style: str = "candles",
    ) -> dict[str, Any]:
        return await self.send({
            "ticks_history": symbol,
            "count": count,
            "end": "latest",
            "style": style,
            "granularity": granularity,
        })

    async def subscribe_ticks(self, symbol: str) -> AsyncIterator[dict[str, Any]]:
        resp = await self.send({"ticks": symbol, "subscribe": 1})
        sub_id = resp["subscription"]["id"]
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscriptions[sub_id] = queue
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscriptions.pop(sub_id, None)
            await self.send({"forget": sub_id})
