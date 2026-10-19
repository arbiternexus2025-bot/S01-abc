from datetime import datetime, timezone
from data_feed import get_ohlc
from S09_pattern_detection import detect_s09, h4_bias
from S19_pattern_detection import (
    detect_s19_signals,
    detect_mtf_with_preset,
    PRESETS,
)

# ============================================================
# S09 Deployment Book (UNCHANGED) + S19 new ranked list
# ============================================================

MODES = [
    # ========== S09 MAIN SESSION (unchanged) ==========
    {"id": "Sess_JPY_M30_W050_Active_BaseLoose", "strategy": "S09", "book": "Main", "family": "Session",
     "market": "USDJPY", "tf": "M30", "wick": 0.50, "age": 120, "session": "Active", "close": False,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.5, "min_z": 0.15,
     "priority": 90},
    {"id": "Sess_JPY_M30_W050_Active_FreqPush", "strategy": "S09", "book": "Main", "family": "Session",
     "market": "USDJPY", "tf": "M30", "wick": 0.50, "age": 120, "session": "Active", "close": False,
     "rr": 1.8, "atr_len": 14, "min_imp": 1.2, "body": 0.45, "rng": 0.60, "max_ba": 1.4, "min_z": 0.18,
     "priority": 88},
    {"id": "Sess_JPY_M30_W050_Active_Imp12", "strategy": "S09", "book": "Main", "family": "Session",
     "market": "USDJPY", "tf": "M30", "wick": 0.50, "age": 120, "session": "Active", "close": False,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.2, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 86},
    {"id": "Sess_JPY_M30_W050_Active", "strategy": "S09", "book": "Main", "family": "Session",
     "market": "USDJPY", "tf": "M30", "wick": 0.50, "age": 120, "session": "Active", "close": False,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 84},
    {"id": "Sess_EUR_M5_W050_London", "strategy": "S09", "book": "Main", "family": "Session",
     "market": "EURUSD", "tf": "M5", "wick": 0.50, "age": 120, "session": "London", "close": False,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 82},
    {"id": "Sess_JPY_M15_W050_NY", "strategy": "S09", "book": "Main", "family": "Session",
     "market": "USDJPY", "tf": "M15", "wick": 0.50, "age": 120, "session": "NY", "close": False,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 80},

    # ========== S09 SATELLITE CLOSE (unchanged) ==========
    {"id": "Close_EUR_M15_W050_RR25", "strategy": "S09", "book": "Satellite", "family": "Close",
     "market": "EURUSD", "tf": "M15", "wick": 0.50, "age": 150, "session": None, "close": True,
     "rr": 2.5, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 95},
    {"id": "Close_EUR_M15_W050_ATR20", "strategy": "S09", "book": "Satellite", "family": "Close",
     "market": "EURUSD", "tf": "M15", "wick": 0.50, "age": 150, "session": None, "close": True,
     "rr": 2.0, "atr_len": 20, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 94},
    {"id": "Close_EUR_M15_W050_A150", "strategy": "S09", "book": "Satellite", "family": "Close",
     "market": "EURUSD", "tf": "M15", "wick": 0.50, "age": 150, "session": None, "close": True,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 93},
    {"id": "Close_GBP_M30_W038_A120", "strategy": "S09", "book": "Satellite", "family": "Close",
     "market": "GBPUSD", "tf": "M30", "wick": 0.38, "age": 120, "session": None, "close": True,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 92},
    {"id": "Close_EUR_M15_W050_A120", "strategy": "S09", "book": "Satellite", "family": "Close",
     "market": "EURUSD", "tf": "M15", "wick": 0.50, "age": 120, "session": None, "close": True,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 91},
    {"id": "Close_EUR_M15_W045_A150", "strategy": "S09", "book": "Satellite", "family": "Close",
     "market": "EURUSD", "tf": "M15", "wick": 0.45, "age": 150, "session": None, "close": True,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 89},
    {"id": "Close_CHF_M15_W050_A150", "strategy": "S09", "book": "Satellite", "family": "Close",
     "market": "USDCHF", "tf": "M15", "wick": 0.50, "age": 150, "session": None, "close": True,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 87},
    {"id": "Close_GBP_M30_W045_A120", "strategy": "S09", "book": "Satellite", "family": "Close",
     "market": "GBPUSD", "tf": "M30", "wick": 0.45, "age": 120, "session": None, "close": True,
     "rr": 2.0, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 85},
    {"id": "Close_EUR_M15_W050_RR22", "strategy": "S09", "book": "Satellite", "family": "Close",
     "market": "EURUSD", "tf": "M15", "wick": 0.50, "age": 150, "session": None, "close": True,
     "rr": 2.2, "atr_len": 14, "min_imp": 1.3, "body": 0.50, "rng": 0.65, "max_ba": 1.3, "min_z": 0.20,
     "priority": 83},

    # ========== S19 NEW RANKED LIST (from agent screenshot) ==========
    # 1–4 H4 single-TF
    {"id": "S19_USDCHF_H4_STRONG_OB", "strategy": "S19", "book": "S19", "family": "STRONG_OB",
     "market": "USDCHF", "tf": "H4", "preset": "H4_STRONG_OB", "priority": 140},
    {"id": "S19_USDJPY_H4_COMBO_QUAL", "strategy": "S19", "book": "S19", "family": "COMBO_QUAL",
     "market": "USDJPY", "tf": "H4", "preset": "H4_QUALITY", "priority": 138},
    {"id": "S19_EURUSD_H4_COMBO_QUAL", "strategy": "S19", "book": "S19", "family": "COMBO_QUAL",
     "market": "EURUSD", "tf": "H4", "preset": "H4_QUALITY", "priority": 136},
    {"id": "S19_XAUUSD_H4_BEST_STACK", "strategy": "S19", "book": "S19", "family": "BEST_STACK",
     "market": "XAUUSD", "tf": "H4", "preset": "H4_QUALITY", "priority": 134},

    # 5,6,8,9,10,11 MTF (H4 context → H1 entry)
    {"id": "S19_USDCHF_MTF_STRONG", "strategy": "S19_MTF", "book": "S19", "family": "MTF_STRONG",
     "market": "USDCHF", "tf": "H1", "preset": "MTF_STRONG", "priority": 132},
    {"id": "S19_XAUUSD_MTF_STRONG", "strategy": "S19_MTF", "book": "S19", "family": "MTF_STRONG",
     "market": "XAUUSD", "tf": "H1", "preset": "MTF_STRONG", "priority": 130},
    {"id": "S19_EURUSD_MTF_STRONG", "strategy": "S19_MTF", "book": "S19", "family": "MTF_STRONG",
     "market": "EURUSD", "tf": "H1", "preset": "MTF_STRONG", "priority": 128},
    {"id": "S19_GBPUSD_MTF_PCT50", "strategy": "S19_MTF", "book": "S19", "family": "MTF_PCT50",
     "market": "GBPUSD", "tf": "H1", "preset": "MTF_PCT50", "priority": 126},
    {"id": "S19_USDJPY_MTF_STRONG", "strategy": "S19_MTF", "book": "S19", "family": "MTF_STRONG",
     "market": "USDJPY", "tf": "H1", "preset": "MTF_STRONG", "priority": 124},
    {"id": "S19_XAUUSD_MTF_PCT50", "strategy": "S19_MTF", "book": "S19", "family": "MTF_PCT50",
     "market": "XAUUSD", "tf": "H1", "preset": "MTF_PCT50", "priority": 122},

    # 7 + 12 USDJPY M30 + EURUSD M30/H1 STRONG_OB
    {"id": "S19_USDJPY_M30_STRONG_OB", "strategy": "S19", "book": "S19", "family": "STRONG_OB",
     "market": "USDJPY", "tf": "M30", "preset": "M30_STRONG_OB", "priority": 120},
    {"id": "S19_EURUSD_M30_STRONG_OB", "strategy": "S19", "book": "S19", "family": "STRONG_OB",
     "market": "EURUSD", "tf": "M30", "preset": "M30_STRONG_OB", "priority": 118},
    {"id": "S19_EURUSD_H1_STRONG_OB", "strategy": "S19", "book": "S19", "family": "STRONG_OB",
     "market": "EURUSD", "tf": "H1", "preset": "H1_STRONG_OB", "priority": 116},

    # S19 M5 SCALP (restored)
    {"id": "S19_USDJPY_M5_VOL40_p5", "strategy": "S19", "book": "S19", "family": "SCALP",
     "market": "USDJPY", "tf": "M5", "preset": "M5_VOL40_P5", "priority": 112},
    {"id": "S19_XAUUSD_M5_COMBO_p3", "strategy": "S19", "book": "S19", "family": "SCALP",
     "market": "XAUUSD", "tf": "M5", "preset": "M5_COMBO_P3", "priority": 110},
]

