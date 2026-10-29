"""
APEX-19 Strategy Runner — S19 + S29 + S35 Hybrid Fib Deep
========================================================
S19: portfolio_routes Tier 1–5
S29: Fib Major Zone rejection (H1/H4/M30)
S35: USDJPY M1 Deep 0.618–0.886 Rank1 RR3.0 + Rank2 RR2.5 (NY/Overlap)
"""
from __future__ import annotations
from data_feed import get_ohlc
from S19_pattern_detection import (
    detect_with_preset as s19_detect_with_preset,
    PRESETS as S19_PRESETS,
    portfolio_routes,
)
from S29_pattern_detection import (
    detect_with_preset as s29_detect_with_preset,
    PRESETS as S29_PRESETS,
)
from S35_Hybrid_Fib_Deep_detection import (
    detect_rank1,
    detect_rank2,
    RANK_META,
)

# ─────────────────────────────────────────────────────────────
# S29 curated book
# ─────────────────────────────────────────────────────────────
S29_BOOK = [
    {"market": "XAUUSD", "tf": "H1",  "preset": "XAU_H1_highWR_combo",   "variant": "highWR_combo",   "expr": 2.789, "wr": 60.3, "n": 411, "pf": 8.03, "dd": 10.0},
    {"market": "USDJPY", "tf": "H4",  "preset": "JPY_H4_highWR_combo",   "variant": "highWR_combo",   "expr": 2.765, "wr": 56.9, "n": 109, "pf": 7.41, "dd": 6.0},
    {"market": "XAUUSD", "tf": "H1",  "preset": "XAU_H1_wick45_confirm", "variant": "wick45_confirm", "expr": 2.677, "wr": 66.0, "n": 477, "pf": 8.88, "dd": 7.0},
    {"market": "USDJPY", "tf": "H4",  "preset": "JPY_H4_wick45_confirm", "variant": "wick45_confirm", "expr": 2.643, "wr": 61.9, "n": 134, "pf": 7.94, "dd": 8.0},
    {"market": "XAUUSD", "tf": "H4",  "preset": "XAU_H4_highWR_combo",   "variant": "highWR_combo",   "expr": 2.640, "wr": 55.3, "n": 94,  "pf": 6.91, "dd": 8.0},
    {"market": "XAUUSD", "tf": "H1",  "preset": "XAU_H1_wick40_confirm", "variant": "wick40_confirm", "expr": 2.621, "wr": 65.2, "n": 563, "pf": 8.53, "dd": 6.0},
    {"market": "USDJPY", "tf": "H4",  "preset": "JPY_H4_wick40_confirm", "variant": "wick40_confirm", "expr": 2.567, "wr": 61.1, "n": 149, "pf": 7.59, "dd": 5.0},
    {"market": "XAUUSD", "tf": "M30", "preset": "XAU_M30_highWR_combo",  "variant": "highWR_combo",   "expr": 2.449, "wr": 58.1, "n": 454, "pf": 6.85, "dd": 7.0},
    {"market": "GBPUSD", "tf": "H4",  "preset": "GBP_H4_wick45_confirm", "variant": "wick45_confirm", "expr": 2.392, "wr": 58.0, "n": 150, "pf": 6.69, "dd": 7.0},
    {"market": "XAUUSD", "tf": "M30", "preset": "XAU_M30_wick40_confirm","variant": "wick40_confirm", "expr": 2.321, "wr": 62.3, "n": 608, "pf": 7.16, "dd": 8.0},
    {"market": "XAUUSD", "tf": "M30", "preset": "XAU_M30_wick45_confirm","variant": "wick45_confirm", "expr": 2.282, "wr": 61.9, "n": 509, "pf": 6.99, "dd": 7.0},
    {"market": "EURUSD", "tf": "H1",  "preset": "EUR_H1_wick40_confirm", "variant": "wick40_confirm", "expr": 2.192, "wr": 61.8, "n": 524, "pf": 6.74, "dd": 8.0},
    {"market": "USDJPY", "tf": "H1",  "preset": "JPY_H1_wick45_confirm", "variant": "wick45_confirm", "expr": 2.120, "wr": 60.8, "n": 388, "pf": 6.41, "dd": 7.0},
    {"market": "EURUSD", "tf": "H1",  "preset": "EUR_H1_wick45_confirm", "variant": "wick45_confirm", "expr": 2.108, "wr": 60.6, "n": 442, "pf": 6.36, "dd": 7.0},
    {"market": "USDJPY", "tf": "H1",  "preset": "JPY_H1_wick40_confirm", "variant": "wick40_confirm", "expr": 2.112, "wr": 60.5, "n": 468, "pf": 6.34, "dd": 7.0},
]

