"""
APEX-19 Strategy Runner
=======================
S19 Top-50 only. No S09.
Detailed reject logging. Tight freshness for earlier alerts.
Highest-rank wins on duplicate market/direction/entry.
"""
from __future__ import annotations
from datetime import datetime, timezone
from data_feed import get_ohlc
from S19_pattern_detection import (
    detect_with_preset,
    detect_mtf_with_preset,
    PRESETS,
    MTF_PRESETS,
)

# ─────────────────────────────────────────────────────────────
# APEX-19 Top 50 modes (rank 1 = best)
# priority = 1000 - rank
# ─────────────────────────────────────────────────────────────

MODES = [
    # rank, id, strategy, market, tf, preset, grade, ExpR, WR, N, setup, priority
    {"rank": 1,  "id": "R01_USDCHF_H4_STRONG_OB",     "strategy": "S19",     "market": "USDCHF", "tf": "H4", "preset": "H4_STRONG_OB",    "grade": "S",  "expr": 2.16, "wr": 93.1, "n": 29,  "setup": "H4 STRONG_OB / COMBO_QUAL", "priority": 999},
    {"rank": 2,  "id": "R02_USDJPY_H4_STRONG_st10",   "strategy": "S19",     "market": "USDJPY", "tf": "H4", "preset": "H4_STRONG_st10",  "grade": "S",  "expr": 2.12, "wr": 91.9, "n": 37,  "setup": "H4 COMBO_QUAL / st10",      "priority": 998},
    {"rank": 3,  "id": "R03_GBPUSD_H4_QUALITY",       "strategy": "S19",     "market": "GBPUSD", "tf": "H4", "preset": "H4_QUALITY",      "grade": "S",  "expr": 2.14, "wr": 92.6, "n": 27,  "setup": "H4 QUALITY baseline",       "priority": 997},
    {"rank": 4,  "id": "R04_EURUSD_H1_STRONG_st15",   "strategy": "S19",     "market": "EURUSD", "tf": "H1", "preset": "H1_STRONG_st15",  "grade": "S",  "expr": 2.13, "wr": 93.3, "n": 104, "setup": "H1 STRONG + EMA50_st15",    "priority": 996},
    {"rank": 5,  "id": "R05_EURUSD_H4_QUALITY",       "strategy": "S19",     "market": "EURUSD", "tf": "H4", "preset": "H4_QUALITY",      "grade": "S",  "expr": 1.91, "wr": 87.9, "n": 33,  "setup": "H4 QUALITY / COMBO_QUAL",   "priority": 995},
    {"rank": 6,  "id": "R06_USDCHF_H1_STRONG_st15",   "strategy": "S19",     "market": "USDCHF", "tf": "H1", "preset": "H1_STRONG_st15",  "grade": "S",  "expr": 2.06, "wr": 91.2, "n": 91,  "setup": "H1 STRONG + EMA50_st15",    "priority": 994},
    {"rank": 7,  "id": "R07_USDCHF_M30_STRONG_st15",  "strategy": "S19",     "market": "USDCHF", "tf": "M30","preset": "M30_STRONG_st15", "grade": "S",  "expr": 2.04, "wr": 91.3, "n": 104, "setup": "M30 STRONG + EMA50_st15",   "priority": 993},
    {"rank": 8,  "id": "R08_EURUSD_H1_STRONG_st10",   "strategy": "S19",     "market": "EURUSD", "tf": "H1", "preset": "H1_STRONG_st10",  "grade": "S",  "expr": 2.02, "wr": 90.2, "n": 143, "setup": "H1 STRONG + EMA50_st10",    "priority": 992},
    {"rank": 9,  "id": "R09_USDJPY_H1_STRONG_st15",   "strategy": "S19",     "market": "USDJPY", "tf": "H1", "preset": "H1_STRONG_st15",  "grade": "S",  "expr": 2.00, "wr": 89.2, "n": 65,  "setup": "H1 STRONG + EMA50_st15",    "priority": 991},
    {"rank": 10, "id": "R10_USDJPY_H1_STRONG_st10",   "strategy": "S19",     "market": "USDJPY", "tf": "H1", "preset": "H1_STRONG_st10",  "grade": "S",  "expr": 1.99, "wr": 88.8, "n": 89,  "setup": "H1 STRONG + EMA50_st10",    "priority": 990},
    {"rank": 11, "id": "R11_USDCHF_H1_STRONG_st10",   "strategy": "S19",     "market": "USDCHF", "tf": "H1", "preset": "H1_STRONG_st10",  "grade": "S",  "expr": 1.99, "wr": 89.0, "n": 146, "setup": "H1 STRONG + EMA50_st10",    "priority": 989},
    {"rank": 12, "id": "R12_XAUUSD_H4_STRONG_OB",     "strategy": "S19",     "market": "XAUUSD", "tf": "H4", "preset": "H4_STRONG_OB",    "grade": "S",  "expr": 1.69, "wr": 74.0, "n": 23,  "setup": "H4 BEST_STACK / STRONG",    "priority": 988},
    {"rank": 13, "id": "R13_GBPUSD_M30_STRONG_st15",  "strategy": "S19",     "market": "GBPUSD", "tf": "M30","preset": "M30_STRONG_st15", "grade": "S",  "expr": 1.89, "wr": 87.2, "n": 117, "setup": "M30 STRONG + EMA50_st15",   "priority": 987},
    {"rank": 14, "id": "R14_EURUSD_M30_STRONG_st15",  "strategy": "S19",     "market": "EURUSD", "tf": "M30","preset": "M30_STRONG_st15", "grade": "S",  "expr": 1.85, "wr": 85.7, "n": 133, "setup": "M30 STRONG + EMA50_st15",   "priority": 986},
    {"rank": 15, "id": "R15_USDJPY_M30_STRONG_st10",  "strategy": "S19",     "market": "USDJPY", "tf": "M30","preset": "M30_STRONG_st10", "grade": "S",  "expr": 1.85, "wr": 85.6, "n": 104, "setup": "M30 STRONG + EMA50_st10",   "priority": 985},
    {"rank": 16, "id": "R16_GBPUSD_M30_STRONG_st10",  "strategy": "S19",     "market": "GBPUSD", "tf": "M30","preset": "M30_STRONG_st10", "grade": "S",  "expr": 1.83, "wr": 85.5, "n": 173, "setup": "M30 STRONG + EMA50_st10",   "priority": 984},
    {"rank": 17, "id": "R17_USDCHF_M30_STRONG_st10",  "strategy": "S19",     "market": "USDCHF", "tf": "M30","preset": "M30_STRONG_st10", "grade": "S",  "expr": 1.86, "wr": 86.2, "n": 160, "setup": "M30 STRONG + EMA50_st10",   "priority": 983},
    {"rank": 18, "id": "R18_USDCHF_MTF_STRONG",       "strategy": "S19_MTF", "market": "USDCHF", "tf": "H1", "preset": "MTF_STRONG",      "grade": "S",  "expr": 1.61, "wr": 78.2, "n": 78,  "setup": "MTF_STRONG H4→H1",          "priority": 982},
    {"rank": 19, "id": "R19_XAUUSD_H1_STRONG_st05",   "strategy": "S19",     "market": "XAUUSD", "tf": "H1", "preset": "H1_STRONG_st05",  "grade": "S",  "expr": 1.70, "wr": 82.2, "n": 146, "setup": "H1 STRONG + EMA50_st05",    "priority": 981},
    {"rank": 20, "id": "R20_XAUUSD_M30_STRONG_OB",    "strategy": "S19",     "market": "XAUUSD", "tf": "M30","preset": "M30_STRONG_OB",   "grade": "S",  "expr": 1.78, "wr": 85.6, "n": 174, "setup": "M30 STRONG baseline",       "priority": 980},
    {"rank": 21, "id": "R21_XAUUSD_MTF_STRONG",       "strategy": "S19_MTF", "market": "XAUUSD", "tf": "H1", "preset": "MTF_STRONG",      "grade": "S",  "expr": 1.53, "wr": 77.4, "n": 62,  "setup": "MTF_STRONG H4→H1",          "priority": 979},
    {"rank": 22, "id": "R22_EURUSD_MTF_STRONG",       "strategy": "S19_MTF", "market": "EURUSD", "tf": "H1", "preset": "MTF_STRONG",      "grade": "S",  "expr": 1.49, "wr": 74.7, "n": 83,  "setup": "MTF_STRONG H4→H1",          "priority": 978},
    {"rank": 23, "id": "R23_GBPUSD_M15_COMBO_st15",   "strategy": "S19",     "market": "GBPUSD", "tf": "M15","preset": "M15_COMBO_st15",  "grade": "A+", "expr": 1.72, "wr": 97.4, "n": 39,  "setup": "M15_COMBO + st15",          "priority": 977},
    {"rank": 24, "id": "R24_USDCHF_M15_COMBO_st15",   "strategy": "S19",     "market": "USDCHF", "tf": "M15","preset": "M15_COMBO_st15",  "grade": "A+", "expr": 1.68, "wr": 95.8, "n": 48,  "setup": "M15_COMBO + st15",          "priority": 976},
    {"rank": 25, "id": "R25_USDJPY_M15_COMBO_st05",   "strategy": "S19",     "market": "USDJPY", "tf": "M15","preset": "M15_COMBO_st05",  "grade": "A+", "expr": 1.65, "wr": 94.4, "n": 89,  "setup": "M15_COMBO + st05",          "priority": 975},
    {"rank": 26, "id": "R26_EURUSD_M15_COMBO_st10",   "strategy": "S19",     "market": "EURUSD", "tf": "M15","preset": "M15_COMBO_st10",  "grade": "A+", "expr": 1.50, "wr": 89.4, "n": 85,  "setup": "M15_COMBO + st10",          "priority": 974},
    {"rank": 27, "id": "R27_USDCHF_M5_COMBO_st15",    "strategy": "S19",     "market": "USDCHF", "tf": "M5", "preset": "M5_COMBO_st15",   "grade": "A+", "expr": 1.61, "wr": 96.4, "n": 28,  "setup": "M5_COMBO + st15",           "priority": 973},
    {"rank": 28, "id": "R28_EURUSD_M5_COMBO_st10",    "strategy": "S19",     "market": "EURUSD", "tf": "M5", "preset": "M5_COMBO_st10",   "grade": "A+", "expr": 1.60, "wr": 95.0, "n": 40,  "setup": "M5_COMBO + st10",           "priority": 972},
    {"rank": 29, "id": "R29_USDJPY_M5_COMBO_st10",    "strategy": "S19",     "market": "USDJPY", "tf": "M5", "preset": "M5_COMBO_st10",   "grade": "A+", "expr": 1.57, "wr": 94.1, "n": 34,  "setup": "M5_COMBO + st10",           "priority": 971},
    {"rank": 30, "id": "R30_GBPUSD_MTF_PCT50",        "strategy": "S19_MTF", "market": "GBPUSD", "tf": "H1", "preset": "MTF_PCT50",       "grade": "S",  "expr": 1.42, "wr": 72.9, "n": 85,  "setup": "MTF_PCT50 H4→H1",           "priority": 970},
    {"rank": 31, "id": "R31_EURUSD_H1_STRONG_OB",     "strategy": "S19",     "market": "EURUSD", "tf": "H1", "preset": "H1_STRONG_OB",    "grade": "S",  "expr": 1.32, "wr": 70.0, "n": 230, "setup": "H1 STRONG baseline",        "priority": 969},
    {"rank": 32, "id": "R32_XAUUSD_H1_STRONG_OB",     "strategy": "S19",     "market": "XAUUSD", "tf": "H1", "preset": "H1_STRONG_OB",    "grade": "S",  "expr": 1.57, "wr": 78.4, "n": 167, "setup": "H1 STRONG + EMA50_s2",      "priority": 968},
    {"rank": 33, "id": "R33_EURUSD_M30_STRONG_st05",  "strategy": "S19",     "market": "EURUSD", "tf": "M30","preset": "M30_STRONG_st05", "grade": "S",  "expr": 1.67, "wr": 80.4, "n": 225, "setup": "M30 STRONG + EMA50_st05",   "priority": 967},
    {"rank": 34, "id": "R34_GBPUSD_M30_STRONG_st05",  "strategy": "S19",     "market": "GBPUSD", "tf": "M30","preset": "M30_STRONG_st05", "grade": "S",  "expr": 1.79, "wr": 84.2, "n": 222, "setup": "M30 STRONG + EMA50_st05",   "priority": 966},
    {"rank": 35, "id": "R35_USDCHF_M30_STRONG_st05",  "strategy": "S19",     "market": "USDCHF", "tf": "M30","preset": "M30_STRONG_st05", "grade": "S",  "expr": 1.78, "wr": 83.8, "n": 210, "setup": "M30 STRONG + EMA50_st05",   "priority": 965},
    {"rank": 36, "id": "R36_GBPUSD_H1_STRONG_OB",     "strategy": "S19",     "market": "GBPUSD", "tf": "H1", "preset": "H1_STRONG_OB",    "grade": "S",  "expr": 1.28, "wr": 69.0, "n": 216, "setup": "H1 STRONG baseline",        "priority": 964},
    {"rank": 37, "id": "R37_XAUUSD_H1_STRONG_OB_b",   "strategy": "S19",     "market": "XAUUSD", "tf": "H1", "preset": "H1_STRONG_OB",    "grade": "A+", "expr": 1.21, "wr": 68.6, "n": 175, "setup": "H1 STRONG baseline",        "priority": 963},
    {"rank": 38, "id": "R38_GBPUSD_M15_STRONG_st15",  "strategy": "S19",     "market": "GBPUSD", "tf": "M15","preset": "M15_STRONG_st15", "grade": "A+", "expr": 1.47, "wr": 89.0, "n": 82,  "setup": "M15_STRONG + st15",         "priority": 962},
    {"rank": 39, "id": "R39_USDCHF_M15_STRONG_st15",  "strategy": "S19",     "market": "USDCHF", "tf": "M15","preset": "M15_STRONG_st15", "grade": "A+", "expr": 1.48, "wr": 89.2, "n": 83,  "setup": "M15_STRONG + st15",         "priority": 961},
    {"rank": 40, "id": "R40_EURUSD_M15_COMBO_st15",   "strategy": "S19",     "market": "EURUSD", "tf": "M15","preset": "M15_COMBO_st15",  "grade": "A+", "expr": 1.50, "wr": 89.5, "n": 57,  "setup": "M15_COMBO + st15",          "priority": 960},
    {"rank": 41, "id": "R41_XAUUSD_M5_COMBO_st05",    "strategy": "S19",     "market": "XAUUSD", "tf": "M5", "preset": "M5_COMBO_st05",   "grade": "A",  "expr": 1.38, "wr": 89.3, "n": 56,  "setup": "M5_COMBO + st05",           "priority": 959},
    {"rank": 42, "id": "R42_XAUUSD_M5_COMBO",         "strategy": "S19",     "market": "XAUUSD", "tf": "M5", "preset": "M5_COMBO",        "grade": "A",  "expr": 1.37, "wr": 89.0, "n": 73,  "setup": "M5_COMBO baseline",         "priority": 958},
    {"rank": 43, "id": "R43_USDJPY_M5_VOL40_st15",    "strategy": "S19",     "market": "USDJPY", "tf": "M5", "preset": "M5_VOL40_st15",   "grade": "A+", "expr": 1.54, "wr": 93.0, "n": 43,  "setup": "M5_VOL40 + st15",           "priority": 957},
    {"rank": 44, "id": "R44_GBPUSD_M5_COMBO_st15",    "strategy": "S19",     "market": "GBPUSD", "tf": "M5", "preset": "M5_COMBO_st15",   "grade": "A",  "expr": 1.48, "wr": 91.9, "n": 37,  "setup": "M5_COMBO + st15",           "priority": 956},
    {"rank": 45, "id": "R45_EURUSD_M15_STRONG_st10",  "strategy": "S19",     "market": "EURUSD", "tf": "M15","preset": "M15_STRONG_st10", "grade": "A",  "expr": 1.27, "wr": 81.6, "n": 136, "setup": "M15_STRONG + st10",         "priority": 955},
    {"rank": 46, "id": "R46_EURUSD_M30_STRONG_OB",    "strategy": "S19",     "market": "EURUSD", "tf": "M30","preset": "M30_STRONG_OB",   "grade": "S",  "expr": 1.70, "wr": 81.4, "n": 258, "setup": "M30 STRONG baseline",       "priority": 954},
    {"rank": 47, "id": "R47_GBPUSD_M30_STRONG_OB",    "strategy": "S19",     "market": "GBPUSD", "tf": "M30","preset": "M30_STRONG_OB",   "grade": "S",  "expr": 1.77, "wr": 84.0, "n": 257, "setup": "M30 STRONG baseline",       "priority": 953},
    {"rank": 48, "id": "R48_XAUUSD_MTF_PCT50",        "strategy": "S19_MTF", "market": "XAUUSD", "tf": "H1", "preset": "MTF_PCT50",       "grade": "S",  "expr": 1.41, "wr": 74.3, "n": 70,  "setup": "MTF_PCT50 H4→H1",           "priority": 952},
    {"rank": 49, "id": "R49_EURUSD_H1_DUAL",          "strategy": "S19",     "market": "EURUSD", "tf": "H1", "preset": "H1_DUAL",         "grade": "A+", "expr": 1.89, "wr": 86.2, "n": 167, "setup": "H1 STRONG + DUAL_50_200",   "priority": 951},
    {"rank": 50, "id": "R50_EURUSD_M5_STRONG_st15",   "strategy": "S19",     "market": "EURUSD", "tf": "M5", "preset": "M5_STRONG_st15",  "grade": "A",  "expr": 1.39, "wr": 88.1, "n": 59,  "setup": "M5_STRONG + st15",          "priority": 950},
]