FRESH = {"M5": 4, "M15": 3, "M30": 3, "H1": 2, "H4": 2}
_h4_cache = {}


def in_session_s09(name, hour=None):
    if name is None:
        return True
    h = hour if hour is not None else datetime.now(timezone.utc).hour
    if name == "Active":
        return 7 <= h < 20
    if name == "London":
        return 7 <= h < 16
    if name == "NY":
        return 12 <= h < 21
    return True


def get_bias_s09(market):
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


def _stop_still_valid(s, high, low, close):
    n = len(close)
    start = s.entry_bar + 1
    if s.direction == 1:
        for i in range(start, n):
            if low[i] <= s.stop:
                return False
        return close[-1] > s.stop
    else:
        for i in range(start, n):
            if high[i] >= s.stop:
                return False
        return close[-1] < s.stop


def run_s09(mode, ohlc):
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    n = len(close)
    hour = None
    if "time" in ohlc and len(ohlc["time"]):
        try:
            hour = datetime.fromtimestamp(float(ohlc["time"][-1]), tz=timezone.utc).hour
        except Exception:
            pass
    if not in_session_s09(mode.get("session"), hour):
        return None, "session"
    bias = get_bias_s09(mode["market"])
    if bias == 0:
        return None, "bias"
    signals, zones, _ = detect_s09(
        high, low, open_, close,
        wick_mult=mode["wick"], max_zone_age=mode["age"], require_close=mode["close"],
        rr=mode["rr"], atr_len=mode.get("atr_len", 14), min_imp=mode.get("min_imp", 1.3),
        body=mode.get("body", 0.50), rng=mode.get("rng", 0.65),
        max_ba=mode.get("max_ba", 1.3), min_z=mode.get("min_z", 0.20),
    )
    if not zones:
        return None, "no_zones"
    if not signals:
        return None, "no_touch"
    s = signals[-1]
    bars_ago = n - 1 - s.entry_bar
    if bars_ago > FRESH.get(mode["tf"], 3):
        return None, f"expired_or_old (bars_ago={bars_ago})"
    if s.direction != bias:
        return None, "bias"
    if not _stop_still_valid(s, high, low, close):
        return None, "stop_hit"
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "strategy": "S09",
        "book": mode.get("book", ""),
        "market": mode["market"],
        "tf": mode["tf"],
        "entry": round(float(s.entry_price), 5),
        "sl": round(float(s.stop), 5),
        "tp": round(float(s.target), 5),
        "family": mode["family"],
        "priority": mode["priority"],
        "risk": abs(float(s.entry_price) - float(s.stop)),
        "rr": mode["rr"],
        "bars_ago": bars_ago,
        "bias": bias,
    }, "ok"


