import requests
import numpy as np

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

def get_ohlc(market: str, tf: str, limit: int = 300):
    symbol = SYMBOL_MAP.get(market, market)
    interval = INTERVAL_MAP.get(tf, "30m")

    try:
        url = f"https://biquote.io/api/{symbol}/ohlc"
        params = {"interval": interval, "limit": limit}
        r = requests.get(url, params=params, timeout=12)
        data = r.json()

        if "bars" not in data:
            print(f"[DATA] Error {market} {tf}: {data}", flush=True)
            return None

        bars = data["bars"]
        closed = [b for b in bars if not b.get("isOpen", False)]
        closed = closed[::-1]  # oldest → newest

        if len(closed) < 80:
            print(f"[DATA] Not enough bars for {market} {tf} ({len(closed)})", flush=True)
            return None

        return {
            "open":  np.array([float(b["open"])  for b in closed]),
            "high":  np.array([float(b["high"])  for b in closed]),
            "low":   np.array([float(b["low"])   for b in closed]),
            "close": np.array([float(b["close"]) for b in closed]),
        }
    except Exception as e:
        print(f"[DATA] Exception {market} {tf}: {e}", flush=True)
        return None
