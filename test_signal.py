import pymongo
import datetime

# Connect to your PilotOS MongoDB
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["pilotos"] # Double check if your DB name is 'pilotos' or 'trading'
signals_col = db["signals"]

# Create a fake signal
test_data = {
    "symbol": "BTC/USD",
    "signal": "BUY",
    "confidence": 85.5,
    "timestamp": datetime.datetime.utcnow()
}

# Insert it
signals_col.insert_one(test_data)
print("Signal injected! Check your dashboard.")