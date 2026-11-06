#!/usr/bin/env python3
"""
S19 Watch / Armed Detection
===========================
Emits a setup when the full S19 sequence is ready but price has NOT
yet touched the Order Block / FVG (POI).

Sequence complete when:
  1. Bias aligned (EMA50 slope)
  2. Liquidity raid done
  3. BOS confirmed
  4. Strong OB (or FVG fallback) identified
  5. PCT50 pullback satisfied (if required)
  6. POI not yet touched → ARMED (alert for analysis)

Uses the same parameter names as S19_pattern_detection.PRESETS.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

from S19_pattern_detection import (
    compute_atr, ema, find_pivots, detect_fvg, atr_percentile_rank,
    session_ok, compute_bias, PRESETS,
)


@dataclass
class ArmedSetup:
    direction: int          # +1 long, -1 short
    armed_bar: int          # bar when POI became valid
    bos_bar: int
    poi_top: float
    poi_bot: float
    entry: float            # mid of POI (reference only)
    stop: float
    target: float
    risk: float
    rr: float
    poi_type: str
    bias: str
    lq_price: float
    bars_until_expiry: int  # remaining bars in max_poi_age window

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["side"] = "LONG" if self.direction == 1 else "SHORT"
        return d


def detect_armed_setups(
    high, low, open_, close, times=None,
    pivot_left: int = 5,
    pivot_right: int = 5,
    rr: float = 5.0,
    min_disp_atr: float = 0.90,
    ob_min_body: float = 0.55,
    bos_body_min: float = 0.40,
    bos_mode: str = "PCT50",
    bos_pct: float = 0.50,
    session: str = "ALL",
    vol_min_pct: float = 0.0,
    max_poi_age: int = 36,
    sl_buffer_atr: float = 0.12,
    allow_fvg_fallback: bool = True,
    one_trade_cooldown: int = 8,
    bias_mode: str = "EMA50_st15",
    **kwargs,
) -> List[ArmedSetup]:
    """
    Return currently ARMED setups (POI ready, not yet touched).
    Only setups still valid as of the last bar are returned.
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

    armed: List[ArmedSetup] = []
    swing_hs: list = []
    swing_ls: list = []
    right = pivot_right
    p_idx = 0
    last_exit = -1

    i = 60
    while i < n:
        if np.isnan(atr[i]) or atr[i] < 1e-9:
            i += 1
            continue
        a = float(atr[i])

        if times is not None and session != "ALL":
            try:
                t_ = times[i]
                if hasattr(t_, "hour"):
                    h = int(t_.hour)
                else:
                    from datetime import datetime, timezone
                    h = datetime.fromtimestamp(float(t_), tz=timezone.utc).hour
            except Exception:
                h = 12
            if not session_ok(h, session):
                i += 1
                continue

        if vol_min_pct > 0 and atr_rank is not None:
            if np.isnan(atr_rank[i]) or atr_rank[i] < vol_min_pct:
                i += 1
                continue

        # Update confirmed pivots
        while p_idx < len(pivots) and pivots[p_idx].idx + right <= i:
            pv = pivots[p_idx]
            if pv.kind == "H":
                swing_hs.append(pv)
            else:
                swing_ls.append(pv)
            p_idx += 1

        bias = compute_bias(bias_mode, close, atr, e50, e200, i, swing_hs, swing_ls)

        # ── LONG ──
        if bias == "BULL" and swing_ls and swing_hs:
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
                                    # Has POI been touched yet?
                                    touched = False
                                    for e in range(bos_bar, i + 1):
                                        if low[e] <= poi_top:
                                            touched = True
                                            break
                                    age = i - bos_bar
                                    if (not touched) and age <= max_poi_age:
                                        # Only keep if still armed on the latest bars
                                        if i >= n - 3:
                                            armed.append(ArmedSetup(
                                                direction=1,
                                                armed_bar=i,
                                                bos_bar=bos_bar,
                                                poi_top=poi_top,
                                                poi_bot=poi_bot,
                                                entry=entry,
                                                stop=stop,
                                                target=entry + rr * risk,
                                                risk=risk,
                                                rr=rr,
                                                poi_type=poi_type,
                                                bias=bias,
                                                lq_price=float(lq.price),
                                                bars_until_expiry=max_poi_age - age,
                                            ))

        # ── SHORT ──
        if bias == "BEAR" and swing_hs and swing_ls:
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
                                    touched = False
                                    for e in range(bos_bar, i + 1):
                                        if high[e] >= poi_bot:
                                            touched = True
                                            break
                                    age = i - bos_bar
                                    if (not touched) and age <= max_poi_age:
                                        if i >= n - 3:
                                            armed.append(ArmedSetup(
                                                direction=-1,
                                                armed_bar=i,
                                                bos_bar=bos_bar,
                                                poi_top=poi_top,
                                                poi_bot=poi_bot,
                                                entry=entry,
                                                stop=stop,
                                                target=entry - rr * risk,
                                                risk=risk,
                                                rr=rr,
                                                poi_type=poi_type,
                                                bias=bias,
                                                lq_price=float(lq.price),
                                                bars_until_expiry=max_poi_age - age,
                                            ))
        i += 1

    # De-dupe: keep best (newest) per direction
    best: Dict[int, ArmedSetup] = {}
    for s in armed:
        if s.direction not in best or s.armed_bar >= best[s.direction].armed_bar:
            best[s.direction] = s
    return list(best.values())


def detect_armed_with_preset(high, low, open_, close, times=None, preset: str = "H1_STRONG_st15_rr8"):
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset {preset}")
    params = PRESETS[preset].copy()
    return detect_armed_setups(high, low, open_, close, times, **params)
