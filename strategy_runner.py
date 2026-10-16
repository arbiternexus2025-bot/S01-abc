from datetime import datetime, timezone
from data_feed import get_ohlc
from S09_pattern_detection import detect_s09, h4_bias

# Official 18 modes (LondonNY included per spec)
MODES = [
    # AGE
    {"id": "Age_USDJPY_M30_W045_A150", "family": "Age", "market": "USDJPY", "tf": "M30",
     "wick": 0.45, "age": 150, "session": None, "close": False, "priority": 100},
    {"id": "Age_USDJPY_M30_W040_A150", "family": "Age", "market": "USDJPY", "tf": "M30",
     "wick": 0.40, "age": 150, "session": None, "close": False, "priority": 98},
    {"id": "Age_EURUSD_M15_W050_A150", "family": "Age", "market": "EURUSD", "tf": "M15",
     "wick": 0.50, "age": 150, "session": None, "close": False, "priority": 96},
    {"id": "Age_USDJPY_M15_W050_A150", "family": "Age", "market": "USDJPY", "tf": "M15",
     "wick": 0.50, "age": 150, "session": None, "close": False, "priority": 94},
    {"id": "Age_USDJPY_M15_W050_A120", "family": "Age", "market": "USDJPY", "tf": "M15",
     "wick": 0.50, "age": 120, "session": None, "close": False, "priority": 92},
    {"id": "Age_USDJPY_M30_W050_A120", "family": "Age", "market": "USDJPY", "tf": "M30",
     "wick": 0.50, "age": 120, "session": None, "close": False, "priority": 90},
    # CLOSE
    {"id": "Close_EURUSD_M15_W050_A150", "family": "Close", "market": "EURUSD", "tf": "M15",
     "wick": 0.50, "age": 150, "session": None, "close": True, "priority": 120},
    {"id": "Close_GBPUSD_M30_W038_A120", "family": "Close", "market": "GBPUSD", "tf": "M30",
     "wick": 0.38, "age": 120, "session": None, "close": True, "priority": 118},
    {"id": "Close_EURUSD_M15_W050_A120", "family": "Close", "market": "EURUSD", "tf": "M15",
     "wick": 0.50, "age": 120, "session": None, "close": True, "priority": 116},
    {"id": "Close_EURUSD_M15_W045_A150", "family": "Close", "market": "EURUSD", "tf": "M15",
     "wick": 0.45, "age": 150, "session": None, "close": True, "priority": 114},
    {"id": "Close_USDCHF_M15_W050_A150", "family": "Close", "market": "USDCHF", "tf": "M15",
     "wick": 0.50, "age": 150, "session": None, "close": True, "priority": 112},
    {"id": "Close_GBPUSD_M30_W045_A120", "family": "Close", "market": "GBPUSD", "tf": "M30",
     "wick": 0.45, "age": 120, "session": None, "close": True, "priority": 110},
    # SESSION
    {"id": "Sess_EURUSD_M5_W050_London", "family": "Session", "market": "EURUSD", "tf": "M5",
     "wick": 0.50, "age": 120, "session": "London", "close": False, "priority": 105},
    {"id": "Sess_GBPUSD_M5_W050_London", "family": "Session", "market": "GBPUSD", "tf": "M5",
     "wick": 0.50, "age": 120, "session": "London", "close": False, "priority": 103},
    {"id": "Sess_USDJPY_M30_W050_Active", "family": "Session", "market": "USDJPY", "tf": "M30",
     "wick": 0.50, "age": 120, "session": "Active", "close": False, "priority": 101},
    {"id": "Sess_USDJPY_M30_W050_LondonNY", "family": "Session", "market": "USDJPY", "tf": "M30",
     "wick": 0.50, "age": 120, "session": "LondonNY", "close": False, "priority": 100},
    {"id": "Sess_USDJPY_M15_W050_NY", "family": "Session", "market": "USDJPY", "tf": "M15",
     "wick": 0.50, "age": 120, "session": "NY", "close": False, "priority": 99},
    {"id": "Sess_GBPUSD_M5_W045_London", "family": "Session", "market": "GBPUSD", "tf": "M5",
     "wick": 0.45, "age": 120, "session": "London", "close": False, "priority": 97},
]

