"""
APEX-19 Strategy Runner — Curated Tier Book
===========================================
S19 only. Research RR (6–8) applied per mode.
Detailed reject logging. Tight freshness for earlier alerts.
Highest-rank wins on duplicate market/direction/entry.
"""
from __future__ import annotations
from data_feed import get_ohlc
from S19_pattern_detection import (
    detect_s19_signals,
    detect_mtf_with_preset,
    PRESETS,
    MTF_PRESETS,
)

# ─────────────────────────────────────────────────────────────
# CURATED BOOK (research RR 6–8)
# Tier 1 = Flagship | Tier 2 = Core | Tier 3 = Satellite
# priority = 1000 - rank
# ─────────────────────────────────────────────────────────────

MODES = [
    # ── Tier 1 — Flagship Core ──
    {
        "rank": 1, "tier": 1, "role": "Flagship",
        "id": "T1_USDJPY_H1_STRONG_st15",
        "strategy": "S19", "market": "USDJPY", "tf": "H1",
        "preset": "H1_STRONG_st15", "rr": 8.0,
        "grade": "S", "expr": 5.23, "wr": 71.0, "n": 62, "oos": 6.50, "maxdd": 5.6,
        "setup": "USDJPY H1 STRONG_st15", "priority": 999,
    },
    {
        "rank": 2, "tier": 1, "role": "Frequency + quality",
        "id": "T1_USDJPY_M30_STRONG_st10",
        "strategy": "S19", "market": "USDJPY", "tf": "M30",
        "preset": "M30_STRONG_st10", "rr": 8.0,
        "grade": "S", "expr": 4.81, "wr": 67.0, "n": 101, "oos": 3.89, "maxdd": 4.6,
        "setup": "USDJPY M30 STRONG_st10", "priority": 998,
    },
    {
        "rank": 3, "tier": 1, "role": "Best H4 EUR",
        "id": "T1_EURUSD_H4_QUALITY_st10",
        "strategy": "S19", "market": "EURUSD", "tf": "H4",
        "preset": "H4_QUALITY_st10", "rr": 8.0,
        "grade": "S", "expr": 4.75, "wr": 71.0, "n": 24, "oos": 6.78, "maxdd": 3.3,
        "setup": "EURUSD H4 QUALITY_st10", "priority": 997,
    },
    {
        "rank": 4, "tier": 1, "role": "Lowest-DD H4",
        "id": "T1_USDCHF_H4_STRONG_OB",
        "strategy": "S19", "market": "USDCHF", "tf": "H4",
        "preset": "H4_STRONG_OB", "rr": 7.0,
        "grade": "S", "expr": 4.50, "wr": 70.0, "n": 30, "oos": 5.67, "maxdd": 2.2,
        "setup": "USDCHF H4 STRONG_OB", "priority": 996,
    },

    # ── Tier 2 — Core Expansion ──
    {
        "rank": 5, "tier": 2, "role": "More JPY H1 trades",
        "id": "T2_USDJPY_H1_STRONG_st10",
        "strategy": "S19", "market": "USDJPY", "tf": "H1",
        "preset": "H1_STRONG_st10", "rr": 8.0,
        "grade": "S", "expr": 4.39, "wr": 62.0, "n": 85, "oos": 4.88, "maxdd": 4.5,
        "setup": "USDJPY H1 STRONG_st10", "priority": 995,
    },
    {
        "rank": 6, "tier": 2, "role": "CHF H1 complement",
        "id": "T2_USDCHF_H1_STRONG_st15",
        "strategy": "S19", "market": "USDCHF", "tf": "H1",
        "preset": "H1_STRONG_st15", "rr": 8.0,
        "grade": "S", "expr": 4.36, "wr": 63.0, "n": 84, "oos": 4.31, "maxdd": 3.4,
        "setup": "USDCHF H1 STRONG_st15", "priority": 994,
    },
    {
        "rank": 7, "tier": 2, "role": "GBP diversification",
        "id": "T2_GBPUSD_H1_STRONG_st15",
        "strategy": "S19", "market": "GBPUSD", "tf": "H1",
        "preset": "H1_STRONG_st15", "rr": 8.0,
        "grade": "S", "expr": 4.08, "wr": 59.0, "n": 103, "oos": 4.91, "maxdd": 5.0,
        "setup": "GBPUSD H1 STRONG_st15", "priority": 993,
    },
    {
        "rank": 8, "tier": 2, "role": "EUR frequency",
        "id": "T2_EURUSD_M30_STRONG_st15",
        "strategy": "S19", "market": "EURUSD", "tf": "M30",
        "preset": "M30_STRONG_st15", "rr": 8.0,
        "grade": "S", "expr": 3.88, "wr": 58.0, "n": 121, "oos": 5.50, "maxdd": 5.8,
        "setup": "EURUSD M30 STRONG_st15", "priority": 992,
    },
    {
        "rank": 9, "tier": 2, "role": "High-WR H4 JPY",
        "id": "T2_USDJPY_H4_QUALITY",
        "strategy": "S19", "market": "USDJPY", "tf": "H4",
        "preset": "H4_QUALITY", "rr": 6.0,
        "grade": "S", "expr": 4.27, "wr": 77.0, "n": 30, "oos": 3.99, "maxdd": 2.0,
        "setup": "USDJPY H4 QUALITY", "priority": 991,
    },

    # ── Tier 3 — Satellites ──
    {
        "rank": 10, "tier": 3, "role": "Scalp — cost sensitive",
        "id": "T3_USDJPY_M5_VOL40_st15",
        "strategy": "S19", "market": "USDJPY", "tf": "M5",
        "preset": "M5_VOL40_st15", "rr": 8.0,
        "grade": "A+", "expr": 4.61, "wr": 66.0, "n": 41, "oos": 6.94, "maxdd": None,
        "setup": "USDJPY M5 VOL40_st15", "priority": 990,
    },
    {
        "rank": 11, "tier": 3, "role": "Scalp CHF",
        "id": "T3_USDCHF_M5_COMBO_st15",
        "strategy": "S19", "market": "USDCHF", "tf": "M5",
        "preset": "M5_COMBO_st15", "rr": 7.0,
        "grade": "A+", "expr": 3.86, "wr": 65.0, "n": 63, "oos": 4.52, "maxdd": None,
        "setup": "USDCHF M5 COMBO_st15", "priority": 989,
    },
    {
        "rank": 12, "tier": 3, "role": "Extra EUR H1",
        "id": "T3_EURUSD_H1_STRONG_st15",
        "strategy": "S19", "market": "EURUSD", "tf": "H1",
        "preset": "H1_STRONG_st15", "rr": 8.0,
        "grade": "A+", "expr": 3.92, "wr": 60.0, "n": 99, "oos": 3.95, "maxdd": None,
        "setup": "EURUSD H1 STRONG_st15", "priority": 988,
    },
    {
        "rank": 13, "tier": 3, "role": "Prefer 6R GBP M30",
        "id": "T3_GBPUSD_M30_STRONG_st15",
        "strategy": "S19", "market": "GBPUSD", "tf": "M30",
        "preset": "M30_STRONG_st15", "rr": 6.0,
        "grade": "A+", "expr": 3.40, "wr": 65.0, "n": 112, "oos": 3.95, "maxdd": None,
        "setup": "GBPUSD M30 STRONG_st15", "priority": 987,
    },
    {
        "rank": 14, "tier": 3, "role": "JPY H1 COMBO",
        "id": "T3_USDJPY_H1_COMBO_st10",
        "strategy": "S19", "market": "USDJPY", "tf": "H1",
        "preset": "H1_COMBO_st10", "rr": 8.0,
        "grade": "A", "expr": 3.50, "wr": 60.0, "n": 0, "oos": None, "maxdd": None,
        "setup": "USDJPY H1 DUAL / COMBO_st10", "priority": 986,
    },
]

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


