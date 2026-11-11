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

Recommended live defaults (from RR-sweep research):
  M30 → RR 3.0
  H1  → RR 3.0 – 3.5
  H4  → RR 4.0 – 5.0

Author  : Edge Lab Research
Version : 1.0.0  (Production)
Date    : 2026-11-10
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


@dataclass
class Signal:
    """Single trade signal ready for an alert engine."""
    market:       str
    timeframe:    str
    direction:    Direction
    poi_type:     POIType
    entry_bar:    int                 # index in the dataframe
    entry_time:   Any                 # timestamp
    entry_price:  float
    stop_price:   float
    target_price: float
    risk:         float               # absolute price distance
    rr:           float
    sweep_level:  float
    bos_bar:      int
    poi_top:      float
    poi_bot:      float
    atr_at_entry: float
    meta:         Dict[str, Any] = field(default_factory=dict)

    @property
    def side(self) -> str:
        return "LONG" if self.direction == Direction.LONG else "SHORT"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["direction"] = self.direction.name
        d["poi_type"]  = self.poi_type.value
        d["side"]      = self.side
        # make timestamps JSON-serialisable
        if hasattr(self.entry_time, "isoformat"):
            d["entry_time"] = self.entry_time.isoformat()
        return d

    def alert_message(self) -> str:
        return (
            f"MARIO PURE  {self.side}  {self.market} {self.timeframe}\n"
            f"POI: {self.poi_type.value}  |  RR: {self.rr:.1f}\n"
            f"Entry: {self.entry_price:.5f}\n"
            f"Stop : {self.stop_price:.5f}\n"
            f"Target: {self.target_price:.5f}\n"
            f"Risk: {self.risk:.5f}"
        )


