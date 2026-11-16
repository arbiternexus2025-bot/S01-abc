#!/usr/bin/env python3
"""
S43 – Parabolic SAR Trail Detection Module
==========================================
Purified, Multi-TF validated & HTF-Aligned edge (XAUUSD)

FINAL LOCKED CHAMPIONS (Research Complete – Nov 2026):

  Rank 1 (Best Overall Quality):
    M5_H4_ALIGN     → M5 entry + H4 PSAR alignment + VOL40

  Rank 2 (Best Swing / Balance):
    H1_H4_ALIGN     → H1 entry + H4 PSAR alignment + VOL40

  Rank 3 (Strong Single-TF):
    H4_PURE         → H4 Pure PSAR Trail (No EMA)

Also available:
  - M5_VOL40, M5_VOL50
  - H1_VOL50, H1_VOL40_BODY
  - M5_H1_ALIGN
  - H4_LDN_VOL40
  - M30_VOL50

Author : Edge Lab Research
Updated: 2026-11-16
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum


# ─────────────────────────────────────────────────────────────
# Signal structure
# ─────────────────────────────────────────────────────────────
@dataclass
class PSARSignal:
    direction: int                  # +1 Long / -1 Short
    entry_bar: int
    entry_time: str
    entry_price: float
    psar_at_entry: float
    atr_at_entry: float
    atr_pct: float
    mode: str
    htf_trend: Optional[int] = None
    stop_initial: Optional[float] = None
    comment: str = ""


# ─────────────────────────────────────────────────────────────
# Mode presets (Final Locked)
# ─────────────────────────────────────────────────────────────
class Mode(str, Enum):
    # === TOP 2 HTF-ALIGNED CHAMPIONS ===
    M5_H4_ALIGN     = "M5_H4_ALIGN"      # Best Overall Quality
    H1_H4_ALIGN     = "H1_H4_ALIGN"      # Best Swing / Balance

    # === STRONG SINGLE-TF ===
    H4_PURE         = "H4_PURE"
    H1_VOL50        = "H1_VOL50"
    M5_VOL40        = "M5_VOL40"

    # === ADDITIONAL VALIDATED ===
    M5_H1_ALIGN     = "M5_H1_ALIGN"
    H1_VOL40_BODY   = "H1_VOL40_BODY"
    M5_VOL50        = "M5_VOL50"
    H4_LDN_VOL40    = "H4_LDN_VOL40"
    M30_VOL50       = "M30_VOL50"


MODE_CONFIG = {
    # ---------- TOP 2 ----------
    Mode.M5_H4_ALIGN: {
        "ltf": "M5",
        "htf": "H4",
        "use_ema": True,
        "min_atr_pct": 0.40,
        "min_body_atr": 0.0,
        "session": None,
        "htf_align": True,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "M5 ← H4 ALIGN + VOL40 – Best Overall Quality (Grade A)"
    },
    Mode.H1_H4_ALIGN: {
        "ltf": "H1",
        "htf": "H4",
        "use_ema": True,
        "min_atr_pct": 0.40,
        "min_body_atr": 0.0,
        "session": None,
        "htf_align": True,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "H1 ← H4 ALIGN + VOL40 – Best Swing / Balance (Grade A)"
    },

    # ---------- SINGLE-TF ----------
    Mode.H4_PURE: {
        "ltf": "H4",
        "htf": None,
        "use_ema": False,
        "min_atr_pct": 0.0,
        "min_body_atr": 0.0,
        "session": None,
        "htf_align": False,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "H4 Pure PSAR Trail (No EMA)"
    },
    Mode.H1_VOL50: {
        "ltf": "H1",
        "htf": None,
        "use_ema": True,
        "min_atr_pct": 0.50,
        "min_body_atr": 0.0,
        "session": None,
        "htf_align": False,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "H1 VOL50 + Trail"
    },
    Mode.M5_VOL40: {
        "ltf": "M5",
        "htf": None,
        "use_ema": True,
        "min_atr_pct": 0.40,
        "min_body_atr": 0.0,
        "session": None,
        "htf_align": False,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "M5 VOL40 + Trail"
    },

    # ---------- ADDITIONAL ----------
    Mode.M5_H1_ALIGN: {
        "ltf": "M5",
        "htf": "H1",
        "use_ema": True,
        "min_atr_pct": 0.40,
        "min_body_atr": 0.0,
        "session": None,
        "htf_align": True,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "M5 ← H1 ALIGN + VOL40"
    },
    Mode.H1_VOL40_BODY: {
        "ltf": "H1",
        "htf": None,
        "use_ema": True,
        "min_atr_pct": 0.40,
        "min_body_atr": 0.40,
        "session": None,
        "htf_align": False,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "H1 VOL40 + Body quality"
    },
    Mode.M5_VOL50: {
        "ltf": "M5",
        "htf": None,
        "use_ema": True,
        "min_atr_pct": 0.50,
        "min_body_atr": 0.0,
        "session": None,
        "htf_align": False,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "M5 VOL50 + Trail"
    },
    Mode.H4_LDN_VOL40: {
        "ltf": "H4",
        "htf": None,
        "use_ema": True,
        "min_atr_pct": 0.40,
        "min_body_atr": 0.0,
        "session": (7, 16),
        "htf_align": False,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "H4 London + VOL40"
    },
    Mode.M30_VOL50: {
        "ltf": "M30",
        "htf": None,
        "use_ema": True,
        "min_atr_pct": 0.50,
        "min_body_atr": 0.0,
        "session": None,
        "htf_align": False,
        "af_start": 0.02,
        "af_max": 0.2,
        "description": "M30 VOL50 + Trail"
    },
}


# ─────────────────────────────────────────────────────────────
# Core Indicators
# ─────────────────────────────────────────────────────────────
def compute_ema(close: np.ndarray, period: int = 9) -> np.ndarray:
    n = len(close)
    out = np.full(n, np.nan)
    if n == 0:
        return out
    alpha = 2.0 / (period + 1)
    out[0] = close[0]
    for i in range(1, n):
        out[i] = alpha * close[i] + (1 - alpha) * out[i - 1]
    return out


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                length: int = 14) -> np.ndarray:
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
                 af_max: float = 0.2) -> Tuple[np.ndarray, np.ndarray]:
    """Classic Parabolic SAR. Returns (sar, trend) where trend: +1 long / -1 short."""
    n = len(high)
    sar = np.full(n, np.nan)
    trend = np.zeros(n, dtype=np.int8)
    ep = np.zeros(n)
    af = np.zeros(n)

    if n == 0:
        return sar, trend

    sar[0] = float(low[0])
    trend[0] = 1
    ep[0] = float(high[0])
    af[0] = af_start

    for i in range(1, n):
        prev_sar, prev_trend, prev_ep, prev_af = sar[i-1], trend[i-1], ep[i-1], af[i-1]

        if prev_trend == 1:
            sar[i] = prev_sar + prev_af * (prev_ep - prev_sar)
            sar[i] = min(sar[i], low[i-1], low[i-2] if i >= 2 else low[i-1])
            if low[i] < sar[i]:
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
        else:
            sar[i] = prev_sar + prev_af * (prev_ep - prev_sar)
            sar[i] = max(sar[i], high[i-1], high[i-2] if i >= 2 else high[i-1])
            if high[i] > sar[i]:
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


def rolling_pct_rank(series: np.ndarray, window: int = 500,
                     min_periods: int = 100) -> np.ndarray:
    """Causal rolling percentile rank."""
    n = len(series)
    out = np.full(n, np.nan)
    for i in range(n):
        start = max(0, i - window + 1)
        if i - start + 1 < min_periods:
            continue
        window_vals = series[start:i+1]
        out[i] = (np.sum(window_vals <= series[i]) - 1) / (len(window_vals) - 1 + 1e-12)
    return out


# ─────────────────────────────────────────────────────────────
# Main Detection Function
# ─────────────────────────────────────────────────────────────
def detect_psar_signals(
    ltf_df: pd.DataFrame,
    mode: str | Mode = Mode.M5_H4_ALIGN,
    htf_df: Optional[pd.DataFrame] = None,
    custom_config: Optional[Dict[str, Any]] = None,
) -> List[PSARSignal]:
    """
    Detect S43 PSAR Trail signals.

    Parameters
    ----------
    ltf_df : pd.DataFrame
        Lower timeframe OHLCV. Must contain: Time (or datetime index), Open, High, Low, Close
    mode : str or Mode
        One of the locked modes (M5_H4_ALIGN, H1_H4_ALIGN, H4_PURE, ...)
    htf_df : pd.DataFrame, optional
        Higher timeframe OHLCV (required for ALIGN modes). Same columns as ltf_df.
    custom_config : dict, optional
        Override any parameter.

    Returns
    -------
    List[PSARSignal]
    """
    if isinstance(mode, str):
        mode = Mode(mode)

    cfg = MODE_CONFIG[mode].copy()
    if custom_config:
        cfg.update(custom_config)

    # ----- Prepare LTF -----
    if 'Time' in ltf_df.columns:
        times = pd.to_datetime(ltf_df['Time'])
    else:
        times = pd.to_datetime(ltf_df.index)

    o = ltf_df['Open'].values.astype(float)
    h = ltf_df['High'].values.astype(float)
    l = ltf_df['Low'].values.astype(float)
    c = ltf_df['Close'].values.astype(float)
    n = len(c)

    ema9 = compute_ema(c, 9)
    atr = compute_atr(h, l, c, 14)
    sar, trend = compute_psar(h, l, c, af_start=cfg['af_start'], af_max=cfg['af_max'])
    atr_pct = rolling_pct_rank(atr, window=500, min_periods=100)

    flip_bull = np.zeros(n, dtype=bool)
    flip_bear = np.zeros(n, dtype=bool)
    for i in range(1, n):
        if trend[i] == 1 and trend[i-1] == -1:
            flip_bull[i] = True
        elif trend[i] == -1 and trend[i-1] == 1:
            flip_bear[i] = True

    # ----- Prepare HTF (if required) -----
    htf_trend = np.zeros(n, dtype=np.int8)
    if cfg.get('htf_align') and htf_df is not None:
        if 'Time' in htf_df.columns:
            htf_times = pd.to_datetime(htf_df['Time'])
        else:
            htf_times = pd.to_datetime(htf_df.index)

        h_high = htf_df['High'].values.astype(float)
        h_low  = htf_df['Low'].values.astype(float)
        h_close = htf_df['Close'].values.astype(float)
        _, h_trend_raw = compute_psar(h_high, h_low, h_close,
                                      af_start=cfg['af_start'], af_max=cfg['af_max'])

        # Map HTF trend onto LTF (causal forward-fill)
        htf_map = pd.DataFrame({'Time': htf_times, 'H_trend': h_trend_raw})
        ltf_map = pd.DataFrame({'Time': times})
        merged = pd.merge_asof(
            ltf_map.sort_values('Time'),
            htf_map.sort_values('Time'),
            on='Time', direction='backward'
        )
        htf_trend = merged['H_trend'].fillna(0).values.astype(np.int8)

    # ----- Signal Generation -----
    signals: List[PSARSignal] = []
    use_ema = cfg.get('use_ema', True)
    min_atr_pct = cfg.get('min_atr_pct', 0.0)
    min_body_atr = cfg.get('min_body_atr', 0.0)
    session = cfg.get('session')
    htf_align = cfg.get('htf_align', False)

    body = np.abs(c - o)

    for i in range(150, n - 1):
        # Session filter
        if session is not None:
            hour = times[i].hour
            if not (session[0] <= hour < session[1]):
                continue

        # Volatility filter
        if np.isnan(atr_pct[i]) or atr_pct[i] < min_atr_pct:
            continue

        # Body quality
        if min_body_atr > 0:
            a = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else 1.0
            if body[i] < min_body_atr * a:
                continue

        # EMA filter
        ema_ok_long = True
        ema_ok_short = True
        if use_ema:
            ema_ok_long = (ema9[i] > ema9[i-1]) and (c[i] > ema9[i])
            ema_ok_short = (ema9[i] < ema9[i-1]) and (c[i] < ema9[i])

        # HTF alignment
        htf_ok_long = True
        htf_ok_short = True
        if htf_align:
            htf_ok_long = (htf_trend[i] == 1)
            htf_ok_short = (htf_trend[i] == -1)

        # Generate signal
        if flip_bull[i] and ema_ok_long and htf_ok_long:
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
                htf_trend=int(htf_trend[i]) if htf_align else None,
                stop_initial=float(sar[i]),
                comment=f"Bullish PSAR flip | ATR%={atr_pct[i]:.2f}" +
                        (f" | HTF={htf_trend[i]}" if htf_align else "")
            ))

        elif flip_bear[i] and ema_ok_short and htf_ok_short:
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
                htf_trend=int(htf_trend[i]) if htf_align else None,
                stop_initial=float(sar[i]),
                comment=f"Bearish PSAR flip | ATR%={atr_pct[i]:.2f}" +
                        (f" | HTF={htf_trend[i]}" if htf_align else "")
            ))

    return signals


def signals_to_dataframe(signals: List[PSARSignal]) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame()
    return pd.DataFrame([asdict(s) for s in signals])


def print_mode_summary():
    print("=" * 72)
    print("S43 PSAR Trail – FINAL LOCKED CHAMPIONS")
    print("=" * 72)
    print("\nTOP 2 HTF-ALIGNED (Recommended):")
    print("  1. M5_H4_ALIGN   → M5 entry + H4 PSAR alignment + VOL40   [Best Overall Quality]")
    print("  2. H1_H4_ALIGN   → H1 entry + H4 PSAR alignment + VOL40   [Best Swing / Balance]")
    print("\nStrong Single-TF:")
    print("  3. H4_PURE       → H4 Pure PSAR Trail (No EMA)")
    print("  4. H1_VOL50 / M5_VOL40")
    print("\nAll available modes:")
    for m in Mode:
        cfg = MODE_CONFIG[m]
        print(f"  - {m.value:18s} : {cfg['description']}")
    print("=" * 72)


# ─────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print_mode_summary()
    print("\nDetection module ready. Import and use detect_psar_signals().")
