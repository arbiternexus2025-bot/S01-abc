import requests
import numpy as np

# Map our internal names → biquote symbols
SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCAD": "USDCAD",
    "USDCHF": "USDCHF",
    "EURUSD": "EURUSD"
}

INTERVAL_MAP = {
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h"
}

def get_ohlc(market: str, tf: str, limit: int = 250):
    symbol = SYMBOL_MAP.get(market, market)
    interval = INTERVAL_MAP.get(tf, "5m")

    try:
        url = f"https://biquote.io/api/{symbol}/ohlc"
        params = {"interval": interval, "limit": limit}
        r = requests.get(url, params=params, timeout=12)
        data = r.json()

        if "bars" not in data:
            print(f"Data error {market} {tf}:", data)
            return None

        bars = data["bars"]

        # bars arrive newest-first → reverse to oldest-first
        # skip the currently open bar if present
        closed = [b for b in bars if not b.get("isOpen", False)]
        closed = closed[::-1]  # now oldest → newest

        if len(closed) < 50:
            print(f"Not enough closed bars for {market} {tf}")
            return None

        return {
            "open":  np.array([float(b["open"])  for b in closed]),
            "high":  np.array([float(b["high"])  for b in closed]),
            "low":   np.array([float(b["low"])   for b in closed]),
            "close": np.array([float(b["close"]) for b in closed]),
        }
    except Exception as e:
        print(f"get_ohlc error {market} {tf}:", e)
        return None