RR = 2.0
FRESH_BARS = 3
_h4_cache = {}

def in_session(name, hour=None):
    if name is None:
        return True
    h = hour if hour is not None else datetime.now(timezone.utc).hour
    if name == "London":
        return 7 <= h < 16
    if name == "NY":
        return 12 <= h < 21
    if name == "Active":
        return 7 <= h < 20
    if name == "LondonNY":
        return (7 <= h < 16) or (12 <= h < 21)
    return True

def get_bias(market):
    now = datetime.now(timezone.utc).timestamp()
    c = _h4_cache.get(market)
    if c and now - c["ts"] < 600:
        return c["bias"]
    ohlc = get_ohlc(market, "H4", limit=120)
    if ohlc is None:
        return 0
    b = h4_bias(ohlc["high"], ohlc["low"], ohlc["close"])
    _h4_cache[market] = {"bias": b, "ts": now}
    return b

def run_mode(mode, ohlc):
    """
    Returns (sig|None, reason).
    Reasons: session | bias | no_zones | no_touch | expired | consumed
             | wick | close | risk | not_fresh | stop_hit | ok
    """
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    n = len(close)

    # Session (use latest bar hour if time available)
    hour = None
    if "time" in ohlc and len(ohlc["time"]):
        try:
            hour = datetime.fromtimestamp(float(ohlc["time"][-1]), tz=timezone.utc).hour
        except Exception:
            hour = None
    if not in_session(mode.get("session"), hour):
        return None, "session"

    bias = get_bias(mode["market"])
    if bias == 0:
        return None, "bias"

    signals, zones, atr = detect_s09(
        high, low, open_, close,
        wick_mult=mode["wick"],
        max_zone_age=mode["age"],
        require_close=mode["close"],
        rr=RR
    )

    if not zones:
        return None, "no_zones"
    if not signals:
        return None, "no_touch"

    s = signals[-1]
    bars_ago = n - 1 - s.entry_bar
    if bars_ago > FRESH_BARS:
        return None, f"expired_or_old (bars_ago={bars_ago})"

    # Bias must match direction
    if s.direction != bias:
        return None, "bias"

    # Stop already violated on recent bars after entry
    start = s.entry_bar + 1
    if s.direction == 1:
        for i in range(start, n):
            if low[i] <= s.stop:
                return None, "stop_hit"
        if close[-1] <= s.stop:
            return None, "stop_hit"
    else:
        for i in range(start, n):
            if high[i] >= s.stop:
                return None, "stop_hit"
        if close[-1] >= s.stop:
            return None, "stop_hit"

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
        "risk": abs(float(s.entry_price) - float(s.stop)),
        "bars_ago": bars_ago,
        "bias": bias,
    }, "ok"

def check_modes(modes, get_ohlc_func):
    results = []
    stats = {}

    def bump(k):
        stats[k] = stats.get(k, 0) + 1

    for mode in modes:
        print(f"  → {mode['id']}", flush=True)
        ohlc = get_ohlc_func(mode["market"], mode["tf"])
        if ohlc is None or len(ohlc["close"]) < 80:
            print("     [no_data]", flush=True)
            bump("no_data")
            continue
        try:
            if "open" not in ohlc:
                ohlc["open"] = ohlc["close"]
            sig, reason = run_mode(mode, ohlc)
            bump(reason.split()[0] if reason else "other")
            if sig is None:
                print(f"     [{reason}]", flush=True)
                continue
            print(
                f"     [SIGNAL] {sig['direction']} @ {sig['entry']} "
                f"SL={sig['sl']} TP={sig['tp']} bias={sig['bias']} bars_ago={sig['bars_ago']}",
                flush=True
            )
            results.append(sig)
        except Exception as e:
            bump("error")
            print(f"     [error] {e}", flush=True)

    print("  == " + " ".join(f"{k}={v}" for k, v in sorted(stats.items())), flush=True)
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
