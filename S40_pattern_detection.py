#!/usr/bin/env python3
"""
S40 — Liquidity Sweep Detection (Live)
======================================
Alerts when a confirmed pivot high/low is swept with rejection.

Definition (no look-ahead)
--------------------------
1. Confirmed pivot (left/right bars)
2. Price trades beyond the pivot (liquidity taken)
3. Close back inside the pivot (rejection)
4. Quality: rejection wick ≥ min_wick_atr × ATR

Direction
---------
  +1 LONG bias  = swept a pivot LOW  (buyers absorbed sell-side liquidity)
  -1 SHORT bias = swept a pivot HIGH (sellers absorbed buy-side liquidity)

Usage
-----
  from S40_pattern_detection import detect_sweeps, detect_with_preset, PRESETS
  sigs = detect_with_preset(high, low, open_, close, times, preset="H4_STRONG")
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone


@dataclass
class SweepSignal:
    direction: int          # +1 long bias, -1 short bias
    bar: int
    level: float            # pivot that was swept
    extreme: float          # wick extreme of sweep candle
    entry: float            # close of sweep candle (reference)
    stop: float             # beyond extreme + buffer
    wick_atr: float
    body_atr: float
    range_atr: float
    is_rejection: bool
    strong: bool
    session: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = "LONG" if self.direction == 1 else "SHORT"
        return d


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
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


def find_pivots(high: np.ndarray, low: np.ndarray, left: int = 5, right: int = 5):
    """Pivot marked on confirmation bar (i+right) — no look-ahead."""
    n = len(high)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(left, n - right):
        window_h = high[i - left: i + right + 1]
        window_l = low[i - left: i + right + 1]
        if high[i] >= np.max(window_h) and np.sum(window_h == high[i]) == 1:
            ph[i + right] = high[i]
        if low[i] <= np.min(window_l) and np.sum(window_l == low[i]) == 1:
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
    lookback: int = 80,
    min_wick_atr: float = 0.30,
    min_range_atr: float = 0.0,
    sl_buffer_atr: float = 0.15,
    require_rejection: bool = True,
    require_strong: bool = True,
) -> List[SweepSignal]:
    """
    Detect liquidity sweeps with optional rejection + strength filters.
    Returns all historical sweeps on the series (caller takes the latest).
    """
    n = len(close)
    if n < left + right + 30:
        return []

    atr = compute_atr(high, low, close)
    ph, pl = find_pivots(high, low, left=left, right=right)

    sweeps: List[SweepSignal] = []
    last_ph, last_ph_bar = np.nan, -999
    last_pl, last_pl_bar = np.nan, -999

    for i in range(n):
        if not np.isnan(ph[i]):
            last_ph, last_ph_bar = ph[i], i
        if not np.isnan(pl[i]):
            last_pl, last_pl_bar = pl[i], i

        atr_i = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else max(high[i] - low[i], 1e-8)
        body = abs(close[i] - open_[i])
        crange = max(high[i] - low[i], 1e-8)

        sess = ""
        if times is not None and i < len(times):
            sess = _session(_hour_utc(times[i]))

        # High sweep → SHORT bias
        if not np.isnan(last_ph) and 0 < (i - last_ph_bar) <= lookback:
            if high[i] > last_ph:
                is_rej = close[i] < last_ph
                wick = high[i] - max(open_[i], close[i])
                wick_atr = wick / atr_i
                body_atr = body / atr_i
                range_atr = crange / atr_i
                strong = (wick_atr >= min_wick_atr) and (range_atr >= min_range_atr)
                keep = True
                if require_rejection and not is_rej:
                    keep = False
                if require_strong and not strong:
                    keep = False
                if keep:
                    extreme = float(high[i])
                    stop = extreme + sl_buffer_atr * atr_i
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
                    ))
                    last_ph = np.nan

        # Low sweep → LONG bias
        if not np.isnan(last_pl) and 0 < (i - last_pl_bar) <= lookback:
            if low[i] < last_pl:
                is_rej = close[i] > last_pl
                wick = min(open_[i], close[i]) - low[i]
                wick_atr = wick / atr_i
                body_atr = body / atr_i
                range_atr = crange / atr_i
                strong = (wick_atr >= min_wick_atr) and (range_atr >= min_range_atr)
                keep = True
                if require_rejection and not is_rej:
                    keep = False
                if require_strong and not strong:
                    keep = False
                if keep:
                    extreme = float(low[i])
                    stop = extreme - sl_buffer_atr * atr_i
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
                    ))
                    last_pl = np.nan

    return sweeps


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

PRESETS = {
    # H4 quality (research default ~0.30–0.40 wick)
    "H4_STRONG": dict(left=5, right=5, lookback=80, min_wick_atr=0.35, min_range_atr=0.50,
                      require_rejection=True, require_strong=True, sl_buffer_atr=0.15),
    "H4_BALANCED": dict(left=5, right=5, lookback=80, min_wick_atr=0.30, min_range_atr=0.0,
                        require_rejection=True, require_strong=True, sl_buffer_atr=0.15),
    "H4_SENSITIVE": dict(left=5, right=5, lookback=100, min_wick_atr=0.25, min_range_atr=0.0,
                         require_rejection=True, require_strong=True, sl_buffer_atr=0.15),
    # H1
    "H1_STRONG": dict(left=5, right=5, lookback=80, min_wick_atr=0.35, min_range_atr=0.50,
                      require_rejection=True, require_strong=True, sl_buffer_atr=0.15),
    "H1_BALANCED": dict(left=5, right=5, lookback=80, min_wick_atr=0.30, min_range_atr=0.0,
                        require_rejection=True, require_strong=True, sl_buffer_atr=0.15),
    # M30
    "M30_BALANCED": dict(left=5, right=5, lookback=60, min_wick_atr=0.30, min_range_atr=0.0,
                         require_rejection=True, require_strong=True, sl_buffer_atr=0.15),
}


def list_presets() -> List[str]:
    return sorted(PRESETS.keys())


def detect_with_preset(
    high, low, open_, close, times=None, preset: str = "H4_BALANCED"
) -> List[SweepSignal]:
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Available: {list_presets()}")
    return detect_sweeps(high, low, open_, close, times, **PRESETS[preset])


def get_latest_signal(signals: List[SweepSignal]) -> Optional[SweepSignal]:
    if not signals:
        return None
    return max(signals, key=lambda s: s.bar)


def format_alert(sig: SweepSignal, symbol: str = "", tf: str = "", preset: str = "") -> str:
    side = "LONG" if sig.direction == 1 else "SHORT"
    what = "LOW swept (bullish)" if sig.direction == 1 else "HIGH swept (bearish)"
    return (
        f"S40 SWEEP {side} {symbol} {tf} [{preset}]\n"
        f"{what}\n"
        f"Level: {sig.level:.5f}  Extreme: {sig.extreme:.5f}\n"
        f"Close: {sig.entry:.5f}  Stop ref: {sig.stop:.5f}\n"
        f"Wick: {sig.wick_atr:.2f} ATR  Strong: {sig.strong}  Sess: {sig.session}"
    )
