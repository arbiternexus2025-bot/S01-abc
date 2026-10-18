import requests
import numpy as np
from datetime import datetime

SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCAD": "USDCAD",
    "USDCHF": "USDCHF",
    "EURUSD": "EURUSD",
}
INTERVAL_MAP = {
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
}


def _parse_time(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def get_ohlc(market: str, tf: str, limit: int = 300):
    symbol = SYMBOL_MAP.get(market, market)
    interval = INTERVAL_MAP.get(tf, "30m")
    try:
        r = requests.get(
            f"https://biquote.io/api/{symbol}/ohlc",
            params={"interval": interval, "limit": limit},
            timeout=12,
        )
        data = r.json()
        if "bars" not in data:
            print(f"[DATA] Error {market} {tf}: {data}", flush=True)
            return None
        bars = [b for b in data["bars"] if not b.get("isOpen", False)][::-1]
        if len(bars) < 80:
            print(f"[DATA] Not enough bars {market} {tf}", flush=True)
            return None
        return {
            "open": np.array([float(b["open"]) for b in bars]),
            "high": np.array([float(b["high"]) for b in bars]),
            "low": np.array([float(b["low"]) for b in bars]),
            "close": np.array([float(b["close"]) for b in bars]),
            "time": np.array([_parse_time(b.get("openTime", "")) for b in bars]),
        }
    except Exception as e:
        print(f"[DATA] Exception {market} {tf}: {e}", flush=True)
        return None
