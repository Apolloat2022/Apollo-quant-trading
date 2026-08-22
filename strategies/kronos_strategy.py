"""
Kronos Foundation Model Strategy for Apollo Quant Trading.
Generates multi-step candlestick forecasts, price targets, take-profit/stop-loss levels,
and trading signals.

Supports dual modes:
1. Direct in-process PyTorch model execution (if torch and kronos model are installed).
2. Remote microservice execution via KRONOS_API_URL (e.g. for Vercel deployment).
"""

import os
import sys
import logging
import requests
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Import Signal dataclass from advanced_strategies
try:
    from strategies.advanced_strategies import Signal
except ImportError:
    @dataclass
    class Signal:
        symbol: str
        signal: str
        confidence: float
        strategy: str
        price: float
        details: dict

# Check for local Kronos model availability
KRONOS_AVAILABLE = False
_kronos_predictor = None

try:
    # Try importing from adjacent kronos project or local package
    kronos_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "kronos-stock-forecast")
    if os.path.exists(kronos_root) and kronos_root not in sys.path:
        sys.path.insert(0, kronos_root)
        
    from model import Kronos, KronosTokenizer, KronosPredictor
    KRONOS_AVAILABLE = True
except Exception as e:
    logger.debug(f"Direct Kronos model import not available ({e}). Will use remote API or fallback if configured.")


def _get_predictor():
    """Lazy initialize local predictor instance"""
    global _kronos_predictor
    if _kronos_predictor is None and KRONOS_AVAILABLE:
        try:
            tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-2k")
            model = Kronos.from_pretrained("NeoQuasar/Kronos-mini")
            _kronos_predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=2048)
            logger.info("Local Kronos-mini model loaded successfully for Apollo Quant Trading.")
        except Exception as e:
            logger.error(f"Failed to load local Kronos model: {e}")
            _kronos_predictor = None
    return _kronos_predictor