# Tighter freshness → earlier alerts (bars ago on last closed bar)
FRESH = {"M5": 2, "M15": 2, "M30": 2, "H1": 1, "H4": 1}


def _stop_still_valid(s, high, low, close) -> bool:
    n = len(close)
    start = s.entry_bar + 1
    if s.direction == 1:
        for i in range(start, n):
            if low[i] <= s.stop:
                return False
        return float(close[-1]) > s.stop
    for i in range(start, n):
        if high[i] >= s.stop:
            return False
    return float(close[-1]) < s.stop


def _digits(market: str) -> int:
    if market == "XAUUSD":
        return 2
    if market == "USDJPY":
        return 3
    return 5


def _pack(mode, s, bars_ago, tf_label):
    d = _digits(mode["market"])
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "rank": mode["rank"],
        "grade": mode["grade"],
        "strategy": "S19",
        "market": mode["market"],
        "tf": tf_label,
        "preset": mode["preset"],
        "setup": mode["setup"],
        "entry": round(float(s.entry_price), d),
        "sl": round(float(s.stop), d),
        "tp": round(float(s.target), d),
        "risk": abs(float(s.entry_price) - float(s.stop)),
        "rr": float(s.rr),
        "bars_ago": bars_ago,
        "priority": mode["priority"],
        "expr": mode["expr"],
        "wr": mode["wr"],
        "n_research": mode["n"],
        "poi_type": getattr(s, "poi_type", "OB"),
        "bias": getattr(s, "bias", ""),
    }


