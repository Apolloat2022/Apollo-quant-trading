"""
Backtesting Engine
Simulates strategy performance on historical data with realistic assumptions.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

COMMISSION = 0.001   # 0.1%
SLIPPAGE   = 0.0005  # 0.05%
POSITION_PCT = 0.02  # 2% of capital per trade


@dataclass
class Trade:
    """Single trade record."""
    entry_time:  pd.Timestamp
    exit_time:   Optional[pd.Timestamp] = None
    entry_price: float = 0.0
    exit_price:  float = 0.0
    quantity:    float = 0.0
    direction:   str   = "LONG"   # LONG or SHORT
    pnl:         float = 0.0
    duration_bars: int = 0


@dataclass
class BacktestResult:
    """Aggregated backtest metrics."""
    total_return:      float = 0.0
    win_rate:          float = 0.0
    profit_factor:     float = 0.0
    sharpe:            float = 0.0
    max_drawdown:      float = 0.0
    avg_trade_duration: float = 0.0
    win_loss_ratio:    float = 0.0
    total_trades:      int   = 0
    equity_curve:      pd.Series = field(default_factory=pd.Series)
    trades:            list  = field(default_factory=list)


# ──────────────────────────────────────────────────────────
# METRICS HELPERS
# ──────────────────────────────────────────────────────────

def _sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
    if returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(periods_per_year))


def _max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / (roll_max + 1e-9)
    return float(drawdown.min())


def _profit_factor(trades: list) -> float:
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss   = abs(sum(t.pnl for t in trades if t.pnl < 0))
    return gross_profit / (gross_loss + 1e-9)


# ──────────────────────────────────────────────────────────
# BACKTEST ENGINE
# ──────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Single-pass vectorised backtester.

    Accepts a signal-generating function and runs it bar-by-bar on historical data.
    """

    def __init__(
        self,
        strategy_fn: Callable[[pd.DataFrame, str], Optional[object]],
        initial_capital: float = 10_000.0,
        commission: float = COMMISSION,
        slippage: float = SLIPPAGE,
        position_pct: float = POSITION_PCT,
        stop_loss_pct: float = 0.01,
        take_profit_pct: float = 0.02,
    ) -> None:
        self.strategy_fn     = strategy_fn
        self.initial_capital = initial_capital
        self.commission      = commission
        self.slippage        = slippage
        self.position_pct    = position_pct
        self.stop_loss_pct   = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    def run(self, df: pd.DataFrame, symbol: str = "SYM", min_bars: int = 60) -> BacktestResult:
        """
        Run backtest on a DataFrame.

        Args:
            df: OHLCV DataFrame
            symbol: Asset symbol
            min_bars: Minimum warm-up bars before trading

        Returns:
            BacktestResult with equity curve and metrics.
        """
        capital    = self.initial_capital
        position   = 0.0   # current quantity (positive = long)
        entry_price = 0.0
        entry_time  = None
        entry_bar   = 0

        equity_values = [capital]
        equity_times  = [df.index[0]]
        trades: list[Trade] = []

        for i in range(min_bars, len(df)):
            window = df.iloc[:i]
            close  = float(df["close"].iloc[i])

            sig = self.strategy_fn(window, symbol)
            signal = sig.signal if sig is not None else "HOLD"

            # ── Check exits ────────────────────────────────
            if position != 0 and entry_price > 0:
                pnl_pct = (close - entry_price) / entry_price
                hit_sl  = pnl_pct < -self.stop_loss_pct
                hit_tp  = pnl_pct >  self.take_profit_pct
                exit_signal = (position > 0 and signal == "SELL") or \
                              (position < 0 and signal == "BUY")

                if hit_sl or hit_tp or exit_signal:
                    exit_px = close * (1 - self.slippage if position > 0 else 1 + self.slippage)
                    pnl     = position * (exit_px - entry_price) - \
                              abs(position) * exit_px * self.commission
                    capital += pnl
                    trades.append(Trade(
                        entry_time=entry_time,
                        exit_time=df.index[i],
                        entry_price=entry_price,
                        exit_price=exit_px,
                        quantity=abs(position),
                        direction="LONG" if position > 0 else "SHORT",
                        pnl=pnl,
                        duration_bars=i - entry_bar,
                    ))
                    position    = 0.0
                    entry_price = 0.0

            # ── Check entries ──────────────────────────────
            if position == 0:
                if signal == "BUY":
                    entry_px    = close * (1 + self.slippage)
                    qty         = (capital * self.position_pct) / entry_px
                    cost        = qty * entry_px * (1 + self.commission)
                    if cost <= capital:
                        position    =  qty
                        entry_price = entry_px
                        entry_time  = df.index[i]
                        entry_bar   = i
                        capital    -= cost

                elif signal == "SELL":
                    entry_px    = close * (1 - self.slippage)
                    qty         = (capital * self.position_pct) / entry_px
                    proceeds    = qty * entry_px * (1 - self.commission)
                    position    = -qty
                    entry_price = entry_px
                    entry_time  = df.index[i]
                    entry_bar   = i
                    capital    += proceeds

            # Mark-to-market
            mtm = capital + position * close
            equity_values.append(mtm)
            equity_times.append(df.index[i])

        # Close any open position at last bar
        if position != 0 and entry_price > 0:
            last_close = float(df["close"].iloc[-1])
            pnl = position * (last_close - entry_price) - \
                  abs(position) * last_close * self.commission
            capital += pnl

        equity = pd.Series(equity_values, index=equity_times)
        returns = equity.pct_change().dropna()

        wins   = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]

        total_return = (equity.iloc[-1] - self.initial_capital) / self.initial_capital
        win_rate     = len(wins) / len(trades) if trades else 0.0
        avg_dur      = np.mean([t.duration_bars for t in trades]) if trades else 0.0
        wl_ratio     = (np.mean([t.pnl for t in wins]) / abs(np.mean([t.pnl for t in losses]) + 1e-9)) if wins and losses else 0.0

        return BacktestResult(
            total_return=round(total_return, 4),
            win_rate=round(win_rate, 4),
            profit_factor=round(_profit_factor(trades), 4),
            sharpe=round(_sharpe(returns), 4),
            max_drawdown=round(_max_drawdown(equity), 4),
            avg_trade_duration=round(avg_dur, 2),
            win_loss_ratio=round(wl_ratio, 4),
            total_trades=len(trades),
            equity_curve=equity,
            trades=trades,
        )

    def walk_forward(
        self,
        df: pd.DataFrame,
        symbol: str = "SYM",
        train_size: int = 400,
        test_size: int = 100,
    ) -> dict:
        """
        Walk-forward analysis: rolling train/test windows.

        Args:
            df: OHLCV DataFrame
            symbol: Asset symbol
            train_size: Bars for training window
            test_size: Bars for test window

        Returns:
            Dict with per-window and averaged metrics.
        """
        results = []
        n = len(df)
        start = train_size

        while start + test_size <= n:
            test_df  = df.iloc[start:start + test_size]
            result   = self.run(test_df, symbol=symbol, min_bars=60)
            results.append(result)
            start += test_size

        if not results:
            return {}

        avg = {
            "windows":          len(results),
            "avg_total_return": round(np.mean([r.total_return for r in results]), 4),
            "avg_win_rate":     round(np.mean([r.win_rate for r in results]), 4),
            "avg_sharpe":       round(np.mean([r.sharpe for r in results]), 4),
            "avg_max_drawdown": round(np.mean([r.max_drawdown for r in results]), 4),
            "avg_profit_factor":round(np.mean([r.profit_factor for r in results]), 4),
        }
        logger.info(f"Walk-forward ({symbol}): {avg}")
        return avg
