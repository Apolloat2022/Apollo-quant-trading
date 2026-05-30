"""
Quick test — sends a fake signal to all configured alert channels.
Run: python test_alerts.py
"""

from dotenv import load_dotenv
load_dotenv()

from alerts.notifier import dispatch_alerts

test_signal = {
    "symbol":     "AAPL",
    "signal":     "BUY",
    "confidence": 0.78,
    "strategy":   "Combined",
    "price":      213.45,
    "asset_type": "stock",
    "details":    {},
}

test_position = {
    "quantity":       4.0,
    "risk_amount":    200.0,
    "stop_loss":      211.31,
    "take_profit":    217.74,
    "position_value": 853.80,
}

print("Sending test alert to console + Telegram...")
results = dispatch_alerts(
    signals=[test_signal],
    channels=["console", "telegram"],
    pos_sizes={"AAPL": test_position},
)
print(f"Results: {results}")
print("Done. Check your Telegram for the test message.")
