import numpy as np
from datetime import datetime, timezone
from S01_pattern_detection import compute_atr as s01_atr, detect_abc_signals
from S04_pattern_detection import compute_atr as s04_atr, detect_ifvg_signals
from S09_pattern_detection import detect_s09_signals

MODES = [
    {"id": "S09_StrongWick_050_USDJPY", "family": "S09", "market": "USDJPY", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "group": "M30"},
    {"id": "S09_StrongWick_050_USDCHF", "family": "S09", "market": "USDCHF", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "group": "M30"},
    {"id": "S09_StrongWick_050_GBPUSD", "family": "S09", "market": "GBPUSD", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "group": "M30"},
    {"id": "S09_StrongWick_050_XAUUSD", "family": "S09", "market": "XAUUSD", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "group": "M30"},
    {"id": "S09_StrongWick_050_EURUSD", "family": "S09", "market": "EURUSD", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "group": "M30"},
    {"id": "S09_Wick_045_XAUUSD", "family": "S09", "market": "XAUUSD", "tf": "M30",
     "wick": 0.45, "rr": 2.5, "group": "M30"},
    {"id": "S09_Wick_045_USDJPY", "family": "S09", "market": "USDJPY", "tf": "M30",
     "wick": 0.45, "rr": 2.5, "group": "M30"},
    {"id": "S04_IFVG_Strict_USDJPY_H4", "family": "S04", "market": "USDJPY", "tf": "H4",
     "filter": "Strict", "rr": 2.5, "sl_mult": 1.0, "group": "H4"},
    {"id": "S01_BRK_USDJPY_M30_p7", "family": "S01", "market": "USDJPY", "tf": "M30",
     "pivot": 7, "min_imp": 1.0, "max_retr": 0.95, "tp_mult": 1.60, "group": "M30"},
    {"id": "S04_IFVG_Bal_EURUSD_M30", "family": "S04", "market": "EURUSD", "tf": "M30",
     "filter": "Balanced", "rr": 2.5, "sl_mult": 1.0, "group": "M30"},
]

def run_s09(mode, ohlc):
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    signals = detect_s09_signals(high, low, open_, close,
                                 wick_mult=mode["wick"], rr=mode.get("rr", 2.5))
    if not signals:
        return None
    s = signals[-1]
    if s.entry_bar < len(close) - 4:
        return None
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "market": mode["market"],
        "tf": mode["tf"],
        "entry": round(float(s.entry_price), 5),
        "sl": round(float(s.stop), 5),
        "tp": round(float(s.target), 5),
        "family": "S09",
        "risk": abs(float(s.entry_price) - float(s.stop))
    }

def run_s04(mode, ohlc):
    high, low = ohlc["high"], ohlc["low"]
    open_ = ohlc.get("open", ohlc["close"])
    close = ohlc["close"]
    atr = s04_atr(high, low, close)
    signals = detect_ifvg_signals(high, low, open_, close, atr,
                                  filter_mode=mode["filter"],
                                  sl_atr_mult=mode["sl_mult"],
                                  tp_rr=mode["rr"],
                                  entry_mode="Broken Boundary")
    if not signals:
        return None
    s = signals[-1]
    if s.entry_bar < len(close) - 4:
        return None
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "market": mode["market"],
        "tf": mode["tf"],
        "entry": round(float(s.entry_price), 5),
        "sl": round(float(s.stop), 5),
        "tp": round(float(s.target), 5),
        "family": "S04",
        "risk": abs(float(s.entry_price) - float(s.stop))
    }

def run_s01(mode, ohlc):
    high, low, close = ohlc["high"], ohlc["low"], ohlc["close"]
    atr = s01_atr(high, low, close)
    signals = detect_abc_signals(high, low, close, atr,
                                 pivot_left=mode["pivot"], pivot_right=mode["pivot"],
                                 min_impulse_atr=mode["min_imp"],
                                 max_retrace=mode["max_retr"],
                                 tp_ab_mult=mode["tp_mult"],
                                 sl_atr_buffer=0.25,
                                 require_bc_break=True)
    if not signals:
        return None
    s = signals[-1]
    if s.entry_bar < len(close) - 4:
        return None
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "market": mode["market"],
        "tf": mode["tf"],
        "entry": round(float(s.entry_price), 5),
        "sl": round(float(s.stop), 5),
        "tp": round(float(s.target), 5),
        "family": "S01",
        "risk": abs(float(s.entry_price) - float(s.stop))
    }

def check_modes(modes_to_check, get_ohlc_func):
    results = []
    for mode in modes_to_check:
        print(f"  → {mode['id']}", flush=True)
        ohlc = get_ohlc_func(mode["market"], mode["tf"])
        if ohlc is None or len(ohlc["close"]) < 80:
            print("     No data", flush=True)
            continue
        try:
            if "open" not in ohlc:
                ohlc["open"] = ohlc["close"]
            if mode["family"] == "S09":
                sig = run_s09(mode, ohlc)
            elif mode["family"] == "S04":
                sig = run_s04(mode, ohlc)
            elif mode["family"] == "S01":
                sig = run_s01(mode, ohlc)
            else:
                sig = None
            if sig:
                print(f"     SIGNAL {sig['direction']} @ {sig['entry']}", flush=True)
                results.append(sig)
            else:
                print("     No signal", flush=True)
        except Exception as e:
            print(f"     Error: {e}", flush=True)
    return results
