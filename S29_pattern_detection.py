#!/usr/bin/env python3
"""
S29 — Fibonacci Major Zone + Strong Rejection (High-WR Purified)
================================================================
Self-contained production detector.

Core logic (validated H4 / H1 / M30):
  1. Identify confirmed swing High → Low (or Low → High) range ≥ min_atr
  2. Define Major zone near the extreme (width 0.10–0.12 of range)
  3. Wait for price to retest the Major zone
  4. Require strong rejection (close outside zone + wick ratio)
  5. Optional next-bar confirmation
  6. Session + Volatility filters
  7. Entry mid-zone, SL beyond swing extreme
  8. Structural targets: mid (0.50) primary, opp_minor (~0.70) secondary

High-WR modes from final refinement (WR 55–66%, ExpR +2.1 to +2.8):
  - highWR_combo
  - wick45_confirm
  - wick40_confirm

Usage:
  from S29_pattern_detection import (
      detect_with_preset, get_latest_signal, format_alert,
      PRESETS, list_presets
  )
  signals = detect_with_preset(high, low, open_, close, times, preset="XAU_H1_wick45_confirm")
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple
from datetime import time as dtime


# ─────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────

@dataclass
class S29Signal:
    direction: int          # +1 long, -1 short
    entry_bar: int
    entry_price: float
    stop: float
    target: float           # primary (mid)
    target2: float          # secondary (opp_minor)
    risk: float
    rr_to_mid: float
    zone_type: str = "maj"
    session: str = ""
    vol_ok: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = "LONG" if self.direction == 1 else "SHORT"
        return d


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    atr = np.full(n, np.nan)
    if n < length:
        return atr
    atr[length-1] = np.mean(tr[:length])
    for i in range(length, n):
        atr[i] = (atr[i-1] * (length-1) + tr[i]) / length
    return atr


def find_swing_highs_lows(high: np.ndarray, low: np.ndarray, left: int = 5, right: int = 5):
    n = len(high)
    sh_idx, sl_idx = [], []
    for i in range(left, n - right):
        if high[i] >= np.max(high[i-left:i+right+1]):
            sh_idx.append(i)
        if low[i] <= np.min(low[i-left:i+right+1]):
            sl_idx.append(i)
    return np.array(sh_idx, dtype=int), np.array(sl_idx, dtype=int)


def in_session(ts, session: str) -> bool:
    """ts: pandas Timestamp, datetime, or unix float seconds (UTC)."""
    if session in ("ALL", "any", None):
        return True
    try:
        if hasattr(ts, "time") and callable(ts.time):
            t = ts.time()
        elif isinstance(ts, (int, float)):
            # unix seconds → UTC clock time
            from datetime import datetime, timezone
            t = datetime.fromtimestamp(float(ts), tz=timezone.utc).time()
        elif isinstance(ts, dtime):
            t = ts
        else:
            return True
    except Exception:
        return True
    if session == "overlap":
        return dtime(12, 0) <= t <= dtime(16, 0)
    if session == "london":
        return dtime(7, 0) <= t <= dtime(16, 0)
    if session == "ny":
        return dtime(12, 0) <= t <= dtime(21, 0)
    if session == "london_ny":
        return dtime(7, 0) <= t <= dtime(21, 0)
    return True


# ─────────────────────────────────────────────────────────────
# Core detector
# ─────────────────────────────────────────────────────────────

def detect_s29_signals(
    high: np.ndarray,
    low: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    times=None,
    *,
    pivot: int = 5,
    zone_width: float = 0.12,
    min_range_atr: float = 2.0,
    min_disp_atr: float = 1.2,
    wick_min: float = 0.40,
    close_strict: bool = True,
    confirm_next: bool = False,
    vol_min_pct: float = 0.40,
    session: str = "overlap",
    sl_buffer_atr: float = 0.08,
    max_hold: int = 80,
    max_poi_age: int = 110,
) -> List[S29Signal]:
    """
    Returns list of S29Signal (both long and short).
    Structural primary target = mid (0.50), secondary = opp_minor (~0.70).
    """
    n = len(close)
    if n < 100:
        return []

    atr = compute_atr(high, low, close)
    sh, sl = find_swing_highs_lows(high, low, left=pivot, right=pivot)

    # ATR percentile rank (simple rolling)
    atr_rank = np.full(n, 0.5)
    window = min(500, n)
    for i in range(window, n):
        past = atr[i-window:i+1]
        valid = past[~np.isnan(past)]
        if len(valid) > 10:
            atr_rank[i] = (valid <= atr[i]).mean()

    signals: List[S29Signal] = []
    used_highs = set()
    used_lows = set()

    # ── SHORTS: High → Low range, retest Major Sell zone ──
    for hi in sh:
        if hi in used_highs:
            continue
        later = sl[(sl > hi) & (sl < hi + 90)]
        if len(later) == 0:
            continue
        lo = later[np.argmin(low[later])]
        if np.isnan(atr[lo]) or atr[lo] <= 0:
            continue
        rng = high[hi] - low[lo]
        if rng / atr[lo] < min_range_atr or rng / atr[lo] < min_disp_atr:
            continue

        maj_top = high[hi]
        maj_bot = high[hi] - zone_width * rng
        mid_lvl = high[hi] - 0.50 * rng
        opp_min = high[hi] - 0.70 * rng

        start = lo + pivot + 1
        if start >= n:
            continue

        for e in range(start, min(start + max_poi_age, n)):
            # Touch major sell zone
            if not (low[e] <= maj_top and high[e] >= maj_bot):
                continue

            # Rejection quality
            cr = high[e] - low[e] + 1e-12
            uw = high[e] - max(open_[e], close[e])
            if close_strict and close[e] >= maj_bot:
                continue
            if uw / cr < wick_min:
                continue

            # Next-bar confirmation
            if confirm_next:
                if e + 1 >= n:
                    continue
                if close[e + 1] > close[e]:
                    continue

            # Filters
            if times is not None and not in_session(times[e], session):
                continue
            if atr_rank[e] < vol_min_pct:
                continue

            entry = (maj_top + maj_bot) / 2.0
            stop = high[hi] + sl_buffer_atr * (atr[e] if not np.isnan(atr[e]) else rng * 0.05)
            risk = stop - entry
            if risk <= 0:
                continue

            sig = S29Signal(
                direction=-1,
                entry_bar=e,
                entry_price=float(entry),
                stop=float(stop),
                target=float(mid_lvl),
                target2=float(opp_min),
                risk=float(risk),
                rr_to_mid=float((entry - mid_lvl) / risk),
                zone_type="maj_sell",
                session=session,
                vol_ok=True,
            )
            signals.append(sig)
            used_highs.add(hi)
            break

    # ── LONGS: Low → High range, retest Major Buy zone ──
    for lo in sl:
        if lo in used_lows:
            continue
        later = sh[(sh > lo) & (sh < lo + 90)]
        if len(later) == 0:
            continue
        hi = later[np.argmax(high[later])]
        if np.isnan(atr[hi]) or atr[hi] <= 0:
            continue
        rng = high[hi] - low[lo]
        if rng / atr[hi] < min_range_atr or rng / atr[hi] < min_disp_atr:
            continue

        maj_bot = low[lo]
        maj_top = low[lo] + zone_width * rng
        mid_lvl = low[lo] + 0.50 * rng
        opp_min = low[lo] + 0.70 * rng

        start = hi + pivot + 1
        if start >= n:
            continue

        for e in range(start, min(start + max_poi_age, n)):
            if not (high[e] >= maj_bot and low[e] <= maj_top):
                continue

            cr = high[e] - low[e] + 1e-12
            lw = min(open_[e], close[e]) - low[e]
            if close_strict and close[e] <= maj_top:
                continue
            if lw / cr < wick_min:
                continue

            if confirm_next:
                if e + 1 >= n:
                    continue
                if close[e + 1] < close[e]:
                    continue

            if times is not None and not in_session(times[e], session):
                continue
            if atr_rank[e] < vol_min_pct:
                continue

            entry = (maj_top + maj_bot) / 2.0
            stop = low[lo] - sl_buffer_atr * (atr[e] if not np.isnan(atr[e]) else rng * 0.05)
            risk = entry - stop
            if risk <= 0:
                continue

            sig = S29Signal(
                direction=1,
                entry_bar=e,
                entry_price=float(entry),
                stop=float(stop),
                target=float(mid_lvl),
                target2=float(opp_min),
                risk=float(risk),
                rr_to_mid=float((mid_lvl - entry) / risk),
                zone_type="maj_buy",
                session=session,
                vol_ok=True,
            )
            signals.append(sig)
            used_lows.add(lo)
            break

    return signals


# ─────────────────────────────────────────────────────────────
# PRESETS — High-WR refined modes from final research
# ─────────────────────────────────────────────────────────────

PRESETS: Dict[str, dict] = {
    # ── XAUUSD H1 (strongest high-WR cluster) ──
    "XAU_H1_wick45_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "XAU_H1_wick40_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.40, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "XAU_H1_highWR_combo": dict(
        pivot=5, zone_width=0.10, min_range_atr=2.0, min_disp_atr=1.4,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.50, session="overlap", sl_buffer_atr=0.08,
    ),

    # ── USDJPY H4 ──
    "JPY_H4_wick45_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "JPY_H4_wick40_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.40, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "JPY_H4_highWR_combo": dict(
        pivot=5, zone_width=0.10, min_range_atr=2.0, min_disp_atr=1.4,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.50, session="overlap", sl_buffer_atr=0.08,
    ),

    # ── XAUUSD H4 ──
    "XAU_H4_highWR_combo": dict(
        pivot=5, zone_width=0.10, min_range_atr=2.0, min_disp_atr=1.4,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.50, session="overlap", sl_buffer_atr=0.08,
    ),
    "XAU_H4_wick45_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),

    # ── XAUUSD M30 ──
    "XAU_M30_highWR_combo": dict(
        pivot=5, zone_width=0.10, min_range_atr=2.0, min_disp_atr=1.4,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.50, session="overlap", sl_buffer_atr=0.08,
    ),
    "XAU_M30_wick40_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.40, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "XAU_M30_wick45_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),

    # ── EURUSD / GBPUSD H1 & H4 ──
    "EUR_H1_wick40_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.40, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "EUR_H1_wick45_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "GBP_H4_wick45_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),


    # ── USDJPY H1 ──
    "JPY_H1_wick45_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "JPY_H1_wick40_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.40, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "JPY_H1_highWR_combo": dict(
        pivot=5, zone_width=0.10, min_range_atr=2.0, min_disp_atr=1.4,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.50, session="overlap", sl_buffer_atr=0.08,
    ),
    # ── Generic high-WR templates ──
    "GEN_wick45_confirm": dict(
        pivot=5, zone_width=0.12, min_range_atr=2.0, min_disp_atr=1.2,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.40, session="overlap", sl_buffer_atr=0.08,
    ),
    "GEN_highWR_combo": dict(
        pivot=5, zone_width=0.10, min_range_atr=2.0, min_disp_atr=1.4,
        wick_min=0.45, close_strict=True, confirm_next=True,
        vol_min_pct=0.50, session="overlap", sl_buffer_atr=0.08,
    ),
}


# Research performance snapshot (for reference / documentation)
RESEARCH_STATS = {
    "XAU_H1_wick45_confirm":  {"n": 477, "wr": 0.660, "expR": 2.677, "pf": 8.88, "dd": 7.0},
    "XAU_H1_wick40_confirm":  {"n": 563, "wr": 0.652, "expR": 2.621, "pf": 8.53, "dd": 6.0},
    "XAU_H1_highWR_combo":    {"n": 411, "wr": 0.603, "expR": 2.789, "pf": 8.03, "dd": 10.0},
    "JPY_H4_wick45_confirm":  {"n": 134, "wr": 0.619, "expR": 2.643, "pf": 7.94, "dd": 8.0},
    "JPY_H4_wick40_confirm":  {"n": 149, "wr": 0.611, "expR": 2.567, "pf": 7.59, "dd": 5.0},
    "JPY_H4_highWR_combo":    {"n": 109, "wr": 0.569, "expR": 2.765, "pf": 7.41, "dd": 6.0},
    "XAU_H4_highWR_combo":    {"n": 94,  "wr": 0.553, "expR": 2.640, "pf": 6.91, "dd": 8.0},
    "XAU_M30_highWR_combo":   {"n": 454, "wr": 0.581, "expR": 2.449, "pf": 6.85, "dd": 7.0},
    "XAU_M30_wick40_confirm": {"n": 608, "wr": 0.623, "expR": 2.321, "pf": 7.16, "dd": 8.0},
    "XAU_M30_wick45_confirm": {"n": 509, "wr": 0.619, "expR": 2.282, "pf": 6.99, "dd": 7.0},
    "EUR_H1_wick40_confirm":  {"n": 524, "wr": 0.618, "expR": 2.192, "pf": 6.74, "dd": 8.0},
    "EUR_H1_wick45_confirm":  {"n": 442, "wr": 0.606, "expR": 2.108, "pf": 6.36, "dd": 7.0},
    "GBP_H4_wick45_confirm":  {"n": 150, "wr": 0.580, "expR": 2.392, "pf": 6.69, "dd": 7.0},
    "JPY_H1_wick45_confirm":  {"n": 388, "wr": 0.608, "expR": 2.120, "pf": 6.41, "dd": 7.0},
    "JPY_H1_wick40_confirm":  {"n": 468, "wr": 0.605, "expR": 2.112, "pf": 6.34, "dd": 7.0},
}


def list_presets() -> List[str]:
    return sorted(PRESETS.keys())


def detect_with_preset(
    high, low, open_, close, times=None, preset: str = "GEN_wick45_confirm"
) -> List[S29Signal]:
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Available: {list_presets()}")
    params = PRESETS[preset].copy()
    return detect_s29_signals(high, low, open_, close, times, **params)


def get_latest_signal(signals: List[S29Signal]) -> Optional[S29Signal]:
    if not signals:
        return None
    return max(signals, key=lambda s: s.entry_bar)


def format_alert(sig: S29Signal, symbol: str = "", tf: str = "", preset: str = "") -> str:
    side = "LONG" if sig.direction == 1 else "SHORT"
    return (
        f"S29 {side} {symbol} {tf} [{preset}]\n"
        f"Entry: {sig.entry_price:.5f}  SL: {sig.stop:.5f}\n"
        f"TP1 (mid): {sig.target:.5f}  TP2 (opp_minor): {sig.target2:.5f}\n"
        f"Risk: {sig.risk:.5f}  RR→mid: {sig.rr_to_mid:.2f}"
    )


# ─────────────────────────────────────────────────────────────
# Convenience: run on DataFrame
# ─────────────────────────────────────────────────────────────

def detect_df(df, preset: str = "GEN_wick45_confirm"):
    """df must have Open, High, Low, Close columns and DatetimeIndex or 'Time'."""
    import pandas as pd
    if not isinstance(df.index, pd.DatetimeIndex):
        if "Time" in df.columns:
            df = df.set_index("Time")
    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    open_ = df["Open"].values.astype(float)
    close = df["Close"].values.astype(float)
    times = df.index
    return detect_with_preset(high, low, open_, close, times, preset=preset)


if __name__ == "__main__":
    print("S29 Pattern Detection – High-WR Fib Major Zone")
    print("Available presets:")
    for p in list_presets():
        stats = RESEARCH_STATS.get(p, {})
        if stats:
            print(f"  {p:30s}  N={stats['n']:4d}  WR={stats['wr']*100:5.1f}%  ExpR={stats['expR']:+.3f}")
        else:
            print(f"  {p}")
