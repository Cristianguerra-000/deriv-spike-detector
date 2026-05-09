// Dashboard cliente. Conecta directamente a Deriv WS para velas en vivo
// y a Firebase Firestore para resultados de algoritmos persistidos.

import {
  db,
  collection,
  doc,
  getDocs,
  onSnapshot,
} from "./firebase-config.js";

const APP_ID = 1089; // App ID público — el token NO se usa en el navegador
const WS_URL = `wss://ws.derivws.com/websockets/v3?app_id=${APP_ID}`;

// ---------- Medias: siempre activas ----------
const MA_CFG = [
  { key: "ema9",    label: "EMA 9",   color: "#4fc3f7", width: 1 },
  { key: "ema21",   label: "EMA 21",  color: "#ff7043", width: 1 },
  { key: "ema50",   label: "EMA 50",  color: "#ffd54f", width: 1 },
  { key: "hull9",   label: "HULL 9",  color: "#ce93d8", width: 2 },
  { key: "bbUpper", label: "BB+",     color: "rgba(255,213,79,.45)", width: 1, dash: true },
  { key: "bbMid",   label: "BB mid",  color: "rgba(255,213,79,.25)", width: 1, dash: true },
  { key: "bbLower", label: "BB−",     color: "rgba(255,213,79,.45)", width: 1, dash: true },
];
const maState = { series: {} };

// ---------- Estado ----------
const state = {
  ws: null,
  reqId: 0,
  pending: new Map(),
  symbol: null,
  granularity: 60,
  chart: null,
  candleSeries: null,
  tickSubId: null,
  candles: [],          // últimas velas cargadas (para cálculos)
  priceLines: [],       // referencias a las price lines dibujadas
  driftLines: [],       // price lines del canal de drift
  lastFavorPct: 0,
  spikeAt: null,        // epoch de la vela donde se detectó un spike
  spikeCooldown: 5,
  newCandleTime: null,
  algoData: {},         // { "crash.drift_channel": { value, signal, metadata, ... }, ... }
};

// ---------- WS helpers ----------
function connect() {
  return new Promise((resolve) => {
    state.ws = new WebSocket(WS_URL);
    state.ws.onopen = () => resolve();
    state.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.req_id && state.pending.has(msg.req_id)) {
        const { resolve } = state.pending.get(msg.req_id);
        state.pending.delete(msg.req_id);
        resolve(msg);
      }
      if (msg.msg_type === "tick" && msg.tick) onTick(msg.tick);
      if (msg.msg_type === "ohlc" && msg.ohlc) onOhlc(msg.ohlc);
    };
  });
}

function send(payload) {
  state.reqId += 1;
  const req = { ...payload, req_id: state.reqId };
  return new Promise((resolve, reject) => {
    state.pending.set(state.reqId, { resolve, reject });
    state.ws.send(JSON.stringify(req));
  });
}

// ---------- UI ----------
const $ = (sel) => document.querySelector(sel);
const drawer = document.getElementById("drawer");
const overlay = document.getElementById("drawerOverlay");

function openDrawer() {
  drawer.classList.add("open");
  overlay.classList.add("visible");
}
function closeDrawer() {
  drawer.classList.remove("open");
  overlay.classList.remove("visible");
}

document.getElementById("drawerToggle").addEventListener("click", () => {
  drawer.classList.contains("open") ? closeDrawer() : openDrawer();
});
overlay.addEventListener("click", closeDrawer);

// ---------- Panel Señal Final ----------
const signalPanel = document.getElementById("signalPanel");
document.getElementById("signalBtn").addEventListener("click", () => {
  signalPanel.classList.toggle("signal-panel--hidden");
});
document.getElementById("signalClose").addEventListener("click", () => {
  signalPanel.classList.add("signal-panel--hidden");
});

