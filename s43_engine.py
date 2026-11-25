"""
S43 — HTF → M1 Limit Trail (XAUUSD locked champions)
====================================================
  A  M5_LIM070   M5 → M1 | NOVOL + no EMA | limit 0.70 ATR | Grade B+
  B  M30_LIM050  M30 → M1 | VOL≥0.40 + EMA9 | limit 0.50 ATR | Grade A
  C  H1_LIM040   H1 → M1 | VOL≥0.40 + EMA9 | limit 0.40 ATR | Grade A
"""
from __future__ import annotations
import numpy as np
from typing import List, Dict
from S43_HTF_M1_Limit_detection import S43Detector, S43Signal

# Live freshness: only alert fills on recent M1 bars
M1_LOOKBACK = 12  # closed M1 bars
MODE_ORDER = ["A", "B", "C"]


def _to_arrays(ohlc: dict) -> Dict[str, np.ndarray]:
    return {
        "Open": np.asarray(ohlc["open"], dtype=float),
        "High": np.asarray(ohlc["high"], dtype=float),
        "Low": np.asarray(ohlc["low"], dtype=float),
        "Close": np.asarray(ohlc["close"], dtype=float),
    }


def _times_dt64(ohlc: dict) -> np.ndarray:
    """Detector requires np.datetime64-compatible times (not raw float unix)."""
    t = np.asarray(ohlc["time"], dtype=float)
    # unix seconds → datetime64[s]
    # guard non-positive / NaN
    t = np.where(np.isfinite(t) & (t > 1e9), t, np.nan)
    # if all bad, synthesize sequential minutes ending "now"
    if not np.any(np.isfinite(t)):
        n = len(ohlc["close"])
        t = np.arange(n, dtype=float) * 60.0 + (np.datetime64("now", "s").astype(float) - (n - 1) * 60.0)
    # fill isolated gaps with linear interp for datetime cast stability
    if np.any(~np.isfinite(t)):
        idx = np.arange(len(t))
        good = np.isfinite(t)
        t = np.interp(idx, idx[good], t[good])
    return (t * 1e9).astype("datetime64[ns]")  # seconds * 1e9 → ns


def scan_s43_mode(
    ohlc_htf: dict,
    ohlc_m1: dict,
    mode: str,
) -> List[dict]:
    if ohlc_htf is None or ohlc_m1 is None:
        return []
    if len(ohlc_m1["close"]) < 120 or len(ohlc_htf["close"]) < 60:
        return []

    code = mode.upper()
    det = S43Detector(mode=code)
    try:
        sigs: List[S43Signal] = det.detect(
            htf_data=_to_arrays(ohlc_htf),
            m1_data=_to_arrays(ohlc_m1),
            htf_times=_times_dt64(ohlc_htf),
            m1_times=_times_dt64(ohlc_m1),
            mode=code,
        )
    except Exception as e:
        print(f"  [S43] detect error mode={code}: {e}", flush=True)
        return []

    n = len(ohlc_m1["close"])
    cfg = S43Detector.MODES[code]
    out = []
    for s in sigs:
        bars_ago = n - 1 - int(s.entry_bar)
        if bars_ago < 0 or bars_ago > M1_LOOKBACK:
            continue
        side = "LONG" if s.direction == 1 else "SHORT"
        entry = float(s.entry_price)
        stop = float(s.stop)
        risk = abs(entry - stop)
        rr = 2.5 if code != "A" else 2.0
        if risk < 1e-12:
            continue
        target = entry + rr * risk if side == "LONG" else entry - rr * risk

        out.append({
            "strategy": "S43",
            "phase": "ENTRY",
            "mode": s.htf_mode or cfg["label"],
            "mode_code": code,
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
            "priority": {"C": 500, "B": 450, "A": 400}.get(code, 300),
            "role": f"S43 {cfg['label']} HTF→M1 Limit Trail",
            "key": f"S43|{cfg['label']}|XAUUSD|{side}|{round(entry, 2)}",
        })
    return out
