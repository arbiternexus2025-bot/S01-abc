#!/usr/bin/env python3
"""
S04 — IFVG (Inverted Fair Value Gap) Sniper Pattern Detection
=============================================================
Exact logic extracted & cleaned from the original "IFVG Sniper Entry Engine" Pine Script
and validated across FX + Gold on M15/M30/H1/H4.

Core idea:
  1. Detect a classic 3-candle FVG (hidden / raw).
  2. Store it with quality metrics of the creating candle.
  3. When price later closes through the opposite side of that FVG → IFVG.
  4. Enter in the direction of the inversion at the Broken Boundary
     (or Confirmation Close).
  5. SL = ATR * mult, TP = risk * RR.
  6. One trade at a time.

Strongest validated configs:
  - USDJPY H4 Strict RR=2.5 SL=1.0 ATR
  - XAUUSD H4 / M30 Balanced RR=2.0–2.5 SL=1.0 ATR
  - EURUSD M30 Balanced RR=2.0–2.5 SL=1.0 ATR
  - GBPUSD H4 Strict / M15 Strict
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class HiddenFVG:
    top: float
    bot: float
    direction: int          # +1 bullish FVG, -1 bearish FVG
    age: int
    gap_atr: float
    body_ratio: float
    range_atr: float
    created_bar: int


@dataclass
class IFVGSignal:
    direction: int          # trade direction (+1 long / -1 short)
    fvg_top: float
    fvg_bot: float
    confirm_close: float
    entry_bar: int
    entry_price: float      # Broken Boundary or Confirmation Close
    stop: float
    target: float
    risk: float
    filter_mode: str


# Filter presets matching the original Pine
FILTER_PRESETS = {
    "Off":      {"min_gap_atr": 0.0,  "min_body": 0.0,  "min_range": 0.0,  "break_buf": 0.0},
    "Loose":     {"min_gap_atr": 0.15, "min_body": 0.40, "min_range": 0.40, "break_buf": 0.0},
    "Balanced":  {"min_gap_atr": 0.25, "min_body": 0.50, "min_range": 0.60, "break_buf": 0.05},
    "Strict":    {"min_gap_atr": 0.40, "min_body": 0.60, "min_range": 0.85, "break_buf": 0.10},
}


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14) -> np.ndarray:
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


def detect_ifvg_signals(
    high: np.ndarray,
    low: np.ndarray,
    open_: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    filter_mode: str = "Balanced",
    max_hidden: int = 120,
    max_age: int = 60,
    min_gap_ticks: int = 0,
    mintick: float = 0.00001,
    atr_len: int = 14,
    sl_atr_mult: float = 1.5,
    tp_rr: float = 3.0,
    entry_mode: str = "Broken Boundary",   # or "Confirmation Close"
    one_trade_at_a_time: bool = True,
) -> List[IFVGSignal]:
    """
    Full IFVG detection engine (confirmed-bar only, no look-ahead).

    Returns list of IFVGSignal in chronological order.
    """
    filt = FILTER_PRESETS.get(filter_mode, FILTER_PRESETS["Balanced"])
    min_gap = min_gap_ticks * mintick
    n = len(close)
    hidden: List[HiddenFVG] = []
    signals: List[IFVGSignal] = []
    trade_active = False
    last_exit_bar = -1

    for i in range(2, n):
        # --- age & expire ---
        for f in hidden:
            f.age += 1
        hidden = [f for f in hidden if f.age <= max_age]

        atr_i = atr[i]
        if np.isnan(atr_i) or atr_i <= 0:
            atr_i = mintick * 10

        # --- quality of current candle ---
        candle_range = max(high[i] - low[i], mintick)
        candle_body = abs(close[i] - open_[i])
        body_ratio = candle_body / candle_range
        range_atr = candle_range / atr_i

        # --- detect raw FVG ---
        if low[i] > high[i - 2] and (low[i] - high[i - 2]) >= min_gap:
            gap = low[i] - high[i - 2]
            hidden.append(HiddenFVG(
                top=low[i], bot=high[i - 2], direction=1, age=0,
                gap_atr=gap / atr_i, body_ratio=body_ratio, range_atr=range_atr,
                created_bar=i
            ))
        if high[i] < low[i - 2] and (low[i - 2] - high[i]) >= min_gap:
            gap = low[i - 2] - high[i]
            hidden.append(HiddenFVG(
                top=low[i - 2], bot=high[i], direction=-1, age=0,
                gap_atr=gap / atr_i, body_ratio=body_ratio, range_atr=range_atr,
                created_bar=i
            ))

        while len(hidden) > max_hidden:
            hidden.pop(0)

        # --- check inversion (newest first) ---
        new_signal = None
        for j in range(len(hidden) - 1, -1, -1):
            f = hidden[j]
            buf = atr_i * filt["break_buf"]
            bull_inv = (f.direction == -1) and (close[i] > f.top + buf)
            bear_inv = (f.direction == 1) and (close[i] < f.bot - buf)

            if bull_inv or bear_inv:
                pass_q = (
                    (filt["min_gap_atr"] == 0 and filt["min_body"] == 0 and filt["min_range"] == 0) or
                    (f.gap_atr >= filt["min_gap_atr"] and
                     f.body_ratio >= filt["min_body"] and
                     f.range_atr >= filt["min_range"])
                )
                if pass_q:
                    direction = 1 if bull_inv else -1
                    if entry_mode == "Confirmation Close":
                        entry = close[i]
                    else:
                        # Broken Boundary
                        entry = f.top if direction == 1 else f.bot

                    risk = atr_i * sl_atr_mult
                    if risk <= 0:
                        risk = mintick * 10
                    if direction == 1:
                        stop = entry - risk
                        target = entry + risk * tp_rr
                    else:
                        stop = entry + risk
                        target = entry - risk * tp_rr

                    new_signal = IFVGSignal(
                        direction=direction,
                        fvg_top=f.top, fvg_bot=f.bot,
                        confirm_close=close[i],
                        entry_bar=i, entry_price=entry,
                        stop=stop, target=target, risk=risk,
                        filter_mode=filter_mode
                    )
                # remove the inverted FVG either way
                hidden.pop(j)
                break

        # --- emit signal (respect one-trade rule) ---
        if new_signal is not None:
            if not one_trade_at_a_time or not trade_active:
                signals.append(new_signal)
                if one_trade_at_a_time:
                    trade_active = True
                    # simple exit tracking so we can free the slot later
                    # (full backtest manages exits; here we just mark active)

        # crude free of the one-trade lock when price hits SL or TP
        if trade_active and signals:
            last = signals[-1]
            if i > last.entry_bar:
                if last.direction == 1:
                    if low[i] <= last.stop or high[i] >= last.target:
                        trade_active = False
                else:
                    if high[i] >= last.stop or low[i] <= last.target:
                        trade_active = False

    return signals


# ---------------------------------------------------------------------------
# Convenience wrapper that also returns the raw hidden FVG list at the end
# ---------------------------------------------------------------------------
def run_ifvg_engine(
    high, low, open_, close,
    filter_mode: str = "Balanced",
    sl_atr_mult: float = 1.0,
    tp_rr: float = 2.5,
    entry_mode: str = "Broken Boundary",
    atr_len: int = 14,
    **kwargs
) -> Dict:
    atr = compute_atr(high, low, close, atr_len)
    signals = detect_ifvg_signals(
        high, low, open_, close, atr,
        filter_mode=filter_mode,
        sl_atr_mult=sl_atr_mult,
        tp_rr=tp_rr,
        entry_mode=entry_mode,
        **kwargs
    )
    return {
        "signals": signals,
        "n_signals": len(signals),
        "longs": sum(1 for s in signals if s.direction == 1),
        "shorts": sum(1 for s in signals if s.direction == -1),
    }