function buildChart() {
  state.chart = LightweightCharts.createChart($("#chart"), {
    autoSize: true,
    layout: { background: { color: "#0b0f1a" }, textColor: "#e6edf7" },
    grid: { vertLines: { color: "#1b2438" }, horzLines: { color: "#1b2438" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    crosshair: { mode: 0 },
  });
  state.candleSeries = state.chart.addCandlestickSeries({
    upColor: "#26a69a", downColor: "#ef5350",
    borderUpColor: "#26a69a", borderDownColor: "#ef5350",
    wickUpColor: "#26a69a", wickDownColor: "#ef5350",
  });
  buildMASeries();
}

// ---------- Medias especiales ----------
function _ema(candles, period) {
  if (candles.length < period) return [];
  const k = 2 / (period + 1);
  let v = candles.slice(0, period).reduce((s, c) => s + c.close, 0) / period;
  const out = [{ time: candles[period - 1].time, value: v }];
  for (let i = period; i < candles.length; i++) {
    v = candles[i].close * k + v * (1 - k);
    out.push({ time: candles[i].time, value: v });
  }
  return out;
}

function _wma(candles, period) {
  const denom = period * (period + 1) / 2;
  const out = [];
  for (let i = period - 1; i < candles.length; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) sum += candles[i - j].close * (period - j);
    out.push({ time: candles[i].time, value: sum / denom, close: sum / denom });
  }
  return out;
}

function _hull(candles, period) {
  // HMA(n) = WMA( 2*WMA(n/2) − WMA(n), sqrt(n) )
  const half = Math.round(period / 2);
  const sq   = Math.round(Math.sqrt(period));
  const wFull = _wma(candles, period);
  const wHalf = _wma(candles, half);
  const offset = period - half;
  const diff = wFull.map((p, i) => ({ time: p.time, close: 2 * wHalf[i + offset].value - p.value }));
  return _wma(diff, sq).map((p) => ({ time: p.time, value: p.close }));
}

function _bb(candles, period = 20, mult = 2) {
  const upper = [], mid = [], lower = [];
  for (let i = period - 1; i < candles.length; i++) {
    const sl = candles.slice(i - period + 1, i + 1);
    const mean = sl.reduce((s, c) => s + c.close, 0) / period;
    const std  = Math.sqrt(sl.reduce((s, c) => s + (c.close - mean) ** 2, 0) / period);
    upper.push({ time: candles[i].time, value: mean + mult * std });
    mid.push(  { time: candles[i].time, value: mean });
    lower.push({ time: candles[i].time, value: mean - mult * std });
  }
  return { upper, mid, lower };
}

function buildMASeries() {
  Object.values(maState.series).forEach((s) => { try { state.chart.removeSeries(s); } catch (_) {} });
  maState.series = {};
  MA_CFG.forEach(({ key, label, color, width, dash }) => {
    maState.series[key] = state.chart.addLineSeries({
      color, lineWidth: width,
      lineStyle: dash ? 2 : 0,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
      title: label,
    });
  });
}

function updateMAs() {
  const c = state.candles;
  if (!c.length || !maState.series.ema9) return;
  maState.series.ema9.setData(_ema(c, 9));
  maState.series.ema21.setData(_ema(c, 21));
  maState.series.ema50.setData(_ema(c, 50));
  maState.series.hull9.setData(_hull(c, 9));
  const bb = _bb(c, 20, 2);
  maState.series.bbUpper.setData(bb.upper);
  maState.series.bbMid.setData(bb.mid);
  maState.series.bbLower.setData(bb.lower);
}

// ---------- Fibonacci especial CRASH/BOOM ----------
// Niveles estándar + niveles de extensión típicos de spikes sintéticos
const FIB_LEVELS = [
  { ratio: 0,     label: "0%",    color: "rgba(255,213,79,.9)",  width: 1 },
  { ratio: 0.236, label: "23.6%", color: "rgba(255,213,79,.5)",  width: 1 },
  { ratio: 0.382, label: "38.2%", color: "rgba(38,194,129,.75)", width: 1 },
  { ratio: 0.5,   label: "50%",   color: "rgba(79,195,247,.9)",  width: 2 },
  { ratio: 0.618, label: "61.8%", color: "rgba(38,194,129,.9)",  width: 2 },
  { ratio: 0.786, label: "78.6%", color: "rgba(239,83,80,.6)",   width: 1 },
  { ratio: 1,     label: "100%",  color: "rgba(255,213,79,.9)",  width: 1 },
  // Extensiones para el target del spike
  { ratio: 1.272, label: "127.2% ext", color: "rgba(206,147,216,.7)", width: 1 },
  { ratio: 1.618, label: "161.8% ext", color: "rgba(206,147,216,.9)", width: 2 },
];

const fibLines = []; // array de price lines de fibonacci

function clearFib() {
  if (!state.candleSeries) return;
  fibLines.forEach((pl) => { try { state.candleSeries.removePriceLine(pl); } catch (_) {} });
  fibLines.length = 0;
}

function drawFib(symbol) {
  clearFib();
  if (!state.candles.length) return;
  // No dibujar en símbolos que no sean crash/boom
  if (!symbol || (!symbol.startsWith("CRASH") && !symbol.startsWith("BOOM"))) return;

  const isCrash = symbol.startsWith("CRASH");
  // Usamos las últimas 200 velas para definir swing high/low
  const window = state.candles.slice(-200);
  const swingHigh = Math.max(...window.map((c) => c.high));
  const swingLow  = Math.min(...window.map((c) => c.low));
  const range = swingHigh - swingLow;

  FIB_LEVELS.forEach(({ ratio, label, color, width }) => {
    // CRASH: retroceso desde arriba hacia abajo (spikes caen)
    // BOOM:  retroceso desde abajo hacia arriba (spikes suben)
    const price = isCrash
      ? swingHigh - ratio * range
      : swingLow  + ratio * range;

    const pl = state.candleSeries.createPriceLine({
      price,
      color,
      lineWidth: width,
      lineStyle: 2,           // dashed para no confundir con medias
      axisLabelVisible: true,
      title: `Fib ${label}`,
    });
    fibLines.push(pl);
  });
}

function renderSymbolList(markets) {
  const buckets = { crash_boom: [], volatility: [], forex: [], indices: [], other: [] };
  for (const m of markets) {
    const cat = m.category;
    if (cat === "crash_boom") buckets.crash_boom.push(m);
    else if (cat === "volatility") buckets.volatility.push(m);
    else if (m.market === "forex") buckets.forex.push(m);
    else if (m.market === "indices" || m.market === "synthetic_index") buckets.indices.push(m);
    else buckets.other.push(m);
  }
  for (const [key, arr] of Object.entries(buckets)) {
    const ul = document.getElementById(`list-${key}`);
    if (!ul) continue;
    ul.innerHTML = "";
    for (const m of arr) {
      const li = document.createElement("li");
      li.textContent = m.display_name || m.symbol;
      li.dataset.symbol = m.symbol;
      li.addEventListener("click", () => {
        selectSymbol(m.symbol, m.display_name);
        closeDrawer();
      });
      ul.appendChild(li);
    }
  }
  $("#marketCount").textContent = `${markets.length} mercados`;
}

$("#searchSymbol").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase();
  document.querySelectorAll(".symbol-list li").forEach((li) => {
    li.style.display = li.textContent.toLowerCase().includes(q) ? "" : "none";
  });
});

