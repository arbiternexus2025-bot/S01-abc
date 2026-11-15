#!/usr/bin/env python3
"""
S43 – Parabolic SAR Trail Detection Module
==========================================
Purified & Multi-TF validated edge (XAUUSD)

Top 3 Locked Champions:
  1. H4_PURE      → H4 Pure PSAR Trail (No EMA)          [Best Overall]
  2. H1_VOL50     → H1 VOL50 + Trail                     [Best Balance]
  3. M5_VOL40     → M5 VOL40 + Trail                     [Best Higher-Frequency]

Also available:
  - H1_VOL40_BODY
  - M5_VOL50
  - H4_LDN_VOL40
  - M30_VOL50

Author: Edge Lab Research
Date  : 2026-11-15
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from enum import Enum


# ─────────────────────────────────────────────────────────────
# Signal structure
# ─────────────────────────────────────────────────────────────
@dataclass
class PSARSignal:
    direction: int              # +1 Long / -1 Short
    entry_bar: int
    entry_time: str
    entry_price: float
    psar_at_entry: float
    atr_at_entry: float
    atr_pct: float
    mode: str
    # Optional fields for downstream use
    stop_initial: Optional[float] = None   # usually the PSAR itself
    comment: str = ""


# ─────────────────────────────────────────────────────────────
# Mode presets (locked from research)
# ─────────────────────────────────────────────────────────────
class Mode(str, Enum):
    H4_PURE         = "H4_PURE"          # Best Overall
    H1_VOL50        = "H1_VOL50"         # Best Balance
    M5_VOL40        = "M5_VOL40"         # Best Higher-Frequency
    H1_VOL40_BODY   = "H1_VOL40_BODY"
    M5_VOL50        = "M5_VOL50"
    H4_LDN_VOL40    = "H4_LDN_VOL40"
    M30_VOL50       = "M30_VOL50"


MODE_CONFIG = {
    Mode.H4_PURE: {
        "tf": "H4",
        "use_ema": False,
        "min_atr_pct": 0.0,
        "min_body_atr": 0.0,
        "session": None,              # (start_hour, end_hour) UTC
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "H4 Pure PSAR Trail – Best Overall"
    },
    Mode.H1_VOL50: {
        "tf": "H1",
        "use_ema": True,
        "min_atr_pct": 0.50,
        "min_body_atr": 0.0,
        "session": None,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "H1 VOL50 + Trail – Best Balance"
    },
    Mode.M5_VOL40: {
        "tf": "M5",
        "use_ema": True,
        "min_atr_pct": 0.40,
        "min_body_atr": 0.0,
        "session": None,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "M5 VOL40 + Trail – Best Higher-Frequency"
    },
    Mode.H1_VOL40_BODY: {
        "tf": "H1",
        "use_ema": True,
        "min_atr_pct": 0.40,
        "min_body_atr": 0.40,
        "session": None,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "H1 VOL40 + Body quality"
    },
    Mode.M5_VOL50: {
        "tf": "M5",
        "use_ema": True,
        "min_atr_pct": 0.50,
        "min_body_atr": 0.0,
        "session": None,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "M5 VOL50 + Trail"
    },
    Mode.H4_LDN_VOL40: {
        "tf": "H4",
        "use_ema": True,
        "min_atr_pct": 0.40,
        "min_body_atr": 0.0,
        "session": (7, 16),           # London
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "H4 London + VOL40"
    },
    Mode.M30_VOL50: {
        "tf": "M30",
        "use_ema": True,
        "min_atr_pct": 0.50,
        "min_body_atr": 0.0,
        "session": None,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "M30 VOL50 + Trail"
    },
}


# ─────────────────────────────────────────────────────────────
# Core indicators
# ─────────────────────────────────────────────────────────────
def compute_ema(close: np.ndarray, period: int = 9) -> np.ndarray:
    """Standard EMA."""
    n = len(close)
    ema = np.full(n, np.nan)
    if n == 0:
        return ema
    alpha = 2.0 / (period + 1)
    ema[0] = close[0]
    for i in range(1, n):
        ema[i] = alpha * close[i] + (1 - alpha) * ema[i - 1]
    return ema


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                length: int = 14) -> np.ndarray:
    """Wilder-style ATR."""
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]))
    atr = np.full(n, np.nan)
    if n < length:
        return atr
    atr[length - 1] = np.mean(tr[:length])
    for i in range(length, n):
        atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length
    return atr


def compute_psar(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                 af_start: float = 0.02, af_step: float = 0.02,
                 af_max: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """
    Classic Parabolic SAR.
    Returns:
        sar   : SAR values
        trend : +1 (long) / -1 (short)
    """
    n = len(high)
    sar = np.full(n, np.nan)
    trend = np.zeros(n, dtype=np.int8)
    ep = np.zeros(n)
    af = np.zeros(n)

    if n == 0:
        return sar, trend

    # Initialise as long
    sar[0] = float(low[0])
    trend[0] = 1
    ep[0] = float(high[0])
    af[0] = af_start

    for i in range(1, n):
        prev_sar = sar[i - 1]
        prev_trend = trend[i - 1]
        prev_ep = ep[i - 1]
        prev_af = af[i - 1]

        if prev_trend == 1:  # was long
            sar[i] = prev_sar + prev_af * (prev_ep - prev_sar)
            # SAR cannot be above prior lows
            if i >= 2:
                sar[i] = min(sar[i], low[i - 1], low[i - 2])
            else:
                sar[i] = min(sar[i], low[i - 1])

            if low[i] < sar[i]:
                # Reverse to short
                trend[i] = -1
                sar[i] = prev_ep
                ep[i] = low[i]
                af[i] = af_start
            else:
                trend[i] = 1
                if high[i] > prev_ep:
                    ep[i] = high[i]
                    af[i] = min(prev_af + af_step, af_max)
                else:
                    ep[i] = prev_ep
                    af[i] = prev_af
        else:  # was short
            sar[i] = prev_sar + prev_af * (prev_ep - prev_sar)
            if i >= 2:
                sar[i] = max(sar[i], high[i - 1], high[i - 2])
            else:
                sar[i] = max(sar[i], high[i - 1])

            if high[i] > sar[i]:
                # Reverse to long
                trend[i] = 1
                sar[i] = prev_ep
                ep[i] = high[i]
                af[i] = af_start
            else:
                trend[i] = -1
                if low[i] < prev_ep:
                    ep[i] = low[i]
                    af[i] = min(prev_af + af_step, af_max)
                else:
                    ep[i] = prev_ep
                    af[i] = prev_af

    return sar, trend


def rolling_percentile_rank(series: np.ndarray, window: int = 500,
                            min_periods: int = 100) -> np.ndarray:
    """
    Rolling percentile rank of the last value in each window.
    Used for VOL filter to avoid full-sample look-ahead.
    """
    n = len(series)
    out = np.full(n, np.nan)
    for i in range(n):
        start = max(0, i - window + 1)
        if i - start + 1 < min_periods:
            continue
        window_vals = series[start:i + 1]
        # percentile rank of the current value
        out[i] = (np.sum(window_vals <= series[i]) - 1) / (len(window_vals) - 1 + 1e-12)
    return out


# ─────────────────────────────────────────────────────────────
# Main detection function
# ─────────────────────────────────────────────────────────────
def detect_psar_signals(
    df: pd.DataFrame,
    mode: str | Mode = Mode.H4_PURE,
    custom_config: Optional[Dict[str, Any]] = None,
) -> List[PSARSignal]:
    """
    Detect S43 PSAR Trail signals on the provided OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: Time (or datetime index), Open, High, Low, Close
        Volume is optional.
    mode : str or Mode
        One of the locked champions (H4_PURE, H1_VOL50, M5_VOL40, ...)
    custom_config : dict, optional
        Override any parameter from MODE_CONFIG.

    Returns
    -------
    List[PSARSignal]
        Detected entry signals (flip bars that pass all filters).
        Exit is always the PSAR trail (handled by the execution layer).
    """
    if isinstance(mode, str):
        mode = Mode(mode)

    cfg = MODE_CONFIG[mode].copy()
    if custom_config:
        cfg.update(custom_config)

    # Prepare arrays
    if 'Time' in df.columns:
        times = pd.to_datetime(df['Time'])
    else:
        times = pd.to_datetime(df.index)

    o = df['Open'].values.astype(float)
    h = df['High'].values.astype(float)
    l = df['Low'].values.astype(float)
    c = df['Close'].values.astype(float)
    n = len(c)

    # Indicators
    ema9 = compute_ema(c, 9)
    atr = compute_atr(h, l, c, 14)
    sar, trend = compute_psar(h, l, c,
                              af_start=cfg['af_start'],
                              af_max=cfg['af_max'])

    # ATR percentile (rolling to stay causal)
    atr_pct = rolling_percentile_rank(atr, window=500, min_periods=100)

    body = np.abs(c - o)

    # Flip detection
    flip_bull = np.zeros(n, dtype=bool)
    flip_bear = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if trend[i] == 1 and trend[i - 1] == -1:
            flip_bull[i] = True
        elif trend[i] == -1 and trend[i - 1] == 1:
            flip_bear[i] = True

    signals: List[PSARSignal] = []

    session = cfg.get('session')
    use_ema = cfg.get('use_ema', True)
    min_atr_pct = cfg.get('min_atr_pct', 0.0)
    min_body_atr = cfg.get('min_body_atr', 0.0)

    for i in range(120, n - 1):  # warm-up
        # Session filter
        if session is not None:
            hour = times[i].hour
            if not (session[0] <= hour < session[1]):
                continue

        # Volatility filter
        if np.isnan(atr_pct[i]) or atr_pct[i] < min_atr_pct:
            continue

        # Body quality filter
        if min_body_atr > 0:
            if np.isnan(atr[i]) or atr[i] <= 0:
                continue
            if body[i] < min_body_atr * atr[i]:
                continue

        # EMA direction filter (optional)
        ema_ok_long = True
        ema_ok_short = True
        if use_ema:
            ema_ok_long = (ema9[i] > ema9[i - 1]) and (c[i] > ema9[i])
            ema_ok_short = (ema9[i] < ema9[i - 1]) and (c[i] < ema9[i])

        # Signal generation (on the flip bar)
        if flip_bull[i] and ema_ok_long:
            # Entry at next bar open (research standard)
            entry_price = o[i + 1]
            signals.append(PSARSignal(
                direction=1,
                entry_bar=i + 1,
                entry_time=str(times[i + 1]),
                entry_price=float(entry_price),
                psar_at_entry=float(sar[i]),
                atr_at_entry=float(atr[i]) if not np.isnan(atr[i]) else 0.0,
                atr_pct=float(atr_pct[i]) if not np.isnan(atr_pct[i]) else 0.0,
                mode=mode.value,
                stop_initial=float(sar[i]),
                comment=f"Bullish PSAR flip | ATR%={atr_pct[i]:.2f}"
            ))

        elif flip_bear[i] and ema_ok_short:
            entry_price = o[i + 1]
            signals.append(PSARSignal(
                direction=-1,
                entry_bar=i + 1,
                entry_time=str(times[i + 1]),
                entry_price=float(entry_price),
                psar_at_entry=float(sar[i]),
                atr_at_entry=float(atr[i]) if not np.isnan(atr[i]) else 0.0,
                atr_pct=float(atr_pct[i]) if not np.isnan(atr_pct[i]) else 0.0,
                mode=mode.value,
                stop_initial=float(sar[i]),
                comment=f"Bearish PSAR flip | ATR%={atr_pct[i]:.2f}"
            ))

    return signals


# ─────────────────────────────────────────────────────────────
# Convenience helpers
# ─────────────────────────────────────────────────────────────
def signals_to_dataframe(signals: List[PSARSignal]) -> pd.DataFrame:
    """Convert list of signals to a clean DataFrame."""
    if not signals:
        return pd.DataFrame()
    return pd.DataFrame([asdict(s) for s in signals])


def print_mode_summary():
    """Print available modes and their research ranking."""
    print("=" * 70)
    print("S43 PSAR Trail – Locked Champions")
    print("=" * 70)
    ranking = [
        (1, Mode.H4_PURE, "Best Overall – Highest quality & risk-adjusted"),
        (2, Mode.H1_VOL50, "Best Balance – Strength + robustness + frequency"),
        (3, Mode.M5_VOL40, "Best Higher-Frequency – Active trading"),
    ]
    for rank, mode, desc in ranking:
        cfg = MODE_CONFIG[mode]
        print(f"\n#{rank}  {mode.value}")
        print(f"    {desc}")
        print(f"    TF: {cfg['tf']} | EMA: {cfg['use_ema']} | "
              f"VOL≥{cfg['min_atr_pct']} | Body≥{cfg['min_body_atr']} | "
              f"Session: {cfg['session']}")
    print("\nOther available modes:")
    for m in Mode:
        if m not in [Mode.H4_PURE, Mode.H1_VOL50, Mode.M5_VOL40]:
            print(f"  - {m.value}: {MODE_CONFIG[m]['description']}")
    print("=" * 70)


# ─────────────────────────────────────────────────────────────
# Example usage / self-test
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from pathlib import Path

    print_mode_summary()

    data_dir = Path("/home/workdir/artifacts/data (1)")
    if not data_dir.exists():
        print("\nData directory not found – detection functions are ready for import.")
        sys.exit(0)

    # Quick smoke test on H4
    print("\n--- Smoke test: H4_PURE ---")
    try:
        df = pd.read_csv(data_dir / "XAUUSD_H4.csv", sep="\t",
                         names=["Time", "Open", "High", "Low", "Close", "Vol1", "Vol2"],
                         header=0)
        df["Time"] = pd.to_datetime(df["Time"])
        sigs = detect_psar_signals(df, mode=Mode.H4_PURE)
        print(f"Detected {len(sigs)} signals")
        if sigs:
            print("Last 3 signals:")
            for s in sigs[-3:]:
                print(f"  {s.entry_time}  {'LONG' if s.direction == 1 else 'SHORT'}  "
                      f"@ {s.entry_price:.2f}  ATR%={s.atr_pct:.2f}")
    except Exception as e:
        print(f"Smoke test failed: {e}")

    print("\nDetection module ready.")
