# Quant Trading Platform — Complete User Guide

---

## TABLE OF CONTENTS

1. [What This App Does](#1-what-this-app-does)
2. [First-Time Setup](#2-first-time-setup)
3. [How to Open the App Every Day](#3-how-to-open-the-app-every-day)
4. [Understanding the Dashboard](#4-understanding-the-dashboard)
5. [How to Run a Backtest](#5-how-to-run-a-backtest)
6. [How to Train ML Models](#6-how-to-train-ml-models)
7. [How to Read Signals — BUY / SELL / HOLD](#7-how-to-read-signals--buy--sell--hold)
8. [When to Be Certain: Confidence Guide](#8-when-to-be-certain-confidence-guide)
9. [Cash Account Rules (Robinhood / Coinbase / E*TRADE)](#9-cash-account-rules-robinhood--coinbase--etrade)
10. [Risk Management Rules](#10-risk-management-rules)
11. [Assets Monitored](#11-assets-monitored)
12. [Alert Setup (Telegram / Email)](#12-alert-setup-telegram--email)
13. [Controlling Alerts — Quiet Hours & Limits](#13-controlling-alerts--quiet-hours--limits)
14. [AI Market Summaries (Gemini)](#14-ai-market-summaries-gemini)
15. [Troubleshooting](#15-troubleshooting)
16. [Quick Reference Card](#16-quick-reference-card)

---

## 1. WHAT THIS APP DOES

This is a **signal generation system**. It watches 14 assets (stocks, crypto, forex)
24/7 and tells you when conditions look favorable to BUY or when to expect a
price drop (SELL). You then execute trades **manually** on your platform of choice.

**It does NOT:**
- Place trades automatically
- Guarantee profits
- Replace your own judgment

**It DOES:**
- Scan markets every 5 minutes
- Apply 4 technical strategies simultaneously
- Calculate position size and risk for each trade
- Show a live dashboard with all signals
- Send alerts to your phone via Telegram
- Generate AI market summaries via Google Gemini after each scan

**Strategies running under the hood:**
| Strategy | What it detects |
|----------|----------------|
| Momentum | Assets with strong directional price moves |
| Ichimoku Cloud | Trend direction and cloud breakouts |
| Mean Reversion | Oversold / overbought conditions |
| Volume-Price | Accumulation and distribution by big players |
| Combined | Weighted vote of all 4 above |

---

## 2. FIRST-TIME SETUP

### Step 1 — Install Python dependencies (one time only)
```
cd C:\APPS\quant-trading-platform
pip install -r requirements.txt
```

### Step 2 — Copy environment file
```
copy .env.example .env
```
Open `.env` in Notepad and fill in any keys you want
(Telegram, email, Gemini AI). The app works without any keys —
they are all optional.

### Step 3 — Done. You are ready to run.

---

## 3. HOW TO OPEN THE APP EVERY DAY

You need **two PowerShell windows** running simultaneously.

### Window 1 — Live Scanner
```
cd C:\APPS\quant-trading-platform
python main_complete.py --mode scan --capital 10000 --alerts console
```
Replace `10000` with your actual trading capital in USD.

This window:
- Fetches live data every 5 minutes
- Prints BUY/SELL signals directly in the console
- Feeds signals into the dashboard in real time

### Window 2 — Dashboard (open in browser)
```
cd C:\APPS\quant-trading-platform
python main_complete.py --mode dashboard
```
Then open your browser and go to:
```
http://localhost:5000
```

### To stop the app
Press **Ctrl + C** once in each window. Wait 2 seconds for clean shutdown.

---

## 4. UNDERSTANDING THE DASHBOARD

When you open http://localhost:5000 you will see:

```
┌──────────────────────────────────────────────┐
│  Total Signals │ BUY │ SELL │ HOLD │ Avg Conf│
├──────────────────────────────────────────────┤
│  Signal Distribution Pie  │  Confidence Bar  │
├──────────────────────────────────────────────┤
│  Backtest Panel                              │
├──────────────────────────────────────────────┤
│  Live Signals Table                          │
│  Time │ Symbol │ Signal │ Strategy │ Price   │
└──────────────────────────────────────────────┘
```

**Metric Cards (top row):**
- Total Signals — how many signals generated this session
- BUY count — number of buy signals
- SELL count — number of sell signals
- HOLD count — number of hold signals
- Avg Confidence — average signal strength (higher = more reliable)

**Signal Distribution Pie:**
- Shows ratio of BUY vs SELL vs HOLD across all assets
- Mostly BUY = bullish market condition
- Mostly SELL = bearish market condition
- Mixed = choppy / sideways market

**Confidence Bar Chart:**
- Average confidence per asset
- Taller bar = more consistent signals for that asset
- Use this to identify which assets are trending clearly

**Live Signals Table:**
- Updates in real time as the scanner runs
- Green BUY badge = potential entry
- Red SELL badge = potential exit or avoid
- Yellow HOLD badge = wait, no clear direction

---

## 5. HOW TO RUN A BACKTEST

A backtest shows how a strategy would have performed on historical data.
Use it to evaluate a strategy BEFORE trading with real money.

### From the Dashboard
1. Go to http://localhost:5000
2. In the Backtest panel:
   - Enter symbol (AAPL, BTC/USDT, EURUSD=X)
   - Select asset type (Stock / Crypto / Forex)
   - Select strategy (Combined recommended)
   - Set your capital amount
3. Click **Run Backtest**

### From PowerShell
```
python main_complete.py --mode backtest --symbol AAPL --asset stock
python main_complete.py --mode backtest --symbol BTC/USDT --asset crypto
python main_complete.py --mode backtest --symbol EURUSD=X --asset forex
python main_complete.py --mode backtest --symbol NVDA --asset stock --walkforward
```

### How to Read Backtest Results

| Metric | Good | Acceptable | Bad |
|--------|------|-----------|-----|
| Total Return | > +10% | 0% to +10% | Negative |
| Win Rate | > 55% | 45–55% | < 45% |
| Profit Factor | > 1.5 | 1.0–1.5 | < 1.0 |
| Sharpe Ratio | > 1.0 | 0–1.0 | Negative |
| Max Drawdown | < 10% | 10–20% | > 20% |

**Profit Factor** is the most important number:
- 1.0 = breaking even
- 1.5 = for every $1 lost, you win $1.50
- 2.0 = for every $1 lost, you win $2.00

**Walk-Forward Analysis** (add --walkforward flag):
- Tests the strategy across multiple rolling time windows
- Much more reliable than a single backtest
- If average metrics are still positive = robust strategy

### Compare All Strategies
Click **Compare All** in the dashboard to see all 4 strategies side by side.
Pick the strategy with the best Sharpe Ratio and Profit Factor for that asset.

---

## 6. HOW TO TRAIN ML MODELS

ML models learn patterns from historical price data and improve signal accuracy
over time. Training is optional but recommended for assets you trade regularly.

### Train a model
```
# Stock (best — lots of history)
python main_complete.py --mode ml_train --symbol AAPL --asset stock --timeframe 1d

# Crypto
python main_complete.py --mode ml_train --symbol BTC/USDT --asset crypto --timeframe 1d

# Forex
python main_complete.py --mode ml_train --symbol EURUSD=X --asset forex --timeframe 1d
```

**Always use --timeframe 1d for training.** Daily data gives 500+ bars which
the model needs to learn properly. Hourly data (1h) gives only ~60 bars which
is too little and produces poor accuracy.

### What good ML results look like

| Metric | Good | Acceptable | Poor |
|--------|------|-----------|------|
| RF Accuracy | > 55% | 45–55% | < 45% |
| GB Accuracy | > 55% | 45–55% | < 45% |

### What to do with poor accuracy
- Use more data: switch to `--timeframe 1d` if you haven't already
- Try a different asset (trending stocks like NVDA work better than choppy ones)
- Retrain every 2–4 weeks as market conditions change

### Models are saved automatically
Trained models are saved in `C:\APPS\quant-trading-platform\models\`
The scanner uses them automatically in future scans.

---

## 7. HOW TO READ SIGNALS — BUY / SELL / HOLD

### Signal Output in PowerShell
```
[BUY] AAPL | conf=0.72 | price=213.45
```
This means:
- Asset: AAPL (Apple stock)
- Direction: BUY
- Confidence: 72% (strong signal)
- Current price: $213.45

### Signal Output in Dashboard
Each signal in the table shows:
- Time — when signal was generated
- Symbol — which asset
- Signal — BUY (green) / SELL (red) / HOLD (yellow)
- Strategy — which strategy triggered it
- Price — price at time of signal
- Confidence — strength bar + percentage

### What triggers each signal

**BUY signal is generated when:**
- Momentum Z-score is positive AND volume is above average
- Price broke above the Ichimoku Cloud AND Tenkan-sen crossed above Kijun-sen
- Price is at the lower Bollinger Band (Z-score below -2, oversold)
- Accumulation detected (price rising on heavy volume)
- Combined weighted score > 0.30

**SELL signal is generated when:**
- Momentum Z-score is negative AND volume is above average
- Price broke below the Ichimoku Cloud AND Tenkan-sen crossed below Kijun-sen
- Price is at the upper Bollinger Band (Z-score above +2, overbought)
- Distribution detected (price falling on heavy volume)
- Combined weighted score < -0.30

**HOLD signal means:**
- No clear directional bias
- Conflicting signals across strategies
- Do nothing — wait for next scan

---

## 8. WHEN TO BE CERTAIN: CONFIDENCE GUIDE

Confidence score is the single most important number. It ranges from 0.0 to 1.0
(shown as 0% to 100% in the dashboard).

### Confidence Levels

| Confidence | Level | What to do |
|-----------|-------|-----------|
| 0.70 – 1.00 | STRONG | High conviction — consider full position size |
| 0.50 – 0.69 | MODERATE | Good signal — consider half position size |
| 0.35 – 0.49 | WEAK | Low conviction — skip or very small position |
| 0.00 – 0.34 | NOISE | Ignore completely |

### Rules for maximum certainty — wait for ALL of these:

**Rule 1: Confidence above 0.60**
Only act on signals where confidence is 60% or higher.

**Rule 2: Multiple strategies agree**
Check the signal details. If 3 or 4 strategies all show BUY, it is much more
reliable than if only 1 shows BUY.

**Rule 3: Volume confirmation**
The momentum strategy shows "volume_confirmed: True" when volume is above
the 20-bar average. This is a key confirmation.

**Rule 4: Market regime is not dangerous**
The risk manager checks the market regime automatically. If regime is
"bearish + high volatility" it will skip BUY signals. Trust this filter.

**Rule 5: The signal repeats**
If the same asset shows BUY on two consecutive scans (10 minutes apart),
that is a stronger signal than a one-time appearance.

**Rule 6: Check the broader market**
Before acting on a stock signal, check if SPY (S&P 500) is trending up.
Before acting on crypto, check if BTC is in a bullish regime.
Assets tend to follow their broader market.

### Example of a HIGH CONFIDENCE trade setup:
```
Signal   : BUY
Symbol   : NVDA
Confidence: 0.78
Strategy : Combined
Components:
  Momentum      → BUY  (conf=0.81, volume confirmed)
  Ichimoku      → BUY  (price above cloud, TK bullish)
  MeanReversion → HOLD (neutral — not overbought yet)
  VolumePrice   → BUY  (accumulation detected)
```
3 out of 4 strategies agree → BUY, high volume → strong setup.

### Example of a LOW CONFIDENCE trade to skip:
```
Signal    : BUY
Symbol    : TSLA
Confidence: 0.38
Components:
  Momentum      → HOLD
  Ichimoku      → HOLD
  MeanReversion → BUY  (only one strategy agrees)
  VolumePrice   → HOLD
```
Only 1 strategy triggered → skip this signal.

---

## 9. ACCOUNT RULES (ROBINHOOD / COINBASE / E*TRADE)

### Robinhood (Margin account — full access)
You can act on both BUY and SELL signals:

| App Signal | You own the asset? | Action |
|-----------|-------------------|--------|
| BUY | No | Buy it |
| BUY | Yes | Hold or add more |
| SELL | No | Short sell via Robinhood Margin |
| SELL | Yes | Sell / close your long position |
| HOLD | Any | Do nothing |

### Coinbase / E*TRADE (Cash account — no shorting)
SELL signals are only useful for exiting positions you already own:

| App Signal | You own the asset? | Action |
|-----------|-------------------|--------|
| BUY | No | Buy it |
| BUY | Yes | Hold or add more |
| SELL | No | Do nothing (skip) |
| SELL | Yes | Sell your position |
| HOLD | Any | Do nothing |

### Entry checklist (before buying):
- [ ] Signal is BUY
- [ ] Confidence is above 0.60
- [ ] At least 2 strategies agree
- [ ] Volume confirmed = True
- [ ] You are not already overexposed to this sector

### Exit checklist (when to sell what you own):
- [ ] App generates SELL signal for your asset, OR
- [ ] Price hits the Take Profit level shown in signal, OR
- [ ] Price hits the Stop Loss level shown in signal

### Position sizing (already calculated by the app):
The signal output includes recommended position size based on 2% capital risk.
Example for $10,000 capital:
```
Risk per trade : $200 (2% of $10,000)
Stop loss      : 1% below entry
Take profit    : 2% above entry
```
This means on a $200 stock: buy 1 share, stop loss at $198, take profit at $204.

---

## 10. RISK MANAGEMENT RULES

These are enforced automatically by the system but you must follow them manually:

### Never risk more than 2% per trade
If you have $10,000 — maximum loss per trade = $200.
If you have $5,000  — maximum loss per trade = $100.

### Daily loss limit = 5%
If you lose more than 5% of your capital in one day, stop trading for the day.
Example: $10,000 capital → stop after losing $500 in one day.

### Stop loss — always use it
Every signal comes with a stop loss price. This is the price at which you
cut your loss. Never hold past the stop loss hoping it recovers.

### Take profit — where to sell winners
Every signal comes with a take profit price (2% above entry).
When price reaches this level, sell at least half your position.

### Never trade these regimes (the app filters these automatically):
- Bearish trend + high volatility = dangerous, no new BUY entries
- Major news events (earnings, Fed announcements) = skip that day

---

## 11. ASSETS MONITORED

### Stocks (via yfinance — US market hours only)
| Symbol | Company |
|--------|---------|
| AAPL | Apple |
| MSFT | Microsoft |
| GOOGL | Alphabet (Google) |
| AMZN | Amazon |
| NVDA | NVIDIA |
| TSLA | Tesla |

### Crypto (via Kraken — 24/7)
| Symbol | Asset |
|--------|-------|
| BTC/USDT | Bitcoin |
| ETH/USDT | Ethereum |
| SOL/USDT | Solana |
| XRP/USDT | XRP |

### Forex (via yfinance — weekdays only)
| Symbol | Pair |
|--------|------|
| EURUSD=X | Euro / US Dollar |
| GBPUSD=X | British Pound / US Dollar |
| USDJPY=X | US Dollar / Japanese Yen |
| AUDUSD=X | Australian Dollar / US Dollar |

---

## 12. ALERT SETUP (TELEGRAM / EMAIL)

### Telegram setup (recommended — free, instant alerts on your phone)

Step 1: Create a Telegram bot
- Open Telegram, search for @BotFather
- Send: /newbot
- Choose a name (e.g. MyQuantBot)
- Copy the token it gives you

Step 2: Get your chat ID
- Search Telegram for @userinfobot
- Send /start — it will show your chat ID

Step 3: Add to .env file
```
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

Step 4: Run scanner with Telegram alerts
```
python main_complete.py --mode scan --capital 10000 --alerts console telegram
```

### Email setup (Gmail)
Step 1: Enable 2-factor auth on Gmail, then create an App Password at:
https://myaccount.google.com/apppasswords

Step 2: Add to .env file
```
EMAIL_FROM=your@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_TO=your@gmail.com
```

Step 3: Run with email alerts
```
python main_complete.py --mode scan --capital 10000 --alerts console email
```

---

## 13. CONTROLLING ALERTS — QUIET HOURS & LIMITS

### Quiet Hours (9pm – 8am)
The app automatically stops sending Telegram, email, and SMS alerts
after 9pm and resumes at 8am. During quiet hours:
- Console (PowerShell) still shows all signals
- No messages sent to your phone
- Fully automatic — no action needed

### Max Alerts Per Scan Cycle
By default only the **top 3 signals** (highest confidence) are sent
to Telegram per scan. The console always shows all signals.

The app covers stocks + crypto + forex — without this limit you could
get 10+ messages per scan. With the cap you only get the best ones.

### How to change the alert limit
Add `--max-alerts` to your scan command:

```
# Default — top 3 alerts per scan
python main_complete.py --mode scan --capital 10000 --alerts console telegram

# Only top 2 alerts
python main_complete.py --mode scan --capital 10000 --alerts console telegram --max-alerts 2

# Top 5 alerts
python main_complete.py --mode scan --capital 10000 --alerts console telegram --max-alerts 5

# Only 1 alert (best signal only)
python main_complete.py --mode scan --capital 10000 --alerts console telegram --max-alerts 1
```

### How quiet hours work
- Quiet period  : 9:00pm to 8:00am (your local time)
- During quiet  : only console output, no phone alerts
- After 8:00am  : Telegram/email resumes automatically
- No restart needed — it checks the time on every scan cycle

### Alert priority during the limit
When more than 3 signals exist in one scan, the app picks the top 3
by confidence score. Example with 5 signals:

```
NVDA  BUY  conf=0.81  ← sent to Telegram (rank 1)
BTC   BUY  conf=0.74  ← sent to Telegram (rank 2)
TSLA  BUY  conf=0.68  ← sent to Telegram (rank 3)
AAPL  SELL conf=0.55  ← console only (rank 4, skipped)
ETH   SELL conf=0.43  ← console only (rank 5, skipped)
```

### What each alert looks like on Telegram
```
🔴 SELL – GOOGL
   Strategy   : Combined
   Price      : 290.41
   Confidence : 42.6%
   Qty        : 6.89
   Stop Loss  : 293.31
   Take Profit: 284.60
   Risk $     : $20.00
```

---

## 14. AI MARKET SUMMARIES (GEMINI)

After every scan cycle, the app calls Google Gemini to generate a plain-English
summary of what the signals mean. It appears as a formatted box in the console:

```
============================================================
  AI MARKET SUMMARY  (Gemini)
============================================================
  The market shows a bullish bias with 4 BUY signals across
  tech stocks and crypto. NVDA and BTC/USDT lead in
  confidence. Elevated volatility in forex warrants caution
  on EURUSD positions.
============================================================
```

### What the AI summary covers
- Overall market bias (bullish / bearish / mixed)
- Which assets have the strongest signals
- Any notable risks worth watching

### Setup (one time only)
1. Go to https://aistudio.google.com/app/apikey
2. Sign in with Google → Create API Key → Copy it
3. Open `.env` and set:
```
GEMINI_API_KEY=your_key_here
```
4. The summary will appear automatically on every scan — no extra flags needed.

### How it works
- Runs automatically in every scan cycle
- Uses the free Gemini Flash model (no cost)
- If the key is missing or the API is unreachable, the app falls back to a
  basic text summary and continues running normally — it never crashes

### Alerts vs. AI Summary
These are two separate and independent features:

| Feature | What it does | Controlled by |
|---------|-------------|---------------|
| Alerts (`--alerts`) | Sends signals to console, Telegram, email | `--alerts` flag |
| AI Summary (Gemini) | Generates market analysis in the console | `GEMINI_API_KEY` in `.env` |

The AI summary always appears in the console regardless of your `--alerts` setting.

---

## 15. TROUBLESHOOTING


### "Can't reach localhost:5000"
The dashboard is not running. Open a second PowerShell and run:
```
cd C:\APPS\quant-trading-platform
python main_complete.py --mode dashboard
```

### "Failed to fetch data" for crypto
Use the correct format: BTC/USDT not BTC or btc.
Binance is geo-blocked in the US — the app automatically falls back to Kraken.

### "No actionable signals this cycle"
This is normal. The strategy is strict by design to avoid false signals.
Markets are often sideways with no clear direction.
Wait for the next scan (every 5 minutes).

### ML accuracy is very low (below 40%)
Train on daily data, not hourly:
```
python main_complete.py --mode ml_train --symbol AAPL --asset stock --timeframe 1d
```

### Multiple "Shutdown signal received" in terminal
You pressed Ctrl+C multiple times. Close the PowerShell window and open a new one.

### Scanner stops after one cycle
Check if the terminal shows an error. Most common cause: no internet connection
or API rate limit hit. Wait 60 seconds and restart.

---

## 16. QUICK REFERENCE CARD

```
╔══════════════════════════════════════════════════════╗
║           DAILY STARTUP (2 PowerShell windows)       ║
╠══════════════════════════════════════════════════════╣
║  PS 1:  cd C:\APPS\quant-trading-platform            ║
║         python main_complete.py --mode scan          ║
║           --capital 10000 --alerts console telegram  ║
║           --max-alerts 3                             ║
║                                                      ║
║  PS 2:  cd C:\APPS\quant-trading-platform            ║
║         python main_complete.py --mode dashboard     ║
║                                                      ║
║  Browser: http://localhost:5000                      ║
╠══════════════════════════════════════════════════════╣
║              SIGNAL ACTION TABLE                     ║
╠══════════════════════════════════════════════════════╣
║  BUY  + conf > 0.60 + 2+ strategies = BUY IT        ║
║  BUY  + conf < 0.60               = SKIP            ║
║  SELL + you own it                = SELL IT          ║
║  SELL + you don't own it          = IGNORE           ║
║  HOLD                             = DO NOTHING       ║
╠══════════════════════════════════════════════════════╣
║              BACKTEST COMMANDS                       ║
╠══════════════════════════════════════════════════════╣
║  python main_complete.py --mode backtest             ║
║       --symbol AAPL --asset stock                    ║
║       --symbol BTC/USDT --asset crypto               ║
║       --symbol EURUSD=X --asset forex                ║
╠══════════════════════════════════════════════════════╣
║              ML TRAINING COMMANDS                    ║
╠══════════════════════════════════════════════════════╣
║  python main_complete.py --mode ml_train             ║
║       --symbol AAPL --asset stock --timeframe 1d     ║
╠══════════════════════════════════════════════════════╣
║              RISK RULES                              ║
╠══════════════════════════════════════════════════════╣
║  Max per trade  : 2% of capital                      ║
║  Daily loss cap : 5% of capital                      ║
║  Stop loss      : 1% below entry price               ║
║  Take profit    : 2% above entry price               ║
╚══════════════════════════════════════════════════════╝
```

---

╔══════════════════════════════════════════════════════╗
║              ALERT CONTROLS                          ║
╠══════════════════════════════════════════════════════╣
║  Quiet hours  : 9pm – 8am (automatic, no setup)     ║
║  Max alerts   : 3 per scan (top by confidence)       ║
║  Change limit : add --max-alerts 2  (or any number) ║
║  During quiet : console shows all, phone is silent  ║
╚══════════════════════════════════════════════════════╝
```

---

*Last updated: March 2026 | Quant Trading Platform v2*
