/* ═══════════════════════════════════════════════════
   Alpha Fund I — Dashboard JavaScript
   ═══════════════════════════════════════════════════ */
const API = "http://localhost:5000/api";
let sectorChart, stressChart, varChart, priceChart;
let currentPriceSymbol = null, currentPeriod = "1mo";

// ── Clock ────────────────────────────────────────────
function updateClock() {
  document.getElementById("clock").textContent =
    new Date().toLocaleTimeString("en-US", { hour12: false });
}
setInterval(updateClock, 1000);
updateClock();

// ── Toast ────────────────────────────────────────────
function toast(msg, type = "info") {
  const c = document.getElementById("toastContainer");
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.innerHTML = `<span>${type === "success" ? "✓" : type === "error" ? "✕" : "ℹ"}</span><span>${msg}</span>`;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ── Nav ──────────────────────────────────────────────
document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", e => {
    e.preventDefault();
    loadTab(item.dataset.tab);
  });
});

function loadTab(tab) {
  document.querySelectorAll(".nav-item").forEach(n => n.classList.toggle("active", n.dataset.tab === tab));
  document.querySelectorAll(".tab-content").forEach(s => s.classList.toggle("active", s.id === `tab-${tab}`));
  const titles = { dashboard: "Dashboard", portfolio: "Portfolio", risk: "Risk Analysis", signals: "Trade Signals", orders: "Orders", market: "Market Data" };
  document.getElementById("pageTitle").textContent = titles[tab] || tab;
  if (tab === "dashboard") loadDashboard();
  if (tab === "portfolio") loadPositions();
  if (tab === "risk") loadRisk();
  if (tab === "signals") loadSignals();
  if (tab === "orders") loadOrders();
  if (tab === "market") loadWatchlist();
}

// ── Fetch helper ─────────────────────────────────────
async function apiFetch(path) {
  try {
    const r = await fetch(API + path);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch (e) {
    console.error("API error:", e);
    return null;
  }
}

function fmt(n, decimals = 2) {
  if (n == null) return "—";
  return Number(n).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
function fmtUSD(n) { return n == null ? "—" : "$" + fmt(n); }
function fmtPct(n) { return n == null ? "—" : fmt(n) + "%"; }
function colorClass(v) { return v > 0 ? "text-green" : v < 0 ? "text-red" : ""; }

// ═══════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════
async function loadDashboard() {
  const [port, risk, overview] = await Promise.all([
    apiFetch("/portfolio"), apiFetch("/risk/report"), apiFetch("/market/overview")
  ]);
  if (port) renderKPIs(port, risk);
  if (overview) renderMarketOverview(overview);
  if (port) renderSectorChart(port.positions || []);
  loadTopSignals();
}

function renderKPIs(port, risk) {
  set("kpiNav", fmtUSD(port.total_nav));
  const pnl = port.total_pnl;
  setEl("kpiPnl", fmtUSD(pnl), colorClass(pnl));
  setEl("kpiPnlPct", fmtPct(port.total_pnl_pct), colorClass(pnl));
  set("kpiCash", fmtUSD(port.cash));
  set("kpiPositions", `${port.num_positions} positions`);

  if (risk && risk.var_analysis) {
    const v = risk.var_analysis.historical_95 || {};
    set("kpiVar", fmtUSD(Math.abs(v.var_dollar || 0)));
    set("kpiCvar", `CVaR: ${fmtUSD(Math.abs(v.cvar_dollar || 0))}`);
  }
  if (risk && risk.portfolio_metrics) {
    const m = risk.portfolio_metrics;
    set("kpiSharpe", fmt(m.sharpe_ratio, 2));
    set("kpiSortino", `Sortino: ${fmt(m.sortino_ratio, 2)}`);
    const mdd = m.max_drawdown;
    setEl("kpiMdd", fmtPct(mdd), mdd < 0 ? "text-red" : "");
    set("kpiVol", `Vol: ${fmtPct(m.annualized_volatility)}`);
  }
}

function renderMarketOverview(data) {
  const grid = document.getElementById("marketOverviewGrid");
  grid.innerHTML = Object.entries(data).map(([name, d]) => {
    const chg = d.change_pct || 0;
    return `<div class="market-tile">
      <div class="market-tile-name">${name}</div>
      <div class="market-tile-price">${d.price ? fmt(d.price) : "—"}</div>
      <div class="market-tile-change ${chg >= 0 ? "positive" : "negative"}">${chg >= 0 ? "▲" : "▼"} ${Math.abs(chg).toFixed(2)}%</div>
    </div>`;
  }).join("");
}

function renderSectorChart(positions) {
  const sectors = {};
  positions.forEach(p => {
    const s = p.sector || "Unknown";
    sectors[s] = (sectors[s] || 0) + (p.market_value || 0);
  });
  const labels = Object.keys(sectors);
  const values = Object.values(sectors);
  const colors = ["#38bdf8","#34d399","#a78bfa","#fbbf24","#f87171","#818cf8","#fb923c","#e879f9"];
  const ctx = document.getElementById("sectorChart").getContext("2d");
  if (sectorChart) sectorChart.destroy();
  sectorChart = new Chart(ctx, {
    type: "doughnut",
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { color: "#94a3b8", font: { size: 11 }, padding: 10 } } },
      cutout: "68%"
    }
  });
}

