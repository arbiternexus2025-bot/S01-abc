from datetime import datetime, timezone
from S09_pattern_detection import detect_s09_signals

MODES = [
    # USDJPY
    {"id": "S09_SW050_Active_USDJPY", "market": "USDJPY", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "session": "Active", "priority": 110},
    {"id": "S09_SW050_NY_USDJPY", "market": "USDJPY", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "session": "NY", "priority": 100},
    {"id": "S09_W045_Active_USDJPY", "market": "USDJPY", "tf": "M30",
     "wick": 0.45, "rr": 2.5, "session": "Active", "priority": 95},
    {"id": "S09_W040_NY_USDJPY", "market": "USDJPY", "tf": "M30",
     "wick": 0.40, "rr": 2.5, "session": "NY", "priority": 90},

    # GBPUSD
    {"id": "S09_SW050_NY_GBPUSD", "market": "GBPUSD", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "session": "NY", "priority": 105},
    {"id": "S09_W045_NY_GBPUSD", "market": "GBPUSD", "tf": "M30",
     "wick": 0.45, "rr": 2.5, "session": "NY", "priority": 85},

    # USDCHF
    {"id": "S09_SW050_Active_USDCHF", "market": "USDCHF", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "session": "Active", "priority": 100},
    {"id": "S09_SW050_London_USDCHF", "market": "USDCHF", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "session": "London", "priority": 95},
    {"id": "S09_W045_London_USDCHF", "market": "USDCHF", "tf": "M30",
     "wick": 0.45, "rr": 2.5, "session": "London", "priority": 80},

    # EURUSD
    {"id": "S09_SW050_NY_EURUSD", "market": "EURUSD", "tf": "M30",
     "wick": 0.50, "rr": 2.5, "session": "NY", "priority": 95},
    {"id": "S09_W045_NY_EURUSD", "market": "EURUSD", "tf": "M30",
     "wick": 0.45, "rr": 2.5, "session": "NY", "priority": 80},

    # XAUUSD
    {"id": "S09_W045_London_XAUUSD", "market": "XAUUSD", "tf": "M30",
     "wick": 0.45, "rr": 2.5, "session": "London", "priority": 90},
    {"id": "S09_W040_London_XAUUSD", "market": "XAUUSD", "tf": "M30",
     "wick": 0.40, "rr": 2.5, "session": "London", "priority": 75},
]

def in_session(session_name):
    h = datetime.now(timezone.utc).hour
    if session_name == "Active":
        return 7 <= h < 21
    if session_name == "London":
        return 7 <= h < 16
    if session_name == "NY":
        return 12 <= h < 21
    return True

def _is_fresh(entry_bar, n):
    return entry_bar >= n - 2

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
    if not in_session(mode["session"]):
        return None
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    signals = detect_s09_signals(high, low, open_, close,
                                 wick_mult=mode["wick"], rr=mode.get("rr", 2.5))
    if not signals:
        return None
    s = signals[-1]
    if not _is_fresh(s.entry_bar, len(close)):
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
        "family": "S09",
        "priority": mode["priority"],
        "premium": True,
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
