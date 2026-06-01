"""
Trading Engine v2
Orchestrates data fetching, strategy execution, risk management, and alerting
for a single scan cycle.
"""

import logging
import time
from dataclasses import asdict
from typing import Optional

from data_fetcher import fetch_asset, STOCK_SYMBOLS, CRYPTO_SYMBOLS, FOREX_SYMBOLS
from strategies.advanced_strategies import combined_strategy, Signal
from risk.manager import RiskManager

logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Core trading engine that ties together data, strategies, and risk.
    """

    def __init__(
        self,
        capital: float = 10_000.0,
        timeframe: str = "1h",
        min_confidence: float = 0.35,
    ) -> None:
        self.capital         = capital
        self.timeframe       = timeframe
        self.min_confidence  = min_confidence
        self.risk_manager    = RiskManager(capital=capital)
        self._last_scan_time = 0.0

    # ──────────────────────────────────────────────────────
    # SCAN
    # ──────────────────────────────────────────────────────

    def scan_asset(
        self,
        symbol: str,
        asset_type: str,
        strategy_fn=None,
        include_hold: bool = False,
    ) -> Optional[dict]:
        """
        Fetch data for one asset and generate a signal.

        Args:
            symbol:      Asset symbol
            asset_type:  'stock', 'crypto', or 'forex'
            strategy_fn: Strategy callable (defaults to combined_strategy)
            include_hold: When True, return the signal even for HOLD / below
                          min_confidence (used to build a full dashboard snapshot).

        Returns:
            Signal dict with risk details, or None.
        """
        if strategy_fn is None:
            strategy_fn = combined_strategy

        df = fetch_asset(symbol, asset_type, timeframe=self.timeframe)
        if df is None or df.empty:
            logger.warning(f"No data for {symbol}")
            return None

        signal_obj: Optional[Signal] = strategy_fn(df, symbol)
        if signal_obj is None:
            return None

        if not include_hold and (signal_obj.signal == "HOLD" or signal_obj.confidence < self.min_confidence):
            return None

        # Market regime check
        regime = self.risk_manager.market_regime(df)
        if not include_hold and regime["trend"] == "bearish" and signal_obj.signal == "BUY" and regime["volatility_regime"] == "high":
            logger.info(f"Skipping {symbol} BUY – bearish high-vol regime.")
            return None

        # Position sizing
        volatility = float(df["close"].pct_change().rolling(20).std().iloc[-1])
        pos = self.risk_manager.calculate_position_size(
            symbol=symbol,
            entry_price=signal_obj.price,
            signal=signal_obj.signal,
            volatility=volatility,
        )

        result = {
            "symbol":     symbol,
            "signal":     signal_obj.signal,
            "confidence": signal_obj.confidence,
            "strategy":   signal_obj.strategy,
            "price":      signal_obj.price,
            "asset_type": asset_type,
            "details":    signal_obj.details,
            "regime":     regime,
        }

        if pos:
            result["position"] = {
                "quantity":       pos.quantity,
                "risk_amount":    pos.risk_amount,
                "stop_loss":      pos.stop_loss,
                "take_profit":    pos.take_profit,
                "position_value": pos.position_value,
            }

        return result

    def scan_all(self, strategy_fn=None, include_hold: bool = False) -> list[dict]:
        """
        Scan all configured assets and return signals.

        Args:
            strategy_fn:  Strategy callable (defaults to combined_strategy)
            include_hold: When True, include every asset's current signal
                          (BUY/SELL/HOLD) — used to keep the dashboard populated.

        Returns:
            List of signal dicts.
        """
        signals = []

        asset_lists = [
            (STOCK_SYMBOLS, "stock"),
            (CRYPTO_SYMBOLS, "crypto"),
            (FOREX_SYMBOLS, "forex"),
        ]

        for symbols, asset_type in asset_lists:
            for sym in symbols:
                try:
                    result = self.scan_asset(sym, asset_type, strategy_fn=strategy_fn, include_hold=include_hold)
                    if result:
                        signals.append(result)
                        logger.info(
                            f"[{result['signal']}] {sym} | conf={result['confidence']:.2f} | "
                            f"price={result['price']:.6g}"
                        )
                except Exception as exc:
                    logger.error(f"Error scanning {sym}: {exc}")
                time.sleep(0.2)  # gentle rate limiting

        return signals
