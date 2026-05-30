"""
Machine Learning Strategies
Random Forest and Gradient Boosting classifiers for signal generation.
"""

import logging
import os
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, accuracy_score
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
os.makedirs(MODELS_DIR, exist_ok=True)

LABEL_MAP = {0: "SELL", 1: "HOLD", 2: "BUY"}
LABEL_REVERSE = {"SELL": 0, "HOLD": 1, "BUY": 2}


# ──────────────────────────────────────────────────────────
# FEATURE ENGINEERING
# ──────────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram."""
    ema_fast   = close.ewm(span=fast, adjust=False).mean()
    ema_slow   = close.ewm(span=slow, adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create 20+ features from OHLCV data.

    Args:
        df: OHLCV DataFrame

    Returns:
        DataFrame of features (NaN rows dropped).
    """
    feat = pd.DataFrame(index=df.index)
    close  = df["close"]
    volume = df["volume"]
    high   = df["high"]
    low    = df["low"]

    # Price returns
    for p in [1, 5, 10, 20]:
        feat[f"ret_{p}"] = close.pct_change(p)

    # Rolling volatility
    for w in [5, 10, 20]:
        feat[f"vol_{w}"] = close.pct_change(1).rolling(w).std()

    # Volume features
    feat["vol_change"]  = volume.pct_change(1)
    feat["vol_ratio"]   = volume / (volume.rolling(20).mean() + 1e-9)

    # RSI
    feat["rsi"] = _rsi(close, 14)

    # MACD
    macd_line, macd_sig, macd_hist = _macd(close)
    feat["macd"]      = macd_line
    feat["macd_sig"]  = macd_sig
    feat["macd_hist"] = macd_hist

    # Bollinger Band position
    ma20  = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    feat["bb_pos"] = (close - (ma20 - 2 * std20)) / (4 * std20 + 1e-9)

    # Moving average crossovers
    ma10 = close.rolling(10).mean()
    ma50 = close.rolling(50).mean()
    feat["ma10_cross"] = (ma10 - ma50) / (ma50 + 1e-9)

    # Price vs MA ratios
    feat["price_ma10"] = close / (ma10 + 1e-9) - 1
    feat["price_ma20"] = close / (ma20 + 1e-9) - 1
    feat["price_ma50"] = close / (ma50 + 1e-9) - 1

    # High-Low range
    feat["hl_range"]   = (high - low) / (close + 1e-9)

    # ATR proxy (5-period)
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    feat["atr5"] = tr.rolling(5).mean() / (close + 1e-9)

    return feat.dropna()


def _create_labels(df: pd.DataFrame, horizon: int = 5, threshold: float = 0.005) -> pd.Series:
    """
    Create forward-return labels: BUY / HOLD / SELL.

    Args:
        df: OHLCV DataFrame
        horizon: Bars ahead to measure return
        threshold: Min return magnitude to classify as BUY/SELL

    Returns:
        Series of integer labels (0=SELL, 1=HOLD, 2=BUY).
    """
    fwd_return = df["close"].shift(-horizon) / df["close"] - 1
    labels = pd.Series(1, index=df.index, dtype=int)   # default HOLD
    labels[fwd_return >  threshold] = 2   # BUY
    labels[fwd_return < -threshold] = 0   # SELL
    return labels


# ──────────────────────────────────────────────────────────
# TRAIN & PREDICT
# ──────────────────────────────────────────────────────────

def train_models(
    df: pd.DataFrame,
    symbol: str,
    horizon: int = 5,
    threshold: float = 0.005,
) -> dict:
    """
    Train Random Forest and Gradient Boosting classifiers.

    Args:
        df: OHLCV DataFrame (at least 200 bars recommended)
        symbol: Asset symbol (used for saving models)
        horizon: Forward return horizon for labels
        threshold: Return threshold for BUY/SELL labels

    Returns:
        Dict with model metrics and feature importances.
    """
    features = engineer_features(df)
    labels   = _create_labels(df, horizon=horizon, threshold=threshold)

    # Align indices
    common_idx = features.index.intersection(labels.index)
    X = features.loc[common_idx]
    y = labels.loc[common_idx]
    y = y.dropna()
    X = X.loc[y.index]

    if len(X) < 100:
        logger.error(f"Insufficient data for {symbol}: {len(X)} samples")
        return {}

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    # Random Forest
    rf = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
    rf.fit(X_train_s, y_train)
    rf_preds = rf.predict(X_test_s)
    rf_acc   = accuracy_score(y_test, rf_preds)

    # Gradient Boosting
    gb = GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42)
    gb.fit(X_train_s, y_train)
    gb_preds = gb.predict(X_test_s)
    gb_acc   = accuracy_score(y_test, gb_preds)

    logger.info(f"[{symbol}] RF accuracy: {rf_acc:.3f}  GB accuracy: {gb_acc:.3f}")

    # Save models
    safe_sym = symbol.replace("/", "_").replace("=", "_")
    joblib.dump(rf,     os.path.join(MODELS_DIR, f"{safe_sym}_rf.pkl"))
    joblib.dump(gb,     os.path.join(MODELS_DIR, f"{safe_sym}_gb.pkl"))
    joblib.dump(scaler, os.path.join(MODELS_DIR, f"{safe_sym}_scaler.pkl"))
    joblib.dump(list(X.columns), os.path.join(MODELS_DIR, f"{safe_sym}_features.pkl"))

    feat_imp = pd.Series(rf.feature_importances_, index=X.columns).sort_values(ascending=False)

    return {
        "rf_accuracy": rf_acc,
        "gb_accuracy": gb_acc,
        "feature_importance": feat_imp.head(10).to_dict(),
        "train_size": len(X_train),
        "test_size":  len(X_test),
        "rf_report":  classification_report(y_test, rf_preds, target_names=["SELL", "HOLD", "BUY"]),
    }


def ml_predict(df: pd.DataFrame, symbol: str) -> Optional[dict]:
    """
    Generate signal using saved ML models.

    Args:
        df: OHLCV DataFrame
        symbol: Asset symbol

    Returns:
        Dict with signal, probabilities, or None if models not found.
    """
    safe_sym = symbol.replace("/", "_").replace("=", "_")
    rf_path      = os.path.join(MODELS_DIR, f"{safe_sym}_rf.pkl")
    gb_path      = os.path.join(MODELS_DIR, f"{safe_sym}_gb.pkl")
    scaler_path  = os.path.join(MODELS_DIR, f"{safe_sym}_scaler.pkl")
    feat_path    = os.path.join(MODELS_DIR, f"{safe_sym}_features.pkl")

    for p in [rf_path, gb_path, scaler_path, feat_path]:
        if not os.path.exists(p):
            logger.warning(f"Model file not found: {p}. Run ml_train first.")
            return None

    try:
        rf      = joblib.load(rf_path)
        gb      = joblib.load(gb_path)
        scaler  = joblib.load(scaler_path)
        feat_names = joblib.load(feat_path)

        features = engineer_features(df)
        if features.empty:
            return None

        # Use most recent bar
        X_latest = features.iloc[[-1]][feat_names]
        X_scaled = scaler.transform(X_latest)

        rf_proba = rf.predict_proba(X_scaled)[0]
        gb_proba = gb.predict_proba(X_scaled)[0]

        # Ensemble average
        avg_proba = (rf_proba + gb_proba) / 2

        classes = rf.classes_
        proba_dict = {LABEL_MAP[int(c)]: round(float(p), 4) for c, p in zip(classes, avg_proba)}

        best_class = int(classes[np.argmax(avg_proba)])
        signal = LABEL_MAP[best_class]
        confidence = round(float(np.max(avg_proba)), 4)

        return {
            "signal":      signal,
            "confidence":  confidence,
            "probabilities": proba_dict,
            "price":       round(float(df["close"].iloc[-1]), 6),
        }
    except Exception as exc:
        logger.error(f"ML predict error for {symbol}: {exc}")
        return None