# ─────────────────────────────────────────────────────────────
# S35 Rank-1 / Rank-2 (USDJPY M1 Deep Fib)
# ─────────────────────────────────────────────────────────────
S35_BOOK = [
    {
        "rank_key": "RANK1",
        "market": "USDJPY",
        "tf": "M1",
        "mode": "RANK1",
        "rr": 3.0,
        "expr": 0.541,
        "wr": 49.5,
        "n": 944,
        "pf": 2.03,
        "dd": 9.0,
        "oos": 0.596,
        "cost2x": 0.421,
        "tpd": 13.9,
        "grade": "A/A+",
        "role": "Deep 0.618–0.886 RR3.0 NY",
        "setup": "USDJPY M1 Deep Fib RR3.0 NY+Overlap",
    },
    {
        "rank_key": "RANK2",
        "market": "USDJPY",
        "tf": "M1",
        "mode": "RANK2",
        "rr": 2.5,
        "expr": 0.497,
        "wr": 51.7,
        "n": 944,
        "pf": 1.99,
        "dd": 10.0,
        "oos": 0.538,
        "cost2x": 0.377,
        "tpd": 13.9,
        "grade": "A",
        "role": "Deep 0.618–0.886 RR2.5 NY",
        "setup": "USDJPY M1 Deep Fib RR2.5 NY+Overlap",
    },
]


def _build_s19_modes():
    modes = []
    try:
        routes = portfolio_routes()
    except Exception as e:
        print(f"[APEX] S19 portfolio_routes failed: {e}", flush=True)
        return []
    for i, r in enumerate(routes, start=1):
        preset = r.get("preset") or r["route"]
        m = r.get("metrics") or {}
        modes.append({
            "rank": i,
            "tier": r["tier"],
            "role": r["role"],
            "id": f"S19_T{r['tier']}_{r['symbol']}_{preset}",
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
            "priority": 2000 - i,
            "route": r.get("route", preset),
        })
    modes.sort(key=lambda x: (x["tier"], -(x["expr"] or 0)))
    for i, m in enumerate(modes, start=1):
        m["rank"] = i
        m["priority"] = 2000 - i
    return modes


def _build_s29_modes():
    modes = []
    for i, b in enumerate(S29_BOOK, start=1):
        modes.append({
            "rank": 100 + i,
            "tier": 6,
            "role": f"S29 {b['variant']}",
            "id": f"S29_{b['market']}_{b['tf']}_{b['variant']}",
            "strategy": "S29",
            "market": b["market"],
            "tf": b["tf"],
            "preset": b["preset"],
            "rr": None,
            "grade": "S" if b["expr"] >= 2.5 else "A+",
            "expr": b["expr"],
            "wr": b["wr"],
            "n": b["n"],
            "oos": None,
            "maxdd": b["dd"],
            "pf": b["pf"],
            "setup": f"{b['market']} {b['tf']} {b['variant']}",
            "priority": 1500 - i,
            "variant": b["variant"],
        })
    return modes


def _build_s35_modes():
    modes = []
    for i, b in enumerate(S35_BOOK, start=1):
        modes.append({
            "rank": 50 + i,  # after S19 tier1-ish priority band
            "tier": 0,       # flagship scalp tier
            "role": b["role"],
            "id": f"S35_USDJPY_M1_{b['rank_key']}",
            "strategy": "S35",
            "market": b["market"],
            "tf": b["tf"],
            "preset": b["rank_key"],
            "mode": b["mode"],
            "rr": b["rr"],
            "grade": b["grade"],
            "expr": b["expr"],
            "wr": b["wr"],
            "n": b["n"],
            "oos": b["oos"],
            "maxdd": b["dd"],
            "pf": b["pf"],
            "cost2x": b["cost2x"],
            "tpd": b["tpd"],
            "setup": b["setup"],
            "priority": 2100 - i,  # Rank1 highest among scalps
        })
    return modes


try:
    MODES = _build_s19_modes() + _build_s35_modes() + _build_s29_modes()
