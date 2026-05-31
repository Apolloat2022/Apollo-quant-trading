"""
On-demand backtest runner for GitHub Actions.
Reads job params from Upstash KV, runs backtest or strategy comparison,
writes result back to KV. Triggered via workflow_dispatch with BACKTEST_JOB_ID.
"""

import logging
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtest_job")

from kv_store import kv_get, kv_set

JOB_ID = os.environ.get("BACKTEST_JOB_ID", "")


def run():
    if not JOB_ID:
        logger.error("BACKTEST_JOB_ID not set.")
        sys.exit(1)

    job = kv_get(f"backtest:{JOB_ID}")
    if not job:
        logger.error(f"Job {JOB_ID} not found in KV.")
        sys.exit(1)

    logger.info(f"Starting job {JOB_ID}: {job['params']}")
    job["status"] = "running"
    kv_set(f"backtest:{JOB_ID}", job, ex=3600)

    params     = job["params"]
    symbol     = params["symbol"]
    asset_type = params["asset_type"]
    capital    = float(params["capital"])
    strategy   = params.get("strategy", "combined")
    mode       = params.get("mode", "backtest")   # "backtest" or "compare"

    try:
        from data_fetcher import fetch_asset
        from strategies.advanced_strategies import (
            combined_strategy, momentum_strategy,
            mean_reversion_strategy, volume_price_strategy,
        )
        from backtest.engine import BacktestEngine

        df = fetch_asset(symbol, asset_type, timeframe="1h", period="180d")
        if df is None or df.empty:
            raise ValueError(f"No data returned for {symbol}")

        if mode == "compare":
            strategies = {
                "combined":       combined_strategy,
                "momentum":       momentum_strategy,
                "mean_reversion": mean_reversion_strategy,
                "volume_price":   volume_price_strategy,
            }
            comparison = {}
            for name, fn in strategies.items():
                r = BacktestEngine(fn, initial_capital=capital).run(df, symbol=symbol)
                comparison[name] = {
                    "total_return": r.total_return,
                    "win_rate":     r.win_rate,
                    "sharpe":       r.sharpe,
                    "max_drawdown": r.max_drawdown,
                    "total_trades": r.total_trades,
                }
                logger.info(f"  {name}: return={r.total_return:.2%} sharpe={r.sharpe}")
            job["result"] = {"symbol": symbol, "comparison": comparison}

        else:
            strat_fn = combined_strategy if strategy == "combined" else momentum_strategy
            r = BacktestEngine(strat_fn, initial_capital=capital).run(df, symbol=symbol)
            job["result"] = {
                "symbol":             symbol,
                "total_return":       r.total_return,
                "win_rate":           r.win_rate,
                "profit_factor":      r.profit_factor,
                "sharpe":             r.sharpe,
                "max_drawdown":       r.max_drawdown,
                "total_trades":       r.total_trades,
                "avg_trade_duration": r.avg_trade_duration,
            }
            logger.info(f"Result: {job['result']}")

        job["status"] = "complete"

    except Exception as exc:
        logger.error(f"Backtest failed: {exc}")
        job["status"] = "error"
        job["error"]  = str(exc)

    job["completed_at"] = time.time()
    kv_set(f"backtest:{JOB_ID}", job, ex=3600)
    logger.info(f"Job {JOB_ID} finished — status: {job['status']}")


if __name__ == "__main__":
    run()
