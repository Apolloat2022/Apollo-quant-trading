"""
Flask Web Dashboard — works locally (in-memory) and on Vercel (Vercel KV).
SocketIO removed; the frontend polls /api/signals every 30 seconds instead.
"""

import logging
import os
import sys
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("America/Chicago")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, jsonify, render_template, request
from kv_store import KV_AVAILABLE, kv_get, kv_set

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "quant-trading-secret-2024")

# ── In-memory fallback (used when KV env vars are not set) ──
_signals_store: list[dict] = []
_lock = threading.Lock()
_MAX_LOCAL = 500


# ──────────────────────────────────────────────────────────
# Signal ingestion (local scanner → POST /api/add_signal)
# ──────────────────────────────────────────────────────────

def add_signal(signal: dict) -> None:
    """Add a signal from the local scanner to the in-memory store."""
    signal.setdefault("timestamp", datetime.now(_TZ).isoformat())
    with _lock:
        _signals_store.append(signal)
        if len(_signals_store) > _MAX_LOCAL:
            _signals_store.pop(0)


def _read_signals(limit: int = 100) -> list[dict]:
    """Read signals from KV (Vercel) or in-memory (local)."""
    if KV_AVAILABLE:
        return (kv_get("signals:latest") or [])[:limit]
    with _lock:
        return list(reversed(_signals_store[-limit:]))


# ──────────────────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────────────────


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/add_signal", methods=["POST"])
def api_add_signal():
    """Receive a signal from the local scanner process."""
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
    limit = int(request.args.get("limit", 100))
    return jsonify(_read_signals(limit))


@app.route("/api/metrics")
def api_metrics():
    signals = _read_signals(500)
    total    = len(signals)
    buys     = sum(1 for s in signals if s.get("signal") == "BUY")
    sells    = sum(1 for s in signals if s.get("signal") == "SELL")
    holds    = total - buys - sells
    avg_conf = sum(s.get("confidence", 0) for s in signals) / (total or 1)
    last_run = kv_get("scanner:last_run") if KV_AVAILABLE else None

    return jsonify({
        "total_signals":  total,
        "buy_count":      buys,
        "sell_count":     sells,
        "hold_count":     holds,
        "avg_confidence": round(avg_conf, 4),
        "last_scan":      last_run,
    })


@app.route("/api/backtest", methods=["POST"])
def api_backtest():
    try:
        body       = request.get_json(force=True) or {}
        symbol     = body.get("symbol", "AAPL")
        asset_type = body.get("asset_type", "stock")
        capital    = float(body.get("capital", 10_000))
        strategy   = body.get("strategy", "combined")

        try:
            from data_fetcher import fetch_asset
            from strategies.advanced_strategies import combined_strategy, momentum_strategy
            from backtest.engine import BacktestEngine
        except ImportError:
            return jsonify({"error": "Backtesting requires the full local installation. Run: python main_complete.py --mode backtest"}), 503

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
        logger.error(f"Backtest error: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/compare", methods=["POST"])
def api_compare():
    try:
        body       = request.get_json(force=True) or {}
        symbol     = body.get("symbol", "AAPL")
        asset_type = body.get("asset_type", "stock")
        capital    = float(body.get("capital", 10_000))

        try:
            from data_fetcher import fetch_asset
            from strategies.advanced_strategies import (
                combined_strategy, momentum_strategy,
                mean_reversion_strategy, volume_price_strategy,
            )
            from backtest.engine import BacktestEngine
        except ImportError:
            return jsonify({"error": "Backtesting requires the full local installation. Run: python main_complete.py --mode backtest"}), 503

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
                "total_return": result.total_return,
                "win_rate":     result.win_rate,
                "sharpe":       result.sharpe,
                "max_drawdown": result.max_drawdown,
                "total_trades": result.total_trades,
            }

        return jsonify({"symbol": symbol, "comparison": comparison})
    except Exception as exc:
        logger.error(f"Compare error: {exc}")
        return jsonify({"error": str(exc)}), 500


def run_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    logger.info(f"Dashboard starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
