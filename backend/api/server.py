import os
import logging
import threading
import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Initialize Flask App
app = Flask(__name__)
app.config["SECRET_KEY"] = "hf-secret-2024"
CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Define frontend path for static serving
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")

@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(FRONTEND_DIR, path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from backend.data_ingestion.market_data import MarketDataIngestion
from backend.models.portfolio import Portfolio, Position, Order
from backend.risk.risk_engine import RiskEngine
from backend.trading.engine import SignalGenerator, OrderManager

# ── Core Services ─────────────────────────────────────────────────────
data_engine = MarketDataIngestion(cache_ttl=30)
risk_engine = RiskEngine()
signal_gen = SignalGenerator()
order_mgr = OrderManager(max_position_pct=0.10, auto_execute=False)

# ── Default Portfolio ─────────────────────────────────────────────────
portfolio = Portfolio(name="Custom Alpha Fund", initial_cash=5_000_000.0)
WATCHLIST = ["EQUITY", "OIL", "GOLD", "BONDS", "INFLATION", "USD_INDEX", "SPY", "AAPL"]

# Seed with initial positions from local datasets
_seed_positions = [
    Position("EQUITY", 1000, 150.0, sector="Equity"),
    Position("OIL", 500, 60.0, sector="Commodities"),
    Position("GOLD", 200, 2000.0, sector="Commodities"),
    Position("BONDS", 300, 100.0, sector="Fixed Income"),
]
for pos in _seed_positions:
    portfolio.add_position(pos)
    portfolio.cash -= pos.cost_basis
    data_engine.subscribe(pos.symbol)

for sym in WATCHLIST:
    data_engine.subscribe(sym)

# ── Real-Time Price Update Callback ──────────────────────────────────
def on_price_update(quotes: dict):
    prices = {sym: q.get("price") or 0.0 for sym, q in quotes.items() if q.get("price")}
    portfolio.update_prices(prices)
    socketio.emit("price_update", {"quotes": {sym: q for sym, q in quotes.items()}, "nav": portfolio.total_nav})

data_engine.add_callback(on_price_update)
if os.environ.get("VERCEL") != "1":
    data_engine.start_polling(interval=20)


# ═══════════════════════════════════════════════════════════════════
# REST API Routes
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "HedgeFund API v1.0"})


# ── Portfolio ─────────────────────────────────────────────────────────
@app.route("/api/portfolio")
def get_portfolio():
    prices = data_engine.get_prices(list(portfolio.positions.keys()))
    portfolio.update_prices(prices)
    return jsonify(portfolio.to_dict())

@app.route("/api/portfolio/positions")
def get_positions():
    prices = data_engine.get_prices(list(portfolio.positions.keys()))
    portfolio.update_prices(prices)
    weights = portfolio.get_weights()
    positions = []
    for sym, pos in portfolio.positions.items():
        d = pos.to_dict()
        d["weight_pct"] = round(weights.get(sym, 0) * 100, 2)
        positions.append(d)
    return jsonify(positions)

@app.route("/api/portfolio/add_position", methods=["POST"])
def add_position():
    data = request.json
    required = ["symbol", "quantity", "avg_cost"]
    if not all(k in data for k in required):
        return jsonify({"error": "Missing required fields"}), 400
    pos = Position(
        symbol=data["symbol"].upper(),
        quantity=float(data["quantity"]),
        avg_cost=float(data["avg_cost"]),
        sector=data.get("sector", "Unknown"),
        asset_class=data.get("asset_class", "equity"),
    )
    cost = pos.cost_basis
    if cost > portfolio.cash:
        return jsonify({"error": "Insufficient cash"}), 400
    portfolio.add_position(pos)
    portfolio.cash -= cost
    data_engine.subscribe(pos.symbol)
    return jsonify({"message": f"Position added: {pos.symbol}", "position": pos.to_dict()})

