import requests
import time
from datetime import datetime, timezone

def get_m5_candles(symbol: str, limit: int = 150):
    """
    Free data using Twelve Data demo + fallback.
    symbol examples: GBP/USD , USD/JPY
    """
    # Convert our symbol format
    if symbol == "GBPUSD":
        td_symbol = "GBP/USD"
    elif symbol == "USDJPY":
        td_symbol = "USD/JPY"
    else:
        td_symbol = symbol

    try:
        # Twelve Data free demo endpoint (limited but works for testing)
        url = (
            f"https://api.twelvedata.com/time_series"
            f"?symbol={td_symbol}"
            f"&interval=5min"
            f"&outputsize={limit}"
            f"&apikey=demo"
        )
        r = requests.get(url, timeout=12)
        data = r.json()

        if "values" not in data:
            print("Data error for", symbol, ":", data.get("message", data))
            return None

        values = data["values"][::-1]  # oldest → newest

        return {
            "open":  [float(x["open"])  for x in values],
            "high":  [float(x["high"])  for x in values],
            "low":   [float(x["low"])   for x in values],
            "close": [float(x["close"]) for x in values],
            "time":  [x["datetime"]     for x in values]
        }

    except Exception as e:
        print("get_m5_candles error:", e)
        return None