except Exception as e:
    print(f"[APEX] mode build error: {e}", flush=True)
    MODES = []

# M1 needs tighter freshness (1–2 bars = 1–2 minutes)
FRESH = {"M1": 2, "M5": 2, "M15": 2, "M30": 2, "H1": 1, "H4": 1}


def _stop_still_valid(s, high, low, close) -> bool:
    n = len(close)
    start = getattr(s, "entry_bar", 0) + 1
    stop = float(s.stop)
    direction = int(s.direction)
    if direction == 1:
        for i in range(start, n):
            if low[i] <= stop:
                return False
        return float(close[-1]) > stop
    for i in range(start, n):
        if high[i] >= stop:
            return False
    return float(close[-1]) < stop


def _digits(market: str) -> int:
    if market == "XAUUSD":
        return 2
    if market == "USDJPY":
        return 3
    return 5


def _pack_s19(mode, s, bars_ago):
    d = _digits(mode["market"])
    entry = float(s.entry_price)
    rr = float(mode.get("rr") or getattr(s, "rr", 2.5))
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
        "tp2": None,
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


def _pack_s29(mode, s, bars_ago):
    d = _digits(mode["market"])
    entry = float(s.entry_price)
    sl = float(s.stop)
    tp = float(s.target)
    tp2 = float(s.target2)
    risk = abs(entry - sl) or 1e-9
    rr = float(getattr(s, "rr_to_mid", abs(tp - entry) / risk))
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "rank": mode["rank"],
        "tier": mode["tier"],
        "role": mode["role"],
        "grade": mode["grade"],
        "strategy": "S29",
        "market": mode["market"],
        "tf": mode["tf"],
        "preset": mode["preset"],
        "setup": mode["setup"],
        "entry": round(entry, d),
        "sl": round(sl, d),
        "tp": round(tp, d),
        "tp2": round(tp2, d),
        "risk": risk,
        "rr": round(rr, 2),
        "bars_ago": bars_ago,
        "priority": mode["priority"],
        "expr": mode["expr"],
        "wr": mode["wr"],
        "n_research": mode["n"],
        "oos": None,
        "maxdd": mode.get("maxdd"),
        "pf": mode.get("pf"),
        "poi_type": getattr(s, "zone_type", "maj"),
        "bias": "",
        "variant": mode.get("variant", ""),
    }


def _pack_s35(mode, s, bars_ago):
    d = _digits(mode["market"])
    entry = float(s.entry_price)
    sl = float(s.stop)
    risk = abs(entry - sl) or float(s.risk) or 1e-9
    # Prefer rank-specific target
    if mode["mode"] == "RANK1":
        tp = float(s.target_r30) if s.target_r30 is not None else entry + (1 if s.direction == 1 else -1) * 3.0 * risk
        rr = 3.0
    else:
        tp = float(s.target_r25) if s.target_r25 is not None else entry + (1 if s.direction == 1 else -1) * 2.5 * risk
        rr = 2.5
    # secondary target for BOTH-style display
    tp2 = None
    if s.target_r30 is not None and s.target_r25 is not None and mode["mode"] == "RANK1":
        tp2 = float(s.target_r25)  # optional secondary
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"],
        "rank": mode["rank"],
        "tier": mode["tier"],
        "role": mode["role"],
        "grade": mode["grade"],
        "strategy": "S35",
        "market": mode["market"],
        "tf": mode["tf"],
        "preset": mode["preset"],
        "setup": mode["setup"],
        "entry": round(entry, d),
        "sl": round(sl, d),
        "tp": round(tp, d),
        "tp2": round(tp2, d) if tp2 is not None else None,
        "risk": risk,
        "rr": rr,
        "bars_ago": bars_ago,
        "priority": mode["priority"],
        "expr": mode["expr"],
        "wr": mode["wr"],
        "n_research": mode["n"],
        "oos": mode.get("oos"),
        "maxdd": mode.get("maxdd"),
        "pf": mode.get("pf"),
        "cost2x": mode.get("cost2x"),
        "tpd": mode.get("tpd"),
        "session": getattr(s, "session", ""),
        "retrace": round(float(getattr(s, "retrace", 0)), 3),
        "poi_type": "DeepFib",
        "bias": "",
    }