@app.route("/api/portfolio/close_position", methods=["POST"])
def close_position():
    data = request.json
    sym = data.get("symbol", "").upper()
    if sym not in portfolio.positions:
        return jsonify({"error": "Position not found"}), 404
    pos = portfolio.positions[sym]
    quote = data_engine.get_quote(sym)
    price = quote.get("price") or pos.avg_cost
    realized = portfolio.remove_position(sym, pos.quantity, price)
    portfolio.cash += pos.quantity * price
    return jsonify({"message": f"Closed {sym}", "realized_pnl": round(realized, 2)})


# ── Market Data ───────────────────────────────────────────────────────
@app.route("/api/market/quote/<symbol>")
def get_quote(symbol):
    return jsonify(data_engine.get_quote(symbol.upper()))

@app.route("/api/market/quotes")
def get_quotes():
    symbols = request.args.get("symbols", "").upper().split(",")
    symbols = [s.strip() for s in symbols if s.strip()]
    if not symbols:
        symbols = WATCHLIST
    return jsonify(data_engine.get_multi_quotes(symbols))

@app.route("/api/market/history/<symbol>")
def get_history(symbol):
    period = request.args.get("period", "1y")
    interval = request.args.get("interval", "1d")
    df = data_engine.get_historical(symbol.upper(), period=period, interval=interval)
    if df.empty:
        return jsonify({"error": "No data found"}), 404
    records = df.reset_index().rename(columns={"Date": "date", "Datetime": "date"}).to_dict("records")
    for r in records:
        if hasattr(r.get("date"), "isoformat"):
            r["date"] = r["date"].isoformat()
    return jsonify({"symbol": symbol.upper(), "period": period, "interval": interval, "data": records})

@app.route("/api/market/overview")
def market_overview():
    return jsonify(data_engine.get_market_overview())

@app.route("/api/market/info/<symbol>")
def ticker_info(symbol):
    return jsonify(data_engine.get_ticker_info(symbol.upper()))

@app.route("/api/market/watchlist")
def get_watchlist():
    quotes = data_engine.get_multi_quotes(WATCHLIST)
    return jsonify(quotes)

@app.route("/api/market/local_datasets")
def list_local_datasets():
    files = [f.replace(".csv", "") for f in os.listdir(data_engine.DATA_DIR) if f.endswith(".csv")]
    return jsonify(files)


# ── Risk ──────────────────────────────────────────────────────────────
@app.route("/api/risk/report")
def risk_report():
    symbols = list(portfolio.positions.keys())
    if not symbols:
        return jsonify({"error": "No positions"}), 400
    returns_df = data_engine.get_multi_returns(symbols + ["SPY"], period="1y")
    weights = portfolio.get_weights()
    benchmark = returns_df["SPY"] if "SPY" in returns_df.columns else None
    report = risk_engine.full_risk_report(returns_df.drop(columns=["SPY"], errors="ignore"), weights, benchmark, portfolio.total_nav)
    return jsonify(report)

@app.route("/api/risk/var")
def var_report():
    symbols = list(portfolio.positions.keys())
    if not symbols:
        return jsonify({"error": "No positions"}), 400
    returns_df = data_engine.get_multi_returns(symbols, period="1y")
    weights = portfolio.get_weights()
    method = request.args.get("method", "historical")
    confidence = float(request.args.get("confidence", 0.95))
    result = risk_engine.portfolio_var(returns_df, weights, confidence, method, portfolio.total_nav)
    return jsonify(result)

@app.route("/api/risk/stress_test")
def stress_test():
    weights = portfolio.get_weights()
    results = risk_engine.stress_test(weights, portfolio.total_nav)
    return jsonify(results)

@app.route("/api/risk/drawdown/<symbol>")
def drawdown(symbol):
    returns = data_engine.get_returns(symbol.upper())
    if returns.empty:
        return jsonify({"error": "No data"}), 404
    dd_series = risk_engine.drawdown_series(returns)
    data = [{"date": str(d)[:10], "drawdown": round(float(v), 4)} for d, v in dd_series.items()]
    return jsonify({"symbol": symbol.upper(), "data": data, "max_drawdown": round(float(dd_series.min()), 4)})


