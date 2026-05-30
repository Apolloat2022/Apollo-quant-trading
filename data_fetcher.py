"""
Data Fetcher Module
Fetches OHLCV data for stocks, crypto, and forex using free APIs.
"""

import logging
import time
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# ASSET LISTS
# ──────────────────────────────────────────────────────────

STOCK_SYMBOLS  = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]
CRYPTO_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"]
# yfinance equivalents used as fallback: BTC-USD, ETH-USD, SOL-USD, XRP-USD
FOREX_SYMBOLS  = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"]

TIMEFRAME_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1wk",
}

CRYPTO_TIMEFRAME_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w",
}


# ──────────────────────────────────────────────────────────
# STOCK
# ──────────────────────────────────────────────────────────

def fetch_stock_data(
    symbol: str,
    timeframe: str = "1h",
    period: str = "60d",
    retries: int = 3,
) -> Optional[pd.DataFrame]:
    """
    Fetch stock OHLCV data via yfinance.

    Args:
        symbol:    Ticker e.g. 'AAPL'
        timeframe: Bar interval e.g. '1h'
        period:    Lookback period e.g. '60d'
        retries:   Retry attempts on failure

    Returns:
        DataFrame [open, high, low, close, volume] or None.
    """
    interval = TIMEFRAME_MAP.get(timeframe, "1h")
    for attempt in range(retries):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return None
            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            })
            df = df[["open", "high", "low", "close", "volume"]].dropna()
            df.index = pd.to_datetime(df.index, utc=True)
            logger.info(f"Fetched {len(df)} bars for {symbol} ({timeframe})")
            return df
        except Exception as exc:
            logger.warning(f"Attempt {attempt+1} failed for {symbol}: {exc}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    logger.error(f"All retries exhausted for {symbol}")
    return None


# ──────────────────────────────────────────────────────────
# CRYPTO
# ──────────────────────────────────────────────────────────

def _crypto_symbol_to_yf(symbol: str) -> str:
    """Convert 'BTC/USDT' -> 'BTC-USD' for yfinance."""
    base = symbol.upper().split("/")[0]
    return f"{base}-USD"


def _fetch_crypto_ccxt(symbol: str, exchange_id: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
    """Try one CCXT exchange. Returns DataFrame or None."""
    try:
        import ccxt
        exchange_cls = getattr(ccxt, exchange_id, None)
        if exchange_cls is None:
            return None
        exchange = exchange_cls({"enableRateLimit": True})
        tf    = CRYPTO_TIMEFRAME_MAP.get(timeframe, "1h")
        ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=limit)
        if not ohlcv:
            return None
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp").dropna()
        logger.info(f"Fetched {len(df)} bars for {symbol} via {exchange_id}")
        return df
    except Exception as exc:
        logger.debug(f"{exchange_id} failed for {symbol}: {exc}")
        return None


def fetch_crypto_data(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 500,
    retries: int = 2,
) -> Optional[pd.DataFrame]:
    """
    Fetch crypto OHLCV data. Tries Binance → Kraken → KuCoin → yfinance.

    Args:
        symbol:    Trading pair e.g. 'BTC/USDT'
        timeframe: Bar interval
        limit:     Number of bars (CCXT exchanges)
        retries:   Retry attempts per exchange

    Returns:
        DataFrame [open, high, low, close, volume] or None.
    """
    # Normalise symbol (accept 'eth', 'eth/usdt', 'ETH/USDT')
    sym_upper = symbol.upper()
    if "/" not in sym_upper:
        sym_upper = sym_upper + "/USDT"

    # 1. Try CCXT exchanges in order (1 attempt each, fail fast)
    for exchange_id in ("binance", "kraken", "kucoin", "bybit", "okx"):
        df = _fetch_crypto_ccxt(sym_upper, exchange_id, timeframe, limit)
        if df is not None and not df.empty:
            return df

    # 2. Fallback: yfinance (BTC-USD format) — works everywhere
    yf_sym = _crypto_symbol_to_yf(sym_upper)
    logger.info(f"All CCXT exchanges failed for {sym_upper}. Falling back to yfinance ({yf_sym})")
    period_map = {"1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d",
                  "1h": "60d", "4h": "60d", "1d": "2y", "1w": "5y"}
    period = period_map.get(timeframe, "60d")
    return fetch_stock_data(yf_sym, timeframe=timeframe, period=period, retries=3)


# ──────────────────────────────────────────────────────────
# FOREX
# ──────────────────────────────────────────────────────────

def fetch_forex_data(
    symbol: str,
    timeframe: str = "1h",
    period: str = "60d",
    retries: int = 3,
) -> Optional[pd.DataFrame]:
    """
    Fetch forex OHLCV data via yfinance.

    Args:
        symbol:    Forex pair e.g. 'EURUSD=X'
        timeframe: Bar interval
        period:    Lookback period
        retries:   Retry attempts

    Returns:
        DataFrame [open, high, low, close, volume] or None.
    """
    return fetch_stock_data(symbol, timeframe=timeframe, period=period, retries=retries)


# ──────────────────────────────────────────────────────────
# UNIFIED + BULK
# ──────────────────────────────────────────────────────────

def fetch_asset(
    symbol: str,
    asset_type: str,
    timeframe: str = "1h",
    period: str = "60d",
) -> Optional[pd.DataFrame]:
    """
    Unified fetch function.

    Args:
        symbol:     Asset symbol
        asset_type: 'stock', 'crypto', or 'forex'
        timeframe:  Bar interval
        period:     Lookback period (stocks/forex)

    Returns:
        DataFrame or None.
    """
    if asset_type == "crypto":
        return fetch_crypto_data(symbol, timeframe=timeframe)
    elif asset_type == "forex":
        return fetch_forex_data(symbol, timeframe=timeframe, period=period)
    else:
        return fetch_stock_data(symbol, timeframe=timeframe, period=period)


def fetch_all_assets(timeframe: str = "1h") -> dict:
    """
    Fetch data for all configured assets.

    Returns:
        Dict mapping symbol -> DataFrame (or None on failure).
    """
    results: dict = {}

    for sym in STOCK_SYMBOLS:
        results[sym] = fetch_stock_data(sym, timeframe=timeframe)
        time.sleep(0.3)

    for sym in CRYPTO_SYMBOLS:
        results[sym] = fetch_crypto_data(sym, timeframe=timeframe)
        time.sleep(0.3)

    for sym in FOREX_SYMBOLS:
        results[sym] = fetch_forex_data(sym, timeframe=timeframe)
        time.sleep(0.3)

    return results
