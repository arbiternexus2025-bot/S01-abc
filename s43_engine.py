"""
S43 — Parabolic SAR Trail live scanner (XAUUSD only)
====================================================
Champions:
  M5_H4_ALIGN  M5 entry + H4 PSAR align + VOL40  · Grade A
  H1_H4_ALIGN  H1 entry + H4 PSAR align + VOL40  · Grade A
  H4_PURE      H4 Pure (no EMA)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import List, Optional

from S43_PSAR_Trail_detection import detect_psar_signals, Mode, MODE_CONFIG


def _naive_utc(t) -> pd.Timestamp:
    try:
        if isinstance(t, (int, float)) and float(t) > 1e9:
            ts = pd.Timestamp(datetime.fromtimestamp(float(t), tz=timezone.utc))
        else:
            ts = pd.Timestamp(t)
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return ts
    except Exception:
        return pd.Timestamp(datetime.utcnow())


def arrays_to_df(ohlc: dict) -> pd.DataFrame:
    n = len(ohlc["close"])
    times = ohlc.get("time")
    if times is None:
        now = datetime.now(timezone.utc).timestamp()
        times = np.array([now - (n - 1 - i) * 300 for i in range(n)])
    return pd.DataFrame({
        "Time": [_naive_utc(x) for x in times],
        "Open": np.asarray(ohlc.get("open", ohlc["close"]), dtype=float),
        "High": np.asarray(ohlc["high"], dtype=float),
        "Low": np.asarray(ohlc["low"], dtype=float),
        "Close": np.asarray(ohlc["close"], dtype=float),
    })


LOOKBACK = {"M5": 3, "H1": 1, "H4": 1}
RR_REF = {"M5_H4_ALIGN": 2.0, "H1_H4_ALIGN": 2.5, "H4_PURE": 3.0}
MODE_PRI = {"M5_H4_ALIGN": 500, "H1_H4_ALIGN": 450, "H4_PURE": 400}


def scan_s43(
    ohlc_ltf: dict,
    market: str,
    mode: str,
    ohlc_htf: Optional[dict] = None,
) -> List[dict]:
    if ohlc_ltf is None or len(ohlc_ltf["close"]) < 150:
        return []
    try:
        mode_e = Mode(mode)
    except Exception:
        return []

    cfg = MODE_CONFIG[mode_e]
    ltf = cfg.get("ltf") or cfg.get("tf") or "H4"
    need_htf = bool(cfg.get("htf_align"))

    df_ltf = arrays_to_df(ohlc_ltf)
    df_htf = None
    if need_htf:
        if ohlc_htf is None or len(ohlc_htf["close"]) < 80:
            return []
        df_htf = arrays_to_df(ohlc_htf)

    try:
        if need_htf:
            sigs = detect_psar_signals(df_ltf, mode=mode_e, htf_df=df_htf)
        else:
            sigs = detect_psar_signals(df_ltf, mode=mode_e, htf_df=None)
    except Exception as e:
        print(f"  [S43] detect error {market} {mode}: {e}", flush=True)
        return []

    n = len(df_ltf)
    lookback = LOOKBACK.get(ltf, 1)
    d = 2 if market == "XAUUSD" else (3 if "JPY" in market else 5)
    rr = RR_REF.get(mode, 2.5)
    out = []

    for s in sigs:
        if s.entry_bar >= n:
            continue
        bars_ago = n - 1 - s.entry_bar
        if bars_ago > lookback or bars_ago < 0:
            continue

        side = "LONG" if s.direction == 1 else "SHORT"
        entry = float(s.entry_price)
        stop = float(s.stop_initial) if s.stop_initial is not None else float(s.psar_at_entry)
        risk = abs(entry - stop)
        if risk < 1e-12:
            continue
        target = entry + rr * risk if side == "LONG" else entry - rr * risk

        tf_label = ltf
        if need_htf and cfg.get("htf"):
            tf_label = f"{ltf}←{cfg['htf']}"

        out.append({
            "strategy": "S43",
            "phase": "ENTRY",
            "mode": mode,
            "market": market,
            "tf": tf_label,
            "direction": side,
            "entry": round(entry, d),
            "stop": round(stop, d),
            "target": round(target, d),
            "psar": round(float(s.psar_at_entry), d),
            "atr_pct": round(float(getattr(s, "atr_pct", 0) or 0), 2),
            "rr": rr,
            "bars_ago": bars_ago,
            "priority": 2000 + MODE_PRI.get(mode, 100),
            "role": cfg.get("description", mode),
            "grade": "A" if "ALIGN" in mode else "A-",
            "trail": True,
            "key": f"S43|{mode}|{market}|{side}|{round(entry, d)}",
        })
    return out
