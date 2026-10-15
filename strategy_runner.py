from datetime import datetime, timezone
from S09_pattern_detection import detect_s09_signals

MODES = [
    # ----- AGE family -----
    {"id": "Age_USDJPY_M30_W045_A150", "family": "Age", "market": "USDJPY", "tf": "M30",
     "wick": 0.45, "age": 150, "session": None, "close": False, "rr": 2.5, "priority": 100},
    {"id": "Age_USDJPY_M30_W040_A150", "family": "Age", "market": "USDJPY", "tf": "M30",
     "wick": 0.40, "age": 150, "session": None, "close": False, "rr": 2.5, "priority": 98},
    {"id": "Age_EURUSD_M15_W050_A150", "family": "Age", "market": "EURUSD", "tf": "M15",
     "wick": 0.50, "age": 150, "session": None, "close": False, "rr": 2.5, "priority": 96},
    {"id": "Age_USDJPY_M15_W050_A150", "family": "Age", "market": "USDJPY", "tf": "M15",
     "wick": 0.50, "age": 150, "session": None, "close": False, "rr": 2.5, "priority": 94},
    {"id": "Age_USDJPY_M15_W050_A120", "family": "Age", "market": "USDJPY", "tf": "M15",
     "wick": 0.50, "age": 120, "session": None, "close": False, "rr": 2.5, "priority": 92},
    {"id": "Age_USDJPY_M30_W050_A120", "family": "Age", "market": "USDJPY", "tf": "M30",
     "wick": 0.50, "age": 120, "session": None, "close": False, "rr": 2.5, "priority": 90},

    # ----- CLOSE family (highest quality) -----
    {"id": "Close_EURUSD_M15_W050_A150", "family": "Close", "market": "EURUSD", "tf": "M15",
     "wick": 0.50, "age": 150, "session": None, "close": True, "rr": 2.5, "priority": 120},
    {"id": "Close_GBPUSD_M30_W038_A120", "family": "Close", "market": "GBPUSD", "tf": "M30",
     "wick": 0.38, "age": 120, "session": None, "close": True, "rr": 2.5, "priority": 118},
    {"id": "Close_EURUSD_M15_W050_A120", "family": "Close", "market": "EURUSD", "tf": "M15",
     "wick": 0.50, "age": 120, "session": None, "close": True, "rr": 2.5, "priority": 116},
    {"id": "Close_EURUSD_M15_W045_A150", "family": "Close", "market": "EURUSD", "tf": "M15",
     "wick": 0.45, "age": 150, "session": None, "close": True, "rr": 2.5, "priority": 114},
    {"id": "Close_USDCHF_M15_W050_A150", "family": "Close", "market": "USDCHF", "tf": "M15",
     "wick": 0.50, "age": 150, "session": None, "close": True, "rr": 2.5, "priority": 112},
    {"id": "Close_GBPUSD_M30_W045_A120", "family": "Close", "market": "GBPUSD", "tf": "M30",
     "wick": 0.45, "age": 120, "session": None, "close": True, "rr": 2.5, "priority": 110},

    # ----- SESSION family (LondonNY dropped) -----
    {"id": "Sess_EURUSD_M5_W050_London", "family": "Session", "market": "EURUSD", "tf": "M5",
     "wick": 0.50, "age": 120, "session": "London", "close": False, "rr": 2.5, "priority": 105},
    {"id": "Sess_GBPUSD_M5_W050_London", "family": "Session", "market": "GBPUSD", "tf": "M5",
     "wick": 0.50, "age": 120, "session": "London", "close": False, "rr": 2.5, "priority": 103},
    {"id": "Sess_USDJPY_M30_W050_Active", "family": "Session", "market": "USDJPY", "tf": "M30",
     "wick": 0.50, "age": 120, "session": "Active", "close": False, "rr": 2.5, "priority": 101},
    {"id": "Sess_USDJPY_M15_W050_NY", "family": "Session", "market": "USDJPY", "tf": "M15",
     "wick": 0.50, "age": 120, "session": "NY", "close": False, "rr": 2.5, "priority": 99},
    {"id": "Sess_GBPUSD_M5_W045_London", "family": "Session", "market": "GBPUSD", "tf": "M5",
     "wick": 0.45, "age": 120, "session": "London", "close": False, "rr": 2.5, "priority": 97},
]

def in_session(session_name):
    if session_name is None:
        return True
    h = datetime.now(timezone.utc).hour
    if session_name == "Active":
        return 7 <= h < 21
    if session_name == "London":
        return 7 <= h < 16
    if session_name == "NY":
        return 12 <= h < 21
    return True

def _is_fresh(entry_bar, n, tf):
    lookback = 3 if tf == "M5" else 2
    return entry_bar >= n - lookback

def _stop_still_valid(sig, ohlc):
    high, low, close = ohlc["high"], ohlc["low"], ohlc["close"]
    n = len(close)
    start = max(0, n - 3)

    if sig["direction"] == "LONG":
        for i in range(start, n):
            if low[i] <= sig["sl"]:
                return False, "stop already hit"
        if close[-1] <= sig["sl"]:
            return False, "price past stop"
    else:
        for i in range(start, n):
            if high[i] >= sig["sl"]:
                return False, "stop already hit"
        if close[-1] >= sig["sl"]:
            return False, "price past stop"
    return True, "ok"

def run_s09(mode, ohlc):
    if not in_session(mode.get("session")):
        return None
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    signals = detect_s09_signals(
        high, low, open_, close,
        wick_mult=mode["wick"],
        rr=mode.get("rr", 2.5),
        max_zone_age=mode.get("age", 120),
        require_close=mode.get("close", False)
    )
    if not signals:
        return None
    s = signals[-1]
    if not _is_fresh(s.entry_bar, len(close), mode["tf"]):
        print("     Rejected → stale", flush=True)
        return None
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "market": mode["market"],
        "tf": mode["tf"],
        "entry": round(float(s.entry_price), 5),
        "sl": round(float(s.stop), 5),
        "tp": round(float(s.target), 5),
        "family": mode["family"],
        "priority": mode["priority"],
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
            sig = run_s09(mode, ohlc)
            if sig is None:
                continue
            ok, reason = _stop_still_valid(sig, ohlc)
            if not ok:
                print(f"     Rejected → {reason}", flush=True)
                continue
            print(f"     SIGNAL {sig['direction']} @ {sig['entry']}", flush=True)
            results.append(sig)
        except Exception as e:
            print(f"     Error: {e}", flush=True)
    return results

def select_highest_modes(signals):
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['market']}|{s['direction']}|{round(s['entry'], 5)}"
        if key not in groups or s["priority"] > groups[key]["priority"]:
            groups[key] = s
    selected = list(groups.values())
    print(f"  → Highest-mode kept {len(selected)}", flush=True)
    return selected
