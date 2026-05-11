"""Pipeline perpetuo: corre SIEMPRE, ejecuta algoritmos en cada nueva vela.

Flujo:
1. Conectar a Deriv WS y autenticar.
2. Cargar catálogo de mercados → Firestore.
3. Para cada símbolo objetivo:
   a. Cargar histórico inicial (600 velas) → CandleBuffer.
   b. Suscribirse a velas en vivo (granularity elegida).
4. Loop infinito: al cerrar cada vela → ejecutar algoritmos del perfil → Firestore.
5. Si se pierde la conexión → reconectar automáticamente con back-off.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pandas as pd
import websockets
from loguru import logger

import algorithms  # noqa: F401  fuerza auto-registro
from algorithms._base import REGISTRY, AlgorithmResult
from algorithms._market_profile import MarketProfile, get_profile
from config.settings import load_config
from core.candle_buffer import CandleBuffer
from core.deriv_client import DerivClient
from core.firebase_client import FirebaseClient
from core.market_loader import fetch_all_markets

# ─── Configuración ────────────────────────────────────────────────────────────
GRANULARITY = 60        # segundos por vela (1 minuto)
HISTORY_BARS = 600      # velas históricas iniciales por símbolo
MIN_BARS     = 50       # mínimo para ejecutar algoritmos
RECONNECT_WAIT = 10     # segundos antes de reconectar tras error

# Algoritmos universales (todos los mercados)
UNIVERSAL = {
    "math.sma", "math.ema", "math.wma",
    "stat.zscore", "stat.hurst", "stat.autocorrelation",
    "hist.range", "vol.atr",
}

# Algoritmos por perfil de mercado
PROFILE_ALGOS: dict[MarketProfile, set[str]] = {
    MarketProfile.CRASH_BOOM: {
        "cb.spike_detector",
        "micro.candle_anatomy", "micro.engulfing",
        "trend.lr_slope",
        # ── Detección y estado event-driven (v2 — núcleo) ──
        "cb.v2.state",          # estado persistente del spike
        "cb.v2.threshold",      # umbral MAD adaptativo
        "cb.v2.hazard",         # probabilidad real (Weibull + empírica)
        "cb.v2.pre_capture",    # captura pre-spike (aprendiz)
        "cb.v2.regime",         # DRIFT / OVERDUE / POST_SPIKE
        "cb.v2.entry",          # Crash→SELL, Boom→BUY
        "cb.v2.exit_time",      # time-stop antes del próximo spike
        "cb.v2.sizing",          # tamaño por hazard
        "cb.v2.quality",        # data quality gate
        "cb.v2.signal",         # ★ SEÑAL FINAL v2 (humano-legible)
        # ── Timing de spikes (sobreviven) ──
        "crash.spike_overdue", "crash.spike_magnitude",
        "crash.spike_interval_var", "crash.spike_cluster",
        "crash.tick_countdown", "crash.consec_spikes",
        "crash.freq_change",
        "boom.spike_overdue", "boom.spike_magnitude",
        "boom.spike_interval_var", "boom.spike_cluster",
        "boom.tick_countdown", "boom.consec_spikes",
        "boom.freq_change",
        # ── Drift (sobreviven los compuestos) ──
        "crash.drift_slope", "crash.drift_channel", "crash.drift_accel",
        "crash.drift_exhaust",
        "crash.recovery_traj", "crash.recovery_pct",
        "boom.drift_slope", "boom.drift_channel", "boom.drift_decel",
        "boom.drift_exhaust", "boom.drift_linear", "boom.drift_vol",
        "boom.micro_drift", "boom.drift_consist",
        "boom.correction_traj", "boom.correction_pct",
        # ── Tensión Pre-Spike (mantener score compuesto) ──
        "crash.tension", "crash.range_compress", "crash.bull_streak",
        "boom.tension", "boom.range_compress", "boom.bear_streak",
        # ── Post-Spike ──
        "crash.post_spike", "crash.retracement", "crash.recovery_speed",
        "crash.impact", "crash.post_mom",
        "crash.aftermath", "crash.reversal",
        "boom.post_spike", "boom.correction_lvl", "boom.correction_speed",
        "boom.impact", "boom.post_mom",
        "boom.aftermath", "boom.reversal",
    },
    MarketProfile.VOLATILITY: {
        "trend.rsi", "trend.macd", "trend.adx",
        "vol.bollinger", "vol.keltner",
        "micro.candle_anatomy",
    },
    MarketProfile.FOREX: {
        "trend.rsi", "trend.macd", "trend.adx",
        "vol.bollinger", "vol.keltner",
        "micro.candle_anatomy", "micro.engulfing",
        "trend.lr_slope",
    },
    MarketProfile.INDICES: {
        "trend.rsi", "trend.macd", "vol.bollinger",
        "micro.candle_anatomy",
    },
}


# ─── Selección de algoritmos por símbolo ──────────────────────────────────────
def get_algos_for(symbol: str, market: str) -> list[Any]:
    profile = get_profile(symbol, market)
    names = UNIVERSAL | PROFILE_ALGOS.get(profile, set())
    return [REGISTRY[n]() for n in names if n in REGISTRY]


# ─── Ejecutar algoritmos sobre un buffer ──────────────────────────────────────
async def run_algorithms(
    symbol: str,
    df: pd.DataFrame,
    algos: list[Any],
    firebase: FirebaseClient | None,
) -> None:
    for algo in algos:
        try:
            result: AlgorithmResult = algo.run(df, symbol)
            logger.info(
                "[{}] {} → {} | {}\n    ↳ {}",
                symbol, algo.name, result.signal, result.value,
                result.interpretation,
            )
            if firebase:
                firebase.save_algorithm_result(algo.name, symbol, result.to_dict())
        except Exception as exc:  # noqa: BLE001
            logger.warning("[{}] {} falló: {}", symbol, algo.name, exc)


# ─── Worker por símbolo ───────────────────────────────────────────────────────
async def symbol_worker(
    symbol: str,
    market: str,
    deriv: DerivClient,
    firebase: FirebaseClient | None,
) -> None:
    """Carga histórico, suscribe a velas y corre algoritmos en cada cierre."""
    buf = CandleBuffer(symbol, max_size=HISTORY_BARS + 50)
    algos = get_algos_for(symbol, market)
    profile = get_profile(symbol, market)

    logger.info("▶ Iniciando worker: {} [{}] — {} algoritmos", symbol, profile.value, len(algos))

    # Histórico inicial
    try:
        hist = await deriv.ticks_history(symbol, count=HISTORY_BARS, granularity=GRANULARITY)
        buf.load_history(hist.get("candles", []))
        logger.info("  {} → {} velas históricas cargadas", symbol, len(buf))
    except Exception as exc:  # noqa: BLE001
        logger.warning("  {} sin histórico: {}", symbol, exc)

    # Primera ejecución con histórico
    if buf.ready(MIN_BARS):
        await run_algorithms(symbol, buf.to_dataframe(), algos, firebase)

    # Suscripción perpetua a velas en vivo
    try:
        req_id = deriv._req_id + 1
        deriv._req_id = req_id
        fut: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
        deriv._pending[req_id] = fut

        payload = {
            "ticks_history": symbol,
            "count": 1,
            "end": "latest",
            "style": "candles",
            "granularity": GRANULARITY,
            "subscribe": 1,
            "req_id": req_id,
        }
        await deriv._ws.send(json.dumps(payload))
        sub_resp = await asyncio.wait_for(fut, timeout=15)
        sub_id = sub_resp.get("subscription", {}).get("id")
        if not sub_id:
            logger.warning("  {} sin sub_id, worker terminado", symbol)
            return

        queue: asyncio.Queue[dict] = asyncio.Queue()
        deriv._subscriptions[sub_id] = queue

        logger.info("  {} suscrito a velas en vivo (sub_id={})", symbol, sub_id)

        while True:
            msg = await queue.get()
            ohlc = msg.get("ohlc")
            if not ohlc:
                continue

            is_new_candle = buf.update(ohlc)

            if is_new_candle and buf.ready(MIN_BARS):
                # Nueva vela cerró → ejecutar todos los algoritmos
                await run_algorithms(symbol, buf.to_dataframe(), algos, firebase)

    except asyncio.CancelledError:
        logger.info("  {} worker cancelado", symbol)
    except Exception as exc:  # noqa: BLE001
        logger.exception("  {} worker error: {}", symbol, exc)


# ─── Loop principal con reconexión automática ────────────────────────────────
async def run_forever() -> None:
    cfg = load_config()

    firebase: FirebaseClient | None
    try:
        firebase = FirebaseClient(cfg.firebase)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Firebase no disponible: {}. Sin persistencia.", exc)
        firebase = None

    attempt = 0
    while True:
        attempt += 1
        logger.info("═══ Intento de conexión #{} ═══", attempt)
        try:
            async with DerivClient(cfg.deriv) as deriv:
                attempt = 0  # reset al conectar correctamente
                markets = await fetch_all_markets(deriv)

                if firebase:
                    firebase.save_market_catalog(markets)

                # Construir lista de símbolos con su market
                market_map = {m["symbol"]: m.get("market", "") for m in markets}

                # Filtrar: crash_boom + volatility + primeros forex
                target = []
                for m in markets:
                    cat = m["category"]
                    if cat in ("crash_boom", "volatility"):
                        target.append(m)
                    elif m.get("market") == "forex" and len([x for x in target if x.get("market") == "forex"]) < 10:
                        target.append(m)

                logger.info("Laboratorio activo: {} símbolos en tiempo real", len(target))

                # Lanzar un worker por símbolo (todos en paralelo)
                tasks = [
                    asyncio.create_task(
                        symbol_worker(m["symbol"], m.get("market", ""), deriv, firebase),
                        name=f"worker-{m['symbol']}",
                    )
                    for m in target
                ]

                # Esperar hasta que algún task falle (señal de reconexión)
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for t in pending:
                    t.cancel()
                for t in done:
                    if t.exception():
                        logger.error("Task {} falló: {}", t.get_name(), t.exception())

        except (websockets.ConnectionClosed, OSError, RuntimeError) as exc:
            logger.error("Conexión perdida: {}. Reconectando en {}s…", exc, RECONNECT_WAIT)
            await asyncio.sleep(RECONNECT_WAIT)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error inesperado: {}. Reconectando en {}s…", exc, RECONNECT_WAIT)
            await asyncio.sleep(RECONNECT_WAIT)


if __name__ == "__main__":
    import sys
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
    logger.add("logs/lab_{time:YYYY-MM-DD}.log", rotation="00:00", retention="7 days",
               level="INFO", encoding="utf-8")

    import pathlib
    pathlib.Path("logs").mkdir(exist_ok=True)

    logger.info("🔬 Laboratorio Deriv — modo PERPETUO")
    asyncio.run(run_forever())

