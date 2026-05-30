"""
Main Orchestrator
Entry point for the Quant Trading Platform.

Modes:
  scan       – Continuous scanning with configurable alerts
  backtest   – Run backtest on a specific symbol
  ml_train   – Train ML models for a symbol
  dashboard  – Launch the web dashboard
"""

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────────────────
# LOGGING SETUP
# ──────────────────────────────────────────────────────────

LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "trading.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

# Signals log for all generated signals
SIGNALS_LOG = LOGS_DIR / "signals_log.txt"

# ──────────────────────────────────────────────────────────
# COLOUR HELPERS (optional – graceful degradation on Windows)
# ──────────────────────────────────────────────────────────

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    _GREEN  = Fore.GREEN
    _RED    = Fore.RED
    _YELLOW = Fore.YELLOW
    _CYAN   = Fore.CYAN
    _RESET  = Style.RESET_ALL
except ImportError:
    _GREEN = _RED = _YELLOW = _CYAN = _RESET = ""


def _colour(text: str, colour: str) -> str:
    return f"{colour}{text}{_RESET}"


# ──────────────────────────────────────────────────────────
# SESSION STATE
# ──────────────────────────────────────────────────────────

_session = {
    "total_signals": 0,
    "buy_count":     0,
    "sell_count":    0,
    "hold_count":    0,
    "confidences":   [],
    "start_time":    datetime.now(),
    "running":       True,
}


def _log_signal(sig: dict) -> None:
    """Append signal to signals_log.txt."""
    line = (
        f"{datetime.utcnow().isoformat()} | {sig.get('symbol')} | "
        f"{sig.get('signal')} | conf={sig.get('confidence', 0):.4f} | "
        f"price={sig.get('price', 0):.6g} | strategy={sig.get('strategy')}\n"
    )
    with open(SIGNALS_LOG, "a", encoding="utf-8") as f:
        f.write(line)


def _update_session(signals: list[dict]) -> None:
    for s in signals:
        _session["total_signals"] += 1
        sig = s.get("signal", "HOLD")
        if sig == "BUY":
            _session["buy_count"] += 1
        elif sig == "SELL":
            _session["sell_count"] += 1
        else:
            _session["hold_count"] += 1
        _session["confidences"].append(s.get("confidence", 0))
        _log_signal(s)


def _print_summary() -> None:
    confs = _session["confidences"]
    avg_c = sum(confs) / len(confs) if confs else 0
    elapsed = datetime.now() - _session["start_time"]

    print("\n" + "=" * 60)
    print(_colour("  SESSION SUMMARY", _CYAN))
    print("=" * 60)
    print(f"  Runtime         : {str(elapsed).split('.')[0]}")
    print(f"  Total Signals   : {_session['total_signals']}")
    print(f"  BUY Signals     : {_colour(str(_session['buy_count']),  _GREEN)}")
    print(f"  SELL Signals    : {_colour(str(_session['sell_count']), _RED)}")
    print(f"  HOLD Signals    : {_colour(str(_session['hold_count']), _YELLOW)}")
    print(f"  Avg Confidence  : {avg_c:.1%}")
    print(f"  Signals Log     : {SIGNALS_LOG}")
    print("=" * 60 + "\n")


# ──────────────────────────────────────────────────────────
# GRACEFUL SHUTDOWN
# ──────────────────────────────────────────────────────────

def _shutdown_handler(signum, frame):
    logger.info("Shutdown signal received.")
    _session["running"] = False


signal.signal(signal.SIGINT,  _shutdown_handler)
signal.signal(signal.SIGTERM, _shutdown_handler)


# ──────────────────────────────────────────────────────────
# MODES
# ──────────────────────────────────────────────────────────

def _is_quiet_hours(quiet_start: int = 21, quiet_end: int = 8) -> bool:
    """Return True if current local time is within quiet hours (default 9pm–8am)."""
    hour = datetime.now().hour
    if quiet_start > quiet_end:
        return hour >= quiet_start or hour < quiet_end
    return quiet_start <= hour < quiet_end


