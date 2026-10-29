#!/usr/bin/env python3
"""
S35 — Hybrid Fib Deep Sniper Detection
======================================
Rank-1 and Rank-2 live deployment candidates from the S34/S35 research cycle.

RANK 1 (Primary – A / A+)
-------------------------
Market      : USDJPY
Timeframe   : M1
Fib zone    : 0.618 – 0.886 (Deep OTE / Sniper)
Impulse     : AB ≥ 1.60 ATR
Entry       : Close of C confirmation bar
SL          : Beyond C ± 0.15 ATR
TP          : Fixed 3.0R
Session     : NY + Overlap only
Metrics     : WR 49.5% | ExpR +0.541 | PF 2.03 | MaxDD 9.0R | OOS +0.596 | cost2x +0.421

RANK 2 (Secondary – A)
----------------------
Same rules as Rank 1, only TP = Fixed 2.5R
Metrics     : WR 51.7% | ExpR +0.497 | PF 1.99 | MaxDD 10.0R | OOS +0.538 | cost2x +0.377

Both ranks share identical entry logic. When mode="BOTH" the detector emits
a single signal per setup (no duplicates) and attaches both targets.

Author      : Edge Lab Research
Date        : 2026-10-29
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Pivot:
    bar: int
    price: float
    ptype: int          # +1 = swing high, -1 = swing low


@dataclass
class FibSignal:
    """
    One clean signal. When both ranks fire, only one object is created
    and target_r25 / target_r30 are both populated.
    """
    direction: int              # +1 long, -1 short
    entry_bar: int
    entry_price: float
    stop: float
    risk: float

    # Rank-specific targets (None if that rank is not requested)
    target_r25: Optional[float] = None   # Rank 2 (2.5R)
    target_r30: Optional[float] = None   # Rank 1 (3.0R)

    # Context
    a_bar: int = 0
    a_price: float = 0.0
    b_bar: int = 0
    b_price: float = 0.0
    c_bar: int = 0
    c_price: float = 0.0
    ab_size: float = 0.0
    retrace: float = 0.0
    session: str = ""
    mode: str = ""              # "RANK1", "RANK2", or "BOTH"
    grade: str = ""

    def primary_target(self) -> float:
        """Prefer Rank-1 target when both are present."""
        if self.target_r30 is not None:
            return self.target_r30
        return self.target_r25


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                length: int = 14) -> np.ndarray:
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n < length:
        return atr
    atr[length - 1] = np.mean(tr[:length])
    for i in range(length, n):
        atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr


def detect_pivots(high: np.ndarray, low: np.ndarray,
                  left: int = 4, right: int = 2,
                  alternate: bool = True) -> List[Pivot]:
    """
    Hybrid confirmed pivots (left=4, right=2) – the setting that produced
    the strongest results on M1 USDJPY.
    """
    n = len(high)
    pivots: List[Pivot] = []
    for i in range(left, n - right):
        is_high = all(high[i] > high[i - j] for j in range(1, left + 1)) and \
                  all(high[i] >= high[i + j] for j in range(1, right + 1))
        is_low  = all(low[i]  < low[i - j]  for j in range(1, left + 1)) and \
                  all(low[i]  <= low[i + j]  for j in range(1, right + 1))

        if is_high:
            if alternate and pivots and pivots[-1].ptype == 1:
                if high[i] > pivots[-1].price:
                    pivots[-1] = Pivot(i, high[i], 1)
            else:
                pivots.append(Pivot(i, high[i], 1))
        elif is_low:
            if alternate and pivots and pivots[-1].ptype == -1:
                if low[i] < pivots[-1].price:
                    pivots[-1] = Pivot(i, low[i], -1)
            else:
                pivots.append(Pivot(i, low[i], -1))
    return pivots


def get_session(hour: int) -> str:
    if 7 <= hour < 12:
        return "London"
    if 12 <= hour < 16:
        return "Overlap"
    if 16 <= hour < 21:
        return "NY"
    return "Asia"


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

def detect_hybrid_fib_deep(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    open_: np.ndarray,
    times: np.ndarray,
    atr: Optional[np.ndarray] = None,
    *,
    # Rank control
    mode: str = "BOTH",                 # "RANK1" | "RANK2" | "BOTH"
    # Core parameters (locked from research)
    pivot_left: int = 4,
    pivot_right: int = 2,
    min_impulse_atr: float = 1.60,
    fib_min: float = 0.618,             # Deep zone
    fib_max: float = 0.886,
    sl_buffer_atr: float = 0.15,
    sessions: Optional[List[str]] = None,
    # Safety
    min_bars_between: int = 3,
) -> List[FibSignal]:
    """
    Detect Hybrid Fib Deep Sniper signals for Rank-1 and/or Rank-2.

    Parameters
    ----------
    mode : str
        "RANK1"  → only 3.0R targets (highest ExpR / PF)
        "RANK2"  → only 2.5R targets (slightly higher WR)
        "BOTH"   → emit one signal per setup with both targets attached
                   (no duplicate entries)

    Returns
    -------
    List[FibSignal]
        Clean list of non-duplicated signals.
    """
    if sessions is None:
        sessions = ["NY", "Overlap"]

    mode = mode.upper()
    if mode not in ("RANK1", "RANK2", "BOTH"):
        raise ValueError("mode must be 'RANK1', 'RANK2' or 'BOTH'")

    if atr is None:
        atr = compute_atr(high, low, close)

    pivots = detect_pivots(high, low, left=pivot_left, right=pivot_right, alternate=True)
    signals: List[FibSignal] = []
    n = len(close)
    last_entry = -100

    i = 0
    while i < len(pivots) - 2:
        a, b, c = pivots[i], pivots[i + 1], pivots[i + 2]
        conf = c.bar + pivot_right
        if conf >= n or np.isnan(atr[conf]):
            i += 1
            continue

        # Session filter (supports datetime, pandas, or unix float seconds UTC)
        try:
            ts = times[conf]
            if hasattr(ts, "hour"):
                hr = int(ts.hour)
            elif isinstance(ts, (int, float)) and float(ts) > 1e9:
                from datetime import datetime, timezone
                hr = datetime.fromtimestamp(float(ts), tz=timezone.utc).hour
            else:
                hr = int(str(ts)[11:13])
            sess = get_session(hr)
        except Exception:
            sess = "Unknown"
        if sess not in sessions:
            i += 1
            continue

        # ----- SHORT setup (H-L-H) -----
        if a.ptype == 1 and b.ptype == -1 and c.ptype == 1:
            ab = a.price - b.price
            if ab <= 0 or ab < min_impulse_atr * atr[conf]:
                i += 1
                continue
            retr = (c.price - b.price) / ab
            if not (fib_min <= retr <= fib_max):
                i += 1
                continue

            if conf - last_entry >= min_bars_between:
                entry = close[conf]
                stop = c.price + sl_buffer_atr * atr[conf]
                risk = stop - entry
                if risk > 0 and risk < 3.5 * atr[conf]:
                    t25 = entry - 2.5 * risk if mode in ("RANK2", "BOTH") else None
                    t30 = entry - 3.0 * risk if mode in ("RANK1", "BOTH") else None

                    grade = "A/A+" if mode == "RANK1" else ("A" if mode == "RANK2" else "A/A+")
                    signals.append(FibSignal(
                        direction=-1,
                        entry_bar=conf,
                        entry_price=entry,
                        stop=stop,
                        risk=risk,
                        target_r25=t25,
                        target_r30=t30,
                        a_bar=a.bar, a_price=a.price,
                        b_bar=b.bar, b_price=b.price,
                        c_bar=c.bar, c_price=c.price,
                        ab_size=ab, retrace=retr,
                        session=sess,
                        mode=mode,
                        grade=grade,
                    ))
                    last_entry = conf

        # ----- LONG setup (L-H-L) -----
        elif a.ptype == -1 and b.ptype == 1 and c.ptype == -1:
            ab = b.price - a.price
            if ab <= 0 or ab < min_impulse_atr * atr[conf]:
                i += 1
                continue
            retr = (b.price - c.price) / ab
            if not (fib_min <= retr <= fib_max):
                i += 1
                continue

            if conf - last_entry >= min_bars_between:
                entry = close[conf]
                stop = c.price - sl_buffer_atr * atr[conf]
                risk = entry - stop
                if risk > 0 and risk < 3.5 * atr[conf]:
                    t25 = entry + 2.5 * risk if mode in ("RANK2", "BOTH") else None
                    t30 = entry + 3.0 * risk if mode in ("RANK1", "BOTH") else None

                    grade = "A/A+" if mode == "RANK1" else ("A" if mode == "RANK2" else "A/A+")
                    signals.append(FibSignal(
                        direction=1,
                        entry_bar=conf,
                        entry_price=entry,
                        stop=stop,
                        risk=risk,
                        target_r25=t25,
                        target_r30=t30,
                        a_bar=a.bar, a_price=a.price,
                        b_bar=b.bar, b_price=b.price,
                        c_bar=c.bar, c_price=c.price,
                        ab_size=ab, retrace=retr,
                        session=sess,
                        mode=mode,
                        grade=grade,
                    ))
                    last_entry = conf

        i += 1

    return signals


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def detect_rank1(high, low, close, open_, times, atr=None, **kwargs) -> List[FibSignal]:
    """Rank-1 only (RR 3.0) – highest expectancy / PF."""
    return detect_hybrid_fib_deep(
        high, low, close, open_, times, atr, mode="RANK1", **kwargs
    )


def detect_rank2(high, low, close, open_, times, atr=None, **kwargs) -> List[FibSignal]:
    """Rank-2 only (RR 2.5) – slightly higher win-rate."""
    return detect_hybrid_fib_deep(
        high, low, close, open_, times, atr, mode="RANK2", **kwargs
    )


def detect_both(high, low, close, open_, times, atr=None, **kwargs) -> List[FibSignal]:
    """
    Both ranks, single signal per setup (no duplicates).
    Each FibSignal contains target_r25 and target_r30.
    """
    return detect_hybrid_fib_deep(
        high, low, close, open_, times, atr, mode="BOTH", **kwargs
    )


# ---------------------------------------------------------------------------
# Metadata / grades for reporting
# ---------------------------------------------------------------------------

RANK_META = {
    "RANK1": {
        "name": "Deep Fib 0.618-0.886 RR3.0 NY",
        "grade": "A / A+",
        "market": "USDJPY",
        "timeframe": "M1",
        "wr": 49.5,
        "expr": 0.541,
        "pf": 2.03,
        "maxdd_r": 9.0,
        "oos_expr": 0.596,
        "cost2x_expr": 0.421,
        "tpd_approx": 13.9,
        "notes": "Primary live candidate – highest ExpR & PF in the whole research cycle.",
    },
    "RANK2": {
        "name": "Deep Fib 0.618-0.886 RR2.5 NY",
        "grade": "A",
        "market": "USDJPY",
        "timeframe": "M1",
        "wr": 51.7,
        "expr": 0.497,
        "pf": 1.99,
        "maxdd_r": 10.0,
        "oos_expr": 0.538,
        "cost2x_expr": 0.377,
        "tpd_approx": 13.9,
        "notes": "Secondary – slightly higher win-rate, still excellent metrics.",
    },
}


def print_rank_summary():
    """Pretty-print the research grades for Rank 1 and Rank 2."""
    print("=" * 72)
    print("S35 Hybrid Fib Deep – Live Deployment Candidates")
    print("=" * 72)
    for key in ("RANK1", "RANK2"):
        m = RANK_META[key]
        print(f"\n{key}  [{m['grade']}]")
        print(f"  {m['name']}")
        print(f"  Market/TF   : {m['market']} {m['timeframe']}")
        print(f"  WR / ExpR   : {m['wr']}%   +{m['expr']:.3f}R")
        print(f"  PF / MaxDD  : {m['pf']:.2f}    {m['maxdd_r']:.1f}R")
        print(f"  OOS ExpR    : +{m['oos_expr']:.3f}")
        print(f"  cost 2×     : +{m['cost2x_expr']:.3f}")
        print(f"  ≈ trades/day: {m['tpd_approx']}")
        print(f"  Notes       : {m['notes']}")
    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Quick self-test (optional)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print_rank_summary()
    print("\nDetection module ready.")
    print("Usage examples:")
    print("  sigs = detect_rank1(high, low, close, open_, times)")
    print("  sigs = detect_rank2(high, low, close, open_, times)")
    print("  sigs = detect_both (high, low, close, open_, times)  # no duplicates")