async function loadTopSignals() {
  const signals = await apiFetch("/signals?symbols=AAPL,MSFT,GOOGL,NVDA,TSLA,META,AMZN,JPM");
  if (!signals) return;
  const el = document.getElementById("topSignalsSummary");
  const top = signals.filter(s => s.signal !== "HOLD").slice(0, 8);
  if (!top.length) { el.innerHTML = '<span class="text-muted">No strong signals currently</span>'; return; }
  el.innerHTML = top.map(s => `
    <div class="signal-summary-chip" onclick="loadTab('signals')">
      <span class="symbol-badge">${s.symbol}</span>
      <span class="signal-badge ${s.signal}">${s.signal}</span>
      <span class="text-muted">${s.confidence}%</span>
    </div>`).join("");
}

// ═══════════════════════════════════════════════════
// PORTFOLIO
// ═══════════════════════════════════════════════════
async function loadPositions() {
  const data = await apiFetch("/portfolio/positions");
  const tbody = document.getElementById("positionsBody");
  if (!data || !data.length) { tbody.innerHTML = '<tr><td colspan="10" class="loading-cell">No positions</td></tr>'; return; }
  tbody.innerHTML = data.map(p => {
    const pnl = p.unrealized_pnl || 0;
    return `<tr>
      <td><span class="symbol-badge">${p.symbol}</span></td>
      <td class="mono">${fmt(p.quantity, 0)}</td>
      <td class="mono">${fmtUSD(p.avg_cost)}</td>
      <td class="mono">${fmtUSD(p.current_price)}</td>
      <td class="mono">${fmtUSD(p.market_value)}</td>
      <td class="mono ${colorClass(pnl)}">${fmtUSD(pnl)}</td>
      <td class="mono ${colorClass(pnl)}">${fmtPct(p.unrealized_pnl_pct)}</td>
      <td class="mono">${fmtPct(p.weight_pct)}</td>
      <td>${p.sector || "—"}</td>
      <td><div class="action-btns">
        <button class="btn btn-sm btn-danger" onclick="closePosition('${p.symbol}')">Close</button>
      </div></td>
    </tr>`;
  }).join("");
}

async function closePosition(symbol) {
  if (!confirm(`Close entire position in ${symbol}?`)) return;
  const r = await fetch(`${API}/portfolio/close_position`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol })
  });
  const d = await r.json();
  if (r.ok) { toast(`Closed ${symbol}. P&L: ${fmtUSD(d.realized_pnl)}`, "success"); loadPositions(); }
  else toast(d.error || "Error", "error");
}

