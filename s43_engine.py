"""
S43 — HTF → M1 Limit Trail (XAUUSD locked champions)
====================================================
  A  M5_LIM070   M5 → M1 | NOVOL + no EMA | limit 0.70 ATR | Grade B+
  B  M30_LIM050  M30 → M1 | VOL≥0.40 + EMA9 | limit 0.50 ATR | Grade A
  C  H1_LIM040   H1 → M1 | VOL≥0.40 + EMA9 | limit 0.40 ATR | Grade A
"""
from __future__ import annotations
import numpy as np
from typing import List, Dict, Optional
from S43_HTF_M1_Limit_detection import S43Detector, S43Signal

# Live freshness: only alert fills on recent M1 bars
M1_LOOKBACK = 8  # minutes of closed M1

MODE_ORDER = ["A", "B", "C"]  # scan order


def _to_arrays(ohlc: dict) -> Dict[str, np.ndarray]:
    return {
        "Open": np.asarray(ohlc["open"], dtype=float),
        "High": np.asarray(ohlc["high"], dtype=float),
        "Low": np.asarray(ohlc["low"], dtype=float),
        "Close": np.asarray(ohlc["close"], dtype=float),
    }


def _times(ohlc: dict) -> np.ndarray:
    # detector accepts any comparable array; use float unix
    return np.asarray(ohlc["time"], dtype=float)


def scan_s43_mode(
    ohlc_htf: dict,
    ohlc_m1: dict,
    mode: str,
) -> List[dict]:
    """Run one locked mode (A/B/C). Returns packed alert dicts."""
    if ohlc_htf is None or ohlc_m1 is None:
        return []
    if len(ohlc_m1["close"]) < 200 or len(ohlc_htf["close"]) < 80:
        return []

    det = S43Detector(mode=mode.upper())
    try:
        sigs: List[S43Signal] = det.detect(
            htf_data=_to_arrays(ohlc_htf),
            m1_data=_to_arrays(ohlc_m1),
            htf_times=_times(ohlc_htf),
            m1_times=_times(ohlc_m1),
            mode=mode.upper(),
        )
    except Exception as e:
        print(f"  [S43] detect error mode={mode}: {e}", flush=True)
        return []

    n = len(ohlc_m1["close"])
    cfg = S43Detector.MODES[mode.upper()]
    out = []
    for s in sigs:
        bars_ago = n - 1 - s.entry_bar
        if bars_ago < 0 or bars_ago > M1_LOOKBACK:
            continue
        side = "LONG" if s.direction == 1 else "SHORT"
        entry = float(s.entry_price)
        stop = float(s.stop)
        # Reference target from initial risk (trail is primary exit)
        risk = abs(entry - stop)
        rr = 2.5 if mode.upper() != "A" else 2.0
        if risk < 1e-12:
            continue
        target = entry + rr * risk if side == "LONG" else entry - rr * risk

        out.append({
            "strategy": "S43",
            "phase": "ENTRY",
            "mode": s.htf_mode or cfg["label"],
            "mode_code": mode.upper(),
            "market": "XAUUSD",
            "tf": f"{cfg['htf']}→M1",
            "direction": side,
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "target": round(target, 2),
            "limit_price": round(float(s.limit_price), 2),
            "limit_off": float(s.limit_off),
            "htf_sig_price": round(float(s.htf_sig_price), 2),
            "grade": s.grade or cfg["grade"],
            "rr": rr,
            "bars_ago": bars_ago,
            "trail": True,
            "priority": {"C": 500, "B": 450, "A": 400}.get(mode.upper(), 300),
            "role": f"S43 {cfg['label']} HTF→M1 Limit Trail",
            "key": f"S43|{cfg['label']}|XAUUSD|{side}|{round(entry, 2)}",
        })
    return out
