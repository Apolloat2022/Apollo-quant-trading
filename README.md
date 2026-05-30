# Apollo Quant Trading Platform

A signal-generation system that monitors 14 assets across stocks, crypto, and forex 24/7. It applies four technical strategies simultaneously, calculates position sizing and risk, serves a live web dashboard, and sends alerts via Telegram or email — all without placing trades automatically.

---

## Features

- **Live Scanner** — scans every 5 minutes, outputs BUY / SELL / HOLD signals with confidence scores
- **4 Strategies** — Momentum, Ichimoku Cloud, Mean Reversion, and Volume-Price run in parallel; a Combined weighted vote aggregates them
- **ML Models** — optional Random Forest + Gradient Boosting models trained on historical data to improve signal accuracy
- **Backtesting** — full backtest and walk-forward analysis for any symbol
- **Risk Manager** — enforces 2% per-trade risk, daily loss cap, stop loss / take profit levels, and market regime filters
- **Web Dashboard** — real-time signal table, confidence charts, and backtest panel at `http://localhost:5000`
- **Alerts** — Telegram, email, and console; quiet hours (9 pm – 8 am) and configurable alert cap
- **AI Summaries** — Google Gemini generates a plain-English market summary after every scan

---

## Project Structure

```
quant-trading-platform/
├── main_complete.py          # Entry point — scan / backtest / ml_train / dashboard modes
├── data_fetcher.py           # Market data from yfinance (stocks/forex) and Kraken (crypto)
├── trading_engine_v2.py      # Strategy execution and signal aggregation
├── strategies/
│   ├── advanced_strategies.py   # Ichimoku, Mean Reversion, Volume-Price
│   └── ml_strategies.py         # ML model inference
├── backtest/
│   └── engine.py                # Backtest and walk-forward engine
├── risk/
│   └── manager.py               # Position sizing, drawdown, regime detection
├── alerts/
│   └── notifier.py              # Telegram, email, console alert dispatch
├── llm/
│   └── analyzer.py              # Gemini AI market summary
├── dashboard/
│   ├── app.py                   # Flask + SocketIO server
│   └── templates/dashboard.html # Live dashboard UI
├── models/                      # Saved ML model files (.pkl)
├── logs/                        # trading.log and signals_log.txt
├── .env.example                 # Template — copy to .env and fill in keys
└── requirements.txt
```

---

## Assets Monitored

| Class | Symbols |
|-------|---------|
| Stocks | AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA |
| Crypto (24/7 via Kraken) | BTC/USDT, ETH/USDT, SOL/USDT, XRP/USDT |
| Forex | EURUSD=X, GBPUSD=X, USDJPY=X, AUDUSD=X |

---

## Requirements

- Python 3.10+
- Internet connection for live data

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/Apolloat2022/Apollo-quant-trading.git
cd Apollo-quant-trading

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env
# Open .env and add any API keys you want (all optional)
```

---

## Configuration

Copy `.env.example` to `.env`. All keys are optional — the app runs without any of them.

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | AI market summaries (free at aistudio.google.com) |
| `TELEGRAM_BOT_TOKEN` | Telegram push alerts |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `EMAIL_FROM` | Gmail address for email alerts |
| `EMAIL_PASSWORD` | Gmail App Password (not your login password) |
| `EMAIL_TO` | Destination address for email alerts |

---

## Usage

### Daily startup (two terminals)

**Terminal 1 — Live scanner**
```bash
python main_complete.py --mode scan --capital 10000 --alerts console telegram
```

**Terminal 2 — Dashboard**
```bash
python main_complete.py --mode dashboard
```

Then open `http://localhost:5000` in your browser.

### Backtest a symbol
```bash
python main_complete.py --mode backtest --symbol AAPL --asset stock
python main_complete.py --mode backtest --symbol BTC/USDT --asset crypto
python main_complete.py --mode backtest --symbol EURUSD=X --asset forex --walkforward
```

### Train ML models
```bash
python main_complete.py --mode ml_train --symbol AAPL --asset stock --timeframe 1d
python main_complete.py --mode ml_train --symbol ETH/USDT --asset crypto --timeframe 1d
```

### Alert options
```bash
--alerts console              # Console only (default)
--alerts console telegram     # Console + Telegram
--alerts console email        # Console + email
--max-alerts 3                # Cap at top 3 signals per scan (by confidence)
```

---

## Signal Guide

| Confidence | Meaning | Action |
|-----------|---------|--------|
| 0.70 – 1.00 | Strong | Consider full position |
| 0.50 – 0.69 | Moderate | Consider half position |
| 0.35 – 0.49 | Weak | Skip or very small size |
| 0.00 – 0.34 | Noise | Ignore |

For highest reliability, wait for **confidence > 0.60** AND **2+ strategies in agreement**.

---

## Risk Rules (applied automatically)

- Max risk per trade: **2% of capital**
- Daily loss cap: **5% of capital**
- Stop loss: 1% below entry
- Take profit: 2% above entry
- BUY signals are suppressed in bearish + high-volatility regimes

---

## Disclaimer

This tool generates signals for informational purposes only. It does not place trades automatically and does not guarantee profitable results. Always apply your own judgment and never risk money you cannot afford to lose.
