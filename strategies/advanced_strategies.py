"""
Advanced Trading Strategies
Momentum, Ichimoku, Mean Reversion, Volume-Price, and Combined strategies.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """Represents a trading signal."""
    symbol:     str
    signal:     str        # 'BUY', 'SELL', 'HOLD'
    confidence: float      # 0.0 – 1.0
    strategy:   str
    price:      float
    details:    dict


def _zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """Rolling Z-score normalisation."""
    mean = series.rolling(window).mean()
    std  = series.rolling(window).std()
    return (series - mean) / (std + 1e-9)


# ──────────────────────────────────────────────────────────
# 1. MOMENTUM STRATEGY
# ──────────────────────────────────────────────────────────

def momentum_strategy(df: pd.DataFrame, symbol: str = "") -> Optional[Signal]:
    """
    Multi-period momentum with volume confirmation.

    Calculates Z-scored returns over 1, 5, 10, and 20 bars.
    Requires volume > 1.2x the 20-bar average for full weight.

    Args:
        df:     OHLCV DataFrame (at least 25 bars required)
        symbol: Asset symbol for labelling

    Returns:
        Signal or None if insufficient data.
    """
    try:
        if len(df) < 25:
            return None

        close  = df["close"]
        volume = df["volume"]

        ret_1  = close.pct_change(1)
        ret_5  = close.pct_change(5)
        ret_10 = close.pct_change(10)
        ret_20 = close.pct_change(20)

        z1  = _zscore(ret_1,  20).iloc[-1]
        z5  = _zscore(ret_5,  20).iloc[-1]
        z10 = _zscore(ret_10, 20).iloc[-1]
        z20 = _zscore(ret_20, 20).iloc[-1]

        momentum_score = z1 * 0.4 + z5 * 0.3 + z10 * 0.2 + z20 * 0.1

        vol_avg       = volume.rolling(20).mean().iloc[-1]
        vol_confirmed = bool(volume.iloc[-1] > vol_avg * 1.2)
        if not vol_confirmed:
            momentum_score *= 0.5

        confidence = min(abs(momentum_score) / 3.0, 1.0)

        if momentum_score > 0.5:
            signal = "BUY"
        elif momentum_score < -0.5:
            signal = "SELL"
        else:
            signal = "HOLD"

        return Signal(
            symbol=symbol,
            signal=signal,
            confidence=round(confidence, 4),
            strategy="Momentum",
            price=round(float(close.iloc[-1]), 6),
            details={
                "momentum_score":  round(float(momentum_score), 4),
                "volume_confirmed": vol_confirmed,
                "z1":  round(float(z1),  4),
                "z5":  round(float(z5),  4),
                "z10": round(float(z10), 4),
                "z20": round(float(z20), 4),
            },
        )
    except Exception as exc:
        logger.error(f"Momentum strategy error for {symbol}: {exc}")
        return None


# ──────────────────────────────────────────────────────────
# 2. ICHIMOKU CLOUD STRATEGY
# ──────────────────────────────────────────────────────────

def _ichimoku(df: pd.DataFrame):
    """Compute Ichimoku Cloud components."""
    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    tenkan = (high.rolling(9).max()  + low.rolling(9).min())  / 2
    kijun  = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou = close.shift(-26)

    return tenkan, kijun, span_a, span_b, chikou


def ichimoku_strategy(df: pd.DataFrame, symbol: str = "") -> Optional[Signal]:
    """
    Ichimoku Cloud strategy.

    BUY  when price is above cloud AND Tenkan-sen > Kijun-sen.
    SELL when price is below cloud AND Tenkan-sen < Kijun-sen.

    Args:
        df:     OHLCV DataFrame (at least 60 bars required)
        symbol: Asset symbol

    Returns:
        Signal or None.
    """
    try:
        if len(df) < 60:
            return None

        tenkan, kijun, span_a, span_b, _ = _ichimoku(df)
        close = df["close"]

        price  = float(close.iloc[-1])
        t_val  = float(tenkan.iloc[-1])
        k_val  = float(kijun.iloc[-1])
        sa_val = float(span_a.iloc[-1]) if not np.isnan(span_a.iloc[-1]) else price
        sb_val = float(span_b.iloc[-1]) if not np.isnan(span_b.iloc[-1]) else price

        cloud_top    = max(sa_val, sb_val)
        cloud_bottom = min(sa_val, sb_val)

        above_cloud = price > cloud_top
        below_cloud = price < cloud_bottom
        tk_bullish  = t_val > k_val

        if above_cloud and tk_bullish:
            signal     = "BUY"
            confidence = min((price - cloud_top) / (cloud_top + 1e-9) * 10 + 0.5, 1.0)
        elif below_cloud and not tk_bullish:
            signal     = "SELL"
            confidence = min((cloud_bottom - price) / (cloud_bottom + 1e-9) * 10 + 0.5, 1.0)
        else:
            signal     = "HOLD"
            confidence = 0.3

        return Signal(
            symbol=symbol,
            signal=signal,
            confidence=round(abs(confidence), 4),
            strategy="Ichimoku",
            price=round(price, 6),
            details={
                "tenkan":      round(t_val,  6),
                "kijun":       round(k_val,  6),
                "span_a":      round(sa_val, 6),
                "span_b":      round(sb_val, 6),
                "above_cloud": above_cloud,
                "below_cloud": below_cloud,
            },
        )
    except Exception as exc:
        logger.error(f"Ichimoku strategy error for {symbol}: {exc}")
        return None


# ──────────────────────────────────────────────────────────
# 3. MEAN REVERSION STRATEGY
# ──────────────────────────────────────────────────────────

def mean_reversion_strategy(df: pd.DataFrame, symbol: str = "") -> Optional[Signal]:
    """
    Mean Reversion using Bollinger Bands and rolling Z-score.

    BUY  when Z-score < -2 (oversold outside lower band).
    SELL when Z-score > +2 (overbought outside upper band).

    Args:
        df:     OHLCV DataFrame (at least 25 bars required)
        symbol: Asset symbol

    Returns:
        Signal or None.
    """
    try:
        if len(df) < 25:
            return None

        close = df["close"]
        ma    = close.rolling(20).mean()
        std   = close.rolling(20).std()
        upper = ma + 2 * std
        lower = ma - 2 * std

        zscore = _zscore(close, 20).iloc[-1]
        price  = float(close.iloc[-1])
        band_range = float(upper.iloc[-1]) - float(lower.iloc[-1]) + 1e-9
        bb_pos = (price - float(lower.iloc[-1])) / band_range

        if zscore < -2:
            signal     = "BUY"
            confidence = min(abs(zscore) / 4.0, 1.0)
        elif zscore > 2:
            signal     = "SELL"
            confidence = min(abs(zscore) / 4.0, 1.0)
        else:
            signal     = "HOLD"
            confidence = 0.2

        return Signal(
            symbol=symbol,
            signal=signal,
            confidence=round(confidence, 4),
            strategy="MeanReversion",
            price=round(price, 6),
            details={
                "zscore":      round(float(zscore), 4),
                "bb_upper":    round(float(upper.iloc[-1]), 6),
                "bb_lower":    round(float(lower.iloc[-1]), 6),
                "bb_mid":      round(float(ma.iloc[-1]),    6),
                "bb_position": round(float(bb_pos), 4),
            },
        )
    except Exception as exc:
        logger.error(f"MeanReversion strategy error for {symbol}: {exc}")
        return None


# ──────────────────────────────────────────────────────────
# 4. VOLUME-PRICE STRATEGY
# ──────────────────────────────────────────────────────────

def _obv(df: pd.DataFrame) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def volume_price_strategy(df: pd.DataFrame, symbol: str = "") -> Optional[Signal]:
    """
    Volume-Price Strategy with OBV and accumulation/distribution detection.

    Accumulation : price up + high volume → BUY
    Distribution : price down + high volume → SELL
    OBV trend confirms direction.

    Args:
        df:     OHLCV DataFrame (at least 25 bars required)
        symbol: Asset symbol

    Returns:
        Signal or None.
    """
    try:
        if len(df) < 25:
            return None

        close  = df["close"]
        volume = df["volume"]

        vol_avg   = volume.rolling(20).mean()
        vol_ratio = float((volume / (vol_avg + 1e-9)).iloc[-1])

        price_chg = float(close.pct_change(1).iloc[-1])
        obv_trend = float(_obv(df).diff(5).iloc[-1])

        accumulation = price_chg > 0 and vol_ratio > 1.2
        distribution = price_chg < 0 and vol_ratio > 1.2
        obv_bullish  = obv_trend > 0

        if accumulation and obv_bullish:
            signal     = "BUY"
            confidence = min(vol_ratio / 3.0, 1.0)
        elif distribution and not obv_bullish:
            signal     = "SELL"
            confidence = min(vol_ratio / 3.0, 1.0)
        else:
            signal     = "HOLD"
            confidence = 0.2

        return Signal(
            symbol=symbol,
            signal=signal,
            confidence=round(confidence, 4),
            strategy="VolumePrice",
            price=round(float(close.iloc[-1]), 6),
            details={
                "volume_ratio": round(vol_ratio, 4),
                "price_change": round(price_chg, 6),
                "obv_trend":    round(obv_trend, 2),
                "accumulation": accumulation,
                "distribution": distribution,
            },
        )
    except Exception as exc:
        logger.error(f"VolumePrice strategy error for {symbol}: {exc}")
        return None


# ──────────────────────────────────────────────────────────
# 5. COMBINED STRATEGY
# ──────────────────────────────────────────────────────────

_WEIGHTS = {
    "Momentum":      0.30,
    "Ichimoku":      0.20,
    "MeanReversion": 0.20,
    "VolumePrice":   0.30,
}

_SIGNAL_SCORE = {"BUY": 1.0, "HOLD": 0.0, "SELL": -1.0}


def combined_strategy(df: pd.DataFrame, symbol: str = "") -> Optional[Signal]:
    """
    Weighted ensemble of all four strategies.

    BUY  if weighted score > 0.3
    SELL if weighted score < -0.3
    HOLD otherwise.

    Args:
        df:     OHLCV DataFrame
        symbol: Asset symbol

    Returns:
        Signal or None.
    """
    try:
        sub_signals = {
            "Momentum":      momentum_strategy(df, symbol),
            "Ichimoku":      ichimoku_strategy(df, symbol),
            "MeanReversion": mean_reversion_strategy(df, symbol),
            "VolumePrice":   volume_price_strategy(df, symbol),
        }

        weighted_score = 0.0
        total_weight   = 0.0
        components: dict = {}

        for name, sig in sub_signals.items():
            if sig is None:
                continue
            w     = _WEIGHTS[name]
            score = _SIGNAL_SCORE[sig.signal] * sig.confidence
            weighted_score += score * w
            total_weight   += w
            components[name] = {
                "signal":     sig.signal,
                "confidence": sig.confidence,
                "contribution": round(score * w, 4),
            }

        if total_weight == 0:
            return None

        normalized = weighted_score / total_weight
        confidence = min(abs(normalized), 1.0)

        if normalized > 0.3:
            signal = "BUY"
        elif normalized < -0.3:
            signal = "SELL"
        else:
            signal = "HOLD"

        return Signal(
            symbol=symbol,
            signal=signal,
            confidence=round(confidence, 4),
            strategy="Combined",
            price=round(float(df["close"].iloc[-1]), 6),
            details={
                "weighted_score": round(normalized, 4),
                "components":     components,
            },
        )
    except Exception as exc:
        logger.error(f"Combined strategy error for {symbol}: {exc}")
        return None
