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
  const resp = await send({
    ticks_history: symbol,
    count: 500,
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
}

function onOhlc(ohlc) {
  if (ohlc.symbol !== state.symbol) return;
  state.candleSeries.update({
    time: +ohlc.open_time,
    open: +ohlc.open, high: +ohlc.high, low: +ohlc.low, close: +ohlc.close,
  });
}

function onTick(_tick) { /* hook futuro */ }

// ---------- Firebase: resultados de algoritmos ----------
const resultUnsubs = [];

async function loadAlgorithmResults(symbol) {
  // Limpia listeners previos
  while (resultUnsubs.length) resultUnsubs.pop()();
  const grid = $("#resultsGrid");
  grid.innerHTML = "";

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
          // Actualizar contador
          $("#firebaseStatus").textContent = `Firebase: ${grid.children.length} señales`;
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