def kronos_strategy(df: pd.DataFrame, symbol: str = "", lookback: int = 400, pred_len: int = 120) -> Optional[Signal]:
    """
    Kronos Foundation Model Strategy.
    Generates 120-step autoregressive candlestick forecast and produces a Signal.
    """
    if df is None or len(df) < 50:
        return None

    current_price = float(df["close"].iloc[-1])
    kronos_api_url = os.environ.get("KRONOS_API_URL", "").rstrip("/")

    # Mode 1: Remote API (e.g. for Vercel serverless deployment)
    if kronos_api_url:
        try:
            payload = {
                "symbol": symbol,
                "lookback": min(lookback, len(df)),
                "pred_len": pred_len,
                "current_price": current_price,
                "candles": df[["open", "high", "low", "close", "volume"]].tail(min(lookback, len(df))).to_dict(orient="records")
            }
            res = requests.post(f"{kronos_api_url}/api/generate-signals", json=payload, timeout=12)
            if res.status_code == 200:
                data = res.json()
                s = data.get("signals", {})
                return Signal(
                    symbol=symbol,
                    signal=s.get("recommendation", "HOLD").replace("STRONG ", "").split(" ")[0],
                    confidence=float(s.get("confidence", 70.0)) / 100.0,
                    strategy="Kronos AI",
                    price=current_price,
                    details={
                        "target_high": s.get("target_high", current_price),
                        "target_low": s.get("target_low", current_price),
                        "target_close": s.get("target_close", current_price),
                        "pct_change": s.get("pct_change", 0.0),
                        "take_profit": s.get("take_profit_2", current_price * 1.03),
                        "stop_loss": s.get("stop_loss", current_price * 0.98),
                        "bias": s.get("bias", "Neutral"),
                        "raw_recommendation": s.get("recommendation", "HOLD")
                    }
                )
        except Exception as e:
            logger.debug(f"Remote Kronos API call failed for {symbol}: {e}. Falling back to local/heuristic.")

    # Mode 2: Direct PyTorch execution
    predictor = _get_predictor()
    if predictor is not None:
        try:
            actual_lookback = min(lookback, len(df))
            x_df = df.iloc[-actual_lookback:][['open', 'high', 'low', 'close', 'volume']]
            
            # Format timestamps
            if 'timestamps' in df.columns:
                x_ts = pd.Series(pd.to_datetime(df.iloc[-actual_lookback:]['timestamps']).values, name='timestamps')
                last_ts = pd.to_datetime(df['timestamps'].iloc[-1])
                time_diff = pd.to_datetime(df['timestamps'].iloc[1]) - pd.to_datetime(df['timestamps'].iloc[0]) if len(df) > 1 else pd.Timedelta(minutes=5)
            elif isinstance(df.index, pd.DatetimeIndex):
                x_ts = pd.Series(df.index[-actual_lookback:].values, name='timestamps')
                last_ts = df.index[-1]
                time_diff = df.index[1] - df.index[0] if len(df) > 1 else pd.Timedelta(minutes=5)
            else:
                x_ts = pd.Series(pd.date_range(end=pd.Timestamp.now(), periods=actual_lookback, freq="5min"), name='timestamps')
                last_ts = x_ts.iloc[-1]
                time_diff = pd.Timedelta(minutes=5)
                
            y_ts = pd.Series(pd.date_range(start=last_ts + time_diff, periods=pred_len, freq=time_diff), name='timestamps')

            pred_df = predictor.predict(
                df=x_df,
                x_timestamp=x_ts,
                y_timestamp=y_ts,
                pred_len=pred_len,
                T=1.0,
                top_p=0.9,
                sample_count=1,
                verbose=False
            )

            start_price = float(x_df['close'].iloc[-1])
            target_close = float(pred_df['close'].iloc[-1])
            target_high = float(pred_df['high'].max())
            target_low = float(pred_df['low'].min())
            
            price_change = target_close - start_price
            pct_change = (price_change / start_price) * 100.0
            max_upside = ((target_high - start_price) / start_price) * 100.0
            max_downside = ((start_price - target_low) / start_price) * 100.0

            if pct_change >= 1.5 and max_upside >= 1.3 * max_downside:
                rec_signal = "BUY"
                raw_rec = "STRONG BUY"
                bias = "Strongly Bullish"
                confidence = min(0.95, 0.75 + abs(pct_change) * 0.03)
            elif pct_change >= 0.4:
                rec_signal = "BUY"
                raw_rec = "BUY"
                bias = "Bullish"
                confidence = min(0.85, 0.65 + abs(pct_change) * 0.04)
            elif pct_change <= -1.5 and max_downside >= 1.3 * max_upside:
                rec_signal = "SELL"
                raw_rec = "STRONG SELL"
                bias = "Strongly Bearish"
                confidence = min(0.95, 0.75 + abs(pct_change) * 0.03)
            elif pct_change <= -0.4:
                rec_signal = "SELL"
                raw_rec = "SELL"
                bias = "Bearish"
                confidence = min(0.85, 0.65 + abs(pct_change) * 0.04)
            else:
                rec_signal = "HOLD"
                raw_rec = "HOLD"
                bias = "Consolidation"
                confidence = 0.65

            tp = target_high if rec_signal == "BUY" else target_low
            sl = max(0.0, start_price - max(abs(price_change) * 0.4, (start_price * 0.01))) if rec_signal == "BUY" else start_price + max(abs(price_change) * 0.4, (start_price * 0.01))

            return Signal(
                symbol=symbol,
                signal=rec_signal,
                confidence=round(confidence, 4),
                strategy="Kronos AI",
                price=current_price,
                details={
                    "target_high": round(target_high, 2 if target_high > 10 else 4),
                    "target_low": round(target_low, 2 if target_low > 10 else 4),
                    "target_close": round(target_close, 2 if target_close > 10 else 4),
                    "pct_change": round(pct_change, 2),
                    "take_profit": round(tp, 2 if tp > 10 else 4),
                    "stop_loss": round(sl, 2 if sl > 10 else 4),
                    "bias": bias,
                    "raw_recommendation": raw_rec
                }
            )
        except Exception as e:
            logger.error(f"Local Kronos prediction error for {symbol}: {e}")

    # Mode 3: Lightweight Technical Trend Fallback (Ensures strategy never breaks if offline)
    ema_20 = df["close"].ewm(span=20).mean().iloc[-1]
    ema_50 = df["close"].ewm(span=50).mean().iloc[-1]
    vol = float(df["close"].pct_change().rolling(20).std().iloc[-1] or 0.02)
    
    if ema_20 > ema_50:
        return Signal(
            symbol=symbol,
            signal="BUY",
            confidence=0.68,
            strategy="Kronos AI (Trend)",
            price=current_price,
            details={
                "target_high": round(current_price * (1 + vol * 2), 2 if current_price > 10 else 4),
                "target_low": round(current_price * (1 - vol * 0.8), 2 if current_price > 10 else 4),
                "target_close": round(current_price * (1 + vol * 1.2), 2 if current_price > 10 else 4),
                "pct_change": round(vol * 120, 2),
                "take_profit": round(current_price * (1 + vol * 2), 2 if current_price > 10 else 4),
                "stop_loss": round(current_price * (1 - vol * 1.0), 2 if current_price > 10 else 4),
                "bias": "Bullish",
                "raw_recommendation": "BUY"
            }
        )
    elif ema_20 < ema_50:
        return Signal(
            symbol=symbol,
            signal="SELL",
            confidence=0.68,
            strategy="Kronos AI (Trend)",
            price=current_price,
            details={
                "target_high": round(current_price * (1 + vol * 0.8), 2 if current_price > 10 else 4),
                "target_low": round(current_price * (1 - vol * 2), 2 if current_price > 10 else 4),
                "target_close": round(current_price * (1 - vol * 1.2), 2 if current_price > 10 else 4),
                "pct_change": round(-vol * 120, 2),
                "take_profit": round(current_price * (1 - vol * 2), 2 if current_price > 10 else 4),
                "stop_loss": round(current_price * (1 + vol * 1.0), 2 if current_price > 10 else 4),
                "bias": "Bearish",
                "raw_recommendation": "SELL"
            }
        )
    else:
        return Signal(
            symbol=symbol,
            signal="HOLD",
            confidence=0.55,
            strategy="Kronos AI (Trend)",
            price=current_price,
            details={
                "target_high": round(current_price * 1.01, 2 if current_price > 10 else 4),
                "target_low": round(current_price * 0.99, 2 if current_price > 10 else 4),
                "target_close": round(current_price, 2 if current_price > 10 else 4),
                "pct_change": 0.0,
                "take_profit": round(current_price * 1.02, 2 if current_price > 10 else 4),
                "stop_loss": round(current_price * 0.98, 2 if current_price > 10 else 4),
                "bias": "Consolidation",
                "raw_recommendation": "HOLD"
            }
        )
