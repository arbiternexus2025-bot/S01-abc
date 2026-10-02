import requests
import numpy as np

SYMBOL_MAP = {
    "XAUUSD": "XAU/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "USDCAD": "USD/CAD",
    "USDCHF": "USD/CHF",
    "EURUSD": "EUR/USD"
}

INTERVAL_MAP = {
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h"
}

def get_ohlc(market: str, tf: str, limit: int = 300):
    symbol = SYMBOL_MAP.get(market, market)
    interval = INTERVAL_MAP.get(tf, "5min")
    try:
        url = (
            f"https://api.twelvedata.com/time_series"
            f"?symbol={symbol}&interval={interval}"
            f"&outputsize={limit}&apikey=demo"
        )
        r = requests.get(url, timeout=15)
        data = r.json()
        if "values" not in data:
            print(f"Data error {market} {tf}:", data.get("message", data))
            return None
        values = data["values"][::-1]
        return {
            "open":  np.array([float(x["open"])  for x in values]),
            "high":  np.array([float(x["high"])  for x in values]),
            "low":   np.array([float(x["low"])   for x in values]),
            "close": np.array([float(x["close"]) for x in values]),
        }
    except Exception as e:
        print("get_ohlc error:", e)
        return None