$("#granularity").addEventListener("change", (e) => {
  state.granularity = Number(e.target.value);
  if (state.symbol) loadCandles(state.symbol);
});

// ---------- Datos ----------
async function loadMarkets() {
  const resp = await send({ active_symbols: "brief", product_type: "basic" });
  const enriched = (resp.active_symbols || []).map((s) => ({
    ...s,
    category: classify(s.symbol, s.market),
  }));
  renderSymbolList(enriched);
}

function classify(sym, market) {
  if (sym.startsWith("CRASH") || sym.startsWith("BOOM")) return "crash_boom";
  if (sym.startsWith("R_") || sym.startsWith("1HZ")) return "volatility";
  return market;
}

async function selectSymbol(symbol, displayName) {
  state.symbol = symbol;
  document.querySelectorAll(".symbol-list li").forEach((li) => {
    li.classList.toggle("active", li.dataset.symbol === symbol);
  });
  await loadCandles(symbol);
  loadAlgorithmResults(symbol);
}

async function loadCandles(symbol) {
  // Forget anterior
  if (state.tickSubId) {
    await send({ forget: state.tickSubId });
    state.tickSubId = null;
  }
  const resp = await send({
    ticks_history: symbol,
    count: 5000,
    end: "latest",
    style: "candles",
    granularity: state.granularity,
    subscribe: 1,
  });
  if (resp.subscription) state.tickSubId = resp.subscription.id;
  const candles = (resp.candles || []).map((c) => ({
    time: c.epoch,
    open: +c.open, high: +c.high, low: +c.low, close: +c.close,
  }));
  state.candleSeries.setData(candles);
  state.candles = candles;
  updateMAs();
  drawFib(symbol);
  drawSpikeMarkers();
  state.chart.timeScale().fitContent();
}

