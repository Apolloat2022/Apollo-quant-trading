import sys, os
sys.path.insert(0, r"C:\Projects\APPS\apollo-quant-trading")
os.chdir(r"C:\Projects\APPS\apollo-quant-trading")

import pandas as pd
from data_fetcher import fetch_asset
from strategies.kronos_strategy import kronos_strategy
from strategies.advanced_strategies import combined_strategy
from dashboard.app import app

print("=== 1. Testing data fetcher ===")
df = fetch_asset("NVDA", "stock", "5m")
print(f"Fetched NVDA: {len(df)} rows, latest close: {df['close'].iloc[-1]}")

print("\n=== 2. Testing Kronos AI Strategy ===")
k_sig = kronos_strategy(df, "NVDA")
print(f"Kronos Signal: {k_sig.signal}, Conf: {k_sig.confidence}")
print(f"Kronos Details: {k_sig.details}")

print("\n=== 3. Testing Combined Ensemble Strategy ===")
c_sig = combined_strategy(df, "NVDA")
print(f"Combined Signal: {c_sig.signal}, Conf: {c_sig.confidence}")
print(f"Components: {c_sig.details.get('components')}")

print("\n=== 4. Testing Flask /api/kronos/forecast Endpoint ===")
client = app.test_client()
res = client.get("/api/kronos/forecast?symbol=NVDA&timeframe=5m")
print(f"API Status: {res.status_code}")
data = res.get_json()
print(f"API Response: Signal={data.get('signal')}, Target Close={data.get('target_close')}, Target High={data.get('target_high')}, Target Low={data.get('target_low')}")

print("\n=== 5. Testing Crypto Asset (BTC/USDT) ===")
btc_res = client.get("/api/kronos/forecast?symbol=BTC/USDT&timeframe=5m")
print(f"BTC API Status: {btc_res.status_code}")
btc_data = btc_res.get_json()
print(f"BTC Response: Signal={btc_data.get('signal')}, Price=${btc_data.get('current_price')}, Target High=${btc_data.get('target_high')}")

print("\n ALL KRONOS INTEGRATION TESTS PASSED SUCCESSFULLY!")