function openAddPosition() { document.getElementById("addPositionModal").classList.add("open"); }
function closeAddPosition() { document.getElementById("addPositionModal").classList.remove("open"); }

async function submitAddPosition() {
  const body = {
    symbol: document.getElementById("newSymbol").value.trim(),
    quantity: parseFloat(document.getElementById("newQty").value),
    avg_cost: parseFloat(document.getElementById("newCost").value),
    sector: document.getElementById("newSector").value.trim() || "Unknown"
  };
  if (!body.symbol || !body.quantity || !body.avg_cost) { toast("Fill all fields", "error"); return; }
  const r = await fetch(`${API}/portfolio/add_position`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  });
  const d = await r.json();
  if (r.ok) { toast(`Added ${body.symbol}`, "success"); closeAddPosition(); loadPositions(); }
  else toast(d.error || "Error", "error");
}

// ═══════════════════════════════════════════════════
// RISK
// ═══════════════════════════════════════════════════
async function loadRisk() {
  const [report, stress] = await Promise.all([apiFetch("/risk/report"), apiFetch("/risk/stress_test")]);
  if (report) {
    const m = report.portfolio_metrics || {};
    const va = report.var_analysis || {};
    const vb = report.vs_benchmark || {};
    const h95 = va.historical_95 || {}; const h99 = va.historical_99 || {};
    set("riskVar95", fmtPct(Math.abs(h95.var_pct || 0)));
    set("riskVarDollar", fmtUSD(Math.abs(h95.var_dollar || 0)));
    set("riskVar99", fmtPct(Math.abs(h99.var_pct || 0)));
    set("riskVar99Dollar", fmtUSD(Math.abs(h99.var_dollar || 0)));
    set("riskCvar", fmtPct(Math.abs(h95.cvar_pct || 0)));
    set("riskBeta", fmt(vb.beta, 2));
    set("riskAlpha", `Alpha: ${fmtPct(vb.alpha)}`);
    set("riskVol", fmtPct(m.annualized_volatility));
    set("riskIR", fmt(vb.information_ratio, 2));
    set("riskCalmar", `Calmar: ${fmt(m.calmar_ratio, 2)}`);

    renderVarChart(va);
    if (report.correlation_matrix) renderCorrelation(report.correlation_matrix);
  }
  if (stress) renderStressChart(stress);
}

function renderStressChart(data) {
  const ctx = document.getElementById("stressChart").getContext("2d");
  if (stressChart) stressChart.destroy();
  stressChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map(d => d.scenario),
      datasets: [{ label: "P&L Impact ($)", data: data.map(d => d.estimated_pnl),
        backgroundColor: data.map(d => d.estimated_pnl < 0 ? "rgba(248,113,113,0.7)" : "rgba(52,211,153,0.7)"),
        borderRadius: 6 }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#94a3b8", callback: v => "$" + (v/1e6).toFixed(1) + "M" }, grid: { color: "rgba(255,255,255,0.04)" } },
        y: { ticks: { color: "#94a3b8", font: { size: 10 } }, grid: { display: false } }
      }
    }
  });
}

function renderVarChart(va) {
  const ctx = document.getElementById("varChart").getContext("2d");
  if (varChart) varChart.destroy();
  const labels = ["Hist 95%", "Hist 99%", "Parametric 95%", "MonteCarlo 95%"];
  const values = [
    Math.abs((va.historical_95 || {}).var_dollar || 0),
    Math.abs((va.historical_99 || {}).var_dollar || 0),
    Math.abs((va.parametric_95 || {}).var_dollar || 0),
    Math.abs((va.monte_carlo_95 || {}).var_dollar || 0),
  ];
  varChart = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets: [{ label: "VaR ($)", data: values, backgroundColor: "rgba(56,189,248,0.6)", borderRadius: 6 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#94a3b8", font: { size: 10 } }, grid: { display: false } },
        y: { ticks: { color: "#94a3b8", callback: v => "$" + (v/1e3).toFixed(0) + "K" }, grid: { color: "rgba(255,255,255,0.04)" } }
      }
    }
  });
}