function onOhlc(ohlc) {
  if (ohlc.symbol !== state.symbol) return;
  state.candleSeries.update({
    time: +ohlc.open_time,
    open: +ohlc.open, high: +ohlc.high, low: +ohlc.low, close: +ohlc.close,
  });

  const isNewCandle = state.newCandleTime !== null && +ohlc.open_time !== state.newCandleTime;

  // Actualizar última vela en cache
  if (state.candles.length) {
    const last = state.candles[state.candles.length - 1];
    if (+ohlc.open_time === last.time) {
      last.open = +ohlc.open; last.high = +ohlc.high;
      last.low = +ohlc.low; last.close = +ohlc.close;
    } else {
      // Nueva vela cerró → detectar spike en la vela que ACABÓ de cerrar
      _detectAndHandleSpike(last);
      state.candles.push({
        time: +ohlc.open_time,
        open: +ohlc.open, high: +ohlc.high, low: +ohlc.low, close: +ohlc.close,
      });
      if (state.candles.length > 5100) state.candles.shift();
    }
  }
  state.newCandleTime = +ohlc.open_time;

  updateMAs();

  // Cada vela nueva: redibujar Fib + trade zones
  if (isNewCandle) {
    drawFib(state.symbol);
    drawSpikeMarkers();
    if (state.symbol) {
      const isCrash = state.symbol.startsWith("CRASH");
      const isBoom  = state.symbol.startsWith("BOOM");
      if ((isCrash || isBoom) && !_inSpikeCooldown()) {
        drawTradeZones(state.symbol, isCrash, state.lastFavorPct);
      }
    }
  } else {
    _updateActualLine();
  }
}

function _detectAndHandleSpike(closedCandle) {
  if (!state.symbol) return;
  const isCrash = state.symbol.startsWith("CRASH");
  const isBoom  = state.symbol.startsWith("BOOM");
  if (!isCrash && !isBoom) return;

  const prev14 = state.candles.slice(-14);
  const atr = prev14.reduce((s, c) => s + (c.high - c.low), 0) / Math.max(prev14.length, 1);
  const candleRange = closedCandle.high - closedCandle.low;
  const bodyMove = Math.abs(closedCandle.close - closedCandle.open);

  const isSpike = candleRange > atr * 3 && bodyMove > atr * 2;
  if (!isSpike) return;

  const crashSpike = closedCandle.close < closedCandle.open;
  const boomSpike  = closedCandle.close > closedCandle.open;
  if (isCrash && !crashSpike) return;
  if (isBoom  && !boomSpike)  return;

  state.spikeAt = closedCandle.time;
  clearPriceLines();

  // Mostrar alerta dentro de la gráfica
  const alert = $("#spikeAlert");
  alert.innerHTML = `
    <div class="spike-alert__icon">${isCrash ? "💥" : "🚀"}</div>
    <div class="spike-alert__title">SPIKE DETECTADO</div>
    <div class="spike-alert__sub">Cooldown ${state.spikeCooldown} velas · ${isCrash ? "Crash bajista" : "Boom alcista"} confirmado</div>
  `;
  alert.className = "spike-alert spike-alert--visible";
  setTimeout(() => { alert.className = "spike-alert spike-alert--hidden"; }, 4500);

}

function _inSpikeCooldown() {
  if (!state.spikeAt || !state.candles.length) return false;
  // Contar velas cerradas desde el spike
  const spikeIdx = state.candles.findIndex((c) => c.time === state.spikeAt);
  if (spikeIdx === -1) return false;
  const velasDespues = state.candles.length - 1 - spikeIdx;
  return velasDespues < state.spikeCooldown;
}

function _updateActualLine() {
  if (!state.candles.length || !state.priceLines.length) return;
  const last = state.candles[state.candles.length - 1].close;
  // La última price line es siempre la de "Actual"
  const pl = state.priceLines[state.priceLines.length - 1];
  try { pl.applyOptions({ price: last, title: `Actual ${last.toFixed(3)}` }); } catch (_) {}
}

function onTick(_tick) { /* hook futuro */ }

// ---------- Firebase: resultados de algoritmos → solo alimentan overlays ----------
const resultUnsubs = [];

// Algoritmos garantizados — se suscriben siempre aunque aún no exista el stub en Firestore
const GUARANTEED_ALGOS = [
  "crash.signal_final", "boom.signal_final",
  "crash.risk_composite", "boom.risk_composite",
  "crash.probability", "boom.probability",
  "crash.regime", "boom.regime",
  "crash.cycle_phase", "boom.cycle_phase",
  "crash.confidence", "boom.confidence",
  "crash.optimal_entry", "boom.optimal_entry",
];

