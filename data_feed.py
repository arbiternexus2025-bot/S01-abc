"""MARIO STRIKE data feed — biquote.io + short HTF cache (cuts latency)."""
from __future__ import annotations
import time
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
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
}

# In-memory cache: (market, tf) -> (ts, ohlc)
_CACHE: dict = {}
_CACHE_TTL = 55.0  # seconds — reuse within one scan cycle


def _parse_time(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _fetch(symbol: str, interval: str, limit: int):
    r = requests.get(
        f"https://biquote.io/api/{symbol}/ohlc",
        params={"interval": interval, "limit": limit},
        timeout=10,
    )
    data = r.json()
    if "bars" not in data:
        return None, data
    bars = [b for b in data["bars"] if not b.get("isOpen", False)]
    bars = list(reversed(bars))
    if len(bars) < 80:
        return None, {"message": f"only {len(bars)} bars"}
    return {
        "open": np.array([float(b["open"]) for b in bars]),
        "high": np.array([float(b["high"]) for b in bars]),
        "low": np.array([float(b["low"]) for b in bars]),
        "close": np.array([float(b["close"]) for b in bars]),
        "time": np.array([_parse_time(b.get("openTime", b.get("time", ""))) for b in bars]),
    }, None


def get_ohlc(market: str, tf: str, limit: int = 320, use_cache: bool = True):
    key = (market, tf)
    now = time.time()
    if use_cache and key in _CACHE:
        ts, ohlc = _CACHE[key]
        if now - ts < _CACHE_TTL:
            return ohlc

    symbol = SYMBOL_MAP.get(market, market)
    interval = INTERVAL_MAP.get(tf)
    if not interval:
        print(f"[DATA] {market} {tf}: unsupported", flush=True)
        return None
    try:
        ohlc, err = _fetch(symbol, interval, limit)
        if ohlc is None:
            print(f"[DATA] {market} {tf}: {err}", flush=True)
            return None
        _CACHE[key] = (now, ohlc)
        return ohlc
    except Exception as e:
        print(f"[DATA] {market} {tf}: {e}", flush=True)
        return None


def clear_cache():
    _CACHE.clear()
