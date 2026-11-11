#!/usr/bin/env python3
"""
MARIO STRIKE — Live dual-phase engine
=====================================
Phase 1  WATCH  : POI armed, price has not touched yet → prepare
Phase 2  ENTRY  : Touch + rejection confirmed           → trade plan

Built on Mario_Pure_detection (Edge Lab research).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from Mario_Pure_detection import (
    MarioPureDetector, DetectorConfig, Direction, POIType,
    _body_ratio, _atr, _pivots,
)


@dataclass
class WatchEvent:
    phase: str              # "WATCH" | "ENTRY"
    market: str
    timeframe: str
    direction: str          # LONG / SHORT
    poi_type: str
    poi_top: float
    poi_bot: float
    entry: float
    stop: float
    target: float
    risk: float
    rr: float
    sweep_level: float
    bos_bar: int
    event_bar: int
    bars_ago: int
    bars_left: int
    atr: float

    def key(self) -> str:
        return f"{self.phase}|{self.market}|{self.direction}|{self.poi_bot:.5f}|{self.poi_top:.5f}"


def arrays_to_df(ohlc: dict) -> pd.DataFrame:
    n = len(ohlc["close"])
    times = ohlc.get("time")
    if times is None:
        now = datetime.now(timezone.utc).timestamp()
        times = np.array([now - (n - 1 - i) * 3600 for i in range(n)])
    tlist = []
    for t in times:
        try:
            if hasattr(t, "to_pydatetime"):
                tlist.append(pd.Timestamp(t))
            elif isinstance(t, (int, float)) and float(t) > 1e9:
                tlist.append(pd.Timestamp(datetime.fromtimestamp(float(t), tz=timezone.utc)))
            else:
                tlist.append(pd.Timestamp(t))
        except Exception:
            tlist.append(pd.Timestamp(datetime.now(timezone.utc)))
    return pd.DataFrame({
        "Time": tlist,
        "Open": np.asarray(ohlc["open"], dtype=float),
        "High": np.asarray(ohlc["high"], dtype=float),
        "Low": np.asarray(ohlc["low"], dtype=float),
        "Close": np.asarray(ohlc["close"], dtype=float),
    })


def _scan_structure(df: pd.DataFrame, cfg: DetectorConfig, market: str, timeframe: str):
    """
    Walk the chart once and yield both WATCH (armed POI) and ENTRY events
    on the most recent bars.
    """
    o = df["Open"].values.astype(float)
    h = df["High"].values.astype(float)
    l = df["Low"].values.astype(float)
    c = df["Close"].values.astype(float)
    n = len(c)
    atr = _atr(h, l, c)
    ph, pl = _pivots(h, l, cfg.pivot_left, cfg.pivot_right)
    if len(ph) < 2 or len(pl) < 2:
        return [], []

    watches: List[WatchEvent] = []
    entries: List[WatchEvent] = []
    last_sig = -999
    swing_h: list = []
    swing_l: list = []
    pi_h = pi_l = 0

    start = max(100, cfg.pivot_left + cfg.pivot_right + 5)

    for i in range(start, n):
        if np.isnan(atr[i]) or atr[i] < 1e-12:
            continue
        a = float(atr[i])
        conf = i - cfg.pivot_right
        while pi_h < len(ph) and ph[pi_h][0] <= conf:
            swing_h.append(ph[pi_h]); pi_h += 1
        while pi_l < len(pl) and pl[pi_l][0] <= conf:
            swing_l.append(pl[pi_l]); pi_l += 1
        if not swing_h or not swing_l:
            continue

        # ── SHORT path ──
        short_w, short_e = _path_short(
            i, o, h, l, c, a, atr, swing_h, swing_l, last_sig, cfg, market, timeframe, n
        )
        if short_e is not None:
            entries.append(short_e)
            last_sig = short_e.event_bar
        elif short_w is not None:
            watches.append(short_w)

        # ── LONG path ──
        long_w, long_e = _path_long(
            i, o, h, l, c, a, atr, swing_h, swing_l, last_sig, cfg, market, timeframe, n
        )
        if long_e is not None:
            entries.append(long_e)
            last_sig = long_e.event_bar
        elif long_w is not None:
            watches.append(long_w)

    return watches, entries


def _path_long(i, o, h, l, c, a, atr, swing_h, swing_l, last_sig, cfg, market, timeframe, n):
    lql = swing_l[-1]
    raid_bar = -1
    for j in range(max(lql[0] + 1, i - 28), i + 1):
        if l[j] < lql[1]:
            raid_bar = j
            break
    if raid_bar <= last_sig:
        return None, None

    bos_bar = -1
    for k in range(raid_bar + 1, i + 1):
        if c[k] > swing_h[-1][1] and _body_ratio(o[k], c[k], h[k], l[k]) >= cfg.bos_body_min:
            bos_bar = k
            break
    if bos_bar < 0:
        return None, None
    if (c[bos_bar] - l[raid_bar]) < cfg.min_disp_atr * a:
        return None, None

    poi_top = poi_bot = None
    poi_type = None
    for m in range(bos_bar - 1, max(raid_bar - 3, bos_bar - 18), -1):
        if c[m] < o[m] and _body_ratio(o[m], c[m], h[m], l[m]) >= cfg.ob_body_min:
            poi_top, poi_bot = float(h[m]), float(l[m])
            poi_type = "OB"
            break
    if poi_top is None and cfg.allow_fvg and bos_bar >= 2:
        if l[bos_bar] > h[bos_bar - 2]:
            poi_bot = float(h[bos_bar - 2])
            poi_top = float(l[bos_bar])
            if poi_top < poi_bot:
                poi_top, poi_bot = poi_bot, poi_top
            poi_type = "FVG"
    if poi_top is None:
        return None, None

    entry = (poi_top + poi_bot) / 2.0
    stop = poi_bot - cfg.sl_buffer_atr * a
    risk = entry - stop
    if not (cfg.min_risk_atr * a <= risk <= cfg.max_risk_atr * a):
        return None, None
    target = entry + cfg.rr * risk

    # Scan for rejection entry up to current bar
    entry_bar = -1
    for e in range(bos_bar, min(bos_bar + cfg.max_poi_age, i + 1)):
        touched = l[e] <= poi_top and h[e] >= poi_bot
        if cfg.require_rejection:
            rng = h[e] - l[e]
            wick_ok = (c[e] - l[e]) >= cfg.rej_wick_ratio * rng if rng > 0 else False
            touched = touched and (c[e] > o[e]) and wick_ok
        if touched and e > last_sig + cfg.cooldown_bars:
            entry_bar = e
            break

    age = i - bos_bar
    if age > cfg.max_poi_age:
        return None, None

    # Only surface events near the right edge of the series
    if entry_bar >= 0 and entry_bar >= n - 4:
        return None, WatchEvent(
            phase="ENTRY", market=market, timeframe=timeframe, direction="LONG",
            poi_type=poi_type or "OB", poi_top=poi_top, poi_bot=poi_bot,
            entry=entry, stop=stop, target=target, risk=risk, rr=cfg.rr,
            sweep_level=float(lql[1]), bos_bar=bos_bar, event_bar=entry_bar,
            bars_ago=n - 1 - entry_bar, bars_left=max(0, cfg.max_poi_age - (entry_bar - bos_bar)),
            atr=a,
        )

    # WATCH: POI exists, not yet touched through current bar
    if entry_bar < 0 and i >= n - 3:
        already = any(l[e] <= poi_top for e in range(bos_bar, i + 1))
        if not already:
            return WatchEvent(
                phase="WATCH", market=market, timeframe=timeframe, direction="LONG",
                poi_type=poi_type or "OB", poi_top=poi_top, poi_bot=poi_bot,
                entry=entry, stop=stop, target=target, risk=risk, rr=cfg.rr,
                sweep_level=float(lql[1]), bos_bar=bos_bar, event_bar=i,
                bars_ago=n - 1 - i, bars_left=max(0, cfg.max_poi_age - age),
                atr=a,
            ), None
    return None, None


def _path_short(i, o, h, l, c, a, atr, swing_h, swing_l, last_sig, cfg, market, timeframe, n):
    lqh = swing_h[-1]
    raid_bar = -1
    for j in range(max(lqh[0] + 1, i - 28), i + 1):
        if h[j] > lqh[1]:
            raid_bar = j
            break
    if raid_bar <= last_sig:
        return None, None

    bos_bar = -1
    for k in range(raid_bar + 1, i + 1):
        if c[k] < swing_l[-1][1] and _body_ratio(o[k], c[k], h[k], l[k]) >= cfg.bos_body_min:
            bos_bar = k
            break
    if bos_bar < 0:
        return None, None
    if (h[raid_bar] - c[bos_bar]) < cfg.min_disp_atr * a:
        return None, None

    poi_top = poi_bot = None
    poi_type = None
    for m in range(bos_bar - 1, max(raid_bar - 3, bos_bar - 18), -1):
        if c[m] > o[m] and _body_ratio(o[m], c[m], h[m], l[m]) >= cfg.ob_body_min:
            poi_top, poi_bot = float(h[m]), float(l[m])
            poi_type = "OB"
            break
    if poi_top is None and cfg.allow_fvg and bos_bar >= 2:
        if h[bos_bar] < l[bos_bar - 2]:
            poi_top = float(l[bos_bar - 2])
            poi_bot = float(h[bos_bar])
            if poi_top < poi_bot:
                poi_top, poi_bot = poi_bot, poi_top
            poi_type = "FVG"
    if poi_top is None:
        return None, None

    entry = (poi_top + poi_bot) / 2.0
    stop = poi_top + cfg.sl_buffer_atr * a
    risk = stop - entry
    if not (cfg.min_risk_atr * a <= risk <= cfg.max_risk_atr * a):
        return None, None
    target = entry - cfg.rr * risk

    entry_bar = -1
    for e in range(bos_bar, min(bos_bar + cfg.max_poi_age, i + 1)):
        touched = h[e] >= poi_bot and l[e] <= poi_top
        if cfg.require_rejection:
            rng = h[e] - l[e]
            wick_ok = (h[e] - c[e]) >= cfg.rej_wick_ratio * rng if rng > 0 else False
            touched = touched and (c[e] < o[e]) and wick_ok
        if touched and e > last_sig + cfg.cooldown_bars:
            entry_bar = e
            break

    age = i - bos_bar
    if age > cfg.max_poi_age:
        return None, None

    if entry_bar >= 0 and entry_bar >= n - 4:
        return None, WatchEvent(
            phase="ENTRY", market=market, timeframe=timeframe, direction="SHORT",
            poi_type=poi_type or "OB", poi_top=poi_top, poi_bot=poi_bot,
            entry=entry, stop=stop, target=target, risk=risk, rr=cfg.rr,
            sweep_level=float(lqh[1]), bos_bar=bos_bar, event_bar=entry_bar,
            bars_ago=n - 1 - entry_bar, bars_left=max(0, cfg.max_poi_age - (entry_bar - bos_bar)),
            atr=a,
        )

    if entry_bar < 0 and i >= n - 3:
        already = any(h[e] >= poi_bot for e in range(bos_bar, i + 1))
        if not already:
            return WatchEvent(
                phase="WATCH", market=market, timeframe=timeframe, direction="SHORT",
                poi_type=poi_type or "OB", poi_top=poi_top, poi_bot=poi_bot,
                entry=entry, stop=stop, target=target, risk=risk, rr=cfg.rr,
                sweep_level=float(lqh[1]), bos_bar=bos_bar, event_bar=i,
                bars_ago=n - 1 - i, bars_left=max(0, cfg.max_poi_age - age),
                atr=a,
            ), None
    return None, None


def scan(ohlc: dict, market: str, timeframe: str) -> List[WatchEvent]:
    """Public API for the live runner."""
    if ohlc is None or len(ohlc.get("close", [])) < 120:
        return []
    if "open" not in ohlc:
        ohlc = dict(ohlc)
        ohlc["open"] = ohlc["close"]
    df = arrays_to_df(ohlc)
    cfg = DetectorConfig().for_timeframe(timeframe)
    watches, entries = _scan_structure(df, cfg, market, timeframe)
    # Prefer ENTRY over WATCH for same direction; keep freshest
    out: Dict[str, WatchEvent] = {}
    for ev in watches + entries:
        k = f"{ev.market}|{ev.direction}"
        if k not in out:
            out[k] = ev
        else:
            # ENTRY beats WATCH; newer bar wins ties
            cur = out[k]
            if ev.phase == "ENTRY" and cur.phase == "WATCH":
                out[k] = ev
            elif ev.phase == cur.phase and ev.event_bar >= cur.event_bar:
                out[k] = ev
    return list(out.values())
