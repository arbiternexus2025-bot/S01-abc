#!/usr/bin/env python3
"""S09 Supply & Demand + Wick Rejection Filter"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass

@dataclass
class SDZone:
    direction: int
    proximal: float
    distal: float
    base_start: int
    base_end: int
    created_bar: int
    structure: str
    base_bars: int
    impulse_atr: float
    zone_height_atr: float

@dataclass
class SDSignal:
    direction: int
    entry_bar: int
    entry_price: float
    stop: float
    target: float
    risk: float
    structure: str
    base_bars: int
    rr: float
    impulse_atr: float
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
    atr[length-1] = np.mean(tr[:length])
    for i in range(length, n):
        atr[i] = (atr[i-1] * (length-1) + tr[i]) / length
    return atr

def detect_sd_zones(high, low, open_, close, atr,
                    min_impulse_atr=1.5, max_base_bars=5, min_base_bars=2,
                    max_base_atr=1.1, min_zone_atr=0.25,
                    body_mult=0.55, range_mult=0.70):
    n = len(close)
    zones = []
    i = 40
    while i < n - 3:
        if np.isnan(atr[i]) or atr[i] < 1e-9:
            i += 1
            continue
        a = atr[i]
        range_i = high[i] - low[i]
        body_up = close[i] - open_[i]
        body_dn = open_[i] - close[i]

        if (body_up > body_mult * a and range_i > range_mult * a and close[i] > high[i-1]):
            found = False
            for bl in range(min_base_bars, max_base_bars + 1):
                bs = i - bl
                if bs < 8:
                    break
                be = i - 1
                b_high = float(np.max(high[bs:be+1]))
                b_low  = float(np.min(low[bs:be+1]))
                b_range = b_high - b_low
                if b_range > max_base_atr * a or b_range < 1e-9:
                    continue
                bodies_h = np.maximum(open_[bs:be+1], close[bs:be+1])
                prox = float(np.max(bodies_h))
                dist = b_low
                if prox <= dist:
                    continue
                imp = (close[i] - b_low) / a
                if imp < min_impulse_atr:
                    continue
                zone_h = (prox - dist) / a
                if zone_h < min_zone_atr:
                    continue
                struct = "DBR" if (bs > 4 and close[bs-1] < close[max(0, bs-5)]) else "RBR"
                zones.append(SDZone(1, prox, dist, bs, be, i, struct, bl, imp, zone_h))
                found = True
                i += 2
                break
            if not found:
                i += 1
            continue

        if (body_dn > body_mult * a and range_i > range_mult * a and close[i] < low[i-1]):
            found = False
            for bl in range(min_base_bars, max_base_bars + 1):
                bs = i - bl
                if bs < 8:
                    break
                be = i - 1
                b_high = float(np.max(high[bs:be+1]))
                b_low  = float(np.min(low[bs:be+1]))
                b_range = b_high - b_low
                if b_range > max_base_atr * a or b_range < 1e-9:
                    continue
                bodies_l = np.minimum(open_[bs:be+1], close[bs:be+1])
                prox = float(np.min(bodies_l))
                dist = b_high
                if prox >= dist:
                    continue
                imp = (b_high - close[i]) / a
                if imp < min_impulse_atr:
                    continue
                zone_h = (dist - prox) / a
                if zone_h < min_zone_atr:
                    continue
                struct = "RBD" if (bs > 4 and close[bs-1] > close[max(0, bs-5)]) else "DBD"
                zones.append(SDZone(-1, prox, dist, bs, be, i, struct, bl, imp, zone_h))
                found = True
                i += 2
                break
            if not found:
                i += 1
            continue
        i += 1
    return zones

def generate_signals_with_wick(high, low, open_, close, atr, zones,
                               rr=2.5, max_zone_age=120, min_impulse_atr=1.5, wick_mult=0.50):
    n = len(close)
    signals = []
    last_exit = -1
    seen = set()

    for z in sorted(zones, key=lambda x: x.created_bar):
        if z.created_bar in seen or z.impulse_atr < min_impulse_atr:
            continue
        for j in range(z.created_bar + 2, min(n, z.created_bar + max_zone_age)):
            if j <= last_exit:
                continue
            if not (low[j] <= z.proximal <= high[j]):
                continue

            a = atr[j]
            if np.isnan(a) or a < 1e-9:
                continue

            if z.direction == 1:
                lower_wick = min(open_[j], close[j]) - low[j]
                if lower_wick < wick_mult * a:
                    continue
                wick_val = lower_wick / a
            else:
                upper_wick = high[j] - max(open_[j], close[j])
                if upper_wick < wick_mult * a:
                    continue
                wick_val = upper_wick / a

            entry = z.proximal
            risk = abs(entry - z.distal)
            if risk < 0.20 * a or risk > 4.0 * a:
                break

            target = entry + z.direction * risk * rr
            signals.append(SDSignal(
                z.direction, j, entry, z.distal, target, risk,
                z.structure, z.base_bars, rr, z.impulse_atr, wick_val
            ))
            last_exit = j + max(6, int(10 * rr))
            seen.add(z.created_bar)
            break
    return signals

def detect_s09_signals(high, low, open_, close, wick_mult=0.50, rr=2.5, min_impulse_atr=1.5):
    atr = compute_atr(high, low, close)
    zones = detect_sd_zones(high, low, open_, close, atr, min_impulse_atr=min_impulse_atr)
    return generate_signals_with_wick(
        high, low, open_, close, atr, zones,
        rr=rr, wick_mult=wick_mult, min_impulse_atr=min_impulse_atr
    )
