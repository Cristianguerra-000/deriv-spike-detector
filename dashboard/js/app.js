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

function buildChart() {
  state.chart = LightweightCharts.createChart($("#chart"), {
    layout: { background: { color: "#131a2b" }, textColor: "#e6edf7" },
    grid: { vertLines: { color: "#1b2438" }, horzLines: { color: "#1b2438" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    crosshair: { mode: 0 },
  });
  state.candleSeries = state.chart.addCandlestickSeries({
    upColor: "#26a69a", downColor: "#ef5350",
    borderUpColor: "#26a69a", borderDownColor: "#ef5350",
    wickUpColor: "#26a69a", wickDownColor: "#ef5350",
  });
  window.addEventListener("resize", () => {
    state.chart.applyOptions({ width: $("#chart").clientWidth });
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
$("#refreshBtn").addEventListener("click", () => state.symbol && loadCandles(state.symbol));

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
  $("#symbolTitle").textContent = displayName || symbol;
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
  // Indicador de carga
  $("#symbolTitle").textContent = `${symbol} · Cargando histórico…`;
  const resp = await send({
    ticks_history: symbol,
    count: 5000,            // máximo permitido por la API de Deriv
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
  // Ajustar zoom para mostrar todo el histórico cargado
  state.chart.timeScale().fitContent();
  // Restaurar título con número de velas cargadas
  const displayName = document.querySelector(`.symbol-list li[data-symbol="${symbol}"]`)?.textContent || symbol;
  $("#symbolTitle").textContent = `${displayName} · ${candles.length} velas`;
}

function onOhlc(ohlc) {
  if (ohlc.symbol !== state.symbol) return;
  state.candleSeries.update({
    time: +ohlc.open_time,
    open: +ohlc.open, high: +ohlc.high, low: +ohlc.low, close: +ohlc.close,
  });
  // Actualizar última vela en cache
  if (state.candles.length) {
    const last = state.candles[state.candles.length - 1];
    if (+ohlc.open_time === last.time) {
      last.open = +ohlc.open; last.high = +ohlc.high;
      last.low = +ohlc.low; last.close = +ohlc.close;
    } else {
      state.candles.push({
        time: +ohlc.open_time,
        open: +ohlc.open, high: +ohlc.high, low: +ohlc.low, close: +ohlc.close,
      });
      if (state.candles.length > 5100) state.candles.shift();
    }
  }
  updateMAs();
}

function onTick(_tick) { /* hook futuro */ }

// ---------- Firebase: resultados de algoritmos ----------
const resultUnsubs = [];

async function loadAlgorithmResults(symbol) {
  // Limpia listeners previos
  while (resultUnsubs.length) resultUnsubs.pop()();
  const grid = $("#resultsGrid");
  grid.innerHTML = "";
  // Limpia zonas de la gráfica del símbolo anterior
  clearPriceLines();
  clearFib();

  // Resetear panel de entrada
  const panel = $("#entryPanel");
  panel.className = "entry-panel entry-waiting";
  $("#entryIcon").textContent = "⏳";
  $("#entryTitle").textContent = "Cargando señales…";
  $("#entrySub").textContent = "Leyendo algoritmos de Firestore";
  $("#entryScore").textContent = "0/0";
  $("#entryBar").style.width = "0%";

  try {
    const algosSnap = await getDocs(collection(db, "results"));
    if (algosSnap.empty) {
      grid.innerHTML = `<div class="result-card"><div class="name">Sin datos</div><div class="value">Ejecuta el pipeline Python</div></div>`;
      $("#firebaseStatus").textContent = "Firebase: vacío";
      return;
    }

    $("#firebaseStatus").textContent = `Firebase: ${algosSnap.size} algoritmos`;

    algosSnap.forEach((algoDoc) => {
      const algoName = algoDoc.id;
      const card = document.createElement("div");
      card.className = "result-card";
      card.id = `card-${algoName.replace(/\./g, "-")}`;
      card.innerHTML = `
        <div class="algo-name">${algoName}</div>
        <span class="signal-badge" data-signal="">…</span>
        <div class="algo-value">—</div>
        <div class="algo-interpretation">Cargando…</div>`;
      grid.appendChild(card);

      // Escucha el documento fijo: results/{algoName}/symbols/{symbol}
      const docRef = doc(db, "results", algoName, "symbols", symbol);
      const unsub = onSnapshot(
        docRef,
        (snap) => {
          if (!snap.exists()) {
            // Sin datos para este símbolo → ocultar card (algoritmo no aplica)
            card.remove();
            return;
          }
          // Re-insertar si estaba oculta (cambio de símbolo rápido)
          if (!grid.contains(card)) grid.appendChild(card);
          const data = snap.data();
          const signal = data.signal || "NEUTRO";
          // Filtrar señales N/A (algoritmo no aplica al mercado)
          if (signal === "N/A") { card.remove(); return; }
          const badge = card.querySelector(".signal-badge");
          badge.textContent = signal;
          badge.className = `signal-badge ${signal.toLowerCase().replace(/\s+/g, "-")}`;
          card.querySelector(".algo-value").textContent = formatValue(data.value);
          card.querySelector(".algo-interpretation").textContent = data.interpretation || "";
          // Actualizar contador y panel de entrada
          $("#firebaseStatus").textContent = `Firebase: ${grid.children.length} señales`;
          updateEntryPanel(symbol);
        },
        () => { card.querySelector(".algo-interpretation").textContent = "Error al leer Firestore."; },
      );
      resultUnsubs.push(unsub);
    });
  } catch (err) {
    console.error("Firebase:", err);
    $("#firebaseStatus").textContent = "Firebase: error";
  }
}

// ---------- Panel de entrada fuerte ----------
// Señales que favorecen movimiento BAJISTA (CRASH busca spike hacia abajo)
const BEARISH_SIGNALS = new Set([
  "REVERSIÓN BAJISTA", "TENDENCIA BAJISTA", "BAJISTA", "BAJISTA DÉBIL",
  "CRUCE BAJISTA", "BREAKOUT BAJISTA", "SOBRECOMPRADO", "SOBRECOMPRA EXTREMA",
  "SPIKE INMINENTE", "PRE-SPIKE", "TENSIÓN ALTA", "TENSIÓN EXTREMA",
  "CONSOLIDACIÓN TENSA", "VELOCIDAD ALTA", "RANGO AMPLIO",
]);
// Señales que favorecen movimiento ALCISTA (BOOM busca spike hacia arriba)
const BULLISH_SIGNALS = new Set([
  "REVERSIÓN ALCISTA", "TENDENCIA ALCISTA", "ALCISTA", "ALCISTA DÉBIL",
  "CRUCE ALCISTA", "BREAKOUT ALCISTA", "SOBREVENDIDO", "SOBREVENTA EXTREMA",
  "SPIKE INMINENTE", "PRE-SPIKE", "TENSIÓN ALTA", "TENSIÓN EXTREMA",
  "CONSOLIDACIÓN TENSA", "VELOCIDAD ALTA", "RANGO AMPLIO",
]);

function updateEntryPanel(symbol) {
  if (!symbol) return;
  const grid = $("#resultsGrid");
  const cards = Array.from(grid.querySelectorAll(".result-card"));
  if (!cards.length) return;

  const isCrash = symbol.startsWith("CRASH");
  const isBoom  = symbol.startsWith("BOOM");
  if (!isCrash && !isBoom) {
    // Símbolo no crash/boom → ocultar panel
    $("#entryPanel").className = "entry-panel entry-waiting";
    clearPriceLines();
    return;
  }

  let favor = 0;
  let total = 0;
  cards.forEach((card) => {
    const badge = card.querySelector(".signal-badge");
    if (!badge) return;
    const sig = (badge.textContent || "").trim().toUpperCase();
    if (!sig || sig === "…" || sig === "NEUTRO" || sig === "SIN PATRÓN" || sig === "LATERAL" || sig === "EQUILIBRADO") return;
    total++;
    if (isCrash && BEARISH_SIGNALS.has(sig)) favor++;
    if (isBoom  && BULLISH_SIGNALS.has(sig))  favor++;
  });

  const pct = total > 0 ? (favor / total) * 100 : 0;
  const panel = $("#entryPanel");
  const dirLabel = isCrash ? "VENTA (spike bajista)" : "COMPRA (spike alcista)";
  const dirEmoji = isCrash ? "⬇️" : "⬆️";

  $("#entryScore").textContent = `${favor}/${total}`;
  $("#entryBar").style.width = `${pct.toFixed(0)}%`;

  if (pct >= 55) {
    panel.className = "entry-panel entry-strong";
    $("#entryIcon").textContent = isCrash ? "🔴" : "🟢";
    $("#entryTitle").textContent = `${dirEmoji} SEÑAL FUERTE DE ENTRADA — ${dirLabel}`;
    $("#entrySub").textContent = `${favor} de ${total} algoritmos confirman el spike. Alta probabilidad de movimiento. Considera entrar.`;
  } else if (pct >= 35) {
    panel.className = "entry-panel entry-moderate";
    $("#entryIcon").textContent = "🟡";
    $("#entryTitle").textContent = `⚠️ SEÑAL MODERADA — Confirmar`;
    $("#entrySub").textContent = `${favor} de ${total} señales a favor de ${dirLabel}. Esperar más confirmación antes de entrar.`;
  } else {
    panel.className = "entry-panel entry-weak";
    $("#entryIcon").textContent = "⏸️";
    $("#entryTitle").textContent = "🚫 SEÑAL DÉBIL — No entrar aún";
    $("#entrySub").textContent = `Solo ${favor} de ${total} señales a favor. Las condiciones no son óptimas para ${dirLabel}.`;
  }

  // Dibujar zonas en la gráfica
  drawTradeZones(symbol, isCrash, pct);
}

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

function formatValue(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toFixed(5);
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

// ---------- Init ----------
(async function init() {
  buildChart();
  await connect();
  await loadMarkets();
})();
