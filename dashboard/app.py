"""
Flask Web Dashboard — Vercel-compatible.
Auth: Clerk JWT  |  Payments: Stripe  |  Storage: Upstash KV
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
from auth import get_user_access, require_access
from kv_store import KV_AVAILABLE, kv_get, kv_set

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "quant-trading-secret-2024")

# ── In-memory fallback for local dev (no KV) ──────────────
_signals_store: list[dict] = []
_lock = threading.Lock()


def add_signal(signal: dict) -> None:
    signal.setdefault("timestamp", datetime.now(_TZ).isoformat())
    with _lock:
        _signals_store.append(signal)
        if len(_signals_store) > 500:
            _signals_store.pop(0)


def _read_signals(limit: int = 100) -> list[dict]:
    if KV_AVAILABLE:
        return (kv_get("signals:latest") or [])[:limit]
    with _lock:
        return list(reversed(_signals_store[-limit:]))


# ──────────────────────────────────────────────────────────
# PUBLIC ROUTES
# ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template(
        "dashboard.html",
        clerk_pk=os.getenv("CLERK_PUBLISHABLE_KEY", ""),
    )


@app.route("/api/add_signal", methods=["POST"])
def api_add_signal():
    """Receive a signal from the local scanner process."""
    try:
        signal = request.get_json(force=True) or {}
        if signal:
            add_signal(signal)
        return jsonify({"ok": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ──────────────────────────────────────────────────────────
# AUTH ROUTES
# ──────────────────────────────────────────────────────────

@app.route("/api/auth/status")
def api_auth_status():
    """Return trial/subscription status for the authenticated user."""
    from auth import _DEV_MODE, verify_token

    if _DEV_MODE:
        return jsonify({
            "has_access": True, "subscribed": False,
            "trial_active": True, "trial_days_left": 7.0,
        })

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    user_id = verify_token(auth[7:])
    if not user_id:
        return jsonify({"error": "Invalid token"}), 401

    return jsonify(get_user_access(user_id))


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    """Create a Stripe Checkout session and return the redirect URL."""
    from auth import _DEV_MODE, verify_token
    from payments import create_checkout_session

    if _DEV_MODE:
        return jsonify({"url": "/"})

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    user_id = verify_token(auth[7:])
    if not user_id:
        return jsonify({"error": "Invalid token"}), 401

    # Try to get email from Clerk API
    email = _get_clerk_email(user_id)
    url = create_checkout_session(user_id, email)
    return jsonify({"url": url})


@app.route("/api/portal", methods=["POST"])
def api_portal():
    """Create a Stripe Customer Portal session."""
    from auth import _DEV_MODE, verify_token
    from payments import create_portal_session

    if _DEV_MODE:
        return jsonify({"url": "/"})

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "Unauthorized"}), 401

    user_id = verify_token(auth[7:])
    if not user_id:
        return jsonify({"error": "Invalid token"}), 401

    access = get_user_access(user_id)
    customer_id = access.get("stripe_customer_id")
    if not customer_id:
        return jsonify({"error": "No active subscription"}), 400

    return jsonify({"url": create_portal_session(customer_id)})


@app.route("/api/webhook", methods=["POST"])
def api_webhook():
    """Stripe webhook endpoint — updates subscription status in KV."""
    from payments import handle_webhook
    payload = request.get_data()
    sig     = request.headers.get("Stripe-Signature", "")
    if handle_webhook(payload, sig):
        return jsonify({"ok": True})
    return jsonify({"error": "Webhook verification failed"}), 400


# ──────────────────────────────────────────────────────────
# PROTECTED DATA ROUTES
# ──────────────────────────────────────────────────────────

@app.route("/api/signals")
@require_access
def api_signals():
    limit = int(request.args.get("limit", 100))
    return jsonify(_read_signals(limit))


@app.route("/api/metrics")
@require_access
def api_metrics():
    signals  = _read_signals(500)
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
@require_access
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
@require_access
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
            return jsonify({"error": "Backtesting requires the full local installation."}), 503

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


# ──────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────

def _get_clerk_email(user_id: str) -> str:
    """Fetch the user's primary email from the Clerk API."""
    try:
        import requests as _req
        r = _req.get(
            f"https://api.clerk.dev/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {os.environ.get('CLERK_SECRET_KEY', '')}"},
            timeout=5,
        )
        if r.ok:
            emails = r.json().get("email_addresses", [])
            if emails:
                return emails[0].get("email_address", "")
    except Exception:
        pass
    return ""


def run_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    logger.info(f"Dashboard starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)