def run_s19(mode, ohlc):
    """Single-TF S19."""
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    times = ohlc.get("time")
    n = len(close)
    preset = mode["preset"]
    if preset not in PRESETS:
        return None, f"bad_preset({preset})"
    try:
        signals = detect_with_preset(high, low, open_, close, times=times, preset=preset)
    except Exception as e:
        return None, f"detect_error({e})"
    if not signals:
        return None, "no_signal"
    s = signals[-1]
    bars_ago = n - 1 - s.entry_bar
    max_age = FRESH.get(mode["tf"], 2)
    if bars_ago > max_age:
        return None, f"expired_or_old (bars_ago={bars_ago} max={max_age})"
    if not _stop_still_valid(s, high, low, close):
        return None, "stop_already_hit"
    return _pack(mode, s, bars_ago, mode["tf"]), "ok"


def run_s19_mtf(mode):
    """H4 context → H1 entry."""
    market = mode["market"]
    ohlc4 = get_ohlc(market, "H4", limit=150)
    ohlc1 = get_ohlc(market, "H1", limit=300)
    if ohlc4 is None or ohlc1 is None:
        return None, "no_data"
    if "open" not in ohlc1:
        ohlc1["open"] = ohlc1["close"]
    if len(ohlc1["close"]) < 80 or len(ohlc4["close"]) < 40:
        return None, "no_data"
    preset = mode["preset"]
    if preset not in MTF_PRESETS:
        return None, f"bad_mtf_preset({preset})"
    try:
        signals = detect_mtf_with_preset(
            ohlc4["high"], ohlc4["low"], ohlc4["close"], ohlc4["time"],
            ohlc1["high"], ohlc1["low"], ohlc1["open"], ohlc1["close"], ohlc1["time"],
            preset=preset,
        )
    except Exception as e:
        return None, f"mtf_error({e})"
    if not signals:
        return None, "no_signal"
    s = signals[-1]
    n = len(ohlc1["close"])
    bars_ago = n - 1 - s.entry_bar
    max_age = FRESH.get("H1", 1)
    if bars_ago > max_age:
        return None, f"expired_or_old (bars_ago={bars_ago} max={max_age})"
    if not _stop_still_valid(s, ohlc1["high"], ohlc1["low"], ohlc1["close"]):
        return None, "stop_already_hit"
    return _pack(mode, s, bars_ago, "H1"), "ok"


