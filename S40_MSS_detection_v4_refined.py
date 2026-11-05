#!/usr/bin/env python3
"""
S40-MSS v4 Refined — Live Liquidity Sweep + Market Structure Shift
=================================================================
Research core from S40_MSS_detection_v4_refined.py adapted for live OHLC arrays.

Sequence (no look-ahead)
------------------------
1. HTF key level (confirmed pivot zone)
2. Price sweeps into that level with strong rejection
3. Price builds a meaningful swing structure
4. MSS: price breaks that swing → setup complete

Direction
---------
  LONG  = support swept + bullish MSS
  SHORT = resistance swept + bearish MSS
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


def compute_atr(high, low, close, length=14):
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n < length:
        return atr
    atr[length - 1] = np.mean(tr[:length])
    for i in range(length, n):
        atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr


def find_pivots(high, low, left=5, right=5):
    n = len(high)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(left, n - right):
        wh = high[i - left:i + right + 1]
        wl = low[i - left:i + right + 1]
        if high[i] >= np.max(wh) and np.sum(wh == high[i]) == 1:
            ph[i + right] = high[i]
        if low[i] <= np.min(wl) and np.sum(wl == low[i]) == 1:
            pl[i + right] = low[i]
    return ph, pl


@dataclass
class SweepMSSEvent:
    bar: int
    direction: int
    sweep_bar: int
    htf_level: float
    htf_zone_low: float
    htf_zone_high: float
    sweep_extreme: float
    mss_level: float
    entry: float
    stop: float
    wick_atr: float
    range_atr: float
    structure_atr: float
    bars_sweep_to_mss: int
    quality: float
    strong: bool = True
    session: str = ""
    symbol: str = ""
    tf: str = ""
    htf: str = ""

    def to_dict(self):
        d = asdict(self)
        d["side"] = "LONG" if self.direction == 1 else "SHORT"
        return d


def _to_df(high, low, open_, close, times):
    """Build a minimal DataFrame for the research detect path."""
    n = len(close)
    if times is None:
        # synthetic hourly timestamps ending "now"
        now = datetime.now(timezone.utc).timestamp()
        times = np.array([now - (n - 1 - i) * 3600 for i in range(n)])
    tlist = []
    for t in times:
        if hasattr(t, "to_pydatetime"):
            tlist.append(pd.Timestamp(t))
        elif isinstance(t, (int, float)) and float(t) > 1e9:
            tlist.append(pd.Timestamp(datetime.fromtimestamp(float(t), tz=timezone.utc)))
        else:
            try:
                tlist.append(pd.Timestamp(t))
            except Exception:
                tlist.append(pd.Timestamp(datetime.now(timezone.utc)))
    return pd.DataFrame({
        "Time": tlist,
        "Open": np.asarray(open_, dtype=float),
        "High": np.asarray(high, dtype=float),
        "Low": np.asarray(low, dtype=float),
        "Close": np.asarray(close, dtype=float),
    })


def build_htf_levels(df_htf, left=5, right=5, zone_mult=0.28):
    high = df_htf["High"].values
    low = df_htf["Low"].values
    close = df_htf["Close"].values
    times = df_htf["Time"].values
    atr = compute_atr(high, low, close)
    ph, pl = find_pivots(high, low, left, right)
    levels = []
    for i in range(len(df_htf)):
        a = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else max(high[i] - low[i], 1e-8)
        if not np.isnan(pl[i]):
            lvl = float(pl[i])
            half = zone_mult * a
            levels.append({
                "time": pd.Timestamp(times[i]),
                "level": lvl,
                "dir": 1,
                "zlow": lvl - half,
                "zhigh": lvl + half * 0.45,
                "used": False,
            })
        if not np.isnan(ph[i]):
            lvl = float(ph[i])
            half = zone_mult * a
            levels.append({
                "time": pd.Timestamp(times[i]),
                "level": lvl,
                "dir": -1,
                "zlow": lvl - half * 0.45,
                "zhigh": lvl + half,
                "used": False,
            })
    return levels


def detect(
    df, htf_levels, left=3, right=3,
    min_wick=0.34, min_range=0.42, min_struct=0.60,
    max_bars=32, min_after=3, max_age_hours=220,
    require_directional_mss=True,
    symbol="", tf="", htf="",
    sl_buffer_atr=0.15,
):
    n = len(df)
    if n < 120 or not htf_levels:
        return []

    high = df["High"].values
    low = df["Low"].values
    open_ = df["Open"].values
    close = df["Close"].values
    times = df["Time"].values
    atr = compute_atr(high, low, close)
    ph, pl = find_pivots(high, low, left, right)

    htf_levels = sorted(htf_levels, key=lambda x: x["time"])
    htf_t = [x["time"] for x in htf_levels]

    events = []
    long_c = []
    short_c = []
    htf_ptr = 0

    for i in range(n):
        t_i = pd.Timestamp(times[i])
        a_i = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else max(high[i] - low[i], 1e-8)
        crange = max(high[i] - low[i], 1e-8)
        body = abs(close[i] - open_[i])
        body_atr = body / a_i

        while htf_ptr < len(htf_levels) and htf_t[htf_ptr] < t_i:
            htf_ptr += 1

        active = []
        for j in range(max(0, htf_ptr - 18), htf_ptr):
            if htf_levels[j].get("used"):
                continue
            age_h = (t_i - htf_t[j]).total_seconds() / 3600.0
            if age_h <= max_age_hours:
                active.append(htf_levels[j])

        # Bullish sweep into HTF support
        for kl in active:
            if kl["dir"] != 1:
                continue
            if low[i] > kl["zhigh"]:
                continue
            if low[i] > kl["level"] + 0.04 * a_i:
                continue
            is_rej = close[i] > kl["level"]
            wick = min(open_[i], close[i]) - low[i]
            wa = wick / a_i
            ra = crange / a_i
            if is_rej and wa >= min_wick and ra >= min_range:
                long_c.append({
                    "sb": i, "st": t_i, "hl": kl["level"],
                    "zl": kl["zlow"], "zh": kl["zhigh"],
                    "ext": float(low[i]), "wa": float(wa), "ra": float(ra),
                    "sh": None, "shb": None, "sa": 0.0, "kl_ref": kl,
                })
                break

        # Bearish sweep into HTF resistance
        for kl in active:
            if kl["dir"] != -1:
                continue
            if high[i] < kl["zlow"]:
                continue
            if high[i] < kl["level"] - 0.04 * a_i:
                continue
            is_rej = close[i] < kl["level"]
            wick = high[i] - max(open_[i], close[i])
            wa = wick / a_i
            ra = crange / a_i
            if is_rej and wa >= min_wick and ra >= min_range:
                short_c.append({
                    "sb": i, "st": t_i, "hl": kl["level"],
                    "zl": kl["zlow"], "zh": kl["zhigh"],
                    "ext": float(high[i]), "wa": float(wa), "ra": float(ra),
                    "sl": None, "slb": None, "sa": 0.0, "kl_ref": kl,
                })
                break

        # Post-sweep structure
        if not np.isnan(ph[i]):
            for c in long_c:
                if c["sh"] is None and i >= c["sb"] + min_after:
                    sa = (float(ph[i]) - c["ext"]) / a_i
                    if sa >= min_struct:
                        c["sh"] = float(ph[i])
                        c["shb"] = i
                        c["sa"] = float(sa)

        if not np.isnan(pl[i]):
            for c in short_c:
                if c["sl"] is None and i >= c["sb"] + min_after:
                    sa = (c["ext"] - float(pl[i])) / a_i
                    if sa >= min_struct:
                        c["sl"] = float(pl[i])
                        c["slb"] = i
                        c["sa"] = float(sa)

        # MSS break
        keep_l = []
        for c in long_c:
            age = i - c["sb"]
            if age > max_bars:
                continue
            if c["sh"] is None:
                keep_l.append(c)
                continue
            broken = close[i] > c["sh"] and i > c["shb"]
            if broken:
                q = (min(c["wa"] / 0.55, 2.0) * 0.38 +
                     min(c["ra"] / 0.90, 1.6) * 0.22 +
                     min(c["sa"] / 1.1, 1.9) * 0.40)
                if close[i] > open_[i] and body_atr >= 0.25:
                    q += 0.12
                strong = (c["wa"] >= 0.40 and c["ra"] >= 0.48 and c["sa"] >= 0.70 and q >= 1.15)
                stop = c["ext"] - sl_buffer_atr * a_i
                events.append(SweepMSSEvent(
                    bar=i, direction=1, sweep_bar=c["sb"],
                    htf_level=c["hl"], htf_zone_low=c["zl"], htf_zone_high=c["zh"],
                    sweep_extreme=c["ext"], mss_level=c["sh"],
                    entry=float(close[i]), stop=float(stop),
                    wick_atr=c["wa"], range_atr=c["ra"], structure_atr=c["sa"],
                    bars_sweep_to_mss=age, quality=float(q), strong=strong,
                    symbol=symbol, tf=tf, htf=htf,
                ))
                if "kl_ref" in c:
                    c["kl_ref"]["used"] = True
            else:
                keep_l.append(c)
        long_c = keep_l

        keep_s = []
        for c in short_c:
            age = i - c["sb"]
            if age > max_bars:
                continue
            if c["sl"] is None:
                keep_s.append(c)
                continue
            broken = close[i] < c["sl"] and i > c["slb"]
            if broken:
                q = (min(c["wa"] / 0.55, 2.0) * 0.38 +
                     min(c["ra"] / 0.90, 1.6) * 0.22 +
                     min(c["sa"] / 1.1, 1.9) * 0.40)
                if close[i] < open_[i] and body_atr >= 0.25:
                    q += 0.12
                strong = (c["wa"] >= 0.40 and c["ra"] >= 0.48 and c["sa"] >= 0.70 and q >= 1.15)
                stop = c["ext"] + sl_buffer_atr * a_i
                events.append(SweepMSSEvent(
                    bar=i, direction=-1, sweep_bar=c["sb"],
                    htf_level=c["hl"], htf_zone_low=c["zl"], htf_zone_high=c["zh"],
                    sweep_extreme=c["ext"], mss_level=c["sl"],
                    entry=float(close[i]), stop=float(stop),
                    wick_atr=c["wa"], range_atr=c["ra"], structure_atr=c["sa"],
                    bars_sweep_to_mss=age, quality=float(q), strong=strong,
                    symbol=symbol, tf=tf, htf=htf,
                ))
                if "kl_ref" in c:
                    c["kl_ref"]["used"] = True
            else:
                keep_s.append(c)
        short_c = keep_s

    return events


HTF_MAP = {"H4": "H4", "H1": "H4", "M30": "H4", "M15": "H1", "M5": "H1"}

PARAMS = {
    "H4":  dict(left=5, right=5, max_bars=26, min_wick=0.36, min_range=0.45, min_struct=0.65, max_age_hours=160),
    "H1":  dict(left=4, right=4, max_bars=32, min_wick=0.34, min_range=0.42, min_struct=0.60, max_age_hours=200),
    "M30": dict(left=3, right=3, max_bars=38, min_wick=0.34, min_range=0.42, min_struct=0.58, max_age_hours=240),
    "M15": dict(left=3, right=3, max_bars=45, min_wick=0.32, min_range=0.40, min_struct=0.55, max_age_hours=280),
    "M5":  dict(left=3, right=3, max_bars=55, min_wick=0.32, min_range=0.40, min_struct=0.52, max_age_hours=320),
}


def detect_live(
    ltf_ohlc: dict,
    htf_ohlc: dict,
    *,
    symbol: str,
    tf: str,
    strong_only: bool = True,
) -> List[SweepMSSEvent]:
    """
    Live entry point.
    ltf_ohlc / htf_ohlc: dicts with open, high, low, close, time arrays.
    """
    htf = HTF_MAP.get(tf, "H4")
    p = PARAMS.get(tf, PARAMS["H1"]).copy()

    df_htf = _to_df(
        htf_ohlc["high"], htf_ohlc["low"], htf_ohlc["open"], htf_ohlc["close"],
        htf_ohlc.get("time"),
    )
    df_ltf = _to_df(
        ltf_ohlc["high"], ltf_ohlc["low"], ltf_ohlc["open"], ltf_ohlc["close"],
        ltf_ohlc.get("time"),
    )
    if len(df_htf) < 80 or len(df_ltf) < 120:
        return []

    levels = build_htf_levels(df_htf, left=5, right=5, zone_mult=0.28)
    if not levels:
        return []

    events = detect(
        df_ltf, levels,
        left=p["left"], right=p["right"],
        min_wick=p["min_wick"], min_range=p["min_range"], min_struct=p["min_struct"],
        max_bars=p["max_bars"], max_age_hours=p["max_age_hours"],
        symbol=symbol, tf=tf, htf=htf,
    )
    if strong_only:
        events = [e for e in events if e.strong]
    return events
