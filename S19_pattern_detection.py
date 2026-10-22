#!/usr/bin/env python3
"""
S19 — Liquidity Raid + BOS + Strong Order Block
================================================
Self-contained production detector for signal-alert bots.

Core logic (validated H4 / H1 / M30 / M15 / M5 + Multi-TF):
  1. Bias (EMA50 slope, optional ATR threshold, dual, price-vs-EMA200)
  2. Liquidity (recent swing high/low) is raided
  3. Break of Structure (BOS) with candle body quality
  4. Strong Order Block (body ratio) as POI  [FVG fallback optional]
  5. Optional ≥50% pullback after BOS (PCT50 mode)
  6. Session + Volatility filters
  7. Entry on touch of POI

Top-50 research presets are all available via PRESETS / TOP50_PRESETS.
Multi-TF (H4 context → H1 entry) via detect_s19_mtf / MTF_PRESETS.

Usage (alert bot):
  from S19_pattern_detection import (
      detect_with_preset, get_latest_signal, format_alert,
      PRESETS, TOP50_PRESETS, list_presets
  )
  signals = detect_with_preset(high, low, open_, close, times, preset="H1_STRONG_st10")
  latest  = get_latest_signal(signals)
  if latest:
      print(format_alert(latest, symbol="EURUSD", tf="H1", preset="H1_STRONG_st10"))
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any


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
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n < length:
        return atr
    atr[length - 1] = np.mean(tr[:length])
    for i in range(length, n):
        atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr


def ema(series: np.ndarray, length: int) -> np.ndarray:
    n = len(series)
    out = np.full(n, np.nan)
    if n < length:
        return out
    k = 2.0 / (length + 1)
    out[length - 1] = np.mean(series[:length])
    for i in range(length, n):
        out[i] = series[i] * k + out[i - 1] * (1 - k)
    return out


def find_pivots(high: np.ndarray, low: np.ndarray, left: int = 5, right: int = 5) -> List[Pivot]:
    """Confirmed pivots only (no look-ahead)."""
    n = len(high)
    pivots = []
    for i in range(left, n - right):
        is_h = all(high[i] > high[i - j] for j in range(1, left + 1)) and \
               all(high[i] >= high[i + j] for j in range(1, right + 1))
        if is_h:
            pivots.append(Pivot(i, float(high[i]), "H"))
            continue
        is_l = all(low[i] < low[i - j] for j in range(1, left + 1)) and \
               all(low[i] <= low[i + j] for j in range(1, right + 1))
        if is_l:
            pivots.append(Pivot(i, float(low[i]), "L"))
    return pivots


def detect_fvg(high, low, open_, close, i, min_gap_atr=0.10, atr=None):
    """Classic 3-candle FVG ending at bar i. Returns (top, bot, direction) or None."""
    if i < 2:
        return None
    if low[i] > high[i - 2]:
        gap = low[i] - high[i - 2]
        if atr is not None and not np.isnan(atr[i]) and gap < min_gap_atr * atr[i]:
            return None
        return (float(low[i]), float(high[i - 2]), +1)
    if high[i] < low[i - 2]:
        gap = low[i - 2] - high[i]
        if atr is not None and not np.isnan(atr[i]) and gap < min_gap_atr * atr[i]:
            return None
        return (float(low[i - 2]), float(high[i]), -1)
    return None


def atr_percentile_rank(atr: np.ndarray, lookback: int = 100) -> np.ndarray:
    n = len(atr)
    rank = np.full(n, np.nan)
    for i in range(lookback, n):
        window = atr[i - lookback:i]
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


def compute_bias(
    bias_mode: str,
    close: np.ndarray,
    atr: np.ndarray,
    e50: np.ndarray,
    e200: np.ndarray,
    i: int,
    swing_hs: List[Pivot],
    swing_ls: List[Pivot],
) -> Optional[str]:
    """
    bias_mode options:
      EMA50_s2     — slope over 2 bars (baseline)
      EMA50_s3     — slope over 3 bars
      EMA50_st05   — slope must exceed 0.05 * ATR
      EMA50_st10   — slope must exceed 0.10 * ATR   [Top-50 default]
      EMA50_st15   — slope must exceed 0.15 * ATR   [max quality]
      Price_EMA200 — close vs EMA200
      EMA50_200    — EMA50 vs EMA200
      DUAL_50_200  — EMA50 slope + price vs EMA200 agree
      STRUCT       — HH/HL vs LH/LL
    """
    if bias_mode == "EMA50_s2":
        if i < 2 or np.isnan(e50[i]) or np.isnan(e50[i - 2]):
            return None
        s = e50[i] - e50[i - 2]
        return "BULL" if s > 0 else ("BEAR" if s < 0 else None)

    if bias_mode == "EMA50_s3":
        if i < 3 or np.isnan(e50[i]) or np.isnan(e50[i - 3]):
            return None
        s = e50[i] - e50[i - 3]
        return "BULL" if s > 0 else ("BEAR" if s < 0 else None)

    if bias_mode in ("EMA50_st05", "EMA50_st10", "EMA50_st15"):
        th = {"EMA50_st05": 0.05, "EMA50_st10": 0.10, "EMA50_st15": 0.15}[bias_mode]
        if i < 2 or np.isnan(e50[i]) or np.isnan(e50[i - 2]) or np.isnan(atr[i]):
            return None
        s = e50[i] - e50[i - 2]
        if abs(s) < th * atr[i]:
            return None
        return "BULL" if s > 0 else "BEAR"

    if bias_mode == "Price_EMA200":
        if np.isnan(e200[i]):
            return None
        return "BULL" if close[i] > e200[i] else ("BEAR" if close[i] < e200[i] else None)

    if bias_mode == "EMA50_200":
        if np.isnan(e50[i]) or np.isnan(e200[i]):
            return None
        return "BULL" if e50[i] > e200[i] else ("BEAR" if e50[i] < e200[i] else None)

    if bias_mode == "DUAL_50_200":
        if i < 2 or np.isnan(e50[i]) or np.isnan(e50[i - 2]) or np.isnan(e200[i]):
            return None
        s = e50[i] - e50[i - 2]
        sb = "BULL" if s > 0 else ("BEAR" if s < 0 else None)
        pb = "BULL" if close[i] > e200[i] else ("BEAR" if close[i] < e200[i] else None)
        return sb if sb and pb and sb == pb else None

    if bias_mode == "STRUCT":
        if len(swing_ls) >= 2 and len(swing_hs) >= 2:
            if swing_ls[-1].price > swing_ls[-2].price and swing_hs[-1].price > swing_hs[-2].price:
                return "BULL"
            if swing_ls[-1].price < swing_ls[-2].price and swing_hs[-1].price < swing_hs[-2].price:
                return "BEAR"
        return None

    # default fallback
    if i < 2 or np.isnan(e50[i]) or np.isnan(e50[i - 2]):
        return None
    s = e50[i] - e50[i - 2]
    return "BULL" if s > 0 else ("BEAR" if s < 0 else None)


# ─────────────────────────────────────────────────────────────
# Main single-TF detector
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
    sl_buffer_atr: float = 0.12,
    allow_fvg_fallback: bool = True,
    one_trade_cooldown: int = 8,
    bias_mode: str = "EMA50_s2",         # see compute_bias()
) -> List[S19Signal]:
    """
    Full S19 detector (confirmed-bar only, no look-ahead).
    Returns chronological list of S19Signal.
    """
    n = len(close)
    if n < 80:
        return []

    atr = compute_atr(high, low, close)
    e50 = ema(close, 50)
    e200 = ema(close, 200)
    atr_rank = atr_percentile_rank(atr) if vol_min_pct > 0 else None
    pivots = find_pivots(high, low, pivot_left, pivot_right)
    if len(pivots) < 4:
        return []

    signals: List[S19Signal] = []
    last_exit = -1
    swing_hs: List[Pivot] = []
    swing_ls: List[Pivot] = []
    right = pivot_right
    p_idx = 0

    i = 60
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
        while p_idx < len(pivots) and pivots[p_idx].idx <= conf_limit:
            p = pivots[p_idx]
            (swing_hs if p.kind == "H" else swing_ls).append(p)
            p_idx += 1

        if len(swing_hs) < 1 or len(swing_ls) < 1:
            i += 1
            continue

        bias = compute_bias(bias_mode, close, atr, e50, e200, i, swing_hs, swing_ls)
        if bias not in ("BULL", "BEAR"):
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
                        entry_ok = bos_mode == "FULL"
                        if bos_mode == "PCT50":
                            mid = low[raid_bar] + bos_pct * disp
                            for e in range(bos_bar, min(bos_bar + max_poi_age, i + 1)):
                                if low[e] <= mid:
                                    entry_ok = True
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
                            if poi_top is None and allow_fvg_fallback:
                                fvg = detect_fvg(high, low, open_, close, bos_bar, 0.10, atr)
                                if fvg and fvg[2] == +1:
                                    poi_top, poi_bot = fvg[0], fvg[1]
                                    poi_type = "FVG"
                            if poi_top is not None:
                                entry = (poi_top + poi_bot) / 2.0
                                stop = poi_bot - sl_buffer_atr * a
                                risk = entry - stop
                                if 0.12 * a <= risk <= 6.0 * a:
                                    touched, touch_bar = False, bos_bar
                                    for e in range(bos_bar, min(bos_bar + max_poi_age, n)):
                                        if low[e] <= poi_top:
                                            touched, touch_bar = True, e
                                            break
                                    if touched and touch_bar > last_exit:
                                        signals.append(S19Signal(
                                            +1, touch_bar, entry, stop, entry + rr * risk, risk, rr,
                                            poi_type, bias, bos_bar, float(lq.price)
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
                        entry_ok = bos_mode == "FULL"
                        if bos_mode == "PCT50":
                            mid = high[raid_bar] - bos_pct * disp
                            for e in range(bos_bar, min(bos_bar + max_poi_age, i + 1)):
                                if high[e] >= mid:
                                    entry_ok = True
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
                            if poi_top is None and allow_fvg_fallback:
                                fvg = detect_fvg(high, low, open_, close, bos_bar, 0.10, atr)
                                if fvg and fvg[2] == -1:
                                    poi_top, poi_bot = fvg[0], fvg[1]
                                    poi_type = "FVG"
                            if poi_top is not None:
                                entry = (poi_top + poi_bot) / 2.0
                                stop = poi_top + sl_buffer_atr * a
                                risk = stop - entry
                                if 0.12 * a <= risk <= 6.0 * a:
                                    touched, touch_bar = False, bos_bar
                                    for e in range(bos_bar, min(bos_bar + max_poi_age, n)):
                                        if high[e] >= poi_bot:
                                            touched, touch_bar = True, e
                                            break
                                    if touched and touch_bar > last_exit:
                                        signals.append(S19Signal(
                                            -1, touch_bar, entry, stop, entry - rr * risk, risk, rr,
                                            poi_type, bias, bos_bar, float(lq.price)
                                        ))
                                        last_exit = touch_bar + max(one_trade_cooldown, int(10 * rr))
        i += 1

    return signals


# ─────────────────────────────────────────────────────────────
# PRESETS — all Top-50 research champions
# ─────────────────────────────────────────────────────────────

PRESETS: Dict[str, dict] = {
    # ── H4 ──
    "H4_QUALITY": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.95,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.25, max_poi_age=28,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "H4_STRONG_OB": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.90,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=28,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "H4_STRONG_st10": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.90,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=28,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_st10",
    ),
    "H4_QUALITY_st10": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.95,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.25, max_poi_age=28,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_st10",
    ),

    # ── H1 ──
    "H1_STRONG_OB": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.90,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=36,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "H1_STRONG_st05": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.90,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=36,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_st05",
    ),
    "H1_STRONG_st10": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.90,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=36,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_st10",
    ),
    "H1_STRONG_st15": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.90,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=36,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_st15",
    ),
    "H1_COMBO": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.90,
        ob_min_body=0.50, bos_body_min=0.40, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.20, max_poi_age=36,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "H1_COMBO_st10": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.90,
        ob_min_body=0.50, bos_body_min=0.40, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.20, max_poi_age=36,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_st10",
    ),
    "H1_DUAL": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.90,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=36,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="DUAL_50_200",
    ),

    # ── M30 ──
    "M30_STRONG_OB": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.85,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=40,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "M30_STRONG_st05": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.85,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=40,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_st05",
    ),
    "M30_STRONG_st10": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.85,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=40,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_st10",
    ),
    "M30_STRONG_st15": dict(
        pivot_left=5, pivot_right=5, rr=2.5, min_disp_atr=0.85,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=40,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_st15",
    ),
    "M30_FREQ": dict(
        pivot_left=3, pivot_right=3, rr=2.0, min_disp_atr=0.75,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="FULL",
        session="LONDON_NY", vol_min_pct=0.15, max_poi_age=40,
        sl_buffer_atr=0.12, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),

    # ── M15 ──
    "M15_STRONG": dict(
        pivot_left=5, pivot_right=5, rr=2.0, min_disp_atr=0.80,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "M15_STRONG_st10": dict(
        pivot_left=5, pivot_right=5, rr=2.0, min_disp_atr=0.80,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st10",
    ),
    "M15_STRONG_st15": dict(
        pivot_left=5, pivot_right=5, rr=2.0, min_disp_atr=0.80,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st15",
    ),
    "M15_COMBO": dict(
        pivot_left=3, pivot_right=3, rr=2.0, min_disp_atr=0.75,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.15, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "M15_COMBO_st05": dict(
        pivot_left=3, pivot_right=3, rr=2.0, min_disp_atr=0.75,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.15, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st05",
    ),
    "M15_COMBO_st10": dict(
        pivot_left=3, pivot_right=3, rr=2.0, min_disp_atr=0.75,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.15, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st10",
    ),
    "M15_COMBO_st15": dict(
        pivot_left=3, pivot_right=3, rr=2.0, min_disp_atr=0.75,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.15, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st15",
    ),

    # ── M5 ──
    "M5_STRONG": dict(
        pivot_left=5, pivot_right=5, rr=2.0, min_disp_atr=0.80,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "M5_STRONG_st15": dict(
        pivot_left=5, pivot_right=5, rr=2.0, min_disp_atr=0.80,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st15",
    ),
    "M5_COMBO": dict(
        pivot_left=3, pivot_right=3, rr=2.0, min_disp_atr=0.70,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.15, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "M5_COMBO_st05": dict(
        pivot_left=3, pivot_right=3, rr=2.0, min_disp_atr=0.70,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.15, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st05",
    ),
    "M5_COMBO_st10": dict(
        pivot_left=3, pivot_right=3, rr=2.0, min_disp_atr=0.70,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.15, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st10",
    ),
    "M5_COMBO_st15": dict(
        pivot_left=3, pivot_right=3, rr=2.0, min_disp_atr=0.70,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.15, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st15",
    ),
    "M5_VOL40": dict(
        pivot_left=5, pivot_right=5, rr=2.0, min_disp_atr=0.80,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.40, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_s2",
    ),
    "M5_VOL40_st15": dict(
        pivot_left=5, pivot_right=5, rr=2.0, min_disp_atr=0.80,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.40, max_poi_age=48,
        sl_buffer_atr=0.15, allow_fvg_fallback=True, bias_mode="EMA50_st15",
    ),
}


# Map Top-50 rank → recommended preset name (for bot routing)
TOP50_PRESETS: Dict[int, str] = {
    1: "H4_STRONG_OB",       # USDCHF H4
    2: "H4_STRONG_st10",     # USDJPY H4
    3: "H4_QUALITY",         # GBPUSD H4
    4: "H1_STRONG_st15",     # EURUSD H1
    5: "H4_QUALITY",         # EURUSD H4
    6: "H1_STRONG_st15",     # USDCHF H1
    7: "M30_STRONG_st15",    # USDCHF M30
    8: "H1_STRONG_st10",     # EURUSD H1
    9: "H1_STRONG_st15",     # USDJPY H1
    10: "H1_STRONG_st10",    # USDJPY H1
    11: "H1_STRONG_st10",    # USDCHF H1
    12: "H4_STRONG_OB",      # XAUUSD H4
    13: "M30_STRONG_st15",   # GBPUSD M30
    14: "M30_STRONG_st15",   # EURUSD M30
    15: "M30_STRONG_st10",   # USDJPY M30
    16: "M30_STRONG_st10",   # GBPUSD M30
    17: "M30_STRONG_st10",   # USDCHF M30
    18: "MTF_STRONG",        # USDCHF H4→H1 (use detect_mtf)
    19: "H1_STRONG_st05",    # XAUUSD H1
    20: "M30_STRONG_OB",     # XAUUSD M30
    21: "MTF_STRONG",        # XAUUSD H4→H1
    22: "MTF_STRONG",        # EURUSD H4→H1
    23: "M15_COMBO_st15",    # GBPUSD M15
    24: "M15_COMBO_st15",    # USDCHF M15
    25: "M15_COMBO_st05",    # USDJPY M15
    26: "M15_COMBO_st10",    # EURUSD M15
    27: "M5_COMBO_st15",     # USDCHF M5
    28: "M5_COMBO_st10",     # EURUSD M5
    29: "M5_COMBO_st10",     # USDJPY M5
    30: "MTF_PCT50",         # GBPUSD H4→H1
    31: "H1_STRONG_OB",      # EURUSD H1 baseline
    32: "H1_STRONG_OB",      # XAUUSD H1
    33: "M30_STRONG_st05",   # EURUSD M30
    34: "M30_STRONG_st05",   # GBPUSD M30
    35: "M30_STRONG_st05",   # USDCHF M30
    36: "H1_STRONG_OB",      # GBPUSD H1
    37: "H1_STRONG_OB",      # XAUUSD H1
    38: "M15_STRONG_st15",   # GBPUSD M15
    39: "M15_STRONG_st15",   # USDCHF M15
    40: "M15_COMBO_st15",    # EURUSD M15
    41: "M5_COMBO_st05",     # XAUUSD M5
    42: "M5_COMBO",          # XAUUSD M5
    43: "M5_VOL40_st15",     # USDJPY M5
    44: "M5_COMBO_st15",     # GBPUSD M5
    45: "M15_STRONG_st10",   # EURUSD M15
    46: "M30_STRONG_OB",     # EURUSD M30
    47: "M30_STRONG_OB",     # GBPUSD M30
    48: "MTF_PCT50",         # XAUUSD H4→H1
    49: "H1_DUAL",           # EURUSD H1
    50: "M5_STRONG_st15",    # EURUSD M5
}


def detect_with_preset(
    high, low, open_, close, times=None, preset: str = "H1_STRONG_st10"
) -> List[S19Signal]:
    """Run detector with a named PRESET (single-TF)."""
    if preset not in PRESETS:
        raise ValueError(
            f"Unknown preset '{preset}'. "
            f"Available: {sorted(PRESETS.keys())}"
        )
    return detect_s19_signals(high, low, open_, close, times=times, **PRESETS[preset])


def list_presets() -> List[str]:
    return sorted(PRESETS.keys())


# ─────────────────────────────────────────────────────────────
# Alert-bot helpers
# ─────────────────────────────────────────────────────────────

def get_latest_signal(signals: List[S19Signal], min_bar: int = 0) -> Optional[S19Signal]:
    """Return the most recent signal (optionally only after min_bar)."""
    if not signals:
        return None
    recent = [s for s in signals if s.entry_bar >= min_bar]
    if not recent:
        return None
    return recent[-1]


def format_alert(
    sig: S19Signal,
    symbol: str = "",
    tf: str = "",
    preset: str = "",
    bar_time: str = "",
) -> str:
    """Human-readable alert string for Telegram / Discord / log."""
    side = "LONG 🟢" if sig.direction == 1 else "SHORT 🔴"
    lines = [
        f"S19 SIGNAL — {side}",
        f"Symbol : {symbol or '?'}",
        f"TF     : {tf or '?'}",
        f"Preset : {preset or '?'}",
        f"Entry  : {sig.entry_price:.5f}",
        f"Stop   : {sig.stop:.5f}",
        f"Target : {sig.target:.5f}",
        f"Risk   : {sig.risk:.5f}  |  R:R = 1:{sig.rr}",
        f"POI    : {sig.poi_type}  |  Bias = {sig.bias}",
        f"LQ     : {sig.lq_price:.5f}",
    ]
    if bar_time:
        lines.append(f"Time   : {bar_time}")
    return "\n".join(lines)


def signal_to_dict(sig: S19Signal, symbol: str = "", tf: str = "", preset: str = "") -> dict:
    """JSON-serializable dict for APIs / DBs."""
    d = sig.to_dict()
    d["symbol"] = symbol
    d["tf"] = tf
    d["preset"] = preset
    return d


# ─────────────────────────────────────────────────────────────
# Multi-TF (H4 context → H1 entry)
# ─────────────────────────────────────────────────────────────

def _build_htf_context(high, low, close, pivot_left=5, pivot_right=5, bias_mode="EMA50_s2"):
    n = len(close)
    atr = compute_atr(high, low, close)
    e50 = ema(close, 50)
    e200 = ema(close, 200)
    pivots = find_pivots(high, low, pivot_left, pivot_right)
    bias = np.full(n, "", dtype=object)
    lq_high = np.full(n, np.nan)
    lq_low = np.full(n, np.nan)
    swing_hs, swing_ls = [], []
    p_idx = 0
    for i in range(60, n):
        conf = i - pivot_right
        while p_idx < len(pivots) and pivots[p_idx].idx <= conf:
            p = pivots[p_idx]
            (swing_hs if p.kind == "H" else swing_ls).append(p)
            p_idx += 1
        b = compute_bias(bias_mode, close, atr, e50, e200, i, swing_hs, swing_ls)
        bias[i] = b if b else ""
        if swing_hs:
            lq_high[i] = swing_hs[-1].price
        if swing_ls:
            lq_low[i] = swing_ls[-1].price
    return bias, lq_high, lq_low


def _map_htf_to_ltf(h4_times, h1_times, h4_bias, h4_lqh, h4_lql):
    n1 = len(h1_times)
    bias1 = np.full(n1, "", dtype=object)
    lqh1 = np.full(n1, np.nan)
    lql1 = np.full(n1, np.nan)
    j = 0
    for i in range(n1):
        t = h1_times[i]
        while j + 1 < len(h4_times) and h4_times[j + 1] <= t:
            j += 1
        if j < len(h4_times) and h4_times[j] <= t:
            bias1[i] = h4_bias[j]
            lqh1[i] = h4_lqh[j]
            lql1[i] = h4_lql[j]
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
    bias_mode: str = "EMA50_s2",
) -> List[S19Signal]:
    """
    Multi-TF detector:
      H4 → bias + liquidity pools
      H1 → raid of H4 LQ → BOS + Strong OB near LQ → entry
    """
    bias4, lqh4, lql4 = _build_htf_context(
        high4, low4, close4, h4_pivot, h4_pivot, bias_mode=bias_mode
    )
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


MTF_PRESETS = {
    "MTF_STRONG": dict(
        h4_pivot=5, h1_pivot=5, rr=2.5, min_disp_atr=0.95,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.20, max_poi_age=40,
        sl_buffer_atr=0.12, bias_mode="EMA50_s2",
    ),
    "MTF_STRONG_st10": dict(
        h4_pivot=5, h1_pivot=5, rr=2.5, min_disp_atr=0.95,
        ob_min_body=0.55, bos_body_min=0.40, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.20, max_poi_age=40,
        sl_buffer_atr=0.12, bias_mode="EMA50_st10",
    ),
    "MTF_PCT50": dict(
        h4_pivot=5, h1_pivot=5, rr=2.5, min_disp_atr=0.85,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="ALL", vol_min_pct=0.0, max_poi_age=40,
        sl_buffer_atr=0.12, bias_mode="EMA50_s2",
    ),
    "MTF_PCT50_LN": dict(
        h4_pivot=5, h1_pivot=5, rr=2.5, min_disp_atr=0.85,
        ob_min_body=0.50, bos_body_min=0.35, bos_mode="PCT50",
        session="LONDON_NY", vol_min_pct=0.0, max_poi_age=40,
        sl_buffer_atr=0.12, bias_mode="EMA50_s2",
    ),
    "MTF_FULL": dict(
        h4_pivot=5, h1_pivot=5, rr=2.0, min_disp_atr=0.80,
        ob_min_body=0.45, bos_body_min=0.30, bos_mode="FULL",
        session="ALL", vol_min_pct=0.0, max_poi_age=40,
        sl_buffer_atr=0.12, bias_mode="EMA50_s2",
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


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("S19 production detector ready for signal-alert bots.")
    print(f"\nSingle-TF presets ({len(PRESETS)}):")
    for name in sorted(PRESETS):
        bm = PRESETS[name].get("bias_mode", "EMA50_s2")
        print(f"  • {name:22s}  bias={bm}")
    print(f"\nMTF presets ({len(MTF_PRESETS)}):")
    for name in sorted(MTF_PRESETS):
        print(f"  • {name}")
    print(f"\nTop-50 rank → preset map: {len(TOP50_PRESETS)} entries")
    print("\nBot example:")
    print('  sigs = detect_with_preset(h, l, o, c, times, preset="H1_STRONG_st10")')
    print("  latest = get_latest_signal(sigs)")
    print('  if latest: print(format_alert(latest, "EURUSD", "H1", "H1_STRONG_st10"))')
