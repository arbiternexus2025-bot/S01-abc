"""MARIO STRIKE data feed — biquote.io OHLC (closed bars only)."""
import requests
import numpy as np
from datetime import datetime

SYMBOL_MAP = {
    "XAUUSD": "XAUUSD",
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "USDCHF": "USDCHF", "USDCAD": "USDCAD", "AUDUSD": "AUDUSD", "NZDUSD": "NZDUSD",
    "EURGBP": "EURGBP", "EURJPY": "EURJPY", "GBPJPY": "GBPJPY", "AUDJPY": "AUDJPY",
    "EURAUD": "EURAUD", "EURCHF": "EURCHF", "GBPCHF": "GBPCHF",
    "CADJPY": "CADJPY", "CHFJPY": "CHFJPY", "AUDCAD": "AUDCAD",
    "AUDNZD": "AUDNZD", "NZDJPY": "NZDJPY",
}

INTERVAL_MAP = {
    "M30": "30m",
    "H1": "1h",
    "H2": "2h",
    "H4": "4h",
}


def _parse_time(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def get_ohlc(market: str, tf: str, limit: int = 350):
    symbol = SYMBOL_MAP.get(market, market)
    interval = INTERVAL_MAP.get(tf, "1h")
    try:
        r = requests.get(
            f"https://biquote.io/api/{symbol}/ohlc",
            params={"interval": interval, "limit": limit},
            timeout=12,
        )
        data = r.json()
        if "bars" not in data:
            print(f"[DATA] {market} {tf}: bad response {str(data)[:100]}", flush=True)
            return None
        bars = [b for b in data["bars"] if not b.get("isOpen", False)]
        bars = list(reversed(bars))
        if len(bars) < 100:
            print(f"[DATA] {market} {tf}: only {len(bars)} bars", flush=True)
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