@dataclass
class DetectorConfig:
    """All tunable parameters.  Defaults = research-locked production values."""
    # Structure
    pivot_left:      int   = 5
    pivot_right:     int   = 3
    min_disp_atr:    float = 0.90
    bos_body_min:    float = 0.35
    ob_body_min:     float = 0.55
    allow_fvg:       bool  = True
    max_poi_age:     int   = 32

    # Entry
    require_rejection: bool  = True
    rej_wick_ratio:    float = 0.25   # min wick / range on touch candle
    sl_buffer_atr:     float = 0.12
    cooldown_bars:     int   = 8

    # Risk
    rr:              float = 3.0      # override per timeframe in live use

    # Safety
    min_risk_atr:    float = 0.08
    max_risk_atr:    float = 5.50

    def for_timeframe(self, tf: str) -> "DetectorConfig":
        """Return a copy with research-recommended RR for the timeframe."""
        cfg = DetectorConfig(**asdict(self))
        tf = tf.upper()
        if tf == "M30":
            cfg.rr = 3.0
        elif tf == "H1":
            cfg.rr = 3.5
        elif tf == "H2":
            cfg.rr = 4.0
        elif tf in ("H4", "D1"):
            cfg.rr = 4.5
        else:
            cfg.rr = 3.0
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

    Usage
    -----
    >>> cfg = DetectorConfig().for_timeframe("H1")
    >>> det = MarioPureDetector(cfg)
    >>> signals = det.detect(df, market="EURUSD", timeframe="H1")
    >>> for s in signals:
    ...     print(s.alert_message())
    """

    def __init__(self, config: Optional[DetectorConfig] = None):
        self.cfg = config or DetectorConfig()

    # ── public API ──────────────────────────────────────────────────────────

    def detect(self,
               df: pd.DataFrame,
               market: str = "UNKNOWN",
               timeframe: str = "H1") -> List[Signal]:
        """
        Run full detection on an OHLCV DataFrame.

        Required columns: Open, High, Low, Close
        Optional        : Time / Datetime index (used for entry_time)

        Returns a list of Signal objects ordered by time.
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

            # update confirmed swings (right-side confirmation)
            conf = i - self.cfg.pivot_right
            while pi_h < len(ph) and ph[pi_h][0] <= conf:
                swing_h.append(ph[pi_h])
                pi_h += 1
            while pi_l < len(pl) and pl[pi_l][0] <= conf:
                swing_l.append(pl[pi_l])
                pi_l += 1
            if not swing_h or not swing_l:
                continue

            # ── SHORT ──────────────────────────────────────────────────────
            sig = self._try_short(
                i, o, h, l, c, atr, swing_h, swing_l,
                last_signal_bar, market, timeframe, times
            )
            if sig is not None:
                signals.append(sig)
                last_signal_bar = sig.entry_bar
                continue   # one signal per bar max

            # ── LONG ───────────────────────────────────────────────────────
            sig = self._try_long(
                i, o, h, l, c, atr, swing_h, swing_l,
                last_signal_bar, market, timeframe, times
            )
            if sig is not None:
                signals.append(sig)
                last_signal_bar = sig.entry_bar

        return signals

    def detect_latest(self,
                      df: pd.DataFrame,
                      market: str = "UNKNOWN",
                      timeframe: str = "H1",
                      lookback_bars: int = 5) -> List[Signal]:
        """
        Convenience for live alert engines.
        Returns only signals whose entry_bar is within the last `lookback_bars`.
        """
        all_sigs = self.detect(df, market, timeframe)
        if not all_sigs:
            return []
        cutoff = len(df) - 1 - lookback_bars
        return [s for s in all_sigs if s.entry_bar >= cutoff]

    # ── internal signal builders ────────────────────────────────────────────

    def _try_short(self, i, o, h, l, c, atr,
                   swing_h, swing_l, last_sig,
                   market, timeframe, times) -> Optional[Signal]:
        cfg = self.cfg
        lqh = swing_h[-1]

        # 1. Liquidity sweep
        raid_bar = -1
        for j in range(max(lqh[0] + 1, i - 28), i + 1):
            if h[j] > lqh[1]:
                raid_bar = j
                break
        if raid_bar <= last_sig:
            return None

        # 2. BOS down
        bos_bar = -1
        for k in range(raid_bar + 1, i + 1):
            if c[k] < swing_l[-1][1] and _body_ratio(o[k], c[k], h[k], l[k]) >= cfg.bos_body_min:
                bos_bar = k
                break
        if bos_bar < 0:
            return None
        if (h[raid_bar] - c[bos_bar]) < cfg.min_disp_atr * atr[i]:
            return None

        # 3. POI (strong bullish OB or bearish FVG)
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

        # 4. Risk geometry
        entry = (poi_top + poi_bot) / 2.0
        stop  = poi_top + cfg.sl_buffer_atr * atr[i]
        risk  = stop - entry
        if not (cfg.min_risk_atr * atr[i] <= risk <= cfg.max_risk_atr * atr[i]):
            return None

        # 5. First touch + rejection
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
    """Serialise a list of signals for an alert queue / webhook."""
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
    """One-liner for batch / cron jobs."""
    df  = load_ohlc(path)
    cfg = (config or DetectorConfig()).for_timeframe(timeframe)
    det = MarioPureDetector(cfg)
    return det.detect(df, market=market, timeframe=timeframe)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI / QUICK TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Mario Pure Detection – Edge Lab")
    parser.add_argument("--file",      required=True, help="Path to OHLC CSV")
    parser.add_argument("--market",    required=True, help="e.g. EURUSD")
    parser.add_argument("--tf",        required=True, help="M30 | H1 | H4")
    parser.add_argument("--rr",        type=float, default=None, help="Override RR")
    parser.add_argument("--latest",    type=int, default=0,
                        help="Only return signals in last N bars (0 = all)")
    parser.add_argument("--json",      action="store_true", help="Output JSON")
    args = parser.parse_args()

    cfg = DetectorConfig().for_timeframe(args.tf)
    if args.rr is not None:
        cfg.rr = args.rr

    det = MarioPureDetector(cfg)
    df  = load_ohlc(args.file)

    if args.latest > 0:
        sigs = det.detect_latest(df, args.market, args.tf, lookback_bars=args.latest)
    else:
        sigs = det.detect(df, args.market, args.tf)

    if args.json:
        print(signals_to_json(sigs))
    else:
        print(f"Mario Pure | {args.market} {args.tf} | RR={cfg.rr} | Signals: {len(sigs)}")
        print("-" * 60)
        for s in sigs[-15:]:          # last 15
            print(s.alert_message())
            print("-" * 40)

    sys.exit(0)