function _subscribeAlgo(algoName, symbol) {
  const docRef = doc(db, "results", algoName, "symbols", symbol);
  const unsub = onSnapshot(docRef, (snap) => {
    if (!snap.exists()) { delete state.algoData[algoName]; }
    else {
      const data = snap.data();
      if (!data.signal || data.signal === "N/A") { delete state.algoData[algoName]; }
      else { state.algoData[algoName] = data; }
    }
    refreshChartVisuals();
  });
  resultUnsubs.push(unsub);
}

async function loadAlgorithmResults(symbol) {
  while (resultUnsubs.length) resultUnsubs.pop()();
  state.algoData = {};
  clearPriceLines();
  clearDriftLines();
  clearFib();
  state.spikeAt = null;
  state.lastFavorPct = 0;
  state.newCandleTime = null;

  // 1. Suscripciones garantizadas (siempre, aunque el stub no exista aún)
  GUARANTEED_ALGOS.forEach((name) => _subscribeAlgo(name, symbol));

  // 2. Descubrimiento dinámico del resto de algoritmos en Firestore
  try {
    const algosSnap = await getDocs(collection(db, "results"));
    if (algosSnap.empty) return;

    algosSnap.forEach((algoDoc) => {
      const algoName = algoDoc.id;
      if (GUARANTEED_ALGOS.includes(algoName)) return; // ya suscrito arriba
      _subscribeAlgo(algoName, symbol);
    });
  } catch (err) {
    console.error("Firebase:", err);
  }
}

// ---------- Refresca todos los visuales según algoData ----------
function refreshChartVisuals() {
  const symbol = state.symbol;
  if (!symbol) return;
  const isCrash = symbol.startsWith("CRASH");
  const isBoom  = symbol.startsWith("BOOM");
  if (!isCrash && !isBoom) return;

  // 1. Calcular score
  let favor = 0, total = 0;
  for (const data of Object.values(state.algoData)) {
    const sig = (data.signal || "").trim().toUpperCase();
    if (!sig || sig === "NEUTRO" || sig === "SIN PATRÓN" || sig === "LATERAL" || sig === "EQUILIBRADO") continue;
    total++;
    if (isCrash && BEARISH_SIGNALS.has(sig)) favor++;
    if (isBoom  && BULLISH_SIGNALS.has(sig)) favor++;
  }
  const pct = total > 0 ? (favor / total) * 100 : 0;
  state.lastFavorPct = pct;

  // 3. Canal de drift
  const channelKey = isCrash ? "crash.drift_channel" : "boom.drift_channel";
  if (state.algoData[channelKey]) drawDriftChannel(state.algoData[channelKey].metadata, isCrash);

  // 4. Tensión de fondo
  const tensionKey = isCrash ? "crash.tension" : "boom.tension";
  if (state.algoData[tensionKey]) applyTensionBg(state.algoData[tensionKey].value, isCrash);

  // 5. Zonas de trade
  if (!_inSpikeCooldown()) drawTradeZones(symbol, isCrash, pct);

  // 6. Panel señal final
  updateSignalPanel(symbol, isCrash, favor, total, pct);
}

