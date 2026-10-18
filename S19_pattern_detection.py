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