def _pack(mode, s, bars_ago):
    d = _digits(mode["market"])
    entry = float(s.entry_price)
    rr = float(mode.get("rr", s.rr))
    risk = abs(entry - float(s.stop))
    if risk < 1e-12:
        risk = abs(float(s.risk)) if getattr(s, "risk", 0) else 1e-9
    if s.direction == 1:
        sl = float(s.stop)
        tp = entry + rr * risk
    else:
        sl = float(s.stop)
        tp = entry - rr * risk
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "rank": mode["rank"],
        "tier": mode["tier"],
        "role": mode["role"],
        "grade": mode["grade"],
        "strategy": "S19",
        "market": mode["market"],
        "tf": mode["tf"],
        "preset": mode["preset"],
        "setup": mode["setup"],
        "entry": round(entry, d),
        "sl": round(sl, d),
        "tp": round(tp, d),
        "risk": risk,
        "rr": rr,
        "bars_ago": bars_ago,
        "priority": mode["priority"],
        "expr": mode["expr"],
        "wr": mode["wr"],
        "n_research": mode["n"],
        "oos": mode.get("oos"),
        "maxdd": mode.get("maxdd"),
        "poi_type": getattr(s, "poi_type", "OB"),
        "bias": getattr(s, "bias", ""),
    }


def run_s19(mode, ohlc):
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    times = ohlc.get("time")
    n = len(close)
    preset = mode["preset"]
    if preset not in PRESETS:
        return None, f"bad_preset({preset})"
    params = dict(PRESETS[preset])
    params["rr"] = float(mode.get("rr", params.get("rr", 2.5)))
    try:
        signals = detect_s19_signals(high, low, open_, close, times=times, **params)
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
    return _pack(mode, s, bars_ago), "ok"


def run_s19_mtf(mode):
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
    s.rr = float(mode.get("rr", s.rr))
    return _pack(mode, s, bars_ago), "ok"


def check_modes(modes, get_ohlc_func):
    results = []
    stats = {}

    def bump(k):
        stats[k] = stats.get(k, 0) + 1

    for mode in modes:
        tag = (
            f"#{mode['rank']:02d} T{mode['tier']} [{mode['grade']}] "
            f"{mode['market']} {mode['tf']} RR{mode['rr']:g}"
        )
        print(f"  → {tag}  {mode['preset']}", flush=True)
        try:
            if mode.get("strategy") == "S19_MTF":
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
                f"bars_ago={sig['bars_ago']}  grade={sig['grade']} tier={sig['tier']}",
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
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['market']}|{s['direction']}|{s['entry']}"
        if key not in groups or s["priority"] > groups[key]["priority"]:
            groups[key] = s
    selected = list(groups.values())
    if len(signals) != len(selected):
        print(f"  → Dedup {len(signals)} → {len(selected)} (best rank kept)", flush=True)
    return selected
