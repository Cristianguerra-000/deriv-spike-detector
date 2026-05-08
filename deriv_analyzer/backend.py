"""
╔══════════════════════════════════════════════════════════════════╗
║  DERIV SYNTHETIC INDICES — SPIKE DETECTION ENGINE v2.0          ║
║  ENFOQUE DIRECCIONAL:  BOOM → caza spike UP                     ║
║                        CRASH → caza spike DOWN                  ║
║  Algoritmos: Z-score Direccional, Bayesiano, HMM, Wavelet,      ║
║              Pattern-N, Bounce Zones, Momentum, Inter-Spike,    ║
║              Kalman Velocity, Tick Rate, Skew Direccional       ║
║  + Sistema de Operaciones Virtuales con historial completo      ║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import math
import os
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
from scipy import stats
from scipy.ndimage import uniform_filter1d
import pywt
from filterpy.kalman import KalmanFilter

# ─── CONFIG ──────────────────────────────────────────────────────
API_TOKEN  = "ASwvPnIeuj1FtaZ"
DERIV_WS   = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
APP_ID     = 1089
PORT       = int(os.environ.get("PORT", 8765))
_BASE_DIR  = Path(__file__).parent

INDICES = {
    "BOOM300N":  {"name": "Boom 300",   "type": "boom",  "freq": 300,  "col": "#00e676"},
    "BOOM500":   {"name": "Boom 500",   "type": "boom",  "freq": 500,  "col": "#69f0ae"},
    "BOOM1000":  {"name": "Boom 1000",  "type": "boom",  "freq": 1000, "col": "#b9f6ca"},
    "CRASH300N": {"name": "Crash 300",  "type": "crash", "freq": 300,  "col": "#ff1744"},
    "CRASH500":  {"name": "Crash 500",  "type": "crash", "freq": 500,  "col": "#ff5252"},
    "CRASH1000": {"name": "Crash 1000", "type": "crash", "freq": 1000, "col": "#ff8a80"},
}

WINDOW             = 500    # ventana estadística ampliada
HIST_SIZE          = 10000  # historial de precios (10 k ticks)
ZSCORE_THR         = 3.8    # umbral spike confirmado
PRE_SPIKE_VOL_DROP = 0.35   # compresión de vol pre-spike

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("deriv")


# ═══════════════════════════════════════════════════════════════════
#  SISTEMA DE OPERACIONES VIRTUALES
# ═══════════════════════════════════════════════════════════════════

class Operation:
    _counter = 0

    def __init__(self, symbol, name, direction, entry_price,
                 stake, entry_epoch, entry_tick, score, itype):
        Operation._counter += 1
        self.op_id       = Operation._counter
        self.symbol      = symbol
        self.name        = name
        self.direction   = direction      # "UP" | "DOWN"
        self.itype       = itype          # "boom" | "crash"
        self.entry_price = entry_price
        self.stake       = stake
        self.entry_epoch = entry_epoch
        self.entry_tick  = entry_tick
        self.score       = round(score, 3)
        self.status      = "OPEN"
        self.exit_price  = None
        self.exit_epoch  = None
        self.exit_tick   = None
        self.pnl         = 0.0
        self.reason      = ""
        self.max_ticks   = 60   # timeout en ticks

    def to_dict(self):
        return {
            "op_id":       self.op_id,
            "symbol":      self.symbol,
            "name":        self.name,
            "direction":   self.direction,
            "itype":       self.itype,
            "entry_price": round(self.entry_price, 5),
            "stake":       round(self.stake, 2),
            "score":       self.score,
            "status":      self.status,
            "exit_price":  round(self.exit_price, 5) if self.exit_price else None,
            "pnl":         round(self.pnl, 2),
            "reason":      self.reason,
            "entry_epoch": self.entry_epoch,
            "exit_epoch":  self.exit_epoch,
            "ticks_in":    (self.exit_tick - self.entry_tick) if self.exit_tick else 0,
        }


class OperationsManager:
    def __init__(self):
        self.balance         = 1000.0
        self.initial_balance = 1000.0
        self.open_ops        : List[Operation] = []
        self.closed_ops      : List[Operation] = []
        self.stake_pct       = 0.02    # 2% por operación
        self.max_concurrent  = 3
        self.min_score       = 0.62
        self.auto_trade      = True
        self.win_multiplier  = 0.92
        self.cooldown        : Dict[str, int] = {}
        self.cooldown_ticks  = 25
        self.total_pnl       = 0.0
        self.total_wins      = 0
        self.total_losses    = 0

    def _can_enter(self, sym: str, tick: int) -> bool:
        if not self.auto_trade:
            return False
        if self.balance < 1.0:
            return False
        last_close = self.cooldown.get(sym, 0)
        if tick - last_close < self.cooldown_ticks:
            return False
        if any(o.symbol == sym for o in self.open_ops):
            return False
        if len(self.open_ops) >= self.max_concurrent:
            return False
        return True

    def try_enter(self, analysis: dict) -> Optional[Operation]:
        sym   = analysis["symbol"]
        score = analysis.get("pre_spike_score", 0)
        alert = analysis.get("alert_level", "NORMAL")
        itype = analysis.get("type", "")

        if score < self.min_score:
            return None
        if alert not in ("ALTO", "CRÍTICO"):
            return None
        if not self._can_enter(sym, analysis.get("tick", 0)):
            return None

        direction = "UP" if itype == "boom" else "DOWN"
        stake = round(max(1.0, self.balance * self.stake_pct), 2)
        if stake > self.balance:
            return None

        self.balance -= stake
        op = Operation(
            symbol      = sym,
            name        = analysis.get("name", sym),
            direction   = direction,
            entry_price = analysis["price"],
            stake       = stake,
            entry_epoch = analysis["epoch"],
            entry_tick  = analysis.get("tick", 0),
            score       = score,
            itype       = itype,
        )
        self.open_ops.append(op)
        log.info(f"[OPS] ABIERTA #{op.op_id} {sym} {direction} @ {op.entry_price} stake={stake}")
        return op

    def check_exits(self, analysis: dict) -> List[Operation]:
        sym    = analysis["symbol"]
        price  = analysis["price"]
        epoch  = analysis["epoch"]
        tick   = analysis.get("tick", 0)
        closed = []

        for op in list(self.open_ops):
            if op.symbol != sym:
                continue
            ticks_in     = tick - op.entry_tick
            should_close = False
            win          = False
            reason       = ""

            if analysis.get("spike_detected"):
                sd = analysis.get("spike_dir")
                if sd == op.direction:
                    should_close = True
                    win          = True
                    reason       = f"SPIKE {sd} ✓"
                elif sd:
                    should_close = True
                    win          = False
                    reason       = f"SPIKE CONTRARIO ✗"

            if not should_close and ticks_in >= op.max_ticks:
                should_close = True
                win          = False
                reason       = "TIMEOUT"

            if should_close:
                op.exit_price = price
                op.exit_epoch = epoch
                op.exit_tick  = tick
                op.status     = "WIN" if win else "LOSS"
                op.pnl        = round(op.stake * self.win_multiplier, 2) if win else round(-op.stake, 2)
                op.reason     = reason
                self.balance  += op.stake + op.pnl
                self.total_pnl += op.pnl
                if win:
                    self.total_wins += 1
                else:
                    self.total_losses += 1
                self.open_ops.remove(op)
                self.closed_ops.append(op)
                if len(self.closed_ops) > 500:
                    self.closed_ops.pop(0)
                self.cooldown[sym] = tick
                log.info(f"[OPS] CERRADA #{op.op_id} {op.status} PnL={op.pnl}")
                closed.append(op)

        return closed

    def status_dict(self) -> dict:
        total = self.total_wins + self.total_losses
        wr    = round(self.total_wins / total, 3) if total > 0 else 0.0
        return {
            "balance":      round(self.balance, 2),
            "initial":      round(self.initial_balance, 2),
            "total_pnl":    round(self.total_pnl, 2),
            "pnl_pct":      round((self.balance - self.initial_balance) / self.initial_balance * 100, 2),
            "open_ops":     [o.to_dict() for o in self.open_ops],
            "closed_ops":   [o.to_dict() for o in reversed(self.closed_ops[-100:])],
            "total_trades": total,
            "win_rate":     wr,
            "wins":         self.total_wins,
            "losses":       self.total_losses,
            "auto_trade":   self.auto_trade,
            "min_score":    self.min_score,
            "stake_pct":    self.stake_pct,
        }


# ═══════════════════════════════════════════════════════════════════
#  ESTADO POR ÍNDICE — todos los algoritmos
# ═══════════════════════════════════════════════════════════════════

class IndexState:
    def __init__(self, symbol: str, meta: dict):
        self.symbol     = symbol
        self.meta       = meta
        self.itype      = meta["type"]
        self.freq       = meta["freq"]
        self.target_dir = "UP" if meta["type"] == "boom" else "DOWN"

        self.prices     = deque(maxlen=HIST_SIZE)
        self.returns    = deque(maxlen=WINDOW)
        self.times      = deque(maxlen=HIST_SIZE)
        self.tick_times = deque(maxlen=200)

        self.spikes      : List[dict] = []
        self.tick_count  = 0
        self.ticks_since_last_spike = 0

        self.kf = self._init_kalman()

        self.alpha = 1.0
        self.beta  = self.freq - 1
        self.observed_spikes = 0
        self.observed_ticks  = 0

        self.hmm_state = "TENDENCIA"
        self.wav_buf   = deque(maxlen=256)

        self.rolling_vol_history = deque(maxlen=100)

        self.spike_intervals_all    = deque(maxlen=200)
        self.spike_intervals_target = deque(maxlen=200)
        self.last_any_spike_tick    = 0
        self.last_target_spike_tick = 0

        self._pattern_score_cache = 0.0
        self._pattern_update_tick = 0
        self.pattern_window = 15

        # Velas OHLC de 1 minuto para el chart (hasta 1500 velas = 25h)
        self.candles_1m: List[dict] = []
        self._current_candle: Optional[dict] = None

        self.bounce_zones        = []
        self._bounce_update_tick = 0

    def _init_kalman(self):
        kf = KalmanFilter(dim_x=2, dim_z=1)
        kf.F = np.array([[1., 1.], [0., 1.]])
        kf.H = np.array([[1., 0.]])
        kf.P *= 1000.
        kf.R = 5.
        kf.Q = np.array([[0.1, 0.], [0., 0.01]])
        kf.x = np.array([[0.], [0.]])
        return kf

    # ── Bounce zones ──────────────────────────────────────────────
    def _compute_bounce_zones(self, prices_list: list) -> list:
        if len(prices_list) < 200:
            return []
        arr    = np.array(prices_list)
        counts, edges = np.histogram(arr, bins=80)
        smooth = uniform_filter1d(counts.astype(float), size=3)
        thr    = float(np.percentile(smooth, 70))
        zones  = []
        for i in range(1, len(smooth) - 1):
            if (smooth[i] > thr and
                    smooth[i] >= smooth[i - 1] and
                    smooth[i] >= smooth[i + 1]):
                zone_price = float((edges[i] + edges[i + 1]) / 2)
                strength   = float(smooth[i]) / float(max(smooth) + 1e-10)
                zones.append({
                    "price":    round(zone_price, 5),
                    "strength": round(strength, 3),
                    "touches":  int(counts[i])
                })
        zones.sort(key=lambda z: -z["strength"])
        return zones[:6]

    # ── Pattern matching ──────────────────────────────────────────
    def _compute_pattern_score(self, rets_list: list) -> float:
        n = self.pattern_window
        if len(rets_list) < n * 3:
            return 0.0
        current = np.array(rets_list[-n:])
        std_c   = float(np.std(current))
        if std_c < 1e-10:
            return 0.0
        current_norm = (current - np.mean(current)) / std_c

        matches_ok  = 0
        comparisons = 0
        hist = list(rets_list[:-n])
        step = max(1, len(hist) // 80)

        for i in range(0, len(hist) - n - 5, step):
            win   = np.array(hist[i:i + n])
            std_w = float(np.std(win))
            if std_w < 1e-10:
                continue
            win_norm = (win - np.mean(win)) / std_w
            corr     = float(np.corrcoef(current_norm, win_norm)[0, 1])
            if np.isnan(corr):
                continue
            if corr > 0.65:
                comparisons += 1
                future = rets_list[i + n: i + n + 20]
                if future:
                    f_arr = np.array(future)
                    thr   = std_c * ZSCORE_THR
                    if self.target_dir == "UP":
                        spike_followed = bool(np.any(f_arr > thr))
                    else:
                        spike_followed = bool(np.any(f_arr < -thr))
                    if spike_followed:
                        matches_ok += 1

        if comparisons == 0:
            return 0.0
        return float(min(1.0, (matches_ok / comparisons) * 2.5))

    # ── Momentum ──────────────────────────────────────────────────
    def _compute_momentum(self, prices_list: list, period: int = 20):
        if len(prices_list) < period + 1:
            return 0.0, 0.0
        arr = np.array(prices_list)
        mom = (arr[-1] - arr[-period - 1]) / (arr[-period - 1] + 1e-10)
        if len(prices_list) >= period * 2 + 1:
            prev_mom = (arr[-period - 1] - arr[-period * 2 - 1]) / (arr[-period * 2 - 1] + 1e-10)
            accel    = float(mom - prev_mom)
        else:
            accel = 0.0
        return float(mom), accel

    # ── Directional Z-score ───────────────────────────────────────
    def _directional_zscore(self, rets_list: list) -> float:
        arr = np.array(rets_list)
        sub = arr[arr > 0] if self.target_dir == "UP" else arr[arr < 0]
        if len(sub) < 5:
            return 0.0
        mu  = float(np.mean(sub))
        sig = float(np.std(sub))
        if sig < 1e-12:
            return 0.0
        last = rets_list[-1]
        if self.target_dir == "UP" and last > 0:
            return float((last - mu) / sig)
        elif self.target_dir == "DOWN" and last < 0:
            return float((last - mu) / sig)
        return 0.0

    # ── Predict next spike ────────────────────────────────────────
    def _predict_next_spike_ticks(self) -> int:
        intervals = list(self.spike_intervals_target) or list(self.spike_intervals_all)
        if len(intervals) < 3:
            return max(1, self.freq - self.ticks_since_last_spike)
        mean_int  = float(np.mean(intervals))
        remaining = max(1, int(mean_int - self.ticks_since_last_spike))
        return remaining

    # ── N-Pattern detection ───────────────────────────────────────
    def _detect_n_pattern(self, prices_list: list) -> dict:
        if len(prices_list) < 40:
            return {"score": 0.0, "label": "—"}
        arr = np.array(prices_list[-40:])
        rng = float(arr.max() - arr.min())
        if rng < 1e-10:
            return {"score": 0.0, "label": "—"}
        norm       = (arr - arr.min()) / rng
        std_recent = float(np.std(norm[-10:]))
        std_prev   = float(np.std(norm[:30]))
        ratio      = std_recent / (std_prev + 1e-10)
        if ratio < 0.4:
            return {"score": float(min(1.0, (0.4 - ratio) * 3)), "label": "COMPRESIÓN-N"}
        diffs        = np.diff(norm)
        sign_changes = int(np.sum(np.diff(np.sign(diffs)) != 0))
        zz_score     = float(min(1.0, sign_changes / 14.0))
        if zz_score > 0.5:
            return {"score": zz_score, "label": "ZIGZAG-N"}
        return {"score": 0.0, "label": "—"}

    # ── TICK PRINCIPAL ────────────────────────────────────────────
    def push_tick(self, price: float, epoch: int) -> dict:
        self.tick_count += 1
        self.ticks_since_last_spike += 1
        self.observed_ticks += 1
        self.tick_times.append(epoch)

        if self.prices:
            self.kf.predict()
        self.kf.update(np.array([[price]]))
        filtered_price  = float(self.kf.x[0, 0])
        kalman_velocity = float(self.kf.x[1, 0])

        ret = 0.0
        if self.prices:
            prev = self.prices[-1]
            if prev > 0:
                ret = math.log(price / prev)

        self.prices.append(price)
        self.times.append(epoch)
        self.returns.append(ret)
        self.wav_buf.append(price)

        # ── ESTADÍSTICOS BASE ─────────────────────────────────────
        rets_list = list(self.returns)
        rets_arr  = np.array(rets_list) if len(rets_list) > 5 else np.zeros(6)

        mu    = float(np.mean(rets_arr))
        sigma = float(np.std(rets_arr)) if len(rets_arr) > 2 else 1e-9
        if sigma == 0:
            sigma = 1e-9

        zscore     = abs(ret - mu) / sigma if len(rets_arr) > 5 else 0.0
        dir_zscore = self._directional_zscore(rets_list) if len(rets_list) > 10 else 0.0

        kurt = float(stats.kurtosis(rets_arr)) if len(rets_arr) > 8 else 0.0
        skew = float(stats.skew(rets_arr))     if len(rets_arr) > 5 else 0.0

        self.rolling_vol_history.append(sigma)
        vol_arr        = np.array(self.rolling_vol_history)
        vol_trend      = float(np.polyfit(range(len(vol_arr)), vol_arr, 1)[0]) if len(vol_arr) > 3 else 0.0
        vol_mean       = float(np.mean(vol_arr))
        vol_compressed = (vol_trend < -PRE_SPIKE_VOL_DROP * sigma) and (sigma < vol_mean * 0.75)

        # ── DETECCIÓN DE SPIKE ────────────────────────────────────
        spike_detected      = zscore > ZSCORE_THR and len(rets_arr) > 20
        spike_dir           = None
        spike_in_target_dir = False

        if spike_detected:
            spike_dir           = "UP" if ret > 0 else "DOWN"
            spike_in_target_dir = (spike_dir == self.target_dir)
            if self.last_any_spike_tick > 0:
                self.spike_intervals_all.append(self.tick_count - self.last_any_spike_tick)
            self.last_any_spike_tick = self.tick_count
            if spike_in_target_dir:
                if self.last_target_spike_tick > 0:
                    self.spike_intervals_target.append(self.tick_count - self.last_target_spike_tick)
                self.last_target_spike_tick = self.tick_count
            self.ticks_since_last_spike = 0
            self.observed_spikes += 1
            self.spikes.append({
                "epoch":     epoch,
                "price":     price,
                "zscore":    round(zscore, 2),
                "direction": spike_dir,
                "tick":      self.tick_count,
                "is_target": spike_in_target_dir,
            })
            if len(self.spikes) > 300:
                self.spikes.pop(0)

        # ── BAYESIANO ─────────────────────────────────────────────
        a_post   = self.alpha + self.observed_spikes
        b_post   = self.beta  + self.observed_ticks - self.observed_spikes
        p_post   = a_post / (a_post + b_post)
        p_next_k = {str(k): round(1 - (1 - p_post) ** k, 4) for k in [10, 25, 50, 100]}

        # ── MOMENTUM ─────────────────────────────────────────────
        prices_list = list(self.prices)
        momentum, accel = self._compute_momentum(prices_list, 20)
        mom_aligned = (self.target_dir == "UP"   and momentum > 0) or \
                      (self.target_dir == "DOWN"  and momentum < 0)

        # ── BOUNCE ZONES ─────────────────────────────────────────
        if self.tick_count - self._bounce_update_tick >= 100 and len(prices_list) >= 200:
            self.bounce_zones        = self._compute_bounce_zones(prices_list)
            self._bounce_update_tick = self.tick_count

        bounce_near       = False
        nearest_zone_dist = 1.0
        if self.bounce_zones:
            dists             = [abs(price - z["price"]) / price for z in self.bounce_zones]
            nearest_zone_dist = float(min(dists))
            bounce_near       = nearest_zone_dist < 0.0008

        # ── PATTERN MATCHING ─────────────────────────────────────
        if self.tick_count - self._pattern_update_tick >= 15 and len(rets_list) >= self.pattern_window * 3:
            try:
                self._pattern_score_cache = self._compute_pattern_score(rets_list)
            except Exception:
                self._pattern_score_cache = 0.0
            self._pattern_update_tick = self.tick_count
        pattern_score = self._pattern_score_cache

        # ── N-PATTERN ────────────────────────────────────────────
        n_pat = self._detect_n_pattern(prices_list)

        # ── TICK RATE ─────────────────────────────────────────────
        tick_rate_anomaly = False
        tick_interval_ms  = 0.0
        if len(self.tick_times) >= 10:
            t_arr    = np.array(list(self.tick_times)[-20:])
            ints_t   = np.diff(t_arr)
            if len(ints_t) > 3:
                tick_interval_ms  = float(np.mean(ints_t)) * 1000
                tick_rate_anomaly = tick_interval_ms < 400

        # ── WAVELET ──────────────────────────────────────────────
        wav_energy_high = 0.0
        wav_anomaly     = False
        if len(self.wav_buf) == 256:
            try:
                coeffs          = pywt.wavedec(list(self.wav_buf), 'haar', level=4)
                wav_energy_high = float(np.sum(coeffs[1] ** 2))
                total_energy    = sum(float(np.sum(c ** 2)) for c in coeffs)
                wav_anomaly     = (wav_energy_high / (total_energy + 1e-10)) > 0.55
            except Exception:
                pass

        # ── KALMAN VELOCITY ALIGNMENT ────────────────────────────
        vel_aligned  = (self.target_dir == "UP"   and kalman_velocity > 0) or \
                       (self.target_dir == "DOWN"  and kalman_velocity < 0)
        skew_aligned = (self.target_dir == "UP"   and skew > 0.6) or \
                       (self.target_dir == "DOWN"  and skew < -0.6)

        # ── HMM HEURÍSTICO ────────────────────────────────────────
        if spike_detected and spike_in_target_dir:
            self.hmm_state = "SPIKE"
        elif spike_detected:
            self.hmm_state = "SPIKE_CONTRARIO"
        elif vol_compressed and kurt > 2.0:
            self.hmm_state = "ACUMULACIÓN"
        elif abs(zscore) > 1.5 and mom_aligned and vel_aligned:
            self.hmm_state = "TENDENCIA_FUERTE"
        elif abs(zscore) > 0.8:
            self.hmm_state = "TENDENCIA"
        else:
            self.hmm_state = "RANGO"

        # ── PREDICCIÓN ───────────────────────────────────────────
        ticks_to_next   = self._predict_next_spike_ticks()
        avg_spike_mag   = sigma * ZSCORE_THR * 3
        price_target_up   = round(price * (1 + avg_spike_mag), 5) if self.target_dir == "UP"  else None
        price_target_down = round(price * (1 - avg_spike_mag), 5) if self.target_dir == "DOWN" else None

        # ── PRE-SPIKE SCORE DIRECCIONAL ───────────────────────────
        s = 0.0
        if vol_compressed:                             s += 0.18
        if kurt > 3.0:                                 s += 0.12
        if skew_aligned:                               s += 0.10
        if wav_anomaly:                                s += 0.10
        if self.ticks_since_last_spike > self.freq * 0.75: s += 0.12
        if pattern_score > 0.3:                        s += pattern_score * 0.12
        if bounce_near:                                s += 0.07
        if tick_rate_anomaly:                          s += 0.06
        if mom_aligned and abs(momentum) > 0.0002:     s += 0.08
        if vel_aligned:                                s += 0.05
        if n_pat["score"] > 0.4:                       s += n_pat["score"] * 0.08
        if dir_zscore > 2.0:                           s += 0.12
        pre_spike_score = float(min(1.0, s))

        alert_level = "CRÍTICO" if pre_spike_score > 0.70 else \
                      "ALTO"    if pre_spike_score > 0.50 else \
                      "MEDIO"   if pre_spike_score > 0.28 else "NORMAL"

        # ── VENTANA PRECIO ────────────────────────────────────────
        prices_win = prices_list[-WINDOW:]
        p_high     = float(max(prices_win)) if prices_win else price
        p_low      = float(min(prices_win)) if prices_win else price

        target_spikes_count = sum(1 for sp in self.spikes if sp.get("is_target"))

        return {
            "symbol":            self.symbol,
            "name":              self.meta["name"],
            "type":              self.itype,
            "color":             self.meta["col"],
            "freq":              self.freq,
            "target_dir":        self.target_dir,
            "tick":              self.tick_count,
            "epoch":             epoch,
            "price":             round(price, 5),
            "price_filtered":    round(filtered_price, 5),
            "price_high":        round(p_high, 5),
            "price_low":         round(p_low, 5),
            "return":            round(ret, 6),
            "zscore":            round(zscore, 3),
            "dir_zscore":        round(dir_zscore, 3),
            "sigma":             round(sigma, 6),
            "mu":                round(mu, 6),
            "kurtosis":          round(kurt, 3),
            "skewness":          round(skew, 3),
            "vol_compressed":    vol_compressed,
            "vol_trend":         round(vol_trend, 8),
            "spike_detected":    spike_detected,
            "spike_dir":         spike_dir,
            "spike_in_target":   spike_in_target_dir,
            "ticks_since_spike": self.ticks_since_last_spike,
            "ticks_to_expected": ticks_to_next,
            "p_post":            round(p_post, 5),
            "p_next":            p_next_k,
            "pre_spike_score":   round(pre_spike_score, 3),
            "alert_level":       alert_level,
            "hmm_state":         self.hmm_state,
            "wav_energy_high":   round(wav_energy_high, 2),
            "wav_anomaly":       wav_anomaly,
            "momentum":          round(momentum, 6),
            "acceleration":      round(accel, 6),
            "mom_aligned":       mom_aligned,
            "pattern_score":     round(pattern_score, 3),
            "n_pattern":         n_pat,
            "bounce_near":       bounce_near,
            "bounce_zones":      self.bounce_zones[:4],
            "nearest_zone_dist": round(nearest_zone_dist, 5),
            "tick_rate_anomaly": tick_rate_anomaly,
            "tick_interval_ms":  round(tick_interval_ms, 1),
            "kalman_velocity":   round(kalman_velocity, 6),
            "vel_aligned":       vel_aligned,
            "price_target_up":   price_target_up,
            "price_target_down": price_target_down,
            "recent_spikes":     self.spikes[-5:],
            "target_spikes_count": target_spikes_count,
            "total_spikes":      len(self.spikes),
        }


# ═══════════════════════════════════════════════════════════════════
#  MOTOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════

class DerivEngine:
    def __init__(self):
        self.states  : Dict[str, IndexState] = {
            sym: IndexState(sym, meta) for sym, meta in INDICES.items()
        }
        self.clients : List[WebSocket] = []
        self.ops     = OperationsManager()
        self.running = False

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.clients:
                self.clients.remove(ws)

    async def run(self):
        self.running = True
        while self.running:
            try:
                await self._connect_and_stream()
            except Exception as e:
                log.error(f"Deriv WS error: {e} — reconectando en 5s")
                await asyncio.sleep(5)

    async def _connect_and_stream(self):
        log.info("Conectando a Deriv WebSocket...")
        async with websockets.connect(DERIV_WS, ping_interval=30) as ws:
            await ws.send(json.dumps({"authorize": API_TOKEN}))
            auth_resp = json.loads(await ws.recv())
            if auth_resp.get("error"):
                log.error(f"Auth error: {auth_resp['error']['message']}")
                return
            log.info(f"Autorizado: {auth_resp.get('authorize', {}).get('email', 'OK')}")

            # ── Cargar historial de ticks antes de suscribir ──────────
            for symbol in INDICES:
                try:
                    await ws.send(json.dumps({
                        "ticks_history": symbol,
                        "count": 5000,
                        "end": "latest",
                        "style": "ticks",
                        "adjust_start_time": 1
                    }))
                    hist_resp = json.loads(await ws.recv())
                    if hist_resp.get("msg_type") == "history":
                        history = hist_resp.get("history", {})
                        prices  = history.get("prices", [])
                        times   = history.get("times", [])
                        state   = self.states[symbol]
                        for price, epoch in zip(prices, times):
                            state.push_tick(float(price), int(epoch))
                        log.info(f"Historial cargado: {symbol} ({len(prices)} ticks)")
                    else:
                        log.warning(f"Historial no disponible para {symbol}")
                except Exception as e:
                    log.warning(f"Error cargando historial {symbol}: {e}")

            # ── Cargar velas OHLC de 1 minuto para el chart ───────────
            for symbol in INDICES:
                try:
                    await ws.send(json.dumps({
                        "ticks_history": symbol,
                        "count": 1500,
                        "end": "latest",
                        "style": "candles",
                        "granularity": 60
                    }))
                    candle_resp = json.loads(await ws.recv())
                    if candle_resp.get("msg_type") == "candles":
                        candles = candle_resp.get("candles", [])
                        self.states[symbol].candles_1m = [
                            {
                                "time":  int(c["epoch"]),
                                "open":  float(c["open"]),
                                "high":  float(c["high"]),
                                "low":   float(c["low"]),
                                "close": float(c["close"]),
                            }
                            for c in candles
                        ]
                        log.info(f"Velas 1m cargadas: {symbol} ({len(candles)} velas)")
                except Exception as e:
                    log.warning(f"Error cargando velas {symbol}: {e}")

            for symbol in INDICES:
                await ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))
                log.info(f"Suscrito a {symbol}")

            async for msg in ws:
                data = json.loads(msg)
                if data.get("msg_type") == "tick":
                    tick = data["tick"]
                    sym  = tick["symbol"]
                    if sym in self.states:
                        price = float(tick["quote"])
                        epoch = int(tick["epoch"])
                        state = self.states[sym]
                        analysis = state.push_tick(price, epoch)

                        # ── Actualizar vela 1m en vivo ─────────────────
                        bucket = (epoch // 60) * 60
                        cc = state._current_candle
                        if cc is None or cc["time"] != bucket:
                            # Cerrar la anterior, abrir nueva
                            if cc is not None:
                                # Asegurar que está en la lista
                                if not state.candles_1m or state.candles_1m[-1]["time"] != cc["time"]:
                                    state.candles_1m.append(cc)
                                    if len(state.candles_1m) > 1500:
                                        state.candles_1m = state.candles_1m[-1500:]
                            new_candle = {"time": bucket, "open": price, "high": price, "low": price, "close": price}
                            state._current_candle = new_candle
                            state.candles_1m.append(new_candle)
                            if len(state.candles_1m) > 1500:
                                state.candles_1m = state.candles_1m[-1500:]
                        else:
                            cc["high"]  = max(cc["high"], price)
                            cc["low"]   = min(cc["low"],  price)
                            cc["close"] = price

                        live_candle = state._current_candle

                        entered_op = self.ops.try_enter(analysis)
                        closed_ops = self.ops.check_exits(analysis)

                        payload: dict = {
                            "type":   "tick",
                            "data":   analysis,
                            "ops":    self.ops.status_dict(),
                            "candle": live_candle,  # Vela 1m en vivo
                        }
                        if entered_op:
                            payload["new_op"] = entered_op.to_dict()
                        if closed_ops:
                            payload["closed_ops_evt"] = [o.to_dict() for o in closed_ops]

                        await self.broadcast(payload)


engine = DerivEngine()

# ═══════════════════════════════════════════════════════════════════
#  FASTAPI
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(title="Deriv Spike Analyzer v2")


@app.on_event("startup")
async def startup():
    asyncio.create_task(engine.run())
    log.info("Motor de análisis v2 iniciado.")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    engine.clients.append(websocket)
    log.info(f"Cliente conectado. Total: {len(engine.clients)}")
    try:
        init_data = {}
        for sym, state in engine.states.items():
            init_data[sym] = {
                "symbol":     sym,
                "name":       state.meta["name"],
                "color":      state.meta["col"],
                "freq":       state.meta["freq"],
                "type":       state.meta["type"],
                "target_dir": state.target_dir,
                "price":      list(state.prices)[-1] if state.prices else 0,
                "total_spikes": len(state.spikes),
                # Velas OHLC de 1 minuto para chart profesional
                "candles_1m": state.candles_1m[-1500:],
            }
        await websocket.send_text(json.dumps({
            "type": "init",
            "data": init_data,
            "ops":  engine.ops.status_dict(),
        }))
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                cmd = json.loads(msg)
                if cmd.get("cmd") == "set_balance":
                    v = float(cmd.get("value", 1000))
                    engine.ops.balance = v
                    engine.ops.initial_balance = v
                elif cmd.get("cmd") == "set_stake_pct":
                    engine.ops.stake_pct = float(cmd.get("value", 0.02))
                elif cmd.get("cmd") == "set_auto_trade":
                    engine.ops.auto_trade = bool(cmd.get("value", True))
                elif cmd.get("cmd") == "set_min_score":
                    engine.ops.min_score = float(cmd.get("value", 0.62))
                await websocket.send_text(json.dumps({
                    "type": "ops_update",
                    "ops":  engine.ops.status_dict(),
                }))
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        if websocket in engine.clients:
            engine.clients.remove(websocket)
        log.info("Cliente desconectado.")


@app.get("/")
async def index():
    return FileResponse(_BASE_DIR / "dashboard.html")


@app.get("/api/state/{symbol}")
async def get_state(symbol: str):
    if symbol not in engine.states:
        return JSONResponse({"error": "Símbolo no encontrado"}, status_code=404)
    s = engine.states[symbol]
    return {
        "symbol":       symbol,
        "tick_count":   s.tick_count,
        "total_spikes": len(s.spikes),
        "last_spikes":  s.spikes[-20:],
        "bounce_zones": s.bounce_zones,
        "prices_sample": list(s.prices)[-100:],
        "target_dir":   s.target_dir,
    }


@app.get("/api/operations")
async def get_operations():
    return engine.ops.status_dict()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)
