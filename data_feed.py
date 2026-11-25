"""EDGE LAB data feed — biquote.io + short cache (incl. M1 for S43)."""
from __future__ import annotations
import time
import requests
import numpy as np
from datetime import datetime

SYMBOL_MAP = {
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "USDCHF": "USDCHF", "USDCAD": "USDCAD", "AUDUSD": "AUDUSD", "NZDUSD": "NZDUSD",
    "XAUUSD": "XAUUSD",
}

INTERVAL_MAP = {
    "M1": "1m",
    "M5": "5m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
}

_CACHE: dict = {}
_CACHE_TTL = 35.0


def _parse_time(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def get_ohlc(market: str, tf: str, limit: int = 400, use_cache: bool = True):
    key = (market, tf)
    now = time.time()
    if use_cache and key in _CACHE:
        ts, ohlc = _CACHE[key]
        if now - ts < _CACHE_TTL:
            return ohlc

    symbol = SYMBOL_MAP.get(market, market)
    interval = INTERVAL_MAP.get(tf)
    if not interval:
        print(f"[DATA] {market} {tf}: unsupported TF", flush=True)
        return None

    # M1 needs longer history for trail + windows
    if tf == "M1":
        limit = max(limit, 1500)
    elif tf == "M5":
        limit = max(limit, 500)

    try:
        r = requests.get(
            f"https://biquote.io/api/{symbol}/ohlc",
            params={"interval": interval, "limit": limit},
            timeout=12,
        )
        data = r.json()
        if "bars" not in data:
            print(f"[DATA] {market} {tf}: {str(data)[:140]}", flush=True)
            return None
        bars = [b for b in data["bars"] if not b.get("isOpen", False)]
        bars = list(reversed(bars))
        need = {"M1": 300, "M5": 150, "M30": 100, "H1": 100, "H4": 80}.get(tf, 100)
        if len(bars) < need:
            print(f"[DATA] {market} {tf}: only {len(bars)} bars (need {need})", flush=True)
            return None
        ohlc = {
            "open": np.array([float(b["open"]) for b in bars]),
            "high": np.array([float(b["high"]) for b in bars]),
            "low": np.array([float(b["low"]) for b in bars]),
            "close": np.array([float(b["close"]) for b in bars]),
            "time": np.array([_parse_time(b.get("openTime", b.get("time", ""))) for b in bars]),
        }
        _CACHE[key] = (now, ohlc)
        return ohlc
    except Exception as e:
        print(f"[DATA] {market} {tf}: {e}", flush=True)
        return None


def clear_cache():
    _CACHE.clear()
