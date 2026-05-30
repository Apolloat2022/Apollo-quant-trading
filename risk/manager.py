"""
Risk Management System
Position sizing, stop-loss/take-profit, daily limits, correlation, and regime filters.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# DATA CLASSES
# ──────────────────────────────────────────────────────────

@dataclass
class PositionSize:
    """Output from position sizing calculation."""
    symbol:        str
    quantity:      float
    risk_amount:   float      # USD at risk
    stop_loss:     float      # price level
    take_profit:   float      # price level
    position_value: float     # total position value


@dataclass
class RiskState:
    """Tracks daily PnL and open positions."""
    daily_loss:     float = 0.0
    daily_trades:   int   = 0
    reset_date:     date  = field(default_factory=date.today)
    open_positions: dict  = field(default_factory=dict)   # symbol -> quantity


# ──────────────────────────────────────────────────────────
# CORRELATION MATRIX  (rough defaults – update from live data)
# ──────────────────────────────────────────────────────────

DEFAULT_CORRELATION_GROUPS = [
    {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"},   # US Tech
    {"BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"},    # Crypto
    {"EURUSD=X", "GBPUSD=X", "AUDUSD=X"},                 # FX majors
    {"USDJPY=X"},                                          # Safe haven
]


class RiskManager:
    """
    Manages position sizing, daily loss limits, and market regime filters.
    """

    def __init__(
        self,
        capital: float = 10_000.0,
        max_position_pct: float = 0.02,
        stop_loss_pct: float = 0.01,
        take_profit_pct: float = 0.02,
        max_daily_loss_pct: float = 0.05,
        max_correlated_exposure_pct: float = 0.15,
    ) -> None:
        self.capital                    = capital
        self.max_position_pct           = max_position_pct
        self.stop_loss_pct              = stop_loss_pct
        self.take_profit_pct            = take_profit_pct
        self.max_daily_loss_pct         = max_daily_loss_pct
        self.max_correlated_exposure    = capital * max_correlated_exposure_pct
        self.state                      = RiskState()

    # ──────────────────────────────────────────────────────
    # POSITION SIZING
    # ──────────────────────────────────────────────────────

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        signal: str,
        volatility: Optional[float] = None,
    ) -> Optional[PositionSize]:
        """
        Calculate position size respecting daily limits and correlation rules.

        Args:
            symbol:       Asset symbol
            entry_price:  Current price
            signal:       'BUY' or 'SELL'
            volatility:   Optional recent volatility (std dev of returns). Used to
                          scale position down in high-vol regimes.

        Returns:
            PositionSize or None if trading is disabled.
        """
        self._reset_daily_if_needed()

        if not self.can_trade():
            logger.warning("Daily loss limit reached – trading disabled for today.")
            return None

        # Volatility adjustment (halve size if vol > 2x normal)
        vol_multiplier = 1.0
        if volatility is not None and volatility > 0:
            normal_vol = 0.01  # 1% daily vol as baseline
            if volatility > normal_vol * 2:
                vol_multiplier = 0.5
            elif volatility > normal_vol * 1.5:
                vol_multiplier = 0.75

        risk_pct    = self.max_position_pct * vol_multiplier
        risk_amount = self.capital * risk_pct

        if signal == "BUY":
            stop_loss   = entry_price * (1 - self.stop_loss_pct)
            take_profit = entry_price * (1 + self.take_profit_pct)
        else:
            stop_loss   = entry_price * (1 + self.stop_loss_pct)
            take_profit = entry_price * (1 - self.take_profit_pct)

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance == 0:
            return None

        quantity       = risk_amount / stop_distance
        position_value = quantity * entry_price

        # Correlated exposure check
        group_exposure = self._correlated_exposure(symbol)
        if group_exposure + position_value > self.max_correlated_exposure:
            scale = max(0.1, (self.max_correlated_exposure - group_exposure) / position_value)
            quantity       *= scale
            position_value *= scale
            risk_amount     = quantity * stop_distance
            logger.info(f"Scaled {symbol} position to {scale:.2f}x due to correlation limit.")

        return PositionSize(
            symbol=symbol,
            quantity=round(quantity, 6),
            risk_amount=round(risk_amount, 2),
            stop_loss=round(stop_loss, 6),
            take_profit=round(take_profit, 6),
            position_value=round(position_value, 2),
        )

    # ──────────────────────────────────────────────────────
    # DAILY LIMITS
    # ──────────────────────────────────────────────────────

    def record_trade_result(self, pnl: float) -> None:
        """Update daily PnL tracker."""
        self._reset_daily_if_needed()
        if pnl < 0:
            self.state.daily_loss += abs(pnl)
        self.state.daily_trades += 1

    def can_trade(self) -> bool:
        """Return False if daily loss limit is breached."""
        self._reset_daily_if_needed()
        return self.state.daily_loss < self.capital * self.max_daily_loss_pct

    def _reset_daily_if_needed(self) -> None:
        today = date.today()
        if self.state.reset_date != today:
            self.state.daily_loss   = 0.0
            self.state.daily_trades = 0
            self.state.reset_date   = today

    # ──────────────────────────────────────────────────────
    # CORRELATION EXPOSURE
    # ──────────────────────────────────────────────────────

    def _correlated_exposure(self, symbol: str) -> float:
        """Return total open exposure for the correlation group containing symbol."""
        for group in DEFAULT_CORRELATION_GROUPS:
            if symbol in group:
                return sum(
                    self.state.open_positions.get(s, 0) for s in group
                )
        return 0.0

    def update_position(self, symbol: str, value: float) -> None:
        """Track open position value for correlation checks."""
        if value == 0:
            self.state.open_positions.pop(symbol, None)
        else:
            self.state.open_positions[symbol] = value

    # ──────────────────────────────────────────────────────
    # MARKET REGIME FILTER
    # ──────────────────────────────────────────────────────

    def market_regime(self, df: pd.DataFrame) -> dict:
        """
        Detect trend and volatility regime.

        Args:
            df: OHLCV DataFrame (at least 200 bars)

        Returns:
            Dict with trend, volatility_regime, risk_multiplier.
        """
        if len(df) < 55:
            return {"trend": "neutral", "volatility_regime": "normal", "risk_multiplier": 0.7}

        close = df["close"]
        ma50  = close.rolling(50).mean().iloc[-1]
        ma200 = close.rolling(min(200, len(df))).mean().iloc[-1]
        price = close.iloc[-1]

        # Trend
        if price > ma50 > ma200:
            trend = "bullish"
        elif price < ma50 < ma200:
            trend = "bearish"
        else:
            trend = "neutral"

        # Volatility
        recent_vol  = close.pct_change().rolling(20).std().iloc[-1]
        baseline_vol = close.pct_change().rolling(60).std().iloc[-1] if len(df) >= 60 else recent_vol

        if recent_vol > baseline_vol * 1.5:
            vol_regime = "high"
        elif recent_vol < baseline_vol * 0.7:
            vol_regime = "low"
        else:
            vol_regime = "normal"

        # Risk multiplier
        multiplier_map = {
            ("bullish",  "high"):   0.5,
            ("bullish",  "normal"): 1.2,
            ("bullish",  "low"):    1.0,
            ("bearish",  "high"):   0.3,
            ("bearish",  "normal"): 0.6,
            ("bearish",  "low"):    0.7,
            ("neutral",  "high"):   0.4,
            ("neutral",  "normal"): 0.8,
            ("neutral",  "low"):    0.9,
        }
        risk_mult = multiplier_map.get((trend, vol_regime), 0.7)

        return {
            "trend":             trend,
            "volatility_regime": vol_regime,
            "risk_multiplier":   risk_mult,
            "recent_vol":        round(float(recent_vol), 6),
            "ma50":              round(float(ma50), 6),
            "ma200":             round(float(ma200), 6),
        }