function renderCorrelation(matrix) {
  const symbols = Object.keys(matrix);
  let html = '<table class="corr-table"><thead><tr><th></th>';
  symbols.forEach(s => html += `<th>${s}</th>`);
  html += "</tr></thead><tbody>";
  symbols.forEach(row => {
    html += `<tr><th>${row}</th>`;
    symbols.forEach(col => {
      const v = (matrix[row] || {})[col];
      const r = v != null ? parseFloat(v) : 0;
      const bg = r > 0 ? `rgba(56,189,248,${Math.abs(r) * 0.5})` : `rgba(248,113,113,${Math.abs(r) * 0.5})`;
      html += `<td style="background:${bg}">${r.toFixed(2)}</td>`;
    });
    html += "</tr>";
  });
  html += "</tbody></table>";
  document.getElementById("correlationMatrix").innerHTML = html;
}

// ═══════════════════════════════════════════════════
// SIGNALS
// ═══════════════════════════════════════════════════
async function loadSignals() {
  const symbols = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,JPM,GS,NFLX,AMD,INTC";
  const data = await apiFetch(`/signals?symbols=${symbols}`);
  const tbody = document.getElementById("signalsBody");
  if (!data) { tbody.innerHTML = '<tr><td colspan="10" class="loading-cell">Error loading signals</td></tr>'; return; }

  tbody.innerHTML = data.map(s => {
    const sigs = s.signals || {};
    const badge = t => `<span class="signal-badge ${t}">${t}</span>`;
    return `<tr>
      <td><span class="symbol-badge clickable" onclick="showPriceChart('${s.symbol}')" style="cursor:pointer;text-decoration:underline">${s.symbol}</span></td>
      <td>${badge(s.signal)}</td>
      <td><div class="confidence-bar">
        <div class="conf-bar-track"><div class="conf-bar-fill" style="width:${s.confidence}%"></div></div>
        <span class="mono" style="font-size:11px">${s.confidence}%</span>
      </div></td>
      <td class="mono">${s.current_price ? fmtUSD(s.current_price) : "—"}</td>
      <td class="mono ${s.rsi > 70 ? "text-red" : s.rsi < 30 ? "text-green" : ""}">${s.rsi ? fmt(s.rsi, 1) : "—"}</td>
      <td class="mono">${s.macd ? fmt(s.macd, 3) : "—"}</td>
      <td>${badge(sigs.momentum || "HOLD")}</td>
      <td>${badge(sigs.bollinger || "HOLD")}</td>
      <td>${badge(sigs.mean_reversion || "HOLD")}</td>
      <td><button class="btn btn-sm btn-primary" onclick="quickOrder('${s.symbol}','${s.signal}')">Order</button></td>
    </tr>`;
  }).join("");
}

async function showPriceChart(symbol) {
  currentPriceSymbol = symbol;
  document.getElementById("priceChartCard").style.display = "block";
  document.getElementById("priceChartTitle").textContent = `${symbol} — Price`;
  await renderPriceChart(symbol, currentPeriod);
}

async function renderPriceChart(symbol, period) {
  const data = await apiFetch(`/market/history/${symbol}?period=${period}&interval=1d`);
  if (!data || !data.data) return;
  const labels = data.data.map(d => d.date?.slice(0, 10));
  const closes = data.data.map(d => d.close);
  const ctx = document.getElementById("priceChart").getContext("2d");
  if (priceChart) priceChart.destroy();
  const grad = ctx.createLinearGradient(0, 0, 0, 300);
  grad.addColorStop(0, "rgba(56,189,248,0.3)");
  grad.addColorStop(1, "rgba(56,189,248,0)");
  priceChart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets: [{ label: symbol, data: closes, borderColor: "#38bdf8", backgroundColor: grad, borderWidth: 2, pointRadius: 0, tension: 0.3, fill: true }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#94a3b8", maxTicksLimit: 8, font: { size: 10 } }, grid: { display: false } },
        y: { ticks: { color: "#94a3b8", callback: v => "$" + fmt(v) }, grid: { color: "rgba(255,255,255,0.04)" } }
      }
    }
  });
}