# ── Signals / Trading ─────────────────────────────────────────────────
@app.route("/api/signals")
def get_signals():
    symbols_param = request.args.get("symbols", ",".join(WATCHLIST))
    symbols = [s.strip().upper() for s in symbols_param.split(",") if s.strip()]
    all_data = data_engine.get_multi_historical(symbols, period="6mo", interval="1d")
    signals = []
    for sym in symbols:
        df = all_data.get(sym, pd.DataFrame())
        sig = signal_gen.aggregate_signal(df, sym)
        signals.append(sig)
    signals.sort(key=lambda x: x["confidence"], reverse=True)
    return jsonify(signals)

@app.route("/api/signals/<symbol>")
def get_signal(symbol):
    df = data_engine.get_historical(symbol.upper(), period="6mo", interval="1d")
    sig = signal_gen.aggregate_signal(df, symbol.upper())
    return jsonify(sig)

@app.route("/api/orders/pending")
def pending_orders():
    return jsonify(order_mgr.get_pending_orders())

@app.route("/api/orders/filled")
def filled_orders():
    return jsonify(order_mgr.get_filled_orders())

@app.route("/api/orders/create", methods=["POST"])
def create_order():
    data = request.json
    order = Order(
        symbol=data["symbol"].upper(),
        side=data["side"],
        quantity=float(data["quantity"]),
        order_type=data.get("order_type", "market"),
        limit_price=data.get("limit_price"),
        strategy="manual",
        notes=data.get("notes", ""),
    )
    order_mgr.pending_orders.append(order)
    return jsonify({"message": "Order created", "order": order.to_dict()})

@app.route("/api/orders/execute/<order_id>", methods=["POST"])
def execute_order(order_id):
    order = next((o for o in order_mgr.pending_orders if o.order_id == order_id), None)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    quote = data_engine.get_quote(order.symbol)
    fill_price = quote.get("price") or 0.0
    if fill_price <= 0:
        return jsonify({"error": "Could not get fill price"}), 400
    order_mgr.execute_paper_order(order, fill_price)
    if order.side == "buy":
        pos = Position(order.symbol, order.quantity, fill_price)
        portfolio.add_position(pos)
        portfolio.cash -= order.quantity * fill_price
    else:
        portfolio.remove_position(order.symbol, order.quantity, fill_price)
        portfolio.cash += order.quantity * fill_price
    return jsonify({"message": "Order executed", "order": order.to_dict()})

@app.route("/api/orders/cancel/<order_id>", methods=["POST"])
def cancel_order(order_id):
    order = next((o for o in order_mgr.pending_orders if o.order_id == order_id), None)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    order.cancel()
    order_mgr.pending_orders = [o for o in order_mgr.pending_orders if o.order_id != order_id]
    return jsonify({"message": "Order cancelled", "order": order.to_dict()})


# ═══════════════════════════════════════════════════════════════════
# WebSocket Events
# ═══════════════════════════════════════════════════════════════════

@socketio.on("connect")
def on_connect():
    emit("connected", {"message": "Connected to HedgeFund WebSocket"})
    emit("portfolio_snapshot", portfolio.to_dict())

@socketio.on("subscribe")
def on_subscribe(data):
    symbol = data.get("symbol", "").upper()
    if symbol:
        data_engine.subscribe(symbol)
        emit("subscribed", {"symbol": symbol})

@socketio.on("request_signals")
def on_request_signals(data):
    symbols = data.get("symbols", WATCHLIST)
    all_data = data_engine.get_multi_historical(symbols, period="6mo")
    signals = [signal_gen.aggregate_signal(all_data.get(s, pd.DataFrame()), s) for s in symbols]
    emit("signals", signals)



if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