def mode_scan(args) -> None:
    """Continuous scan loop."""
    from trading_engine_v2 import TradingEngine
    from alerts.notifier import dispatch_alerts
    from llm.analyzer import generate_market_summary

    engine   = TradingEngine(capital=args.capital, timeframe=args.timeframe)
    channels = args.alerts
    max_alerts = args.max_alerts

    logger.info(f"Starting scan | capital=${args.capital:,.0f} | interval={args.interval}s | "
                f"alerts={channels} | max_alerts={max_alerts} | quiet=9pm–8am")

    while _session["running"]:
        logger.info("─" * 50)
        logger.info("Scanning all assets…")

        signals = engine.scan_all()
        _update_session(signals)

        if signals:
            # Push signals to dashboard
            try:
                import requests as _requests
                for s in signals:
                    _requests.post("http://127.0.0.1:5000/api/add_signal", json=s, timeout=2)
            except Exception:
                pass  # Dashboard may not be running — that's fine

            # Sort by confidence descending — best signals first
            signals_sorted = sorted(signals, key=lambda s: s.get("confidence", 0), reverse=True)

            # Quiet hours: console only, no Telegram/email/SMS
            if _is_quiet_hours():
                logger.info("Quiet hours (9pm–8am) — console only, no external alerts.")
                alert_channels = ["console"] if "console" in channels else []
            else:
                alert_channels = channels

            # Cap at max_alerts for external channels (console always shows all)
            console_signals  = signals_sorted
            external_signals = signals_sorted[:max_alerts]

            if "console" in alert_channels:
                dispatch_alerts(console_signals, ["console"])
            external_ch = [c for c in alert_channels if c != "console"]
            if external_ch:
                dispatch_alerts(external_signals, external_ch,
                                pos_sizes={s["symbol"]: s.get("position") for s in external_signals})
                logger.info(f"Sent {len(external_signals)} alert(s) via {external_ch} "
                            f"(top {max_alerts} by confidence)")

            # AI market summary (Gemini)
            summary = generate_market_summary([{
                "symbol": s["symbol"], "signal": s["signal"],
                "strategy": s["strategy"], "confidence": s["confidence"],
            } for s in signals_sorted])
            if summary:
                print("\n" + "=" * 60)
                print(_colour("  AI MARKET SUMMARY  (Gemini)", _CYAN))
                print("=" * 60)
                for line in summary.splitlines():
                    print(f"  {line}")
                print("=" * 60 + "\n")
        else:
            logger.info("No actionable signals this cycle.")

        if not _session["running"]:
            break

        logger.info(f"Next scan in {args.interval}s…")
        for _ in range(args.interval):
            if not _session["running"]:
                break
            time.sleep(1)

    _print_summary()


def mode_backtest(args) -> None:
    """Run backtest on a single symbol."""
    from data_fetcher import fetch_asset
    from strategies.advanced_strategies import combined_strategy, momentum_strategy, mean_reversion_strategy
    from backtest.engine import BacktestEngine

    STRATEGY_MAP = {
        "combined":       combined_strategy,
        "momentum":       momentum_strategy,
        "mean_reversion": mean_reversion_strategy,
    }

    strat_fn = STRATEGY_MAP.get(args.strategy, combined_strategy)
    logger.info(f"Backtesting {args.symbol} | strategy={args.strategy} | capital=${args.capital:,.0f}")

    df = fetch_asset(args.symbol, args.asset, timeframe=args.timeframe, period="365d")
    if df is None or df.empty:
        logger.error(f"Failed to fetch data for {args.symbol}")
        return

    engine = BacktestEngine(strat_fn, initial_capital=args.capital)
    result = engine.run(df, symbol=args.symbol)

    print("\n" + "=" * 60)
    print(_colour(f"  BACKTEST: {args.symbol} | {args.strategy}", _CYAN))
    print("=" * 60)
    print(f"  Total Return    : {_colour(f'{result.total_return:.2%}', _GREEN if result.total_return >= 0 else _RED)}")
    print(f"  Win Rate        : {result.win_rate:.1%}")
    print(f"  Profit Factor   : {result.profit_factor:.2f}")
    print(f"  Sharpe Ratio    : {result.sharpe:.2f}")
    print(f"  Max Drawdown    : {_colour(f'{result.max_drawdown:.2%}', _RED)}")
    print(f"  Total Trades    : {result.total_trades}")
    print(f"  Avg Duration    : {result.avg_trade_duration:.1f} bars")
    print(f"  Win/Loss Ratio  : {result.win_loss_ratio:.2f}")
    print("=" * 60)

    # Walk-forward
    if args.walkforward:
        logger.info("Running walk-forward analysis…")
        wf = engine.walk_forward(df, symbol=args.symbol)
        print("\n  Walk-Forward Averages:")
        for k, v in wf.items():
            print(f"    {k:<22}: {v}")

    from llm.analyzer import analyze_strategy_performance
    suggestions = analyze_strategy_performance({
        "total_return": result.total_return,
        "win_rate": result.win_rate,
        "sharpe": result.sharpe,
        "max_drawdown": result.max_drawdown,
        "profit_factor": result.profit_factor,
    })
    if suggestions:
        print(f"\n  LLM Suggestions:\n{suggestions}")