// ---------- Panel Señal Final — actualiza contenido ----------
function updateSignalPanel(symbol, isCrash, favor, total, pct) {
  const key  = isCrash ? "crash.signal_final" : "boom.signal_final";
  const data = state.algoData[key];
  const action = data?.metadata?.action || (data ? data.signal : null);
  const actionLow = (action || "na").toLowerCase();

  // Dot de color en el botón
  const dot = document.getElementById("signalBtnDot");
  dot.className = `signal-btn__dot signal-btn__dot--${actionLow}`;

  // Acción principal
  const spAction = document.getElementById("spAction");
  spAction.className = `sp-action sp-action--${actionLow}`;
  spAction.textContent = action || "Sin datos";

  // Score
  const score = data?.metadata?.score ?? data?.value ?? null;
  document.getElementById("spScore").textContent = score !== null ? `${score}/100` : "—";

  // Barra
  const spBar = document.getElementById("spBar");
  spBar.style.width = score !== null ? `${score}%` : "0%";
  spBar.className = `sp-bar sp-bar--${actionLow}`;

  // Métricas de detalle (grid 2 columnas)
  const details = [];
  if (data?.metadata) {
    const m = data.metadata;
    if (m.regime !== undefined)      details.push({ label: "Régimen",    val: m.regime });
    if (m.cycle_pct !== undefined)   details.push({ label: "Ciclo",      val: `${m.cycle_pct}%` });
    if (m.risk_score !== undefined)  details.push({ label: "Riesgo",     val: `${m.risk_score}/100` });
    if (m.confidence !== undefined)  details.push({ label: "Confianza",  val: `${m.confidence}%` });
    if (m.rsi !== undefined)         details.push({ label: "RSI (7)",    val: m.rsi });
    const barsKey = isCrash ? "bars_since_crash" : "bars_since_boom";
    if (m[barsKey] !== undefined)    details.push({ label: "Velas desde spike", val: m[barsKey] });
  }
  document.getElementById("spDetails").innerHTML = details.map(
    (d) => `<div class="sp-detail-item"><span class="sp-detail-label">${d.label}</span><span class="sp-detail-val">${d.val}</span></div>`
  ).join("");

  // Interpretación
  document.getElementById("spReason").textContent = data?.interpretation || "Esperando datos de Firebase…";

  // Contexto: mismos tags del overlay
  const tensionKey = isCrash ? "crash.tension" : "boom.tension";
  const overdueKey = isCrash ? "crash.spike_overdue" : "boom.spike_overdue";
  const countKey   = isCrash ? "crash.tick_countdown" : "boom.tick_countdown";
  const riskKey    = isCrash ? "crash.risk_composite" : "boom.risk_composite";
  const probKey    = isCrash ? "crash.probability" : "boom.probability";
  const ctx = [];

  if (state.algoData[tensionKey]) {
    const v = state.algoData[tensionKey].value;
    const cls = v >= 70 ? "tag-hot" : v >= 40 ? "tag-warn" : "tag-ok";
    ctx.push(`<span class="${cls}">⚡ Tensión ${v}/100</span>`);
  }
  if (state.algoData[overdueKey]) {
    const v = Math.round(state.algoData[overdueKey].value);
    const cls = v >= 80 ? "tag-hot" : v >= 50 ? "tag-warn" : "tag-ok";
    ctx.push(`<span class="${cls}">⏱ Overdue ${v}%</span>`);
  }
  if (state.algoData[countKey]) {
    const v = Math.round(state.algoData[countKey].value);
    ctx.push(`<span>🕐 ~${v} velas estimadas</span>`);
  }
  if (state.algoData[riskKey]) {
    const v = Math.round(state.algoData[riskKey].value);
    const cls = v >= 70 ? "tag-hot" : v >= 40 ? "tag-warn" : "tag-ok";
    ctx.push(`<span class="${cls}">🎯 Riesgo compuesto ${v}/100</span>`);
  }
  if (state.algoData[probKey]) {
    const m = state.algoData[probKey].metadata;
    if (m) {
      const p10 = m.prob_10 !== undefined ? `${(m.prob_10 * 100).toFixed(0)}%` : "—";
      const p20 = m.prob_20 !== undefined ? `${(m.prob_20 * 100).toFixed(0)}%` : "—";
      ctx.push(`<span>📊 Prob. 10v: ${p10} · 20v: ${p20}</span>`);
    }
  }
  // Señal de consenso (del overlay existente)
  const dir = isCrash ? "⬇ Crash" : "⬆ Boom";
  const cons = pct >= 55 ? "Fuerte" : pct >= 35 ? "Moderada" : "Débil";
  const cls  = pct >= 55 ? "tag-ok" : pct >= 35 ? "tag-warn" : "tag-hot";
  ctx.push(`<span class="${cls}">📈 ${dir} ${cons} (${favor}/${total} algos · ${pct.toFixed(0)}%)</span>`);

  document.getElementById("spContext").innerHTML = ctx.join("");
}

// ---------- Canal de drift ----------
function clearDriftLines() {
  if (!state.candleSeries) return;
  state.driftLines.forEach((pl) => { try { state.candleSeries.removePriceLine(pl); } catch (_) {} });
  state.driftLines = [];
}

