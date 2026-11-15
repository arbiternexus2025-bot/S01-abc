"""
S43 — Parabolic SAR Trail live scanner
======================================
Champions:
  H4_PURE   Best Overall
  H1_VOL50  Best Balance
  M5_VOL40  Best Higher-Frequency (XAU focus)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import List

from S43_PSAR_Trail_detection import detect_psar_signals, Mode, MODE_CONFIG


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
        times = np.array([now - (n - 1 - i) * 300 for i in range(n)])
    return pd.DataFrame({
        "Time": [_naive_utc(t) for t in times],
        "Open": np.asarray(ohlc.get("open", ohlc["close"]), dtype=float),
        "High": np.asarray(ohlc["high"], dtype=float),
        "Low": np.asarray(ohlc["low"], dtype=float),
        "Close": np.asarray(ohlc["close"], dtype=float),
    })


# Freshness: keep alerts tight (anti-late)
LOOKBACK = {"H4": 1, "H1": 1, "M5": 3}

# Research-facing RR reference for messaging (trail is primary exit)
RR_REF = {"H4_PURE": 3.0, "H1_VOL50": 2.5, "M5_VOL40": 2.0}

MODE_PRI = {"H4_PURE": 400, "H1_VOL50": 300, "M5_VOL40": 200}


def scan_s43(ohlc: dict, market: str, mode: str) -> List[dict]:
    if ohlc is None or len(ohlc["close"]) < 150:
        return []
    if mode not in MODE_CONFIG:
        return []

    cfg = MODE_CONFIG[Mode(mode) if not isinstance(mode, Mode) else mode]
    tf = cfg["tf"]
    df = arrays_to_df(ohlc)

    # detect requires room for entry at i+1 — drop incomplete edge safely
    try:
        sigs = detect_psar_signals(df, mode=mode)
    except Exception as e:
        print(f"  [S43] detect error {market} {mode}: {e}", flush=True)
        return []

    n = len(df)
    lookback = LOOKBACK.get(tf, 1)
    d = 2 if market == "XAUUSD" else (3 if "JPY" in market else 5)
    rr = RR_REF.get(mode, 2.5)
    out = []

    for s in sigs:
        # entry_bar can be last index; skip if would need future bar
        if s.entry_bar >= n:
            continue
        bars_ago = n - 1 - s.entry_bar
        if bars_ago > lookback or bars_ago < 0:
            continue

        side = "LONG" if s.direction == 1 else "SHORT"
        entry = float(s.entry_price)
        stop = float(s.stop_initial) if s.stop_initial is not None else float(s.psar_at_entry)
        risk = abs(entry - stop)
        if risk < 1e-12:
            continue
        if side == "LONG":
            target = entry + rr * risk
        else:
            target = entry - rr * risk

        out.append({
            "strategy": "S43",
            "phase": "ENTRY",
            "mode": mode,
            "market": market,
            "tf": tf,
            "direction": side,
            "entry": round(entry, d),
            "stop": round(stop, d),
            "target": round(target, d),
            "psar": round(float(s.psar_at_entry), d),
            "atr_pct": round(float(s.atr_pct), 2),
            "rr": rr,
            "bars_ago": bars_ago,
            "priority": 2000 + MODE_PRI.get(mode, 100),
            "role": MODE_CONFIG[Mode(mode)]["description"],
            "trail": True,
            "key": f"S43|{mode}|{market}|{side}|{round(entry, d)}",
        })
    return out
