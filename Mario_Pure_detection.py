#!/usr/bin/env python3
"""
================================================================================
  MARIO PURE  |  Edge Lab Research
  Production Detection Module  •  Alert-Engine Ready
================================================================================

Strategy (locked from research):
  1. Liquidity Sweep of a confirmed swing
  2. Break of Structure (BOS) with body-quality filter
  3. Identify Point of Interest (POI):
       - Primary  : Strong opposing Order Block (body ratio filter)
       - Fallback : Fair Value Gap (3-candle imbalance)
  4. Entry on first touch of the POI that also shows rejection
  5. Stop beyond the POI + ATR buffer
  6. Fixed Risk:Reward target

No inducement filter.  No EMA bias.
Direction comes purely from Sweep + BOS.

MODES
─────
  SINGLE   – Structure + rejection on the same timeframe
  DUAL     – HTF structure (Sweep+BOS+POI) + LTF rejection confirmation
             Recommended live mode for lower latency:
             HTF = H1, LTF = M30

Recommended live defaults (from RR-sweep + Dual-TF research):
  M30          → RR 3.0   (single)
  H1           → RR 3.5   (single)
  H1 → M30     → RR 3.5   (dual – preferred for alerts)
  H4           → RR 4.5   (single)
  H4 → M30/H1  → RR 4.5   (dual)

Author  : Edge Lab Research
Version : 2.0.0  (Production – Dual-TF)
Date    : 2026-11-12
================================================================================
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
import json
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
#  ENUMS & DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

class Direction(Enum):
    LONG  = 1
    SHORT = -1


class POIType(Enum):
    ORDER_BLOCK = "OB"
    FVG         = "FVG"


class Mode(Enum):
    SINGLE = "SINGLE"
    DUAL   = "DUAL"


@dataclass
class Signal:
    """Single trade signal ready for an alert engine."""
    market:       str
    timeframe:    str                 # display TF (e.g. "H1→M30" for dual)
    direction:    Direction
    poi_type:     POIType
    entry_bar:    int
    entry_time:   Any
    entry_price:  float
    stop_price:   float
    target_price: float
    risk:         float
    rr:           float
    sweep_level:  float
    bos_bar:      int
    poi_top:      float
    poi_bot:      float
    atr_at_entry: float
    mode:         str = "SINGLE"
    meta:         Dict[str, Any] = field(default_factory=dict)

    @property
    def side(self) -> str:
        return "LONG" if self.direction == Direction.LONG else "SHORT"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["direction"] = self.direction.name
        d["poi_type"]  = self.poi_type.value
        d["side"]      = self.side
        if hasattr(self.entry_time, "isoformat"):
            d["entry_time"] = self.entry_time.isoformat()
        elif hasattr(self.entry_time, "strftime"):
            d["entry_time"] = str(self.entry_time)
        return d

    def alert_message(self) -> str:
        mode_tag = f" [{self.mode}]" if self.mode == "DUAL" else ""
        return (
            f"MARIO PURE{mode_tag}  {self.side}  {self.market} {self.timeframe}\n"
            f"POI: {self.poi_type.value}  |  RR: {self.rr:.1f}\n"
            f"Entry: {self.entry_price:.5f}\n"
            f"Stop : {self.stop_price:.5f}\n"
            f"Target: {self.target_price:.5f}\n"
            f"Risk: {self.risk:.5f}"
        )

    def alert_message_rich(self) -> str:
        """Richer format matching the Telegram style used in live."""
        arrow = "▲ LONG" if self.direction == Direction.LONG else "▼ SHORT"
        colour = "🟢" if self.direction == Direction.LONG else "🔴"
        mode_tag = " · DUAL" if self.mode == "DUAL" else ""
        zone = f"{self.poi_bot:.5f} → {self.poi_top:.5f} ({self.poi_type.value})"
        return (
            f"🎯 MARIO STRIKE · ENTRY{mode_tag}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{self.market} · {self.timeframe}\n"
            f"{colour} {arrow}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Price returned into the zone and printed rejection.\n"
            f"The setup is complete.\n\n"
            f"✅ TRADE PLAN\n"
            f"• Entry area: {self.entry_price:.5f}\n"
            f"• Stop loss: {self.stop_price:.5f}\n"
            f"• Take profit: {self.target_price:.5f}\n"
            f"• Risk : Reward = 1 : {self.rr:.1f}\n\n"
            f"📍 Zone used: {zone}\n\n"
            f"🔥 ACTION\n"
            f"Primary focus: execute a {'BUY' if self.direction == Direction.LONG else 'SELL'} near {self.entry_price:.5f}.\n"
            f"Manage risk. Do not chase if price has already run far from the zone."
        )


@dataclass
class DetectorConfig:
    """All tunable parameters. Defaults = research-locked production values."""
    # Structure
    pivot_left:      int   = 5
    pivot_right:     int   = 3
    min_disp_atr:    float = 0.90
    bos_body_min:    float = 0.35
    ob_body_min:     float = 0.55
    allow_fvg:       bool  = True
    max_poi_age:     int   = 32          # HTF bars

    # Entry
    require_rejection: bool  = True
    rej_wick_ratio:    float = 0.25
    sl_buffer_atr:     float = 0.12
    cooldown_bars:     int   = 8

    # Risk
    rr:              float = 3.5

    # Safety
    min_risk_atr:    float = 0.08
    max_risk_atr:    float = 5.50

    # Dual-TF
    mode:            str   = "SINGLE"    # "SINGLE" | "DUAL"
    htf:             str   = "H1"
    ltf:             str   = "M30"

    def for_timeframe(self, tf: str) -> "DetectorConfig":
        """Return a copy with research-recommended RR for the timeframe."""
        cfg = DetectorConfig(**{k: getattr(self, k) for k in self.__dataclass_fields__})
        tf = tf.upper()
        if tf == "M30":
            cfg.rr = 3.0
        elif tf == "H1":
            cfg.rr = 3.5
        elif tf in ("H4", "D1"):
            cfg.rr = 4.5
        else:
            cfg.rr = 3.0
        return cfg

    def as_dual(self, htf: str = "H1", ltf: str = "M30") -> "DetectorConfig":
        """Return a dual-mode config (HTF structure + LTF rejection)."""
        cfg = self.for_timeframe(htf)
        cfg.mode = "DUAL"
        cfg.htf = htf.upper()
        cfg.ltf = ltf.upper()
        return cfg


# ─────────────────────────────────────────────────────────────────────────────
#  CORE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _body_ratio(o: float, c: float, h: float, l: float) -> float:
    rng = h - l
    return abs(c - o) / rng if rng > 1e-12 else 0.0


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
    tr = np.maximum(high - low,
                    np.maximum(np.abs(high - np.roll(close, 1)),
                               np.abs(low  - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atr = np.full_like(close, np.nan, dtype=float)
    if len(close) < length:
        return atr
    atr[length - 1] = np.mean(tr[:length])
    for i in range(length, len(close)):
        atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr


def _pivots(high: np.ndarray, low: np.ndarray,
            left: int = 5, right: int = 3) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """Confirmed swing highs / lows (no look-ahead beyond `right`)."""
    ph, pl = [], []
    n = len(high)
    for i in range(left, n - right):
        if high[i] >= high[i - left: i + right + 1].max():
            ph.append((i, float(high[i])))
        if low[i]  <= low [i - left: i + right + 1].min():
            pl.append((i, float(low[i])))
    return ph, pl


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN DETECTOR
# ─────────────────────────────────────────────────────────────────────────────

class MarioPureDetector:
    """
    Production detector for Mario Pure strategy.

    Usage — Single TF
    -----------------
    >>> cfg = DetectorConfig().for_timeframe("H1")
    >>> det = MarioPureDetector(cfg)
    >>> signals = det.detect(df, market="EURUSD", timeframe="H1")

    Usage — Dual TF (recommended for lower-latency alerts)
    ------------------------------------------------------
    >>> cfg = DetectorConfig().as_dual(htf="H1", ltf="M30")
    >>> det = MarioPureDetector(cfg)
    >>> signals = det.detect_dual(df_htf, df_ltf, market="EURUSD")
    """

    def __init__(self, config: Optional[DetectorConfig] = None):
        self.cfg = config or DetectorConfig()

    # ── public API ──────────────────────────────────────────────────────────

    def detect(self,
               df: pd.DataFrame,
               market: str = "UNKNOWN",
               timeframe: str = "H1") -> List[Signal]:
        """
        Single-timeframe detection.
        Required columns: Open, High, Low, Close
        Optional: Time / DatetimeIndex
        """
        self._validate(df)
        o = df["Open"].values.astype(float)
        h = df["High"].values.astype(float)
        l = df["Low"].values.astype(float)
        c = df["Close"].values.astype(float)
        n = len(c)

        times = self._extract_times(df)
        atr   = _atr(h, l, c)
        ph, pl = _pivots(h, l, self.cfg.pivot_left, self.cfg.pivot_right)

        if len(ph) < 2 or len(pl) < 2:
            return []

        signals: List[Signal] = []
        last_signal_bar = -999
        swing_h: List[Tuple[int, float]] = []
        swing_l: List[Tuple[int, float]] = []
        pi_h = pi_l = 0

        for i in range(max(100, self.cfg.pivot_left + self.cfg.pivot_right + 5), n - 2):
            if np.isnan(atr[i]) or atr[i] < 1e-12:
                continue

            conf = i - self.cfg.pivot_right
            while pi_h < len(ph) and ph[pi_h][0] <= conf:
                swing_h.append(ph[pi_h]); pi_h += 1
            while pi_l < len(pl) and pl[pi_l][0] <= conf:
                swing_l.append(pl[pi_l]); pi_l += 1
            if not swing_h or not swing_l:
                continue

            sig = self._try_short(
                i, o, h, l, c, atr, swing_h, swing_l,
                last_signal_bar, market, timeframe, times
            )
            if sig is not None:
                signals.append(sig)
                last_signal_bar = sig.entry_bar
                continue

            sig = self._try_long(
                i, o, h, l, c, atr, swing_h, swing_l,
                last_signal_bar, market, timeframe, times
            )
            if sig is not None:
                signals.append(sig)
                last_signal_bar = sig.entry_bar

        return signals

    def detect_dual(self,
                    df_htf: pd.DataFrame,
                    df_ltf: pd.DataFrame,
                    market: str = "UNKNOWN") -> List[Signal]:
        """
        Dual-timeframe detection (recommended for live alerts).

        HTF = structure (Sweep + BOS + POI)
        LTF = rejection confirmation inside the HTF POI

        This fires earlier than waiting for a full HTF candle close,
        which is the main latency fix for the free alert engine.
        """
        self._validate(df_htf)
        self._validate(df_ltf)

        pois = self._detect_htf_pois(df_htf)
        if not pois:
            return []

        return self._match_ltf_rejection(df_ltf, pois, market)

    def detect_latest(self,
                      df: pd.DataFrame,
                      market: str = "UNKNOWN",
                      timeframe: str = "H1",
                      lookback_bars: int = 5) -> List[Signal]:
        """Single-TF: only signals whose entry_bar is within the last N bars."""
        all_sigs = self.detect(df, market, timeframe)
        if not all_sigs:
            return []
        cutoff = len(df) - 1 - lookback_bars
        return [s for s in all_sigs if s.entry_bar >= cutoff]

    def detect_dual_latest(self,
                           df_htf: pd.DataFrame,
                           df_ltf: pd.DataFrame,
                           market: str = "UNKNOWN",
                           lookback_bars: int = 8) -> List[Signal]:
        """Dual-TF: only signals in the last N LTF bars (for live polling)."""
        all_sigs = self.detect_dual(df_htf, df_ltf, market)
        if not all_sigs:
            return []
        cutoff = len(df_ltf) - 1 - lookback_bars
        return [s for s in all_sigs if s.entry_bar >= cutoff]

    # ── HTF structure (for dual) ────────────────────────────────────────────

    def _detect_htf_pois(self, df: pd.DataFrame) -> List[Dict]:
        cfg = self.cfg
        o = df["Open"].values.astype(float)
        h = df["High"].values.astype(float)
        l = df["Low"].values.astype(float)
        c = df["Close"].values.astype(float)
        times = self._extract_times(df)
        n = len(c)
        atr = _atr(h, l, c)
        ph, pl = _pivots(h, l, cfg.pivot_left, cfg.pivot_right)
        if len(ph) < 2 or len(pl) < 2:
            return []

        pois: List[Dict] = []
        swing_h, swing_l = [], []
        pi_h = pi_l = 0
        last_bos = -999

        for i in range(max(100, cfg.pivot_left + cfg.pivot_right + 5), n - 2):
            if np.isnan(atr[i]) or atr[i] < 1e-12:
                continue
            conf = i - cfg.pivot_right
            while pi_h < len(ph) and ph[pi_h][0] <= conf:
                swing_h.append(ph[pi_h]); pi_h += 1
            while pi_l < len(pl) and pl[pi_l][0] <= conf:
                swing_l.append(pl[pi_l]); pi_l += 1
            if not swing_h or not swing_l:
                continue

            # SHORT structure
            lqh = swing_h[-1]
            raid = -1
            for j in range(max(lqh[0] + 1, i - 28), i + 1):
                if h[j] > lqh[1]:
                    raid = j
                    break
            if raid > last_bos:
                bos = -1
                for k in range(raid + 1, i + 1):
                    if c[k] < swing_l[-1][1] and _body_ratio(o[k], c[k], h[k], l[k]) >= cfg.bos_body_min:
                        bos = k
                        break
                if bos >= 0 and (h[raid] - c[bos]) >= cfg.min_disp_atr * atr[i]:
                    poi_top = poi_bot = None
                    ptype = None
                    for m in range(bos - 1, max(raid - 3, bos - 18), -1):
                        if c[m] > o[m] and _body_ratio(o[m], c[m], h[m], l[m]) >= cfg.ob_body_min:
                            poi_top, poi_bot = float(h[m]), float(l[m])
                            ptype = POIType.ORDER_BLOCK
                            break
                    if poi_top is None and cfg.allow_fvg and bos >= 2 and h[bos] < l[bos - 2]:
                        poi_top = float(l[bos - 2])
                        poi_bot = float(h[bos])
                        if poi_top < poi_bot:
                            poi_top, poi_bot = poi_bot, poi_top
                        ptype = POIType.FVG
                    if poi_top is not None:
                        pois.append(dict(
                            side=Direction.SHORT, bos_bar=bos, bos_time=times[bos],
                            sweep_level=lqh[1],
                            poi_top=poi_top, poi_bot=poi_bot, ptype=ptype,
                            atr=float(atr[i])
                        ))
                        last_bos = bos

            # LONG structure
            lql = swing_l[-1]
            raid = -1
            for j in range(max(lql[0] + 1, i - 28), i + 1):
                if l[j] < lql[1]:
                    raid = j
                    break
            if raid > last_bos:
                bos = -1
                for k in range(raid + 1, i + 1):
                    if c[k] > swing_h[-1][1] and _body_ratio(o[k], c[k], h[k], l[k]) >= cfg.bos_body_min:
                        bos = k
                        break
                if bos >= 0 and (c[bos] - l[raid]) >= cfg.min_disp_atr * atr[i]:
                    poi_top = poi_bot = None
                    ptype = None
                    for m in range(bos - 1, max(raid - 3, bos - 18), -1):
                        if c[m] < o[m] and _body_ratio(o[m], c[m], h[m], l[m]) >= cfg.ob_body_min:
                            poi_top, poi_bot = float(h[m]), float(l[m])
                            ptype = POIType.ORDER_BLOCK
                            break
                    if poi_top is None and cfg.allow_fvg and bos >= 2 and l[bos] > h[bos - 2]:
                        poi_bot = float(h[bos - 2])
                        poi_top = float(l[bos])
                        if poi_top < poi_bot:
                            poi_top, poi_bot = poi_bot, poi_top
                        ptype = POIType.FVG
                    if poi_top is not None:
                        pois.append(dict(
                            side=Direction.LONG, bos_bar=bos, bos_time=times[bos],
                            sweep_level=lql[1],
                            poi_top=poi_top, poi_bot=poi_bot, ptype=ptype,
                            atr=float(atr[i])
                        ))
                        last_bos = bos
        return pois

    def _match_ltf_rejection(self,
                             df_ltf: pd.DataFrame,
                             pois: List[Dict],
                             market: str) -> List[Signal]:
        cfg = self.cfg
        o = df_ltf["Open"].values.astype(float)
        h = df_ltf["High"].values.astype(float)
        l = df_ltf["Low"].values.astype(float)
        c = df_ltf["Close"].values.astype(float)
        times = self._extract_times(df_ltf)
        n = len(c)
        atr_ltf = _atr(h, l, c)

        # time → index map
        time_idx = {}
        for i, t in enumerate(times):
            ts = pd.Timestamp(t) if not isinstance(t, pd.Timestamp) else t
            time_idx[ts] = i

        sorted_times = sorted(time_idx.keys())
        signals: List[Signal] = []
        last_entry_ts = pd.Timestamp("1970-01-01")
        display_tf = f"{cfg.htf}→{cfg.ltf}"

        for poi in pois:
            bos_ts = pd.Timestamp(poi["bos_time"])
            # first LTF bar at or after BOS
            start_i = None
            for t in sorted_times:
                if t >= bos_ts:
                    start_i = time_idx[t]
                    break
            if start_i is None:
                continue

            # validity window (time-based, ~ max_poi_age HTF bars)
            # H1 → ~32 hours; H4 → ~5 days
            hours = cfg.max_poi_age * (4 if cfg.htf == "H4" else 1)
            end_ts = bos_ts + pd.Timedelta(hours=hours)

            poi_top, poi_bot = poi["poi_top"], poi["poi_bot"]
            side = poi["side"]
            atr_h = poi["atr"]

            for e in range(start_i, n):
                e_ts = pd.Timestamp(times[e])
                if e_ts > end_ts:
                    break
                if np.isnan(atr_ltf[e]):
                    continue

                if side == Direction.SHORT:
                    touched = h[e] >= poi_bot and l[e] <= poi_top
                    rng = h[e] - l[e]
                    wick_ok = (h[e] - c[e]) >= cfg.rej_wick_ratio * rng if rng > 0 else False
                    rej = touched and (c[e] < o[e]) and wick_ok
                else:
                    touched = l[e] <= poi_top and h[e] >= poi_bot
                    rng = h[e] - l[e]
                    wick_ok = (c[e] - l[e]) >= cfg.rej_wick_ratio * rng if rng > 0 else False
                    rej = touched and (c[e] > o[e]) and wick_ok

                if not rej:
                    continue
                if e_ts <= last_entry_ts + pd.Timedelta(hours=1):
                    continue

                entry = (poi_top + poi_bot) / 2.0
                if side == Direction.SHORT:
                    stop = poi_top + cfg.sl_buffer_atr * atr_h
                    risk = stop - entry
                    target = entry - cfg.rr * risk
                else:
                    stop = poi_bot - cfg.sl_buffer_atr * atr_h
                    risk = entry - stop
                    target = entry + cfg.rr * risk

                if risk <= 0:
                    continue
                if not (cfg.min_risk_atr * atr_h <= risk <= cfg.max_risk_atr * atr_h):
                    continue

                sig = Signal(
                    market=market,
                    timeframe=display_tf,
                    direction=side,
                    poi_type=poi["ptype"],
                    entry_bar=e,
                    entry_time=times[e],
                    entry_price=entry,
                    stop_price=stop,
                    target_price=target,
                    risk=risk,
                    rr=cfg.rr,
                    sweep_level=poi["sweep_level"],
                    bos_bar=poi["bos_bar"],
                    poi_top=poi_top,
                    poi_bot=poi_bot,
                    atr_at_entry=atr_h,
                    mode="DUAL",
                    meta={"htf": cfg.htf, "ltf": cfg.ltf, "bos_time": str(poi["bos_time"])}
                )
                signals.append(sig)
                last_entry_ts = e_ts
                break  # one entry per POI

        return signals

    # ── single-TF signal builders ───────────────────────────────────────────

    def _try_short(self, i, o, h, l, c, atr,
                   swing_h, swing_l, last_sig,
                   market, timeframe, times) -> Optional[Signal]:
        cfg = self.cfg
        lqh = swing_h[-1]

        raid_bar = -1
        for j in range(max(lqh[0] + 1, i - 28), i + 1):
            if h[j] > lqh[1]:
                raid_bar = j
                break
        if raid_bar <= last_sig:
            return None

        bos_bar = -1
        for k in range(raid_bar + 1, i + 1):
            if c[k] < swing_l[-1][1] and _body_ratio(o[k], c[k], h[k], l[k]) >= cfg.bos_body_min:
                bos_bar = k
                break
        if bos_bar < 0:
            return None
        if (h[raid_bar] - c[bos_bar]) < cfg.min_disp_atr * atr[i]:
            return None

        poi_top = poi_bot = None
        poi_type = None
        for m in range(bos_bar - 1, max(raid_bar - 3, bos_bar - 18), -1):
            if c[m] > o[m] and _body_ratio(o[m], c[m], h[m], l[m]) >= cfg.ob_body_min:
                poi_top, poi_bot = float(h[m]), float(l[m])
                poi_type = POIType.ORDER_BLOCK
                break
        if poi_top is None and cfg.allow_fvg and bos_bar >= 2:
            if h[bos_bar] < l[bos_bar - 2]:
                poi_top = float(l[bos_bar - 2])
                poi_bot = float(h[bos_bar])
                if poi_top < poi_bot:
                    poi_top, poi_bot = poi_bot, poi_top
                poi_type = POIType.FVG
        if poi_top is None:
            return None

        entry = (poi_top + poi_bot) / 2.0
        stop  = poi_top + cfg.sl_buffer_atr * atr[i]
        risk  = stop - entry
        if not (cfg.min_risk_atr * atr[i] <= risk <= cfg.max_risk_atr * atr[i]):
            return None

        for e in range(bos_bar, min(bos_bar + cfg.max_poi_age, len(c))):
            touched = h[e] >= poi_bot and l[e] <= poi_top
            if cfg.require_rejection:
                rng = h[e] - l[e]
                wick_ok = (h[e] - c[e]) >= cfg.rej_wick_ratio * rng if rng > 0 else False
                touched = touched and (c[e] < o[e]) and wick_ok
            if touched and e > last_sig + cfg.cooldown_bars:
                target = entry - cfg.rr * risk
                return Signal(
                    market=market, timeframe=timeframe,
                    direction=Direction.SHORT, poi_type=poi_type,
                    entry_bar=e, entry_time=times[e],
                    entry_price=entry, stop_price=stop, target_price=target,
                    risk=risk, rr=cfg.rr,
                    sweep_level=lqh[1], bos_bar=bos_bar,
                    poi_top=poi_top, poi_bot=poi_bot,
                    atr_at_entry=float(atr[i]),
                    mode="SINGLE",
                    meta={"raid_bar": raid_bar}
                )
        return None

    def _try_long(self, i, o, h, l, c, atr,
                  swing_h, swing_l, last_sig,
                  market, timeframe, times) -> Optional[Signal]:
        cfg = self.cfg
        lql = swing_l[-1]

        raid_bar = -1
        for j in range(max(lql[0] + 1, i - 28), i + 1):
            if l[j] < lql[1]:
                raid_bar = j
                break
        if raid_bar <= last_sig:
            return None

        bos_bar = -1
        for k in range(raid_bar + 1, i + 1):
            if c[k] > swing_h[-1][1] and _body_ratio(o[k], c[k], h[k], l[k]) >= cfg.bos_body_min:
                bos_bar = k
                break
        if bos_bar < 0:
            return None
        if (c[bos_bar] - l[raid_bar]) < cfg.min_disp_atr * atr[i]:
            return None

        poi_top = poi_bot = None
        poi_type = None
        for m in range(bos_bar - 1, max(raid_bar - 3, bos_bar - 18), -1):
            if c[m] < o[m] and _body_ratio(o[m], c[m], h[m], l[m]) >= cfg.ob_body_min:
                poi_top, poi_bot = float(h[m]), float(l[m])
                poi_type = POIType.ORDER_BLOCK
                break
        if poi_top is None and cfg.allow_fvg and bos_bar >= 2:
            if l[bos_bar] > h[bos_bar - 2]:
                poi_bot = float(h[bos_bar - 2])
                poi_top = float(l[bos_bar])
                if poi_top < poi_bot:
                    poi_top, poi_bot = poi_bot, poi_top
                poi_type = POIType.FVG
        if poi_top is None:
            return None

        entry = (poi_top + poi_bot) / 2.0
        stop  = poi_bot - cfg.sl_buffer_atr * atr[i]
        risk  = entry - stop
        if not (cfg.min_risk_atr * atr[i] <= risk <= cfg.max_risk_atr * atr[i]):
            return None

        for e in range(bos_bar, min(bos_bar + cfg.max_poi_age, len(c))):
            touched = l[e] <= poi_top and h[e] >= poi_bot
            if cfg.require_rejection:
                rng = h[e] - l[e]
                wick_ok = (c[e] - l[e]) >= cfg.rej_wick_ratio * rng if rng > 0 else False
                touched = touched and (c[e] > o[e]) and wick_ok
            if touched and e > last_sig + cfg.cooldown_bars:
                target = entry + cfg.rr * risk
                return Signal(
                    market=market, timeframe=timeframe,
                    direction=Direction.LONG, poi_type=poi_type,
                    entry_bar=e, entry_time=times[e],
                    entry_price=entry, stop_price=stop, target_price=target,
                    risk=risk, rr=cfg.rr,
                    sweep_level=lql[1], bos_bar=bos_bar,
                    poi_top=poi_top, poi_bot=poi_bot,
                    atr_at_entry=float(atr[i]),
                    mode="SINGLE",
                    meta={"raid_bar": raid_bar}
                )
        return None

    # ── utilities ───────────────────────────────────────────────────────────

    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        required = {"Open", "High", "Low", "Close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing columns: {missing}")

    @staticmethod
    def _extract_times(df: pd.DataFrame) -> List[Any]:
        if "Time" in df.columns:
            return list(df["Time"])
        if isinstance(df.index, pd.DatetimeIndex):
            return list(df.index)
        return list(range(len(df)))


# ─────────────────────────────────────────────────────────────────────────────
#  ALERT-ENGINE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def signals_to_json(signals: List[Signal], pretty: bool = True) -> str:
    """Serialise a list of signals for an alert engine / webhook."""
    payload = [s.to_dict() for s in signals]
    return json.dumps(payload, indent=2 if pretty else None, default=str)


def load_ohlc(path: str | Path) -> pd.DataFrame:
    """
    Robust loader for the Edge Lab CSV format
    (tab-separated, possible extra column, datetime first).
    """
    path = Path(path)
    df = pd.read_csv(path, sep="\t", header=0,
                     names=["Time", "Open", "High", "Low", "Close", "Volume", "X"],
                     usecols=range(6))
    df["Time"] = pd.to_datetime(df["Time"])
    return df.sort_values("Time").reset_index(drop=True)


def run_file(path: str | Path,
             market: str,
             timeframe: str,
             config: Optional[DetectorConfig] = None) -> List[Signal]:
    """One-liner for single-TF batch / cron jobs."""
    df  = load_ohlc(path)
    cfg = (config or DetectorConfig()).for_timeframe(timeframe)
    det = MarioPureDetector(cfg)
    return det.detect(df, market=market, timeframe=timeframe)


def run_dual(path_htf: str | Path,
             path_ltf: str | Path,
             market: str,
             htf: str = "H1",
             ltf: str = "M30",
             config: Optional[DetectorConfig] = None) -> List[Signal]:
    """One-liner for dual-TF batch / cron jobs (recommended live path)."""
    df_htf = load_ohlc(path_htf)
    df_ltf = load_ohlc(path_ltf)
    cfg = (config or DetectorConfig()).as_dual(htf=htf, ltf=ltf)
    det = MarioPureDetector(cfg)
    return det.detect_dual(df_htf, df_ltf, market=market)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI / QUICK TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Mario Pure Detection v2 – Edge Lab")
    parser.add_argument("--file",      help="Path to single-TF OHLC CSV")
    parser.add_argument("--htf-file",  help="Path to HTF CSV (dual mode)")
    parser.add_argument("--ltf-file",  help="Path to LTF CSV (dual mode)")
    parser.add_argument("--market",    required=True, help="e.g. EURUSD")
    parser.add_argument("--tf",        default="H1", help="M30 | H1 | H4 (single mode)")
    parser.add_argument("--htf",       default="H1", help="HTF for dual (default H1)")
    parser.add_argument("--ltf",       default="M30", help="LTF for dual (default M30)")
    parser.add_argument("--mode",      default="single", choices=["single", "dual"])
    parser.add_argument("--rr",        type=float, default=None, help="Override RR")
    parser.add_argument("--latest",    type=int, default=0,
                        help="Only return signals in last N bars (0 = all)")
    parser.add_argument("--json",      action="store_true", help="Output JSON")
    parser.add_argument("--rich",      action="store_true", help="Rich Telegram-style message")
    args = parser.parse_args()

    if args.mode == "dual":
        if not args.htf_file or not args.ltf_file:
            print("Dual mode requires --htf-file and --ltf-file", file=sys.stderr)
            sys.exit(1)
        cfg = DetectorConfig().as_dual(htf=args.htf, ltf=args.ltf)
        if args.rr is not None:
            cfg.rr = args.rr
        det = MarioPureDetector(cfg)
        df_htf = load_ohlc(args.htf_file)
        df_ltf = load_ohlc(args.ltf_file)
        if args.latest > 0:
            sigs = det.detect_dual_latest(df_htf, df_ltf, args.market, lookback_bars=args.latest)
        else:
            sigs = det.detect_dual(df_htf, df_ltf, args.market)
    else:
        if not args.file:
            print("Single mode requires --file", file=sys.stderr)
            sys.exit(1)
        cfg = DetectorConfig().for_timeframe(args.tf)
        if args.rr is not None:
            cfg.rr = args.rr
        det = MarioPureDetector(cfg)
        df = load_ohlc(args.file)
        if args.latest > 0:
            sigs = det.detect_latest(df, args.market, args.tf, lookback_bars=args.latest)
        else:
            sigs = det.detect(df, args.market, args.tf)

    if args.json:
        print(signals_to_json(sigs))
    else:
        mode_label = f"DUAL {args.htf}→{args.ltf}" if args.mode == "dual" else f"SINGLE {args.tf}"
        print(f"Mario Pure v2 | {args.market} | {mode_label} | RR={cfg.rr} | Signals: {len(sigs)}")
        print("-" * 60)
        for s in sigs[-15:]:
            print(s.alert_message_rich() if args.rich else s.alert_message())
            print("-" * 40)

    sys.exit(0)
