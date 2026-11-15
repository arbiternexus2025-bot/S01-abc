"""MARIO STRIKE — Single-TF ENTRY (structure)."""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import List
from Mario_Pure_detection import MarioPureDetector, DetectorConfig


def _naive_utc(t) -> pd.Timestamp:
    try:
        if isinstance(t, (int, float)) and float(t) > 1e9:
            ts = pd.Timestamp(datetime.fromtimestamp(float(t), tz=timezone.utc))
        else:
            ts = pd.Timestamp(t)
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return ts
    except Exception:
        return pd.Timestamp(datetime.utcnow())


def arrays_to_df(ohlc: dict) -> pd.DataFrame:
    n = len(ohlc["close"])
    times = ohlc.get("time")
    if times is None:
        now = datetime.now(timezone.utc).timestamp()
        times = np.array([now - (n - 1 - i) * 3600 for i in range(n)])
    return pd.DataFrame({
        "Time": [_naive_utc(t) for t in times],
        "Open": np.asarray(ohlc.get("open", ohlc["close"]), dtype=float),
        "High": np.asarray(ohlc["high"], dtype=float),
        "Low": np.asarray(ohlc["low"], dtype=float),
        "Close": np.asarray(ohlc["close"], dtype=float),
    })


LOOKBACK = {"M30": 2, "H1": 1, "H4": 1}
TF_PRI = {"H4": 300, "H1": 200, "M30": 100}


def scan_mario(ohlc: dict, market: str, tf: str) -> List[dict]:
    if ohlc is None or len(ohlc["close"]) < 120:
        return []
    df = arrays_to_df(ohlc)
    cfg = DetectorConfig().for_timeframe(tf)
    cfg.mode = "SINGLE"
    det = MarioPureDetector(cfg)
    lookback = LOOKBACK.get(tf, 1)
    sigs = det.detect_latest(df, market=market, timeframe=tf, lookback_bars=lookback)
    n = len(df)
    d = 2 if market == "XAUUSD" else (3 if "JPY" in market else 5)
    out = []
    for s in sigs:
        bars_ago = n - 1 - s.entry_bar
        if bars_ago > lookback:
            continue
        side = s.side
        out.append({
            "strategy": "MARIO",
            "phase": "ENTRY",
            "mode": "SINGLE",
            "market": market,
            "tf": tf,
            "direction": side,
            "poi_type": s.poi_type.value if hasattr(s.poi_type, "value") else str(s.poi_type),
            "poi_top": round(float(s.poi_top), d),
            "poi_bot": round(float(s.poi_bot), d),
            "entry": round(float(s.entry_price), d),
            "stop": round(float(s.stop_price), d),
            "target": round(float(s.target_price), d),
            "rr": float(s.rr),
            "bars_ago": bars_ago,
            "priority": 1000 + TF_PRI.get(tf, 100),
            "role": f"Mario Structure {tf}",
            "key": f"MARIO|{market}|{side}|{tf}|{round(float(s.entry_price), d)}",
        })
    return out