def mode_ml_train(args) -> None:
    """Train ML models for a symbol."""
    from data_fetcher import fetch_asset
    from strategies.ml_strategies import train_models

    logger.info(f"Training ML models for {args.symbol} ({args.asset})")
    df = fetch_asset(args.symbol, args.asset, timeframe=args.timeframe, period="365d")
    if df is None or df.empty:
        logger.error(f"Failed to fetch data for {args.symbol}")
        return

    metrics = train_models(df, symbol=args.symbol)
    if metrics:
        print("\n" + "=" * 60)
        print(_colour(f"  ML TRAINING: {args.symbol}", _CYAN))
        print("=" * 60)
        print(f"  RF Accuracy  : {metrics.get('rf_accuracy', 0):.3f}")
        print(f"  GB Accuracy  : {metrics.get('gb_accuracy', 0):.3f}")
        print(f"  Train Samples: {metrics.get('train_size', 0)}")
        print(f"  Test Samples : {metrics.get('test_size', 0)}")
        print("\n  Top Features:")
        for feat, imp in list(metrics.get("feature_importance", {}).items())[:5]:
            print(f"    {feat:<20}: {imp:.4f}")
        print(f"\n  Classification Report:\n{metrics.get('rf_report', '')}")
        print("=" * 60)
    else:
        logger.error("Training failed.")


def mode_dashboard(args) -> None:
    """Launch web dashboard."""
    from dashboard.app import run_dashboard
    logger.info(f"Launching dashboard on http://0.0.0.0:{args.port}")
    run_dashboard(host="0.0.0.0", port=args.port, debug=args.debug)


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="quant-trading",
        description="Quant Trading Platform – signal generation for manual execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main_complete.py --mode scan --capital 10000 --alerts console
  python main_complete.py --mode scan --alerts console telegram
  python main_complete.py --mode backtest --symbol AAPL --asset stock
  python main_complete.py --mode backtest --symbol BTC/USDT --asset crypto --walkforward
  python main_complete.py --mode ml_train --symbol BTC/USDT --asset crypto
  python main_complete.py --mode dashboard --port 5000
        """,
    )

    p.add_argument("--mode", choices=["scan", "backtest", "ml_train", "dashboard"],
                   default="scan", help="Operating mode")
    p.add_argument("--capital",    type=float, default=float(os.getenv("DEFAULT_CAPITAL", 10000)),
                   help="Trading capital in USD")
    p.add_argument("--symbol",     default="AAPL",   help="Asset symbol for backtest/ml_train")
    p.add_argument("--asset",      default="stock",  choices=["stock", "crypto", "forex"],
                   help="Asset type")
    p.add_argument("--timeframe",  default="1h",     help="Bar timeframe (1h, 4h, 1d, …)")
    p.add_argument("--strategy",   default="combined",
                   choices=["combined", "momentum", "mean_reversion"],
                   help="Strategy for backtest mode")
    p.add_argument("--alerts",     nargs="+",
                   default=["console"],
                   choices=["console", "telegram", "email", "sms", "webhook"],
                   help="Alert channels")
    p.add_argument("--interval",   type=int, default=int(os.getenv("SCAN_INTERVAL", 300)),
                   help="Scan interval in seconds (scan mode)")
    p.add_argument("--max-alerts", type=int, default=3, dest="max_alerts",
                   help="Max Telegram/email alerts per scan cycle (default: 3)")
    p.add_argument("--port",       type=int, default=5000,  help="Dashboard port")
    p.add_argument("--walkforward",action="store_true",     help="Run walk-forward analysis (backtest mode)")
    p.add_argument("--debug",      action="store_true",     help="Enable Flask debug mode")

    return p


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    logger.info(f"Quant Trading Platform | mode={args.mode} | capital=${args.capital:,.0f}")

    MODE_MAP = {
        "scan":       mode_scan,
        "backtest":   mode_backtest,
        "ml_train":   mode_ml_train,
        "dashboard":  mode_dashboard,
    }

    fn = MODE_MAP.get(args.mode)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
