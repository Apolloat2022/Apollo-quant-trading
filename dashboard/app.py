"""
Flask Web Dashboard with real-time WebSocket updates.
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("America/Chicago")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "quant-trading-secret-2024")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# In-memory signal store (replace with DB in production)
_signals_store: list[dict] = []
_lock = threading.Lock()


def add_signal(signal: dict) -> None:
    """Add a signal to the in-memory store and push via WebSocket."""
    with _lock:
        signal["timestamp"] = datetime.now(_TZ).isoformat()
        _signals_store.append(signal)
        if len(_signals_store) > 500:
            _signals_store.pop(0)
    socketio.emit("new_signal", signal, namespace="/")


# ──────────────────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve main dashboard page."""
    return render_template("dashboard.html")


@app.route("/api/add_signal", methods=["POST"])
def api_add_signal():
    """Receive a signal from the scanner process."""
    try:
        signal = request.get_json(force=True) or {}
        if signal:
            add_signal(signal)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error(f"add_signal error: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/signals")
def api_signals():
    """Return latest signals as JSON."""
    limit = int(request.args.get("limit", 100))
    with _lock:
        recent = list(reversed(_signals_store[-limit:]))
    return jsonify(recent)


@app.route("/api/metrics")
def api_metrics():
    """Return aggregate metrics."""
    with _lock:
        signals = list(_signals_store)

    total  = len(signals)
    buys   = sum(1 for s in signals if s.get("signal") == "BUY")
    sells  = sum(1 for s in signals if s.get("signal") == "SELL")
    holds  = total - buys - sells
    avg_conf = sum(s.get("confidence", 0) for s in signals) / (total or 1)

    return jsonify({
        "total_signals": total,
        "buy_count":     buys,
        "sell_count":    sells,
        "hold_count":    holds,
        "avg_confidence": round(avg_conf, 4),
    })


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    """Run a backtest on the requested symbol."""
    try:
        body       = request.get_json(force=True) or {}
        symbol     = body.get("symbol", "AAPL")
        asset_type = body.get("asset_type", "stock")
        capital    = float(body.get("capital", 10_000))
        strategy   = body.get("strategy", "combined")

        from data_fetcher import fetch_asset
        from strategies.advanced_strategies import combined_strategy, momentum_strategy
        from backtest.engine import BacktestEngine

        df = fetch_asset(symbol, asset_type, timeframe="1h", period="180d")
        if df is None or df.empty:
            return jsonify({"error": "Failed to fetch data"}), 400

        strat_fn = combined_strategy if strategy == "combined" else momentum_strategy
        engine   = BacktestEngine(strat_fn, initial_capital=capital)
        result   = engine.run(df, symbol=symbol)

        return jsonify({
            "symbol":             symbol,
            "total_return":       result.total_return,
            "win_rate":           result.win_rate,
            "profit_factor":      result.profit_factor,
            "sharpe":             result.sharpe,
            "max_drawdown":       result.max_drawdown,
            "total_trades":       result.total_trades,
            "avg_trade_duration": result.avg_trade_duration,
        })
    except Exception as exc:
        logger.error(f"Backtest API error: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/compare", methods=["POST"])
def api_compare():
    """Compare multiple strategies on the same symbol."""
    try:
        body       = request.get_json(force=True) or {}
        symbol     = body.get("symbol", "AAPL")
        asset_type = body.get("asset_type", "stock")
        capital    = float(body.get("capital", 10_000))

        from data_fetcher import fetch_asset
        from strategies.advanced_strategies import (
            combined_strategy, momentum_strategy,
            mean_reversion_strategy, volume_price_strategy,
        )
        from backtest.engine import BacktestEngine

        df = fetch_asset(symbol, asset_type, timeframe="1h", period="180d")
        if df is None or df.empty:
            return jsonify({"error": "Failed to fetch data"}), 400

        strategies = {
            "combined":       combined_strategy,
            "momentum":       momentum_strategy,
            "mean_reversion": mean_reversion_strategy,
            "volume_price":   volume_price_strategy,
        }

        comparison = {}
        for name, fn in strategies.items():
            engine = BacktestEngine(fn, initial_capital=capital)
            result = engine.run(df, symbol=symbol)
            comparison[name] = {
                "total_return":  result.total_return,
                "win_rate":      result.win_rate,
                "sharpe":        result.sharpe,
                "max_drawdown":  result.max_drawdown,
                "total_trades":  result.total_trades,
            }

        return jsonify({"symbol": symbol, "comparison": comparison})
    except Exception as exc:
        logger.error(f"Compare API error: {exc}")
        return jsonify({"error": str(exc)}), 500


# ──────────────────────────────────────────────────────────
# WEBSOCKET EVENTS
# ──────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    logger.info(f"WebSocket client connected: {request.sid}")
    with _lock:
        recent = list(reversed(_signals_store[-20:]))
    emit("initial_signals", recent)


@socketio.on("disconnect")
def on_disconnect():
    logger.info(f"WebSocket client disconnected: {request.sid}")


def run_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    """Start the Flask-SocketIO server."""
    logger.info(f"Dashboard starting on http://{host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=False)