def run_s19(mode, ohlc):
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    times = ohlc.get("time")
    n = len(close)
    preset = mode["preset"]
    if preset not in S19_PRESETS:
        return None, f"bad_preset({preset})"
    try:
        signals = s19_detect_with_preset(high, low, open_, close, times=times, preset=preset)
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
    return _pack_s19(mode, s, bars_ago), "ok"


def run_s29(mode, ohlc):
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    times = ohlc.get("time")
    n = len(close)
    preset = mode["preset"]
    if preset not in S29_PRESETS:
        return None, f"bad_preset({preset})"
    try:
        signals = s29_detect_with_preset(high, low, open_, close, times=times, preset=preset)
    except Exception as e:
        return None, f"detect_error({e})"
    if not signals:
        return None, "no_signal"
    s = max(signals, key=lambda x: x.entry_bar)
    bars_ago = n - 1 - s.entry_bar
    max_age = FRESH.get(mode["tf"], 2)
    if bars_ago > max_age:
        return None, f"expired_or_old (bars_ago={bars_ago} max={max_age})"
    if not _stop_still_valid(s, high, low, close):
        return None, "stop_already_hit"
    return _pack_s29(mode, s, bars_ago), "ok"


def run_s35(mode, ohlc):
    high, low, open_, close = ohlc["high"], ohlc["low"], ohlc["open"], ohlc["close"]
    times = ohlc.get("time")
    n = len(close)
    if n < 120:
        return None, "no_data"
    try:
        if mode["mode"] == "RANK1":
            signals = detect_rank1(high, low, close, open_, times)
        else:
            signals = detect_rank2(high, low, close, open_, times)
    except Exception as e:
        return None, f"detect_error({e})"
    if not signals:
        return None, "no_signal"
    s = max(signals, key=lambda x: x.entry_bar)
    bars_ago = n - 1 - s.entry_bar
    max_age = FRESH.get("M1", 2)
    if bars_ago > max_age:
        return None, f"expired_or_old (bars_ago={bars_ago} max={max_age})"
    if not _stop_still_valid(s, high, low, close):
        return None, "stop_already_hit"
    return _pack_s35(mode, s, bars_ago), "ok"


def check_modes(modes, get_ohlc_func):
    results = []
    stats = {}

    def bump(k):
        stats[k] = stats.get(k, 0) + 1

    for mode in modes:
        tag = (
            f"#{mode['rank']:03d} {mode['strategy']} T{mode['tier']} [{mode['grade']}] "
            f"{mode['market']} {mode['tf']}"
        )
        print(f"  → {tag}  {mode.get('preset', mode.get('mode', ''))}", flush=True)
        try:
            # M1 needs deeper history for pivots
            limit = 800 if mode["tf"] == "M1" else 300
            ohlc = get_ohlc_func(mode["market"], mode["tf"]) if mode["tf"] != "M1" else get_ohlc(mode["market"], "M1", limit=limit)
            # allow override when get_ohlc_func is bound without limit
            if mode["tf"] == "M1" and (ohlc is None or len(ohlc.get("close", [])) < 120):
                ohlc = get_ohlc(mode["market"], "M1", limit=800)
            if ohlc is None or len(ohlc["close"]) < 80:
                print("     ✗ [no_data]", flush=True)
                bump("no_data")
                continue
            if "open" not in ohlc:
                ohlc["open"] = ohlc["close"]
            if mode["strategy"] == "S35":
                sig, reason = run_s35(mode, ohlc)
            elif mode["strategy"] == "S29":
                sig, reason = run_s29(mode, ohlc)
            else:
                sig, reason = run_s19(mode, ohlc)
            key = reason.split()[0] if reason else "other"
            bump(key)
            if sig is None:
                print(f"     ✗ [{reason}]", flush=True)
                continue
            extra = f" TP2={sig['tp2']}" if sig.get("tp2") else ""
            print(
                f"     ★ {sig['strategy']} {sig['direction']} @ {sig['entry']}  "
                f"SL={sig['sl']} TP={sig['tp']}{extra}  RR={sig.get('rr')}  "
                f"bars_ago={sig['bars_ago']}  grade={sig['grade']}",
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
        key = f"{s['strategy']}|{s['market']}|{s['direction']}|{s['entry']}"
        if key not in groups or s["priority"] > groups[key]["priority"]:
            groups[key] = s
    selected = list(groups.values())
    if len(signals) != len(selected):
        print(f"  → Dedup {len(signals)} → {len(selected)}", flush=True)
    return selected
