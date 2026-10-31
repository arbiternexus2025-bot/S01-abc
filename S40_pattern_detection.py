#!/usr/bin/env python3
"""
S40 — Liquidity Sweep Detection v2 (Live / Production)
======================================================
Upgraded from Edge Lab research (S25 / S40 / S40b):

  • Confirmed pivots only (no look-ahead)
  • Must trade BEYOND pivot (liquidity taken)
  • Must CLOSE back inside pivot (rejection)
  • Rejection wick ≥ min ATR multiple
  • Sweep candle range quality filter
  • Close preference: reject side of level (strict)
  • Optional: body not dominating the rejection wick
  • Freshness is enforced by the live runner (bars_ago)

Direction
---------
  +1 LONG  = swept a pivot LOW
  -1 SHORT = swept a pivot HIGH

Presets
-------
  H4_STRONG / H1_STRONG     — production defaults (wick ≥ 0.35 ATR)
  H4_BALANCED / H1_BALANCED — slightly more frequent (wick ≥ 0.30 ATR)
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


@dataclass
class SweepSignal:
    direction: int
    bar: int
    level: float
    extreme: float
    entry: float
    stop: float
    wick_atr: float
    body_atr: float
    range_atr: float
    is_rejection: bool
    strong: bool
    session: str = ""
    pivot_age: int = 0          # bars from pivot confirm → sweep
    quality: float = 0.0        # composite score for ranking

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = "LONG" if self.direction == 1 else "SHORT"
        return d


def compute_atr(high, low, close, length: int = 14) -> np.ndarray:
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


def find_pivots(high, low, left: int = 5, right: int = 5):
    """Pivot value written on confirmation bar (i+right) — no look-ahead."""
    n = len(high)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(left, n - right):
        wh = high[i - left: i + right + 1]
        wl = low[i - left: i + right + 1]
        if high[i] >= np.max(wh) and np.sum(wh == high[i]) == 1:
            ph[i + right] = high[i]
        if low[i] <= np.min(wl) and np.sum(wl == low[i]) == 1:
            pl[i + right] = low[i]
    return ph, pl


def _hour_utc(ts) -> int:
    try:
        if hasattr(ts, "hour"):
            return int(ts.hour)
        if isinstance(ts, (int, float)) and float(ts) > 1e9:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc).hour
        return int(str(ts)[11:13])
    except Exception:
        return -1


def _session(hour: int) -> str:
    if 7 <= hour < 12:
        return "London"
    if 12 <= hour < 16:
        return "Overlap"
    if 16 <= hour < 21:
        return "NY"
    return "Asia"


def detect_sweeps(
    high: np.ndarray,
    low: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    times=None,
    *,
    left: int = 5,
    right: int = 5,
    lookback: int = 60,
    min_wick_atr: float = 0.35,
    min_range_atr: float = 0.40,
    max_body_to_wick: float = 2.5,   # reject if body >> wick (not a rejection candle)
    min_penetrate_atr: float = 0.05, # must actually break the level by a bit
    sl_buffer_atr: float = 0.15,
    require_rejection: bool = True,
    require_strong: bool = True,
) -> List[SweepSignal]:
    """
    Detect liquidity sweeps with rejection + quality filters.
    Each pivot is consumed on first valid sweep (no double-count).
    """
    n = len(close)
    if n < left + right + 40:
        return []

    atr = compute_atr(high, low, close)
    ph, pl = find_pivots(high, low, left=left, right=right)

    sweeps: List[SweepSignal] = []
    last_ph, last_ph_bar = np.nan, -999
    last_pl, last_pl_bar = np.nan, -999
    # Track levels already alerted in this series (anti-dupe inside detector)
    used_levels: set = set()

    for i in range(n):
        if not np.isnan(ph[i]):
            last_ph, last_ph_bar = float(ph[i]), i
        if not np.isnan(pl[i]):
            last_pl, last_pl_bar = float(pl[i]), i

        atr_i = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else max(high[i] - low[i], 1e-8)
        body = abs(close[i] - open_[i])
        crange = max(high[i] - low[i], 1e-8)
        sess = ""
        if times is not None and i < len(times):
            sess = _session(_hour_utc(times[i]))

        # ── HIGH sweep → SHORT bias ──
        if not np.isnan(last_ph) and 0 < (i - last_ph_bar) <= lookback:
            penetrate = high[i] - last_ph
            if penetrate > min_penetrate_atr * atr_i:
                is_rej = close[i] < last_ph
                wick = high[i] - max(open_[i], close[i])
                wick_atr = wick / atr_i
                body_atr = body / atr_i
                range_atr = crange / atr_i
                body_ok = (wick > 1e-12) and (body / wick <= max_body_to_wick)
                strong = (wick_atr >= min_wick_atr) and (range_atr >= min_range_atr) and body_ok

                keep = True
                if require_rejection and not is_rej:
                    keep = False
                if require_strong and not strong:
                    keep = False

                lvl_key = ("H", round(last_ph, 5))
                if keep and lvl_key not in used_levels:
                    extreme = float(high[i])
                    stop = extreme + sl_buffer_atr * atr_i
                    # Quality: wick strength + penetration + how clean the close is
                    close_depth = (last_ph - close[i]) / atr_i if is_rej else 0.0
                    quality = wick_atr + 0.5 * min(penetrate / atr_i, 1.0) + 0.3 * max(close_depth, 0)
                    sweeps.append(SweepSignal(
                        direction=-1,
                        bar=i,
                        level=float(last_ph),
                        extreme=extreme,
                        entry=float(close[i]),
                        stop=float(stop),
                        wick_atr=float(wick_atr),
                        body_atr=float(body_atr),
                        range_atr=float(range_atr),
                        is_rejection=bool(is_rej),
                        strong=bool(strong),
                        session=sess,
                        pivot_age=int(i - last_ph_bar),
                        quality=float(quality),
                    ))
                    used_levels.add(lvl_key)
                    last_ph = np.nan

        # ── LOW sweep → LONG bias ──
        if not np.isnan(last_pl) and 0 < (i - last_pl_bar) <= lookback:
            penetrate = last_pl - low[i]
            if penetrate > min_penetrate_atr * atr_i:
                is_rej = close[i] > last_pl
                wick = min(open_[i], close[i]) - low[i]
                wick_atr = wick / atr_i
                body_atr = body / atr_i
                range_atr = crange / atr_i
                body_ok = (wick > 1e-12) and (body / wick <= max_body_to_wick)
                strong = (wick_atr >= min_wick_atr) and (range_atr >= min_range_atr) and body_ok

                keep = True
                if require_rejection and not is_rej:
                    keep = False
                if require_strong and not strong:
                    keep = False

                lvl_key = ("L", round(last_pl, 5))
                if keep and lvl_key not in used_levels:
                    extreme = float(low[i])
                    stop = extreme - sl_buffer_atr * atr_i
                    close_depth = (close[i] - last_pl) / atr_i if is_rej else 0.0
                    quality = wick_atr + 0.5 * min(penetrate / atr_i, 1.0) + 0.3 * max(close_depth, 0)
                    sweeps.append(SweepSignal(
                        direction=1,
                        bar=i,
                        level=float(last_pl),
                        extreme=extreme,
                        entry=float(close[i]),
                        stop=float(stop),
                        wick_atr=float(wick_atr),
                        body_atr=float(body_atr),
                        range_atr=float(range_atr),
                        is_rejection=bool(is_rej),
                        strong=bool(strong),
                        session=sess,
                        pivot_age=int(i - last_pl_bar),
                        quality=float(quality),
                    ))
                    used_levels.add(lvl_key)
                    last_pl = np.nan

    return sweeps


PRESETS = {
    "H4_STRONG": dict(
        left=5, right=5, lookback=60,
        min_wick_atr=0.35, min_range_atr=0.45, max_body_to_wick=2.0,
        min_penetrate_atr=0.05, require_rejection=True, require_strong=True,
        sl_buffer_atr=0.15,
    ),
    "H1_STRONG": dict(
        left=5, right=5, lookback=50,
        min_wick_atr=0.35, min_range_atr=0.40, max_body_to_wick=2.0,
        min_penetrate_atr=0.05, require_rejection=True, require_strong=True,
        sl_buffer_atr=0.15,
    ),
    "H4_BALANCED": dict(
        left=5, right=5, lookback=70,
        min_wick_atr=0.30, min_range_atr=0.35, max_body_to_wick=2.5,
        min_penetrate_atr=0.03, require_rejection=True, require_strong=True,
        sl_buffer_atr=0.15,
    ),
    "H1_BALANCED": dict(
        left=5, right=5, lookback=60,
        min_wick_atr=0.30, min_range_atr=0.30, max_body_to_wick=2.5,
        min_penetrate_atr=0.03, require_rejection=True, require_strong=True,
        sl_buffer_atr=0.15,
    ),
}


def list_presets():
    return sorted(PRESETS.keys())


def detect_with_preset(high, low, open_, close, times=None, preset: str = "H4_STRONG"):
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Available: {list_presets()}")
    return detect_sweeps(high, low, open_, close, times, **PRESETS[preset])


def get_latest_signal(signals: List[SweepSignal]) -> Optional[SweepSignal]:
    if not signals:
        return None
    # Prefer highest quality among the most recent bar cluster
    latest_bar = max(s.bar for s in signals)
    recent = [s for s in signals if s.bar >= latest_bar - 0]
    return max(recent, key=lambda s: (s.bar, s.quality))
