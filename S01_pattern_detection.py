#!/usr/bin/env python3
"""
S01 — Fibonacci Expansion Continuation (ABC) Pattern Detection
==============================================================
Core research logic used across the validated S01 models.

Pattern:
  1. Detect alternating swing pivots (High-Low-High or Low-High-Low).
  2. Form 3-point ABC structure.
  3. Require AB impulse >= min_impulse * ATR.
  4. Require BC retracement <= max_retrace of AB.
  5. Optional volume / session filters.
  6. Entry on break of the BC trendline (pure structure break).
  7. SL beyond C (or ATR-based), TP = entry ± k * AB size (Fibonacci expansion).

Validated strongest on: XAUUSD M5 (Hybrid swings), USDJPY H4, GBPUSD M15, etc.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Pivot:
    bar: int
    price: float
    ptype: int          # +1 = swing high, -1 = swing low


@dataclass
class ABCSignal:
    direction: int      # +1 long, -1 short
    a_bar: int
    a_price: float
    b_bar: int
    b_price: float
    c_bar: int
    c_price: float
    ab_size: float
    retrace: float
    entry_bar: int
    entry_price: float
    stop: float
    target: float
    risk: float


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
        atr[i] = (atr[i-1] * (length - 1) + tr[i]) / length
    return atr


def detect_pivots(
    high: np.ndarray,
    low: np.ndarray,
    left: int = 5,
    right: int = 5,
    alternate: bool = True,
) -> List[Pivot]:
    """
    Confirmed pivot detection (no look-ahead once right bars have closed).
    When alternate=True, consecutive same-type pivots are replaced by the extreme.
    """
    n = len(high)
    pivots: List[Pivot] = []
    for i in range(left, n - right):
        is_high = True
        is_low = True
        for j in range(1, left + 1):
            if high[i] <= high[i - j]:
                is_high = False
            if low[i] >= low[i - j]:
                is_low = False
        for j in range(1, right + 1):
            if high[i] <= high[i + j]:
                is_high = False
            if low[i] >= low[i + j]:
                is_low = False

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


def detect_abc_signals(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    pivot_left: int = 5,
    pivot_right: int = 5,
    min_impulse_atr: float = 1.0,
    max_retrace: float = 0.90,
    tp_ab_mult: float = 1.0,
    sl_atr_buffer: float = 0.25,
    require_bc_break: bool = True,
) -> List[ABCSignal]:
    """
    Core S01 ABC Continuation detector.

    Long setup  : Low(A) – High(B) – Low(C)  then close breaks above BC line.
    Short setup : High(A) – Low(B) – High(C) then close breaks below BC line.

    Entry on the bar that confirms the BC trendline break.
    """
    pivots = detect_pivots(high, low, left=pivot_left, right=pivot_right, alternate=True)
    signals: List[ABCSignal] = []
    n = len(close)

    # We need at least 3 pivots and must wait for pivot confirmation (right bars)
    i = 0
    while i < len(pivots) - 2:
        a, b, c = pivots[i], pivots[i + 1], pivots[i + 2]

        # SHORT: H-L-H
        if a.ptype == 1 and b.ptype == -1 and c.ptype == 1:
            ab = a.price - b.price
            if ab <= 0:
                i += 1
                continue
            # ATR at C confirmation bar (c.bar + pivot_right)
            conf_bar = c.bar + pivot_right
            if conf_bar >= n or np.isnan(atr[conf_bar]):
                i += 1
                continue
            atr_c = atr[conf_bar]
            if ab < min_impulse_atr * atr_c:
                i += 1
                continue
            retr = (c.price - b.price) / ab
            if retr > max_retrace or retr < 0:
                i += 1
                continue

            # Scan forward for BC trendline break
            for e in range(conf_bar + 1, n):
                # Linear BC from B to C extended
                bars_bc = max(c.bar - b.bar, 1)
                bc_price = b.price + (c.price - b.price) * (e - b.bar) / bars_bc
                if require_bc_break:
                    if close[e] < bc_price and close[e - 1] >= bc_price:
                        entry = close[e]
                        stop = c.price + sl_atr_buffer * atr[e]
                        risk = stop - entry
                        if risk <= 0:
                            break
                        target = entry - tp_ab_mult * ab
                        signals.append(ABCSignal(
                            direction=-1,
                            a_bar=a.bar, a_price=a.price,
                            b_bar=b.bar, b_price=b.price,
                            c_bar=c.bar, c_price=c.price,
                            ab_size=ab, retrace=retr,
                            entry_bar=e, entry_price=entry,
                            stop=stop, target=target, risk=risk
                        ))
                        break
                else:
                    # Alternative: enter at C confirmation
                    entry = close[conf_bar]
                    stop = c.price + sl_atr_buffer * atr[conf_bar]
                    risk = stop - entry
                    if risk > 0:
                        target = entry - tp_ab_mult * ab
                        signals.append(ABCSignal(
                            direction=-1,
                            a_bar=a.bar, a_price=a.price,
                            b_bar=b.bar, b_price=b.price,
                            c_bar=c.bar, c_price=c.price,
                            ab_size=ab, retrace=retr,
                            entry_bar=conf_bar, entry_price=entry,
                            stop=stop, target=target, risk=risk
                        ))
                    break

        # LONG: L-H-L
        elif a.ptype == -1 and b.ptype == 1 and c.ptype == -1:
            ab = b.price - a.price
            if ab <= 0:
                i += 1
                continue
            conf_bar = c.bar + pivot_right
            if conf_bar >= n or np.isnan(atr[conf_bar]):
                i += 1
                continue
            atr_c = atr[conf_bar]
            if ab < min_impulse_atr * atr_c:
                i += 1
                continue
            retr = (b.price - c.price) / ab
            if retr > max_retrace or retr < 0:
                i += 1
                continue

            for e in range(conf_bar + 1, n):
                bars_bc = max(c.bar - b.bar, 1)
                bc_price = b.price + (c.price - b.price) * (e - b.bar) / bars_bc
                if require_bc_break:
                    if close[e] > bc_price and close[e - 1] <= bc_price:
                        entry = close[e]
                        stop = c.price - sl_atr_buffer * atr[e]
                        risk = entry - stop
                        if risk <= 0:
                            break
                        target = entry + tp_ab_mult * ab
                        signals.append(ABCSignal(
                            direction=1,
                            a_bar=a.bar, a_price=a.price,
                            b_bar=b.bar, b_price=b.price,
                            c_bar=c.bar, c_price=c.price,
                            ab_size=ab, retrace=retr,
                            entry_bar=e, entry_price=entry,
                            stop=stop, target=target, risk=risk
                        ))
                        break
                else:
                    entry = close[conf_bar]
                    stop = c.price - sl_atr_buffer * atr[conf_bar]
                    risk = entry - stop
                    if risk > 0:
                        target = entry + tp_ab_mult * ab
                        signals.append(ABCSignal(
                            direction=1,
                            a_bar=a.bar, a_price=a.price,
                            b_bar=b.bar, b_price=b.price,
                            c_bar=c.bar, c_price=c.price,
                            ab_size=ab, retrace=retr,
                            entry_bar=conf_bar, entry_price=entry,
                            stop=stop, target=target, risk=risk
                        ))
                    break
        i += 1

    return signals


# ---------------------------------------------------------------------------
# Convenience: Hybrid pivot (confirmed + min ATR swing + alternation)
# This was the best swing detector in S01 research.
# ---------------------------------------------------------------------------
def detect_hybrid_pivots(
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    left: int = 5,
    right: int = 5,
    min_swing_atr: float = 0.5,
) -> List[Pivot]:
    """Hybrid = confirmed pivot + minimum ATR size + forced alternation."""
    raw = detect_pivots(high, low, left=left, right=right, alternate=True)
    filtered: List[Pivot] = []
    for p in raw:
        if np.isnan(atr[p.bar]) or atr[p.bar] <= 0:
            continue
        if filtered:
            dist = abs(p.price - filtered[-1].price)
            if dist < min_swing_atr * atr[p.bar]:
                # replace if more extreme
                if p.ptype == filtered[-1].ptype:
                    if (p.ptype == 1 and p.price > filtered[-1].price) or \
                       (p.ptype == -1 and p.price < filtered[-1].price):
                        filtered[-1] = p
                continue
        filtered.append(p)
    return filtered
