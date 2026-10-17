#!/usr/bin/env python3
"""S09 detector — per-mode geometry params from promote list"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass

@dataclass
class SDZone:
    direction: int
    proximal: float
    distal: float
    created_bar: int
    structure: str
    impulse_atr: float

@dataclass
class SDSignal:
    direction: int
    entry_bar: int
    entry_price: float
    stop: float
    target: float
    risk: float
    structure: str
    rr: float
    wick_atr: float

def compute_atr(high, low, close, length=14):
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    atr = np.full(n, np.nan)
    if n < length:
        return atr
    atr[length - 1] = np.mean(tr[:length])
    for i in range(length, n):
        atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr

def compute_ema(close, length):
    n = len(close)
    ema = np.full(n, np.nan)
    if n < length:
        return ema
    ema[length - 1] = np.mean(close[:length])
    k = 2.0 / (length + 1)
    for i in range(length, n):
        ema[i] = close[i] * k + ema[i - 1] * (1 - k)
    return ema

def h4_bias(high, low, close):
    if len(close) < 60:
        return 0
    ema20 = compute_ema(close, 20)
    ema50 = compute_ema(close, 50)
    i = len(close) - 1
    if np.isnan(ema20[i]) or np.isnan(ema50[i]):
        return 0
    h1 = float(np.max(high[i - 7:i + 1]))
    h0 = float(np.max(high[i - 15:i - 7]))
    l1 = float(np.min(low[i - 7:i + 1]))
    l0 = float(np.min(low[i - 15:i - 7]))
    bull_struct = (h1 > h0) or (l1 > l0)
    bear_struct = (l1 < l0) or (h1 < h0)
    if ema20[i] > ema50[i] and close[i] > ema50[i] and bull_struct:
        return 1
    if ema20[i] < ema50[i] and close[i] < ema50[i] and bear_struct:
        return -1
    return 0

def detect_sd_zones(high, low, open_, close, atr,
                    min_impulse_atr=1.3, body_mult=0.50, range_mult=0.65,
                    max_base_atr=1.3, min_zone_atr=0.20,
                    min_base_bars=1, max_base_bars=6):
    n = len(close)
    zones = []
    i = 40
    while i < n - 1:
        if np.isnan(atr[i]) or atr[i] < 1e-9:
            i += 1
            continue
        a = atr[i]
        rng = high[i] - low[i]
        body_up = close[i] - open_[i]
        body_dn = open_[i] - close[i]

        if body_up >= body_mult * a and rng >= range_mult * a and close[i] > high[i - 1]:
            found = False
            for bl in range(min_base_bars, max_base_bars + 1):
                bs = i - bl
                if bs < 5:
                    break
                be = i - 1
                b_high = float(np.max(high[bs:be + 1]))
                b_low = float(np.min(low[bs:be + 1]))
                if (b_high - b_low) > max_base_atr * a:
                    continue
                prox = float(np.max(np.maximum(open_[bs:be + 1], close[bs:be + 1])))
                dist = b_low
                if prox <= dist:
                    continue
                imp = (close[i] - b_low) / a
                if imp < min_impulse_atr:
                    continue
                if (prox - dist) / a < min_zone_atr:
                    continue
                zones.append(SDZone(1, prox, dist, i, "DEM", imp))
                found = True
                i += 2
                break
            if not found:
                i += 1
            continue

        if body_dn >= body_mult * a and rng >= range_mult * a and close[i] < low[i - 1]:
            found = False
            for bl in range(min_base_bars, max_base_bars + 1):
                bs = i - bl
                if bs < 5:
                    break
                be = i - 1
                b_high = float(np.max(high[bs:be + 1]))
                b_low = float(np.min(low[bs:be + 1]))
                if (b_high - b_low) > max_base_atr * a:
                    continue
                prox = float(np.min(np.minimum(open_[bs:be + 1], close[bs:be + 1])))
                dist = b_high
                if prox >= dist:
                    continue
                imp = (b_high - close[i]) / a
                if imp < min_impulse_atr:
                    continue
                if (dist - prox) / a < min_zone_atr:
                    continue
                zones.append(SDZone(-1, prox, dist, i, "SUP", imp))
                found = True
                i += 2
                break
            if not found:
                i += 1
            continue
        i += 1
    return zones

def generate_signals(high, low, open_, close, atr, zones,
                     wick_mult=0.50, max_zone_age=120, require_close=False, rr=2.0):
    n = len(close)
    signals = []
    seen = set()
    last_exit = -1

    for z in sorted(zones, key=lambda x: x.created_bar):
        if z.created_bar in seen:
            continue
        for j in range(z.created_bar + 2, min(n, z.created_bar + max_zone_age + 1)):
            if j <= last_exit:
                continue
            if not (low[j] <= z.proximal <= high[j]):
                continue

            seen.add(z.created_bar)
            a = atr[j]
            if np.isnan(a) or a < 1e-9:
                break

            if z.direction == 1:
                wick = min(open_[j], close[j]) - low[j]
                if wick < wick_mult * a:
                    break
                wick_val = wick / a
            else:
                wick = high[j] - max(open_[j], close[j])
                if wick < wick_mult * a:
                    break
                wick_val = wick / a

            if require_close:
                if z.direction == 1 and close[j] < open_[j]:
                    break
                if z.direction == -1 and close[j] > open_[j]:
                    break

            entry = z.proximal
            risk = abs(entry - z.distal)
            if risk < 0.20 * a or risk > 4.0 * a:
                break

            target = entry + z.direction * risk * rr
            signals.append(SDSignal(
                z.direction, j, entry, z.distal, target, risk,
                z.structure, rr, wick_val
            ))
            last_exit = j + max(6, int(10 * rr))
            break
    return signals

def detect_s09(high, low, open_, close,
               wick_mult=0.50, max_zone_age=120, require_close=False, rr=2.0,
               atr_len=14, min_imp=1.3, body=0.50, rng=0.65,
               max_ba=1.3, min_z=0.20):
    atr = compute_atr(high, low, close, length=atr_len)
    zones = detect_sd_zones(
        high, low, open_, close, atr,
        min_impulse_atr=min_imp, body_mult=body, range_mult=rng,
        max_base_atr=max_ba, min_zone_atr=min_z
    )
    signals = generate_signals(
        high, low, open_, close, atr, zones,
        wick_mult=wick_mult, max_zone_age=max_zone_age,
        require_close=require_close, rr=rr
    )
    return signals, zones, atr
