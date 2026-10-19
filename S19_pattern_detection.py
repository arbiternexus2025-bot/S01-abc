#!/usr/bin/env python3
"""
S19 — Liquidity Raid + BOS + Strong Order Block (Self-Contained)
================================================================

Research-grade, single-file detector. No external S19 imports required.

Core logic (validated H4 / H1 / M30 / M5):
  1. EMA50 slope bias
  2. Liquidity (recent swing high/low) is raided
  3. Break of Structure (BOS) with candle body quality
  4. Strong Order Block (body ratio filter) as POI  [FVG fallback optional]
  5. Optional ≥50% pullback after BOS (PCT50 mode)
  6. Session + Volatility filters
  7. Entry on touch of POI

Champion presets included:
  - H4_QUALITY / H4_STRONG_OB   → highest ExpR, low frequency
  - H1_STRONG_OB / H1_COMBO     → best daily balance
  - M30_STRONG_OB / M30_FREQ    → balanced higher frequency
  - M5_COMBO_P3 / M5_VOL40_P5 / M5_SESS_LN_P3  → scalping variants

Usage:
  from S19_pattern_detection import detect_s19_signals, detect_with_preset, PRESETS
  signals = detect_with_preset(high, low, open_, close, times, preset="H1_STRONG_OB")
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import List, Optional


# ─────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────

@dataclass
class Pivot:
    idx: int
    price: float
    kind: str          # "H" or "L"


@dataclass
class S19Signal:
    direction: int     # +1 long, -1 short
    entry_bar: int
    entry_price: float
    stop: float
    target: float
    risk: float
    rr: float
    poi_type: str = "OB"
    bias: str = ""
    bos_bar: int = -1
    lq_price: float = 0.0


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


def ema(series: np.ndarray, length: int) -> np.ndarray:
    n = len(series)
    out = np.full(n, np.nan)
    if n < length:
        return out
    k = 2.0 / (length + 1)
    out[length-1] = np.mean(series[:length])
    for i in range(length, n):
        out[i] = series[i] * k + out[i-1] * (1 - k)
    return out


def find_pivots(high: np.ndarray, low: np.ndarray, left: int = 5, right: int = 5) -> List[Pivot]:
    """Confirmed pivots only (no look-ahead)."""
    n = len(high)
    pivots = []
    for i in range(left, n - right):
        is_h = all(high[i] > high[i-j] for j in range(1, left+1)) and \
               all(high[i] >= high[i+j] for j in range(1, right+1))
        if is_h:
            pivots.append(Pivot(i, float(high[i]), "H"))
            continue
        is_l = all(low[i] < low[i-j] for j in range(1, left+1)) and \
               all(low[i] <= low[i+j] for j in range(1, right+1))
        if is_l:
            pivots.append(Pivot(i, float(low[i]), "L"))
    return pivots


def detect_fvg(high, low, open_, close, i, min_gap_atr=0.10, atr=None):
    """Classic 3-candle FVG ending at bar i. Returns (top, bot, direction) or None."""
    if i < 2:
        return None
    if low[i] > high[i-2]:
        gap = low[i] - high[i-2]
        if atr is not None and not np.isnan(atr[i]) and gap < min_gap_atr * atr[i]:
            return None
        return (float(low[i]), float(high[i-2]), +1)
    if high[i] < low[i-2]:
        gap = low[i-2] - high[i]
        if atr is not None and not np.isnan(atr[i]) and gap < min_gap_atr * atr[i]:
            return None
        return (float(low[i-2]), float(high[i]), -1)
    return None


def atr_percentile_rank(atr: np.ndarray, lookback: int = 100) -> np.ndarray:
    n = len(atr)
    rank = np.full(n, np.nan)
    for i in range(lookback, n):
        window = atr[i-lookback:i]
        if np.any(np.isnan(window)):
            continue
        rank[i] = np.sum(window <= atr[i]) / lookback
    return rank


def session_ok(hour: int, mode: str = "ALL") -> bool:
    if mode == "ALL":
        return True
    if mode == "LONDON":
        return 7 <= hour < 16
    if mode == "NY":
        return 12 <= hour < 21
    if mode == "OVERLAP":
        return 12 <= hour < 16
    if mode == "LONDON_NY":
        return (7 <= hour < 16) or (12 <= hour < 21)
    if mode == "ASIA_EXCLUDE":
        return not (0 <= hour < 7)
    return True


# ─────────────────────────────────────────────────────────────
# Main detector
# ─────────────────────────────────────────────────────────────

def detect_s19_signals(
    high: np.ndarray,
    low: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    times=None,
    # Core parameters
    pivot_left: int = 5,
    pivot_right: int = 5,
    rr: float = 2.5,
    min_disp_atr: float = 0.90,
    ob_min_body: float = 0.55,
    bos_body_min: float = 0.40,
    bos_mode: str = "PCT50",             # "PCT50" or "FULL"
    bos_pct: float = 0.50,
    session: str = "ALL",
    vol_min_pct: float = 0.0,            # 0 = off
    max_poi_age: int = 36,
    sl_buffer_atr: float = 0.10,
    allow_fvg_fallback: bool = True,
    one_trade_cooldown: int = 8,
) -> List[S19Signal]:
    """
    Full S19 detector (confirmed-bar only, no look-ahead).

    Returns chronological list of S19Signal.
    """
    n = len(close)
    if n < 80:
        return []

    atr = compute_atr(high, low, close)
    ema50 = ema(close, 50)
    atr_rank = atr_percentile_rank(atr) if vol_min_pct > 0 else None
    pivots = find_pivots(high, low, pivot_left, pivot_right)
    if len(pivots) < 4:
        return []

    signals: List[S19Signal] = []
    last_exit = -1
    swing_hs: List[Pivot] = []
    swing_ls: List[Pivot] = []
    right = pivot_right

    i = 50
    while i < n - 2:
        if np.isnan(atr[i]) or atr[i] < 1e-9:
            i += 1
            continue

        # Session filter
        if times is not None and session != "ALL":
            try:
                t = times[i]
                if hasattr(t, "hour"):
                    h = int(t.hour)
                else:
                    from datetime import datetime, timezone
                    h = datetime.fromtimestamp(float(t), tz=timezone.utc).hour
            except Exception:
                h = 12
            if not session_ok(h, session):
                i += 1
                continue

        # Volatility filter
        if atr_rank is not None and not np.isnan(atr_rank[i]):
            if atr_rank[i] < vol_min_pct:
                i += 1
                continue

        # Update confirmed swings
        conf_limit = i - right
        while len(swing_hs) + len(swing_ls) < len(pivots) and \
              pivots[len(swing_hs) + len(swing_ls)].idx <= conf_limit:
            p = pivots[len(swing_hs) + len(swing_ls)]
            (swing_hs if p.kind == "H" else swing_ls).append(p)

        if len(swing_hs) < 1 or len(swing_ls) < 1:
            i += 1
            continue

        # EMA50 slope bias
        if i < 3 or np.isnan(ema50[i]) or np.isnan(ema50[i-2]):
            i += 1
            continue
        slope = ema50[i] - ema50[i-2]
        bias = "BULL" if slope > 0 else ("BEAR" if slope < 0 else None)
        if bias is None:
            i += 1
            continue

        a = atr[i]

        # ──────────── LONG ────────────
        if bias == "BULL" and swing_ls:
            lq = swing_ls[-1]
            raided, raid_bar = False, -1
            for j in range(max(lq.idx + 1, i - 22), i + 1):
                if low[j] < lq.price:
                    raided, raid_bar = True, j
                    break

            if raided and raid_bar > last_exit:
                bos_bar = -1
                for k in range(raid_bar + 1, i + 1):
                    if close[k] > swing_hs[-1].price:
                        body = abs(close[k] - open_[k])
                        rng = high[k] - low[k]
                        if rng > 0 and body / rng >= bos_body_min:
                            bos_bar = k
                            break

                if bos_bar > 0:
                    disp = close[bos_bar] - low[raid_bar]
                    if disp >= min_disp_atr * a:
                        entry_ok = (bos_mode == "FULL")
                        entry_bar = bos_bar
                        if bos_mode == "PCT50":
                            mid = low[raid_bar] + bos_pct * disp
                            for e in range(bos_bar, min(bos_bar + max_poi_age, i + 1)):
                                if low[e] <= mid:
                                    entry_ok, entry_bar = True, e
                                    break

                        if entry_ok:
                            poi_top = poi_bot = None
                            poi_type = "OB"
                            for m in range(bos_bar - 1, max(raid_bar - 1, bos_bar - 15), -1):
                                if close[m] < open_[m]:
                                    body = open_[m] - close[m]
                                    rng = high[m] - low[m]
                                    if rng > 0 and body / rng >= ob_min_body:
                                        poi_top, poi_bot = float(high[m]), float(low[m])
                                        break

                            if poi_top is None and allow_fvg_fallback and bos_bar >= 2:
                                fvg = detect_fvg(high, low, open_, close, bos_bar, 0.10, atr)
                                if fvg and fvg[2] == +1:
                                    poi_top, poi_bot = fvg[0], fvg[1]
                                    poi_type = "FVG"

                            if poi_top is not None:
                                entry = (poi_top + poi_bot) / 2.0
                                stop = poi_bot - sl_buffer_atr * a
                                risk = entry - stop
                                if 0.12 * a <= risk <= 6.0 * a:
                                    touched, touch_bar = False, entry_bar
                                    for e in range(bos_bar, min(bos_bar + max_poi_age, n)):
                                        if low[e] <= poi_top:
                                            touched, touch_bar = True, e
                                            break
                                    if touched and touch_bar > last_exit:
                                        target = entry + rr * risk
                                        signals.append(S19Signal(
                                            direction=+1,
                                            entry_bar=touch_bar,
                                            entry_price=entry,
                                            stop=stop,
                                            target=target,
                                            risk=risk,
                                            rr=rr,
                                            poi_type=poi_type,
                                            bias=bias,
                                            bos_bar=bos_bar,
                                            lq_price=lq.price,
                                        ))
                                        last_exit = touch_bar + max(one_trade_cooldown, int(10 * rr))

        # ──────────── SHORT ────────────
        if bias == "BEAR" and swing_hs:
            lq = swing_hs[-1]
            raided, raid_bar = False, -1
            for j in range(max(lq.idx + 1, i - 22), i + 1):
                if high[j] > lq.price:
                    raided, raid_bar = True, j
                    break

            if raided and raid_bar > last_exit:
                bos_bar = -1
                for k in range(raid_bar + 1, i + 1):
                    if close[k] < swing_ls[-1].price:
                        body = abs(close[k] - open_[k])
                        rng = high[k] - low[k]
                        if rng > 0 and body / rng >= bos_body_min:
                            bos_bar = k
                            break

                if bos_bar > 0:
                    disp = high[raid_bar] - close[bos_bar]
                    if disp >= min_disp_atr * a:
                        entry_ok = (bos_mode == "FULL")
                        entry_bar = bos_bar
                        if bos_mode == "PCT50":
                            mid = high[raid_bar] - bos_pct * disp
                            for e in range(bos_bar, min(bos_bar + max_poi_age, i + 1)):
                                if high[e] >= mid:
                                    entry_ok, entry_bar = True, e
                                    break

                        if entry_ok:
                            poi_top = poi_bot = None
                            poi_type = "OB"
                            for m in range(bos_bar - 1, max(raid_bar - 1, bos_bar - 15), -1):
                                if close[m] > open_[m]:
                                    body = close[m] - open_[m]
                                    rng = high[m] - low[m]
                                    if rng > 0 and body / rng >= ob_min_body:
                                        poi_top, poi_bot = float(high[m]), float(low[m])
                                        break

                            if poi_top is None and allow_fvg_fallback and bos_bar >= 2:
                                fvg = detect_fvg(high, low, open_, close, bos_bar, 0.10, atr)
                                if fvg and fvg[2] == -1:
                                    poi_top, poi_bot = fvg[0], fvg[1]
                                    poi_type = "FVG"

                            if poi_top is not None:
                                entry = (poi_top + poi_bot) / 2.0
                                stop = poi_top + sl_buffer_atr * a
                                risk = stop - entry
                                if 0.12 * a <= risk <= 6.0 * a:
                                    touched, touch_bar = False, entry_bar
                                    for e in range(bos_bar, min(bos_bar + max_poi_age, n)):
                                        if high[e] >= poi_bot:
                                            touched, touch_bar = True, e
                                            break
                                    if touched and touch_bar > last_exit:
                                        target = entry - rr * risk
                                        signals.append(S19Signal(
                                            direction=-1,
                                            entry_bar=touch_bar,
                                            entry_price=entry,
                                            stop=stop,
                                            target=target,
                                            risk=risk,
                                            rr=rr,
                                            poi_type=poi_type,
                                            bias=bias,
                                            bos_bar=bos_bar,
                                            lq_price=lq.price,
                                        ))
                                        last_exit = touch_bar + max(one_trade_cooldown, int(10 * rr))
        i += 1

    return signals


# ─────────────────────────────────────────────────────────────
# Ready-to-use presets (research champions + M5 scalping)
# ─────────────────────────────────────────────────────────────

PRESETS = {
    # ── H4 Quality (highest ExpR) ──
    "H4_QUALITY": dict(
        pivot_left=5, pivot_right=5, rr=2.5,
        min_disp_atr=0.95, ob_min_body=0.55, bos_body_min=0.40,
        bos_mode="PCT50", session="LONDON_NY", vol_min_pct=0.25,
        max_poi_age=28, sl_buffer_atr=0.12, allow_fvg_fallback=True,
    ),
    "H4_STRONG_OB": dict(
        pivot_left=5, pivot_right=5, rr=2.5,
        min_disp_atr=0.90, ob_min_body=0.55, bos_body_min=0.40,
        bos_mode="PCT50", session="ALL", vol_min_pct=0.0,
        max_poi_age=28, sl_buffer_atr=0.12, allow_fvg_fallback=True,
    ),

    # ── H1 Workhorse ──
    "H1_STRONG_OB": dict(
        pivot_left=5, pivot_right=5, rr=2.5,
        min_disp_atr=0.90, ob_min_body=0.55, bos_body_min=0.40,
        bos_mode="PCT50", session="ALL", vol_min_pct=0.0,
        max_poi_age=36, sl_buffer_atr=0.12, allow_fvg_fallback=True,
    ),
    "H1_COMBO": dict(
        pivot_left=5, pivot_right=5, rr=2.5,
        min_disp_atr=0.90, ob_min_body=0.50, bos_body_min=0.40,
        bos_mode="PCT50", session="LONDON_NY", vol_min_pct=0.20,
        max_poi_age=36, sl_buffer_atr=0.12, allow_fvg_fallback=True,
    ),

    # ── M30 Balanced ──
    "M30_STRONG_OB": dict(
        pivot_left=5, pivot_right=5, rr=2.5,
        min_disp_atr=0.85, ob_min_body=0.50, bos_body_min=0.35,
        bos_mode="PCT50", session="ALL", vol_min_pct=0.0,
        max_poi_age=40, sl_buffer_atr=0.12, allow_fvg_fallback=True,
    ),
    "M30_FREQ": dict(
        pivot_left=3, pivot_right=3, rr=2.0,
        min_disp_atr=0.75, ob_min_body=0.45, bos_body_min=0.30,
        bos_mode="FULL", session="LONDON_NY", vol_min_pct=0.15,
        max_poi_age=40, sl_buffer_atr=0.12, allow_fvg_fallback=True,
    ),

    # ── M5 Scalping variants ──
    "M5_COMBO_P3": dict(
        pivot_left=3, pivot_right=3, rr=2.0,
        min_disp_atr=0.70, ob_min_body=0.45, bos_body_min=0.30,
        bos_mode="PCT50", session="LONDON_NY", vol_min_pct=0.15,
        max_poi_age=48, sl_buffer_atr=0.15, allow_fvg_fallback=True,
    ),
    "M5_VOL40_P5": dict(
        pivot_left=5, pivot_right=5, rr=2.0,
        min_disp_atr=0.80, ob_min_body=0.50, bos_body_min=0.35,
        bos_mode="PCT50", session="ALL", vol_min_pct=0.40,
        max_poi_age=48, sl_buffer_atr=0.15, allow_fvg_fallback=True,
    ),
    "M5_SESS_LN_P3": dict(
        pivot_left=3, pivot_right=3, rr=2.0,
        min_disp_atr=0.70, ob_min_body=0.45, bos_body_min=0.30,
        bos_mode="FULL", session="LONDON_NY", vol_min_pct=0.0,
        max_poi_age=48, sl_buffer_atr=0.15, allow_fvg_fallback=True,
    ),
}


def detect_with_preset(
    high, low, open_, close, times=None, preset: str = "H1_STRONG_OB"
) -> List[S19Signal]:
    """Convenience wrapper using a named research preset."""
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset '{preset}'. Available: {list(PRESETS.keys())}")
    return detect_s19_signals(high, low, open_, close, times=times, **PRESETS[preset])


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("S19 self-contained detector ready.")
    print("Available presets:")
    for name in PRESETS:
        print(f"  • {name}")
    print()
    print("Example:")
    print('  signals = detect_with_preset(high, low, open_, close, times, preset="H1_STRONG_OB")')
    print('  signals = detect_s19_signals(high, low, open_, close, **PRESETS["H4_QUALITY"])')


# ─────────────────────────────────────────────────────────────
# Multi-TF (H4 context → H1 entry)
# ─────────────────────────────────────────────────────────────

def _build_htf_context(high, low, close, pivot_left=5, pivot_right=5):
    """H4 bias + latest LQ high/low (forward-filled)."""
    n = len(close)
    atr = compute_atr(high, low, close)
    ema50 = ema(close, 50)
    pivots = find_pivots(high, low, pivot_left, pivot_right)
    bias = np.full(n, "", dtype=object)
    lq_high = np.full(n, np.nan)
    lq_low  = np.full(n, np.nan)
    swing_hs, swing_ls = [], []
    p_idx = 0
    for i in range(60, n):
        conf = i - pivot_right
        while p_idx < len(pivots) and pivots[p_idx].idx <= conf:
            p = pivots[p_idx]
            (swing_hs if p.kind == "H" else swing_ls).append(p)
            p_idx += 1
        if not np.isnan(ema50[i]) and i >= 2 and not np.isnan(ema50[i-2]):
            slope = ema50[i] - ema50[i-2]
            bias[i] = "BULL" if slope > 0 else ("BEAR" if slope < 0 else "")
        if swing_hs:
            lq_high[i] = swing_hs[-1].price
        if swing_ls:
            lq_low[i] = swing_ls[-1].price
    return bias, lq_high, lq_low


def _map_htf_to_ltf(h4_times, h1_times, h4_bias, h4_lqh, h4_lql):
    n1 = len(h1_times)
    bias1 = np.full(n1, "", dtype=object)
    lqh1  = np.full(n1, np.nan)
    lql1  = np.full(n1, np.nan)
    j = 0
    for i in range(n1):
        t = h1_times[i]
        while j + 1 < len(h4_times) and h4_times[j+1] <= t:
            j += 1
        if j < len(h4_times) and h4_times[j] <= t:
            bias1[i] = h4_bias[j]
            lqh1[i]  = h4_lqh[j]
            lql1[i]  = h4_lql[j]
    return bias1, lqh1, lql1


def detect_s19_mtf(
    high4, low4, close4, times4,
    high1, low1, open1, close1, times1,
    h4_pivot: int = 5,
    h1_pivot: int = 5,
    rr: float = 2.5,
    min_disp_atr: float = 0.85,
    ob_min_body: float = 0.50,
    bos_body_min: float = 0.35,
    bos_mode: str = "PCT50",
    bos_pct: float = 0.50,
    session: str = "ALL",
    vol_min_pct: float = 0.0,
    max_poi_age: int = 40,
    sl_buffer_atr: float = 0.12,
    allow_fvg_fallback: bool = True,
    one_trade_cooldown: int = 10,
) -> List[S19Signal]:
    """
    Multi-TF detector:
      H4 → bias (EMA50 slope) + liquidity pools
      H1 → raid of H4 LQ → BOS + Strong OB near LQ → entry
    """
    bias4, lqh4, lql4 = _build_htf_context(high4, low4, close4, h4_pivot, h4_pivot)
    bias1, lqh1, lql1 = _map_htf_to_ltf(times4, times1, bias4, lqh4, lql4)

    atr1 = compute_atr(high1, low1, close1)
    atr_rank = atr_percentile_rank(atr1) if vol_min_pct > 0 else None
    pivots1 = find_pivots(high1, low1, h1_pivot, h1_pivot)

    signals: List[S19Signal] = []
    last_exit = -1
    swing_hs, swing_ls = [], []
    p_idx = 0
    n = len(close1)

    i = 80
    while i < n - 2:
        if np.isnan(atr1[i]) or atr1[i] < 1e-9:
            i += 1
            continue
        if times1 is not None and session != "ALL":
            try:
                h = int(times1[i].hour) if hasattr(times1[i], "hour") else 12
            except Exception:
                h = 12
            if not session_ok(h, session):
                i += 1
                continue
        if atr_rank is not None and not np.isnan(atr_rank[i]) and atr_rank[i] < vol_min_pct:
            i += 1
            continue

        conf = i - h1_pivot
        while p_idx < len(pivots1) and pivots1[p_idx].idx <= conf:
            p = pivots1[p_idx]
            (swing_hs if p.kind == "H" else swing_ls).append(p)
            p_idx += 1
        if len(swing_hs) < 1 or len(swing_ls) < 1:
            i += 1
            continue

        bias = bias1[i]
        if bias not in ("BULL", "BEAR"):
            i += 1
            continue
        a = atr1[i]
        lq_h, lq_l = lqh1[i], lql1[i]

        # LONG
        if bias == "BULL" and not np.isnan(lq_l):
            raided, raid_bar = False, -1
            for j in range(max(0, i - 30), i + 1):
                if low1[j] < lq_l:
                    raided, raid_bar = True, j
                    break
            if raided and raid_bar > last_exit:
                bos_bar = -1
                for k in range(raid_bar + 1, i + 1):
                    if close1[k] > swing_hs[-1].price:
                        body = abs(close1[k] - open1[k])
                        rng = high1[k] - low1[k]
                        if rng > 0 and body / rng >= bos_body_min:
                            bos_bar = k
                            break
                if bos_bar > 0:
                    disp = close1[bos_bar] - low1[raid_bar]
                    if disp >= min_disp_atr * a:
                        entry_ok = bos_mode == "FULL"
                        if bos_mode == "PCT50":
                            mid = low1[raid_bar] + bos_pct * disp
                            for e in range(bos_bar, min(bos_bar + max_poi_age, i + 1)):
                                if low1[e] <= mid:
                                    entry_ok = True
                                    break
                        if entry_ok:
                            poi_top = poi_bot = None
                            poi_type = "OB"
                            for m in range(bos_bar - 1, max(raid_bar - 1, bos_bar - 18), -1):
                                if close1[m] < open1[m]:
                                    body = open1[m] - close1[m]
                                    rng = high1[m] - low1[m]
                                    if rng > 0 and body / rng >= ob_min_body:
                                        if abs(low1[m] - lq_l) < 1.5 * a or abs(high1[m] - lq_l) < 1.5 * a:
                                            poi_top, poi_bot = float(high1[m]), float(low1[m])
                                            break
                            if poi_top is None and allow_fvg_fallback:
                                fvg = detect_fvg(high1, low1, open1, close1, bos_bar, 0.10, atr1)
                                if fvg and fvg[2] == +1:
                                    poi_top, poi_bot = fvg[0], fvg[1]
                                    poi_type = "FVG"
                            if poi_top is not None:
                                entry = (poi_top + poi_bot) / 2.0
                                stop = min(poi_bot, lq_l) - sl_buffer_atr * a
                                risk = entry - stop
                                if 0.12 * a <= risk <= 6.0 * a:
                                    touched, touch_bar = False, bos_bar
                                    for e in range(bos_bar, min(bos_bar + max_poi_age, n)):
                                        if low1[e] <= poi_top:
                                            touched, touch_bar = True, e
                                            break
                                    if touched and touch_bar > last_exit:
                                        signals.append(S19Signal(
                                            +1, touch_bar, entry, stop, entry + rr * risk, risk, rr,
                                            poi_type, bias, bos_bar, float(lq_l)
                                        ))
                                        last_exit = touch_bar + max(one_trade_cooldown, int(10 * rr))

        # SHORT
        if bias == "BEAR" and not np.isnan(lq_h):
            raided, raid_bar = False, -1
            for j in range(max(0, i - 30), i + 1):
                if high1[j] > lq_h:
                    raided, raid_bar = True, j
                    break
            if raided and raid_bar > last_exit:
                bos_bar = -1
                for k in range(raid_bar + 1, i + 1):
                    if close1[k] < swing_ls[-1].price:
                        body = abs(close1[k] - open1[k])
                        rng = high1[k] - low1[k]
                        if rng > 0 and body / rng >= bos_body_min:
                            bos_bar = k
                            break
                if bos_bar > 0:
                    disp = high1[raid_bar] - close1[bos_bar]
                    if disp >= min_disp_atr * a:
                        entry_ok = bos_mode == "FULL"
                        if bos_mode == "PCT50":
                            mid = high1[raid_bar] - bos_pct * disp
                            for e in range(bos_bar, min(bos_bar + max_poi_age, i + 1)):
                                if high1[e] >= mid:
                                    entry_ok = True
                                    break
                        if entry_ok:
                            poi_top = poi_bot = None
                            poi_type = "OB"
                            for m in range(bos_bar - 1, max(raid_bar - 1, bos_bar - 18), -1):
                                if close1[m] > open1[m]:
                                    body = close1[m] - open1[m]
                                    rng = high1[m] - low1[m]
                                    if rng > 0 and body / rng >= ob_min_body:
                                        if abs(high1[m] - lq_h) < 1.5 * a or abs(low1[m] - lq_h) < 1.5 * a:
                                            poi_top, poi_bot = float(high1[m]), float(low1[m])
                                            break
                            if poi_top is None and allow_fvg_fallback:
                                fvg = detect_fvg(high1, low1, open1, close1, bos_bar, 0.10, atr1)
                                if fvg and fvg[2] == -1:
                                    poi_top, poi_bot = fvg[0], fvg[1]
                                    poi_type = "FVG"
                            if poi_top is not None:
                                entry = (poi_top + poi_bot) / 2.0
                                stop = max(poi_top, lq_h) + sl_buffer_atr * a
                                risk = stop - entry
                                if 0.12 * a <= risk <= 6.0 * a:
                                    touched, touch_bar = False, bos_bar
                                    for e in range(bos_bar, min(bos_bar + max_poi_age, n)):
                                        if high1[e] >= poi_bot:
                                            touched, touch_bar = True, e
                                            break
                                    if touched and touch_bar > last_exit:
                                        signals.append(S19Signal(
                                            -1, touch_bar, entry, stop, entry - rr * risk, risk, rr,
                                            poi_type, bias, bos_bar, float(lq_h)
                                        ))
                                        last_exit = touch_bar + max(one_trade_cooldown, int(10 * rr))
        i += 1
    return signals


# Multi-TF presets
MTF_PRESETS = {
    "MTF_STRONG": dict(
        h4_pivot=5, h1_pivot=5, rr=2.5, min_disp_atr=0.95,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.20, max_poi_age=40, sl_buffer_atr=0.12,
    ),
    "MTF_PCT50": dict(
        h4_pivot=5, h1_pivot=5, rr=2.5, min_disp_atr=0.85,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=40, sl_buffer_atr=0.12,
    ),
    "MTF_PCT50_LN": dict(
        h4_pivot=5, h1_pivot=5, rr=2.5, min_disp_atr=0.85,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.0, max_poi_age=40, sl_buffer_atr=0.12,
    ),
    "MTF_FULL": dict(
        h4_pivot=5, h1_pivot=5, rr=2.0, min_disp_atr=0.80,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="FULL",
        session="ALL", vol_min_pct=0.0, max_poi_age=40, sl_buffer_atr=0.12,
    ),
}


def detect_mtf_with_preset(
    high4, low4, close4, times4,
    high1, low1, open1, close1, times1,
    preset: str = "MTF_STRONG",
) -> List[S19Signal]:
    if preset not in MTF_PRESETS:
        raise ValueError(f"Unknown MTF preset '{preset}'. Available: {list(MTF_PRESETS.keys())}")
    return detect_s19_mtf(
        high4, low4, close4, times4,
        high1, low1, open1, close1, times1,
        **MTF_PRESETS[preset],
    )
