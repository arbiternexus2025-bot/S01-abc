"""
MARIO STRIKE — Dual-TF entry engine (v2.0.0)
============================================
HTF: Sweep + BOS + POI
LTF: Rejection inside HTF POI  →  ENTRY only (no WATCH)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from Mario_Pure_detection import MarioPureDetector, DetectorConfig


def _naive_utc(t) -> pd.Timestamp:
    """Force tz-naive UTC so HTF/LTF timestamps always compare cleanly."""
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
    tlist = [_naive_utc(t) for t in times]
    return pd.DataFrame({
        "Time": tlist,
        "Open": np.asarray(ohlc.get("open", ohlc["close"]), dtype=float),
        "High": np.asarray(ohlc["high"], dtype=float),
        "Low": np.asarray(ohlc["low"], dtype=float),
        "Close": np.asarray(ohlc["close"], dtype=float),
    })


def scan_dual(
    ohlc_htf: dict,
    ohlc_ltf: dict,
    market: str,
    htf: str,
    ltf: str,
    lookback_bars: int = 3,
) -> List[dict]:
    """
    Entry-only Dual-TF scan.
    Returns packed signal dicts for alerts (fresh LTF entries only).
    """
    if ohlc_htf is None or ohlc_ltf is None:
        return []
    if len(ohlc_htf["close"]) < 100 or len(ohlc_ltf["close"]) < 100:
        return []

    df_htf = arrays_to_df(ohlc_htf)
    df_ltf = arrays_to_df(ohlc_ltf)

    cfg = DetectorConfig().as_dual(htf=htf, ltf=ltf)
    det = MarioPureDetector(cfg)
    sigs = det.detect_dual_latest(df_htf, df_ltf, market=market, lookback_bars=lookback_bars)

    out = []
    n_ltf = len(df_ltf)
    for s in sigs:
        bars_ago = n_ltf - 1 - s.entry_bar
        if bars_ago > lookback_bars:
            continue
        side = s.side
        d = 2 if market == "XAUUSD" else (3 if "JPY" in market else 5)
        out.append({
            "phase": "ENTRY",
            "mode": "DUAL",
            "market": market,
            "htf": htf,
            "ltf": ltf,
            "tf": f"{htf}→{ltf}",
            "direction": side,
            "poi_type": s.poi_type.value if hasattr(s.poi_type, "value") else str(s.poi_type),
            "poi_top": round(float(s.poi_top), d),
            "poi_bot": round(float(s.poi_bot), d),
            "entry": round(float(s.entry_price), d),
            "stop": round(float(s.stop_price), d),
            "target": round(float(s.target_price), d),
            "risk": round(float(s.risk), d + 1),
            "rr": float(s.rr),
            "sweep_level": round(float(s.sweep_level), d),
            "bars_ago": bars_ago,
            "priority": _priority(htf, ltf),
            "key": f"ENTRY|{market}|{side}|{round(float(s.poi_bot), d)}|{round(float(s.poi_top), d)}",
        })
    return out


def _priority(htf: str, ltf: str) -> int:
    # Prefer higher HTF; then finer LTF (faster confirmation)
    h = {"H4": 400, "H1": 300, "M30": 200}.get(htf, 100)
    l = {"M15": 30, "M30": 20, "H1": 10}.get(ltf, 0)
    return h + l
