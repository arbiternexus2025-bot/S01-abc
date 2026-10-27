
"""
APEX-19 Strategy Runner — Full Tier 1–5 Portfolio
================================================
Uses S19_pattern_detection portfolio presets (*_rr4/5/6/7/8).
Detailed reject logging. Tight freshness. Best-rank dedup.
"""
from __future__ import annotations
from data_feed import get_ohlc
from S19_pattern_detection import (
    detect_s19_signals,
    detect_with_preset,
    PRESETS,
    portfolio_routes,
)

# Build MODES from detector portfolio_routes (single source of truth)
def _build_modes():
    modes = []
    for i, r in enumerate(portfolio_routes(), start=1):
        preset = r.get("preset") or r["route"]
        m = r.get("metrics") or {}
        modes.append({
            "rank": i,
            "tier": r["tier"],
            "role": r["role"],
            "id": f"T{r['tier']}_{r['symbol']}_{preset}",
            "strategy": "S19",
            "market": r["symbol"],
            "tf": r["tf"],
            "preset": preset,
            "rr": float(r["rr"]),
            "grade": "S" if r["tier"] <= 2 else ("A+" if r["tier"] == 3 else ("A" if r["tier"] == 4 else "B+")),
            "expr": m.get("ExpR", 0),
            "wr": m.get("WR", 0),
            "n": int(m.get("N", 0)),
            "oos": m.get("OOS"),
            "maxdd": m.get("MaxDD"),
            "setup": f"{r['symbol']} {r['tf']} {preset}",
            "priority": 1000 - i - (r["tier"] * 10),
            "route": r["route"],
        })
    # Re-rank by tier then ExpR so Tier1 stays highest priority
    modes.sort(key=lambda x: (x["tier"], -(x["expr"] or 0)))
    for i, m in enumerate(modes, start=1):
        m["rank"] = i
        m["priority"] = 1000 - i
    return modes

try:
    MODES = _build_modes()
except Exception as e:
    print(f"[APEX] portfolio_routes load failed: {e} — using empty", flush=True)
    MODES = []

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
    rr = float(mode.get("rr", getattr(s, "rr", 2.5)))
    risk = abs(entry - float(s.stop))
    if risk < 1e-12:
        risk = abs(float(getattr(s, "risk", 0))) or 1e-9
    if s.direction == 1:
        sl, tp = float(s.stop), entry + rr * risk
    else:
        sl, tp = float(s.stop), entry - rr * risk
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
    # Preset already encodes RR; still force mode RR if different
    try:
        signals = detect_with_preset(high, low, open_, close, times=times, preset=preset)
    except TypeError:
        # older signature fallback
        params = dict(PRESETS[preset])
        params["rr"] = float(mode.get("rr", params.get("rr", 2.5)))
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

    print("  == " + " ".join(f"{k}={v}" for k, v in sorted(stats.items())), flush=True)
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