document.querySelectorAll(".period-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentPeriod = btn.dataset.period;
    if (currentPriceSymbol) renderPriceChart(currentPriceSymbol, currentPeriod);
  });
});

// ═══════════════════════════════════════════════════
// ORDERS
// ═══════════════════════════════════════════════════
async function loadOrders() {
  const [pending, filled] = await Promise.all([apiFetch("/orders/pending"), apiFetch("/orders/filled")]);
  renderPendingOrders(pending || []);
  renderFilledOrders(filled || []);
}

function renderPendingOrders(orders) {
  const tbody = document.getElementById("pendingOrdersBody");
  if (!orders.length) { tbody.innerHTML = '<tr><td colspan="8" class="loading-cell">No pending orders</td></tr>'; return; }
  tbody.innerHTML = orders.map(o => `<tr>
    <td class="mono text-muted">${o.order_id}</td>
    <td><span class="symbol-badge">${o.symbol}</span></td>
    <td><span class="signal-badge ${o.side === "buy" ? "BUY" : "SELL"}">${o.side.toUpperCase()}</span></td>
    <td class="mono">${fmt(o.quantity, 0)}</td>
    <td>${o.order_type}</td>
    <td class="text-muted">${o.strategy}</td>
    <td class="text-muted">${o.created_at?.slice(0, 16).replace("T", " ")}</td>
    <td><div class="action-btns">
      <button class="btn btn-sm btn-success" onclick="executeOrder('${o.order_id}')">Execute</button>
      <button class="btn btn-sm btn-danger" onclick="cancelOrder('${o.order_id}')">Cancel</button>
    </div></td>
  </tr>`).join("");
}

function renderFilledOrders(orders) {
  const tbody = document.getElementById("filledOrdersBody");
  if (!orders.length) { tbody.innerHTML = '<tr><td colspan="7" class="loading-cell">No filled orders</td></tr>'; return; }
  tbody.innerHTML = orders.map(o => `<tr>
    <td class="mono text-muted">${o.order_id}</td>
    <td><span class="symbol-badge">${o.symbol}</span></td>
    <td><span class="signal-badge ${o.side === "buy" ? "BUY" : "SELL"}">${o.side.toUpperCase()}</span></td>
    <td class="mono">${fmt(o.quantity, 0)}</td>
    <td class="mono">${fmtUSD(o.filled_price)}</td>
    <td class="text-muted">${o.strategy}</td>
    <td class="text-muted">${o.filled_at?.slice(0, 16).replace("T", " ") || "—"}</td>
  </tr>`).join("");
}

async function executeOrder(id) {
  const r = await fetch(`${API}/orders/execute/${id}`, { method: "POST" });
  const d = await r.json();
  if (r.ok) { toast("Order executed!", "success"); loadOrders(); }
  else toast(d.error || "Error", "error");
}

async function cancelOrder(id) {
  const r = await fetch(`${API}/orders/cancel/${id}`, { method: "POST" });
  if (r.ok) { toast("Order cancelled", "info"); loadOrders(); }
}

function openCreateOrder() { document.getElementById("createOrderModal").classList.add("open"); }
function closeCreateOrder() { document.getElementById("createOrderModal").classList.remove("open"); }

document.getElementById("orderType").addEventListener("change", e => {
  document.getElementById("limitPriceGroup").style.display = e.target.value === "limit" ? "block" : "none";
});

