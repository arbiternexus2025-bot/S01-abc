"""MARIO STRIKE data feed — biquote.io OHLC (closed bars only).
H2 is built by aggregating H1 bars (biquote has no native 2h).
"""
from __future__ import annotations
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

# Native biquote intervals only
INTERVAL_MAP = {
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
}


def _parse_time(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _fetch_native(symbol: str, interval: str, limit: int):
    r = requests.get(
        f"https://biquote.io/api/{symbol}/ohlc",
        params={"interval": interval, "limit": limit},
        timeout=12,
    )
    data = r.json()
    if "bars" not in data:
        return None, data
    bars = [b for b in data["bars"] if not b.get("isOpen", False)]
    bars = list(reversed(bars))
    if len(bars) < 80:
        return None, {"message": f"only {len(bars)} closed bars"}
    return {
        "open": np.array([float(b["open"]) for b in bars]),
        "high": np.array([float(b["high"]) for b in bars]),
        "low": np.array([float(b["low"]) for b in bars]),
        "close": np.array([float(b["close"]) for b in bars]),
        "time": np.array([_parse_time(b.get("openTime", b.get("time", ""))) for b in bars]),
    }, None


def _resample_h1_to_h2(ohlc: dict) -> dict | None:
    """Aggregate consecutive H1 bars into H2 (2×1h). Drop incomplete last pair."""
    n = len(ohlc["close"])
    if n < 120:
        return None
    # Align to even pairs from the end so the latest completed H2 is included
    start = n % 2  # if odd length, drop oldest orphan
    o, h, l, c, t = (
        ohlc["open"][start:],
        ohlc["high"][start:],
        ohlc["low"][start:],
        ohlc["close"][start:],
        ohlc["time"][start:],
    )
    m = len(c) // 2
    if m < 80:
        return None
    o2 = np.empty(m)
    h2 = np.empty(m)
    l2 = np.empty(m)
    c2 = np.empty(m)
    t2 = np.empty(m)
    for i in range(m):
        j = i * 2
        o2[i] = o[j]
        h2[i] = max(h[j], h[j + 1])
        l2[i] = min(l[j], l[j + 1])
        c2[i] = c[j + 1]
        t2[i] = t[j]
    return {"open": o2, "high": h2, "low": l2, "close": c2, "time": t2}


def get_ohlc(market: str, tf: str, limit: int = 350):
    symbol = SYMBOL_MAP.get(market, market)
    try:
        if tf == "H2":
            # Fetch more H1 bars so resampled H2 has enough history
            ohlc, err = _fetch_native(symbol, "1h", limit=min(limit * 2, 700))
            if ohlc is None:
                print(f"[DATA] {market} H2 (via H1): {err}", flush=True)
                return None
            h2 = _resample_h1_to_h2(ohlc)
            if h2 is None:
                print(f"[DATA] {market} H2: not enough H1 bars to build 2h", flush=True)
                return None
            return h2

        interval = INTERVAL_MAP.get(tf)
        if not interval:
            print(f"[DATA] {market} {tf}: unsupported TF", flush=True)
            return None
        ohlc, err = _fetch_native(symbol, interval, limit)
        if ohlc is None:
            print(f"[DATA] {market} {tf}: {err}", flush=True)
            return None
        return ohlc
    except Exception as e:
        print(f"[DATA] {market} {tf}: {e}", flush=True)
        return None
