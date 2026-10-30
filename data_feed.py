"""APEX-19 data feed — biquote.io OHLC (closed bars only)."""
import requests
import numpy as np
from datetime import datetime

# Majors + minors + gold (symbols that fail simply return no_data)
SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCHF": "USDCHF",
    "USDCAD": "USDCAD",
    "AUDUSD": "AUDUSD",
    "NZDUSD": "NZDUSD",
    "EURGBP": "EURGBP",
    "EURJPY": "EURJPY",
    "GBPJPY": "GBPJPY",
    "AUDJPY": "AUDJPY",
    "EURAUD": "EURAUD",
    "EURCHF": "EURCHF",
    "GBPCHF": "GBPCHF",
    "CADJPY": "CADJPY",
    "CHFJPY": "CHFJPY",
    "AUDCAD": "AUDCAD",
    "AUDNZD": "AUDNZD",
    "NZDJPY": "NZDJPY",
}

INTERVAL_MAP = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
}


def _parse_time(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def get_ohlc(market: str, tf: str, limit: int = 300):
    """
    Fetch closed OHLC bars. Returns dict with open/high/low/close/time arrays,
    or None on failure.
    """
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
            print(f"[DATA] {market} {tf}: bad response {str(data)[:120]}", flush=True)
            return None
        bars = [b for b in data["bars"] if not b.get("isOpen", False)]
        bars = list(reversed(bars))
        if len(bars) < 80:
            print(f"[DATA] {market} {tf}: only {len(bars)} closed bars", flush=True)
            return None
        return {
            "open": np.array([float(b["open"]) for b in bars]),
            "high": np.array([float(b["high"]) for b in bars]),
            "low": np.array([float(b["low"]) for b in bars]),
            "close": np.array([float(b["close"]) for b in bars]),
            "time": np.array([_parse_time(b.get("openTime", b.get("time", ""))) for b in bars]),
        }
    except Exception as e:
        print(f"[DATA] {market} {tf}: {e}", flush=True)
        return None