def run_s19(mode, ohlc):
    """Single-TF S19 (H4 / H1 / M30 presets)."""
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    times = ohlc.get("time")
    n = len(close)
    preset_name = mode.get("preset", "H1_STRONG_OB")
    if preset_name not in PRESETS:
        return None, f"bad_preset({preset_name})"
    params = dict(PRESETS[preset_name])
    signals = detect_s19_signals(high, low, open_, close, times=times, **params)
    if not signals:
        return None, "no_signal"
    s = signals[-1]
    bars_ago = n - 1 - s.entry_bar
    if bars_ago > FRESH.get(mode["tf"], 3):
        return None, f"expired_or_old (bars_ago={bars_ago})"
    if not _stop_still_valid(s, high, low, close):
        return None, "stop_hit"
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "strategy": "S19",
        "book": "S19",
        "market": mode["market"],
        "tf": mode["tf"],
        "entry": round(float(s.entry_price), 5),
        "sl": round(float(s.stop), 5),
        "tp": round(float(s.target), 5),
        "family": mode["family"],
        "priority": mode["priority"],
        "risk": abs(float(s.entry_price) - float(s.stop)),
        "rr": s.rr,
        "bars_ago": bars_ago,
        "bias": getattr(s, "bias", None),
        "poi_type": getattr(s, "poi_type", "OB"),
    }, "ok"