async function submitCreateOrder() {
  const body = {
    symbol: document.getElementById("orderSymbol").value.trim().toUpperCase(),
    side: document.getElementById("orderSide").value,
    quantity: parseFloat(document.getElementById("orderQty").value),
    order_type: document.getElementById("orderType").value,
    limit_price: parseFloat(document.getElementById("orderLimitPrice").value) || null,
  };
  if (!body.symbol || !body.quantity) { toast("Fill all fields", "error"); return; }
  const r = await fetch(`${API}/orders/create`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  });
  const d = await r.json();
  if (r.ok) { toast("Order created", "success"); closeCreateOrder(); loadOrders(); }
  else toast(d.error || "Error", "error");
}

async function quickOrder(symbol, signal) {
  if (signal === "HOLD") { toast("No action needed — signal is HOLD", "info"); return; }
  document.getElementById("orderSymbol").value = symbol;
  document.getElementById("orderSide").value = signal === "BUY" ? "buy" : "sell";
  document.getElementById("orderQty").value = 100;
  openCreateOrder();
  loadTab("orders");
}

// ═══════════════════════════════════════════════════
// WATCHLIST
// ═══════════════════════════════════════════════════
async function loadWatchlist() {
  const data = await apiFetch("/market/watchlist");
  const tbody = document.getElementById("watchlistBody");
  if (!data) { tbody.innerHTML = '<tr><td colspan="7" class="loading-cell">Error</td></tr>'; return; }
  const rows = Object.values(data);
  tbody.innerHTML = rows.map(q => {
    const chg = q.change_pct || 0;
    return `<tr>
      <td><span class="symbol-badge">${q.symbol}</span></td>
      <td class="mono">${q.price ? fmtUSD(q.price) : "—"}</td>
      <td class="mono ${colorClass(chg)}">${q.change ? (chg >= 0 ? "+" : "") + fmtUSD(q.change) : "—"}</td>
      <td class="mono ${colorClass(chg)}">${(chg >= 0 ? "+" : "") + fmtPct(chg)}</td>
      <td class="mono">${q.day_high ? fmtUSD(q.day_high) : "—"}</td>
      <td class="mono">${q.day_low ? fmtUSD(q.day_low) : "—"}</td>
      <td><button class="btn btn-sm btn-ghost" onclick="showPriceChart('${q.symbol}');loadTab('signals')">Chart</button></td>
    </tr>`;
  }).join("");
}

// ── Search filter ─────────────────────────────────
document.getElementById("symbolSearch").addEventListener("input", e => {
  const q = e.target.value.toUpperCase();
  document.querySelectorAll("#watchlistBody tr").forEach(row => {
    row.style.display = row.textContent.toUpperCase().includes(q) ? "" : "none";
  });
});

// ═══════════════════════════════════════════════════
// WebSocket
// ═══════════════════════════════════════════════════
function setupSocket() {
  try {
    const socket = io("http://localhost:5000");
    socket.on("connect", () => {
      document.getElementById("liveDot").classList.add("live");
      document.getElementById("liveStatus").textContent = "Live";
    });
    socket.on("disconnect", () => {
      document.getElementById("liveDot").classList.remove("live");
      document.getElementById("liveStatus").textContent = "Disconnected";
    });
    socket.on("price_update", data => {
      if (data.nav) {
        const el = document.getElementById("kpiNav");
        if (el) el.textContent = fmtUSD(data.nav);
      }
    });
  } catch (e) {
    document.getElementById("liveStatus").textContent = "Offline mode";
  }
}

// ── Utilities ─────────────────────────────────────
function set(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function setEl(id, val, cls) { const el = document.getElementById(id); if (!el) return; el.textContent = val; el.className = `kpi-value ${cls}`; }
function refreshAll() { const active = document.querySelector(".tab-content.active"); if (active) loadTab(active.id.replace("tab-","")); }

// ── Init ──────────────────────────────────────────
setupSocket();
loadDashboard();