def check_modes(modes, get_ohlc_func):
    results = []
    stats = {}

    def bump(k):
        stats[k] = stats.get(k, 0) + 1

    for mode in modes:
        tag = f"R{mode['rank']:02d} {mode['market']} {mode['tf']} [{mode['grade']}]"
        print(f"  → {tag}  {mode['preset']}", flush=True)
        try:
            if mode["strategy"] == "S19_MTF":
                sig, reason = run_s19_mtf(mode)
            else:
                ohlc = get_ohlc_func(mode["market"], mode["tf"])
                if ohlc is None or len(ohlc["close"]) < 80:
                    print("     ✗ [no_data]", flush=True)
                    bump("no_data")
                    continue
                if "open" not in ohlc:
                    ohlc["open"] = ohlc["close"]
                sig, reason = run_s19(mode, ohlc)

            key = reason.split()[0] if reason else "other"
            bump(key)
            if sig is None:
                print(f"     ✗ [{reason}]", flush=True)
                continue
            print(
                f"     ★ SIGNAL {sig['direction']} @ {sig['entry']}  "
                f"SL={sig['sl']} TP={sig['tp']}  RR={sig['rr']}  "
                f"bars_ago={sig['bars_ago']}  grade={sig['grade']}",
                flush=True,
            )
            results.append(sig)
        except Exception as e:
            bump("error")
            print(f"     ✗ [error] {e}", flush=True)

    summary = " ".join(f"{k}={v}" for k, v in sorted(stats.items()))
    print(f"  == {summary}", flush=True)
    return results


def select_highest_modes(signals):
    """Same market + direction + entry → keep highest priority (best rank)."""
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['market']}|{s['direction']}|{s['entry']}"
        if key not in groups or s["priority"] > groups[key]["priority"]:
            groups[key] = s
    selected = list(groups.values())
    if len(signals) != len(selected):
        print(f"  → Dedup {len(signals)} → {len(selected)} (highest rank kept)", flush=True)
    return selected
