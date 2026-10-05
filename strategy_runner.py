import numpy as np
from datetime import datetime, timezone
from S01_pattern_detection import compute_atr as s01_atr, detect_abc_signals
from S03_pattern_detection import compute_atr as s03_atr, detect_hs_signals
from S04_pattern_detection import compute_atr as s04_atr, detect_ifvg_signals

# ====================== ALL 15 MODES ======================
MODES = [
    # ----- S-tier M5 (scan every 3 min) -----
    {"id": "Hybrid_Strict_SESS_VOL", "family": "S01", "market": "XAUUSD", "tf": "M5",
     "pivot": 5, "min_imp": 1.75, "max_retr": 0.88, "tp_mult": 0.55, "session": True, "group": "M5"},
    {"id": "Hybrid_Strict_COMBO", "family": "S01", "market": "XAUUSD", "tf": "M5",
     "pivot": 5, "min_imp": 1.80, "max_retr": 0.87, "tp_mult": 0.55, "session": True, "group": "M5"},
    {"id": "XAU_M5_BAL", "family": "S01", "market": "XAUUSD", "tf": "M5",
     "pivot": 5, "min_imp": 1.75, "max_retr": 0.88, "tp_mult": 0.55, "session": True, "group": "M5"},
    {"id": "XAU_M5_QUAL", "family": "S01", "market": "XAUUSD", "tf": "M5",
     "pivot": 5, "min_imp": 1.90, "max_retr": 0.85, "tp_mult": 0.58, "session": True, "group": "M5"},

    # ----- Higher TF (scan every 9 min) -----
    {"id": "USDJPY_H4_Strict_RR2.5", "family": "S04", "market": "USDJPY", "tf": "H4",
     "filter": "Strict", "rr": 2.5, "sl_mult": 1.0, "group": "HTF"},
    {"id": "JPY_H4_QUAL", "family": "S01", "market": "USDJPY", "tf": "H4",
     "pivot": 7, "min_imp": 1.90, "max_retr": 0.84, "tp_mult": 0.58, "session": True, "group": "HTF"},
    {"id": "GBPUSD_H4_Strict_RR3.0", "family": "S04", "market": "GBPUSD", "tf": "H4",
     "filter": "Strict", "rr": 3.0, "sl_mult": 1.5, "group": "HTF"},
    {"id": "XAUUSD_H4_Bal_RR2.5", "family": "S04", "market": "XAUUSD", "tf": "H4",
     "filter": "Balanced", "rr": 2.5, "sl_mult": 1.0, "group": "HTF"},
    {"id": "XAUUSD_H4_Bal_RR2.0", "family": "S04", "market": "XAUUSD", "tf": "H4",
     "filter": "Balanced", "rr": 2.0, "sl_mult": 1.0, "group": "HTF"},
    {"id": "XAUUSD_M30_Bal_RR2.5", "family": "S04", "market": "XAUUSD", "tf": "M30",
     "filter": "Balanced", "rr": 2.5, "sl_mult": 1.0, "group": "HTF"},
    {"id": "PureHS_XAU_H4_p7", "family": "S03", "market": "XAUUSD", "tf": "H4",
     "pivot": 7, "min_h_atr": 1.2, "rr": 2.0, "group": "HTF"},
    {"id": "BRK_USDJPY_M30_p7", "family": "S01", "market": "USDJPY", "tf": "M30",
     "pivot": 7, "min_imp": 1.0, "max_retr": 0.95, "tp_mult": 1.60, "session": False, "group": "HTF"},
    {"id": "EURUSD_M30_Bal_RR2.5", "family": "S04", "market": "EURUSD", "tf": "M30",
     "filter": "Balanced", "rr": 2.5, "sl_mult": 1.0, "group": "HTF"},
    {"id": "GBP_M15_BAL", "family": "S01", "market": "GBPUSD", "tf": "M15",
     "pivot": 5, "min_imp": 1.70, "max_retr": 0.89, "tp_mult": 0.52, "session": True, "group": "HTF"},
    {"id": "XAUUSD_M30_Bal_RR2.0", "family": "S04", "market": "XAUUSD", "tf": "M30",
     "filter": "Balanced", "rr": 2.0, "sl_mult": 1.0, "group": "HTF"},
]

def is_session_ok():
    h = datetime.now(timezone.utc).hour
    return 7 <= h <= 20

def run_s01(mode, ohlc):
    high, low, close = ohlc["high"], ohlc["low"], ohlc["close"]
    atr = s01_atr(high, low, close)
    if mode.get("session") and not is_session_ok():
        return None
    signals = detect_abc_signals(
        high, low, close, atr,
        pivot_left=mode["pivot"], pivot_right=mode["pivot"],
        min_impulse_atr=mode["min_imp"],
        max_retrace=mode["max_retr"],
        tp_ab_mult=mode["tp_mult"],
        sl_atr_buffer=0.25,
        require_bc_break=True
    )
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
        "family": "S01"
    }

def run_s04(mode, ohlc):
    high = ohlc["high"]
    low = ohlc["low"]
    open_ = ohlc.get("open", ohlc["close"])
    close = ohlc["close"]
    atr = s04_atr(high, low, close)
    signals = detect_ifvg_signals(
        high, low, open_, close, atr,
        filter_mode=mode["filter"],
        sl_atr_mult=mode["sl_mult"],
        tp_rr=mode["rr"],
        entry_mode="Broken Boundary"
    )
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
        "family": "S04"
    }

def run_s03(mode, ohlc):
    high, low, close = ohlc["high"], ohlc["low"], ohlc["close"]
    atr = s03_atr(high, low, close)
    try:
        signals = detect_hs_signals(
            high, low, close, atr,
            pivot_left=mode["pivot"],
            pivot_right=mode["pivot"],
            min_height_atr=mode["min_h_atr"],
            fixed_rr=mode["rr"]
        )
    except Exception:
        return None
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
        "family": "S03"
    }

def check_modes(modes_to_check, get_ohlc_func):
    results = []
    for mode in modes_to_check:
        print(f"  → Checking {mode['id']} ({mode['market']} {mode['tf']})", flush=True)
        ohlc = get_ohlc_func(mode["market"], mode["tf"])
        if ohlc is None or len(ohlc["close"]) < 80:
            print(f"     No data / insufficient bars", flush=True)
            continue
        try:
            if mode["family"] == "S01":
                sig = run_s01(mode, ohlc)
            elif mode["family"] == "S04":
                sig = run_s04(mode, ohlc)
            elif mode["family"] == "S03":
                sig = run_s03(mode, ohlc)
            else:
                sig = None

            if sig:
                print(f"     SIGNAL FOUND → {sig['direction']} @ {sig['entry']}", flush=True)
                results.append(sig)
            else:
                print(f"     No signal", flush=True)
        except Exception as e:
            print(f"     Error: {e}", flush=True)
    return results