function drawDriftChannel(meta, isCrash) {
  if (!meta || !state.candleSeries) return;
  clearDriftLines();
  const upper = meta.upper_band;
  const lower = meta.lower_band;
  const mid   = meta.trend_mid;
  if (!upper || !lower) return;

  const make = (price, color, title) => {
    const pl = state.candleSeries.createPriceLine({
      price, color, lineWidth: 1, lineStyle: 2,
      axisLabelVisible: true, title,
    });
    state.driftLines.push(pl);
  };

  if (isCrash) {
    make(upper, "rgba(239,83,80,0.7)", "Canal ↑");
    make(mid,   "rgba(239,83,80,0.35)", "Drift mid");
    make(lower, "rgba(38,166,154,0.7)", "Canal ↓");
  } else {
    make(upper, "rgba(38,166,154,0.7)", "Canal ↑");
    make(mid,   "rgba(38,166,154,0.35)", "Drift mid");
    make(lower, "rgba(239,83,80,0.7)", "Canal ↓");
  }
}

// ---------- Marcadores de spikes históricos ----------
function drawSpikeMarkers() {
  if (!state.candleSeries || !state.candles.length || !state.symbol) return;
  const isCrash = state.symbol.startsWith("CRASH");
  const isBoom  = state.symbol.startsWith("BOOM");
  if (!isCrash && !isBoom) return;

  const candles = state.candles;
  const body = candles.map((c) => Math.abs(c.close - c.open));
  const sortedBody = [...body].sort((a, b) => a - b);
  const normalBody = sortedBody[Math.floor(sortedBody.length * 0.75)];
  const threshold = normalBody * 2.5;

  const markers = [];
  candles.forEach((c) => {
    if (isCrash) {
      const wick = Math.min(c.open, c.close) - c.low;
      if (wick > threshold) {
        markers.push({ time: c.time, position: "belowBar", color: "#ef5350", shape: "arrowDown", text: "▼" });
      }
    } else {
      const wick = c.high - Math.max(c.open, c.close);
      if (wick > threshold) {
        markers.push({ time: c.time, position: "aboveBar", color: "#26a69a", shape: "arrowUp", text: "▲" });
      }
    }
  });

  state.candleSeries.setMarkers(markers);
}

// ---------- Fondo de tensión ----------
function applyTensionBg(tensionValue, isCrash) {
  const el = $("#tensionBg");
  if (!el) return;
  const v = Math.min(Math.max(Number(tensionValue) || 0, 0), 100);
  const alpha = (v / 100) * 0.12;
  if (v < 20) {
    el.style.background = "transparent";
    el.style.opacity = "0";
    return;
  }
  el.style.opacity = "1";
  el.style.background = isCrash
    ? `radial-gradient(ellipse at top, rgba(239,83,80,${alpha}) 0%, transparent 70%)`
    : `radial-gradient(ellipse at bottom, rgba(38,166,154,${alpha}) 0%, transparent 70%)`;
}

// ---------- Señales que cuentan como favorables ----------
// Señales que favorecen movimiento BAJISTA (CRASH busca spike hacia abajo)
const BEARISH_SIGNALS = new Set([
  "REVERSIÓN BAJISTA", "TENDENCIA BAJISTA", "BAJISTA", "BAJISTA DÉBIL",
  "CRUCE BAJISTA", "BREAKOUT BAJISTA", "SOBRECOMPRADO", "SOBRECOMPRA EXTREMA",
  "SPIKE INMINENTE", "PRE-SPIKE", "TENSIÓN ALTA", "TENSIÓN EXTREMA",
  "CONSOLIDACIÓN TENSA", "VELOCIDAD ALTA", "RANGO AMPLIO",
  "TECHO DEL CANAL", "RACHA EXTREMA", "RACHA ALTA", "DIVERGENCIA BAJISTA",
]);
// Señales que favorecen movimiento ALCISTA (BOOM busca spike hacia arriba)
const BULLISH_SIGNALS = new Set([
  "REVERSIÓN ALCISTA", "TENDENCIA ALCISTA", "ALCISTA", "ALCISTA DÉBIL",
  "CRUCE ALCISTA", "BREAKOUT ALCISTA", "SOBREVENDIDO", "SOBREVENTA EXTREMA",
  "SPIKE INMINENTE", "PRE-SPIKE", "TENSIÓN ALTA", "TENSIÓN EXTREMA",
  "CONSOLIDACIÓN TENSA", "VELOCIDAD ALTA", "RANGO AMPLIO",
  "PISO DEL CANAL", "RACHA EXTREMA", "RACHA ALTA", "DIVERGENCIA ALCISTA",
]);

// ---------- Zonas en la gráfica ----------
function clearPriceLines() {
  if (!state.candleSeries) return;
  state.priceLines.forEach((pl) => {
    try { state.candleSeries.removePriceLine(pl); } catch (_) {}
  });
  state.priceLines = [];
}

