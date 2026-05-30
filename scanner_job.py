"""
One-shot scanner for GitHub Actions.
Runs a full scan cycle across all assets and writes results to Vercel KV.
Exits when done — GitHub Actions cron handles the repeat schedule.
"""

import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("scanner_job")

from trading_engine_v2 import TradingEngine
from kv_store import kv_get, kv_set, KV_AVAILABLE

CAPITAL     = float(os.environ.get("CAPITAL") or "10000")
MAX_SIGNALS = 200  # rolling window kept in KV


def run() -> None:
    if not KV_AVAILABLE:
        logger.error("UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN not set — add them as GitHub repository secrets.")
        sys.exit(1)

    logger.info(f"Starting scan — capital=${CAPITAL:,.0f}")
    engine = TradingEngine(capital=CAPITAL)

    new_signals = engine.scan_all()

    now = datetime.now(timezone.utc).isoformat()
    for s in new_signals:
        s.setdefault("timestamp", now)

    # Merge with existing rolling window
    existing: list = kv_get("signals:latest") or []
    combined = new_signals + existing
    combined  = combined[:MAX_SIGNALS]

    kv_set("signals:latest",  combined, ex=7200)
    kv_set("scanner:last_run", now,      ex=7200)

    logger.info(
        f"Scan done — {len(new_signals)} new signal(s), "
        f"{len(combined)} total in KV."
    )


if __name__ == "__main__":
    run()
