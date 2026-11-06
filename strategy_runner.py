"""
APEX-19 — S19 Lethal Edge Watch Engine
======================================
S-tier S19 only · Majors + minors + gold · M30 / H1 / H4
Alerts when setup is ARMED (ready) before POI touch — for analysis, not auto-entry.
"""
from __future__ import annotations
from data_feed import get_ohlc
from S19_pattern_detection import PRESETS
from S19_watch_detection import detect_armed_with_preset

# ─────────────────────────────────────────────────────────────
# Markets
# ─────────────────────────────────────────────────────────────
MARKETS = [
    # Majors
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    # Minors
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURAUD", "EURCHF", "GBPCHF",
    "CADJPY", "CHFJPY", "AUDCAD", "AUDNZD", "NZDJPY",
    # Gold
    "XAUUSD",
]

# Lethal presets by TF (from research deployment guide)
LETHAL = {
    "H4": [
        ("H4_QUALITY_st10_rr8", "S", "Sniper Quality RR8"),
        ("H4_QUALITY_st10_rr5", "S", "Sniper Quality RR5"),
        ("H4_STRONG_st10_rr5", "S", "Strong RR5"),
    ],
    "H1": [
        ("H1_STRONG_st15_rr8", "S", "Flagship st15 RR8"),
        ("H1_STRONG_st10_rr8", "S", "Strong st10 RR8"),
    ],
    "M30": [
        ("M30_STRONG_st15_rr8", "S", "Frequency+Quality st15 RR8"),
        ("M30_STRONG_st10_rr8", "S", "Frequency st10 RR8"),
    ],
}

FRESH = {"M30": 2, "H1": 1, "H4": 1}


def _build_modes():
    modes = []
    rank = 0
    # Priority: H4 Quality > H1 Flagship > M30
    base_pri = {"H4": 2000, "H1": 1800, "M30": 1600}
    for market in MARKETS:
        for tf, presets in LETHAL.items():
            for preset, grade, role in presets:
                if preset not in PRESETS:
                    continue
                rank += 1
                modes.append({
                    "rank": rank,
                    "tier": 1,
                    "role": role,
                    "id": f"S19_{market}_{tf}_{preset}",
                    "strategy": "S19",
                    "market": market,
                    "tf": tf,
                    "preset": preset,
                    "rr": float(PRESETS[preset].get("rr", 5.0)),
                    "grade": grade,
                    "setup": f"{market} {tf} {role}",
                    "priority": base_pri[tf] + (50 if "QUALITY" in preset or "st15" in preset else 0)
                               + int(PRESETS[preset].get("rr", 5)),
                })
    return modes


try:
    MODES = _build_modes()
except Exception as e:
    print(f"[APEX] mode build error: {e}", flush=True)
    MODES = []


def _digits(market: str) -> int:
    if market == "XAUUSD":
        return 2
    if "JPY" in market:
        return 3
    return 5


def run_watch(mode, ohlc):
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    times = ohlc.get("time")
    n = len(close)
    preset = mode["preset"]
    try:
        armed = detect_armed_with_preset(high, low, open_, close, times=times, preset=preset)
    except Exception as e:
        return None, f"detect_error({e})"
    if not armed:
        return None, "no_setup"
    # Prefer newest armed
    s = max(armed, key=lambda x: x.armed_bar)
    bars_ago = n - 1 - s.armed_bar
    if bars_ago > FRESH.get(mode["tf"], 2):
        return None, f"stale (bars_ago={bars_ago})"

    d = _digits(mode["market"])
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "rank": mode["rank"],
        "role": mode["role"],
        "grade": "S",
        "strategy": "S19",
        "market": mode["market"],
        "tf": mode["tf"],
        "preset": mode["preset"],
        "setup": mode["setup"],
        "status": "ARMED",
        "poi_type": s.poi_type,
        "poi_top": round(s.poi_top, d),
        "poi_bot": round(s.poi_bot, d),
        "entry_ref": round(s.entry, d),
        "sl": round(s.stop, d),
        "tp_ref": round(s.target, d),
        "rr": s.rr,
        "lq_price": round(s.lq_price, d),
        "bias": s.bias,
        "bars_until_expiry": s.bars_until_expiry,
        "bars_ago": bars_ago,
        "priority": mode["priority"],
        "bos_bar": s.bos_bar,
    }, "ok"


def check_modes(modes, get_ohlc_func):
    results = []
    stats = {}

    def bump(k):
        stats[k] = stats.get(k, 0) + 1

    for mode in modes:
        tag = f"#{mode['rank']:03d} S19 [S] {mode['market']} {mode['tf']}"
        print(f"  → {tag}  {mode['preset']}", flush=True)
        try:
            ohlc = get_ohlc_func(mode["market"], mode["tf"])
            if ohlc is None or len(ohlc["close"]) < 100:
                print("     ✗ [no_data]", flush=True)
                bump("no_data")
                continue
            if "open" not in ohlc:
                ohlc["open"] = ohlc["close"]
            sig, reason = run_watch(mode, ohlc)
            key = reason.split()[0] if reason else "other"
            bump(key)
            if sig is None:
                print(f"     ✗ [{reason}]", flush=True)
                continue
            print(
                f"     ★ ARMED {sig['direction']} {sig['market']} {sig['tf']} "
                f"POI {sig['poi_bot']}–{sig['poi_top']} "
                f"bias={sig['bias']} expiry={sig['bars_until_expiry']}b",
                flush=True,
            )
            results.append(sig)
        except Exception as e:
            bump("error")
            print(f"     ✗ [error] {e}", flush=True)

    print("  == " + " ".join(f"{k}={v}" for k, v in sorted(stats.items())), flush=True)
    return results


def select_highest_modes(signals):
    """One alert per market + direction — prefer higher TF / quality preset."""
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['market']}|{s['direction']}"
        if key not in groups or s["priority"] > groups[key]["priority"]:
            groups[key] = s
    selected = list(groups.values())
    if len(signals) != len(selected):
        print(f"  → Dedup {len(signals)} → {len(selected)}", flush=True)
    return selected
