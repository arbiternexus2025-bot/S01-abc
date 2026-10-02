#!/usr/bin/env python3
"""
S03 — Pure Head & Shoulders / Inverse Head & Shoulders Detection
================================================================
Classical pattern recognition as validated in S03 research.

Head & Shoulders (bearish):
  Left Shoulder (high) → Head (higher high) → Right Shoulder (high ≈ left)
  Neckline connecting the two troughs between shoulders/head.
  Entry on close below neckline.

Inverse Head & Shoulders (bullish):
  Left Shoulder (low) → Head (lower low) → Right Shoulder (low ≈ left)
  Neckline connecting the two peaks.
  Entry on close above neckline.

Research finding:
  Strong, clean edge ONLY on XAUUSD H4 (pivot 6–9, RR 1.5–2.0).
  Extremely low drawdown, excellent cost resilience.
  Does not transfer to LTF or most other pairs.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Pivot:
    bar: int
    price: float
    ptype: int          # +1 high, -1 low


@dataclass
class HSPattern:
    kind: str           # "HS" or "IHS"
    ls_bar: int         # left shoulder
    ls_price: float
    head_bar: int
    head_price: float
    rs_bar: int         # right shoulder
    rs_price: float
    neck_bar1: int
    neck_price1: float
    neck_bar2: int
    neck_price2: float
    neckline_slope: float
    height: float       # head to neckline distance


@dataclass
class HSSignal:
    direction: int      # +1 long (IHS), -1 short (HS)
    kind: str
    pattern: HSPattern
    entry_bar: int
    entry_price: float
    stop: float
    target: float
    risk: float


def compute_atr(high, low, close, length=14):
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
    atr = np.full(n, np.nan)
    if n < length:
        return atr
    atr[length-1] = np.mean(tr[:length])
    for i in range(length, n):
        atr[i] = (atr[i-1]*(length-1) + tr[i]) / length
    return atr


def detect_pivots(high, low, left=7, right=7):
    n = len(high)
    pivots = []
    for i in range(left, n - right):
        is_h = all(high[i] > high[i-j] for j in range(1, left+1)) and \
               all(high[i] > high[i+j] for j in range(1, right+1))
        is_l = all(low[i] < low[i-j] for j in range(1, left+1)) and \
               all(low[i] < low[i+j] for j in range(1, right+1))
        if is_h:
            pivots.append(Pivot(i, high[i], 1))
        elif is_l:
            pivots.append(Pivot(i, low[i], -1))
    return pivots


def _neckline_price(p: HSPattern, bar: int) -> float:
    """Price of the neckline at a given bar (linear interpolation/extrapolation)."""
    dx = p.neck_bar2 - p.neck_bar1
    if dx == 0:
        return p.neck_price1
    return p.neck_price1 + p.neckline_slope * (bar - p.neck_bar1)


def detect_hs_patterns(
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    pivot_left: int = 7,
    pivot_right: int = 7,
    min_height_atr: float = 1.2,
    shoulder_tol: float = 1.5,      # max |LS - RS| / ATR
) -> List[HSPattern]:
    """
    Scan alternating pivots for classic H&S and Inverse H&S.
    """
    pivots = detect_pivots(high, low, left=pivot_left, right=pivot_right)
    patterns: List[HSPattern] = []
    n = len(high)

    # We need sequences of 5 pivots: S-H-S structure with intervening opposite pivots
    # Simplified robust scan: look for High-Low-High-Low-High (HS) or Low-High-Low-High-Low (IHS)
    for i in range(len(pivots) - 4):
        p0, p1, p2, p3, p4 = pivots[i:i+5]

        # ----- Head & Shoulders (bearish) -----
        # LS(high) - trough - Head(high) - trough - RS(high)
        if (p0.ptype == 1 and p1.ptype == -1 and p2.ptype == 1 and
            p3.ptype == -1 and p4.ptype == 1):
            ls, trough1, head, trough2, rs = p0, p1, p2, p3, p4
            # Head must be higher than both shoulders
            if head.price <= ls.price or head.price <= rs.price:
                continue
            conf = rs.bar + pivot_right
            if conf >= n or np.isnan(atr[conf]):
                continue
            atr_c = atr[conf]
            # Shoulder symmetry
            if abs(ls.price - rs.price) > shoulder_tol * atr_c:
                continue
            # Height
            neck_mid = (trough1.price + trough2.price) / 2.0
            height = head.price - neck_mid
            if height < min_height_atr * atr_c:
                continue
            slope = (trough2.price - trough1.price) / max(trough2.bar - trough1.bar, 1)
            patterns.append(HSPattern(
                kind="HS",
                ls_bar=ls.bar, ls_price=ls.price,
                head_bar=head.bar, head_price=head.price,
                rs_bar=rs.bar, rs_price=rs.price,
                neck_bar1=trough1.bar, neck_price1=trough1.price,
                neck_bar2=trough2.bar, neck_price2=trough2.price,
                neckline_slope=slope,
                height=height
            ))

        # ----- Inverse Head & Shoulders (bullish) -----
        if (p0.ptype == -1 and p1.ptype == 1 and p2.ptype == -1 and
            p3.ptype == 1 and p4.ptype == -1):
            ls, peak1, head, peak2, rs = p0, p1, p2, p3, p4
            if head.price >= ls.price or head.price >= rs.price:
                continue
            conf = rs.bar + pivot_right
            if conf >= n or np.isnan(atr[conf]):
                continue
            atr_c = atr[conf]
            if abs(ls.price - rs.price) > shoulder_tol * atr_c:
                continue
            neck_mid = (peak1.price + peak2.price) / 2.0
            height = neck_mid - head.price
            if height < min_height_atr * atr_c:
                continue
            slope = (peak2.price - peak1.price) / max(peak2.bar - peak1.bar, 1)
            patterns.append(HSPattern(
                kind="IHS",
                ls_bar=ls.bar, ls_price=ls.price,
                head_bar=head.bar, head_price=head.price,
                rs_bar=rs.bar, rs_price=rs.price,
                neck_bar1=peak1.bar, neck_price1=peak1.price,
                neck_bar2=peak2.bar, neck_price2=peak2.price,
                neckline_slope=slope,
                height=height
            ))

    return patterns


def detect_hs_signals(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    pivot_left: int = 7,
    pivot_right: int = 7,
    min_height_atr: float = 1.2,
    shoulder_tol: float = 1.5,
    rr: float = 2.0,
    sl_buffer_atr: float = 0.25,
) -> List[HSSignal]:
    """
    Full pipeline: find patterns → wait for neckline break → emit signal.
    """
    patterns = detect_hs_patterns(
        high, low, atr,
        pivot_left=pivot_left, pivot_right=pivot_right,
        min_height_atr=min_height_atr, shoulder_tol=shoulder_tol
    )
    signals: List[HSSignal] = []
    n = len(close)
    used = set()

    for pat in patterns:
        start = pat.rs_bar + pivot_right + 1
        if start >= n:
            continue
        for e in range(start, min(start + 80, n)):  # limited look-forward
            neck = _neckline_price(pat, e)
            atr_e = atr[e] if not np.isnan(atr[e]) and atr[e] > 0 else 1e-8

            if pat.kind == "HS":
                # bearish break
                if close[e] < neck and close[e-1] >= _neckline_price(pat, e-1):
                    entry = close[e]
                    stop = max(pat.ls_price, pat.rs_price) + sl_buffer_atr * atr_e
                    risk = stop - entry
                    if risk <= 0:
                        break
                    target = entry - rr * risk
                    # alternative measured move: target = entry - pat.height
                    signals.append(HSSignal(
                        direction=-1, kind="HS", pattern=pat,
                        entry_bar=e, entry_price=entry,
                        stop=stop, target=target, risk=risk
                    ))
                    used.add(id(pat))
                    break
            else:  # IHS
                if close[e] > neck and close[e-1] <= _neckline_price(pat, e-1):
                    entry = close[e]
                    stop = min(pat.ls_price, pat.rs_price) - sl_buffer_atr * atr_e
                    risk = entry - stop
                    if risk <= 0:
                        break
                    target = entry + rr * risk
                    signals.append(HSSignal(
                        direction=1, kind="IHS", pattern=pat,
                        entry_bar=e, entry_price=entry,
                        stop=stop, target=target, risk=risk
                    ))
                    used.add(id(pat))
                    break

    return signals
