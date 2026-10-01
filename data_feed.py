import requests
import time
from datetime import datetime

# Free data source - no key required
BASE_URL = "https://biquote.io/api"

def get_ohlc(symbol: str, interval: str = "5", limit: int = 300):
    """
    symbol examples: EURUSD, GBPUSD, USDJPY, XAUUSD
    interval: 5 = M5, 15 = M15, 60 = H1
    """
    try:
        url = f"{BASE_URL}/{symbol}"
        # Note: biquote live quotes + simple candles
        # For production we will expand this
        r = requests.get(url, timeout=10)
        data = r.json()
        return data
    except Exception as e:
        print("Data error:", e)
        return None

def get_m5_candles(symbol: str, limit: int = 200):
    """Simple placeholder - we will improve later"""
    # For now we use a free source that can give us recent data
    # In next version we will use proper historical endpoint
    return None