function drawTradeZones(symbol, isCrash, favorPct) {
  clearPriceLines();
  if (!state.candles.length) return;
  // Tomar últimas 100 velas para definir el rango operativo
  const window = state.candles.slice(-100);
  const highs = window.map((c) => c.high);
  const lows  = window.map((c) => c.low);
  const recentHigh = Math.max(...highs);
  const recentLow  = Math.min(...lows);
  const range = recentHigh - recentLow;
  const last  = state.candles[state.candles.length - 1].close;

  // ATR aproximado (rango medio de las últimas 14 velas)
  const atrWin = state.candles.slice(-14);
  const atr = atrWin.reduce((s, c) => s + (c.high - c.low), 0) / Math.max(atrWin.length, 1);

  // Color según fuerza de la señal
  const strong   = favorPct >= 55;
  const moderate = favorPct >= 35 && favorPct < 55;
  const isFresh  = strong || moderate;

  // ---- Zonas según tipo de índice ----
  let entryPrice, targetPrice, stopPrice, safePrice;
  let entryLabel, targetLabel, stopLabel, safeLabel;
  let entryColor, targetColor, stopColor, safeColor;

  if (isCrash) {
    // CRASH: spike hacia ABAJO. Entrar VENTA cerca del techo, target abajo.
    entryPrice  = recentHigh - atr * 0.3;       // zona de entrada (cerca del techo)
    targetPrice = recentLow - atr * 0.5;        // objetivo del spike
    stopPrice   = recentHigh + atr * 1.0;       // stop arriba del techo
    safePrice   = recentLow + atr * 1.5;        // zona segura (lejos del techo)

    entryLabel  = `🎯 ENTRADA VENTA ${entryPrice.toFixed(3)}`;
    targetLabel = `💰 TARGET SPIKE ${targetPrice.toFixed(3)}`;
    stopLabel   = `🛑 STOP ${stopPrice.toFixed(3)}`;
    safeLabel   = `🛡️ ZONA SEGURA`;

    entryColor  = strong ? "#ef5350" : (moderate ? "#ffd54f" : "#93a1b8");
    targetColor = "#ef5350";
    stopColor   = "#ff7043";
    safeColor   = "#26c281";
  } else {
    // BOOM: spike hacia ARRIBA. Entrar COMPRA cerca del piso, target arriba.
    entryPrice  = recentLow  + atr * 0.3;       // zona de entrada (cerca del piso)
    targetPrice = recentHigh + atr * 0.5;       // objetivo del spike
    stopPrice   = recentLow  - atr * 1.0;       // stop abajo del piso
    safePrice   = recentHigh - atr * 1.5;       // zona segura (lejos del piso)

    entryLabel  = `🎯 ENTRADA COMPRA ${entryPrice.toFixed(3)}`;
    targetLabel = `💰 TARGET SPIKE ${targetPrice.toFixed(3)}`;
    stopLabel   = `🛑 STOP ${stopPrice.toFixed(3)}`;
    safeLabel   = `🛡️ ZONA SEGURA`;

    entryColor  = strong ? "#26c281" : (moderate ? "#ffd54f" : "#93a1b8");
    targetColor = "#26c281";
    stopColor   = "#ff7043";
    safeColor   = "#42a5f5";
  }

  const lineStyle = isFresh ? 0 : 2;   // 0=Solid, 2=Dashed
  const lineWidth = strong ? 3 : 2;

  const make = (price, color, title, style = lineStyle, width = 2) => {
    const pl = state.candleSeries.createPriceLine({
      price,
      color,
      lineWidth: width,
      lineStyle: style,
      axisLabelVisible: true,
      title,
    });
    state.priceLines.push(pl);
  };

  // Línea de entrada (la más importante: marcada con grosor según fuerza)
  make(entryPrice, entryColor, entryLabel, 0, lineWidth);
  // Target del spike
  make(targetPrice, targetColor, targetLabel, 2, 2);
  // Stop loss
  make(stopPrice, stopColor, stopLabel, 1, 2);     // 1=Dotted
  // Zona segura (referencia opuesta)
  make(safePrice, safeColor, safeLabel, 2, 1);
  // Precio actual de referencia (sutil)
  make(last, "#4fc3f7", `Actual ${last.toFixed(3)}`, 2, 1);
}

// ---------- Init ----------
(async function init() {
  buildChart();
  await connect();
  await loadMarkets();
})();