def run_s19_mtf(mode):
    """Multi-TF S19: H4 context → H1 entry."""
    market = mode["market"]
    ohlc4 = get_ohlc(market, "H4", limit=150)
    ohlc1 = get_ohlc(market, "H1", limit=300)
    if ohlc4 is None or ohlc1 is None:
        return None, "no_data"
    if "open" not in ohlc1:
        ohlc1["open"] = ohlc1["close"]
    if len(ohlc1["close"]) < 80 or len(ohlc4["close"]) < 50:
        return None, "no_data"

    preset_name = mode.get("preset", "MTF_STRONG")
    try:
        signals = detect_mtf_with_preset(
            ohlc4["high"], ohlc4["low"], ohlc4["close"], ohlc4["time"],
            ohlc1["high"], ohlc1["low"], ohlc1["open"], ohlc1["close"], ohlc1["time"],
            preset=preset_name,
        )
    except Exception as e:
        return None, f"mtf_error({e})"

    if not signals:
        return None, "no_signal"

    s = signals[-1]
    n = len(ohlc1["close"])
    bars_ago = n - 1 - s.entry_bar
    if bars_ago > FRESH.get("H1", 2):
        return None, f"expired_or_old (bars_ago={bars_ago})"
    if not _stop_still_valid(s, ohlc1["high"], ohlc1["low"], ohlc1["close"]):
        return None, "stop_hit"

    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "strategy": "S19",
        "book": "S19",
        "market": market,
        "tf": "H1",
        "entry": round(float(s.entry_price), 5),
        "sl": round(float(s.stop), 5),
        "tp": round(float(s.target), 5),
        "family": mode["family"],
        "priority": mode["priority"],
        "risk": abs(float(s.entry_price) - float(s.stop)),
        "rr": s.rr,
        "bars_ago": bars_ago,
        "bias": getattr(s, "bias", None),
        "poi_type": getattr(s, "poi_type", "OB"),
    }, "ok"


def check_modes(modes, get_ohlc_func):
    results = []
    stats = {}

    def bump(k):
        stats[k] = stats.get(k, 0) + 1

    for mode in modes:
        print(f"  → {mode['id']}", flush=True)
        try:
            strat = mode.get("strategy")
            if strat == "S19_MTF":
                sig, reason = run_s19_mtf(mode)
            elif strat == "S19":
                ohlc = get_ohlc_func(mode["market"], mode["tf"])
                if ohlc is None or len(ohlc["close"]) < 80:
                    print("     [no_data]", flush=True)
                    bump("no_data")
                    continue
                if "open" not in ohlc:
                    ohlc["open"] = ohlc["close"]
                sig, reason = run_s19(mode, ohlc)
            else:
                ohlc = get_ohlc_func(mode["market"], mode["tf"])
                if ohlc is None or len(ohlc["close"]) < 80:
                    print("     [no_data]", flush=True)
                    bump("no_data")
                    continue
                if "open" not in ohlc:
                    ohlc["open"] = ohlc["close"]
                sig, reason = run_s09(mode, ohlc)

            bump(reason.split()[0] if reason else "other")
            if sig is None:
                print(f"     [{reason}]", flush=True)
                continue
            print(
                f"     [SIGNAL] {sig['strategy']} {sig['direction']} @ {sig['entry']} "
                f"SL={sig['sl']} TP={sig['tp']} RR={sig['rr']} bars_ago={sig['bars_ago']}",
                flush=True,
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
