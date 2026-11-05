"""
APEX-19 Strategy Runner — S-tier only (S19 + S29) + S40 MSS v4
==============================================================
S19 / S29: grade S only
S40: HTF key level → Sweep → MSS (v4 refined, strong only)
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
from S40_MSS_detection_v4_refined import detect_live, HTF_MAP, PARAMS

# ─────────────────────────────────────────────────────────────
# S29 — S-tier only (ExpR ≥ 2.5)
# ─────────────────────────────────────────────────────────────
S29_BOOK = [
    {"market": "XAUUSD", "tf": "H1",  "preset": "XAU_H1_highWR_combo",   "variant": "highWR_combo",   "expr": 2.789, "wr": 60.3, "n": 411, "pf": 8.03, "dd": 10.0},
    {"market": "USDJPY", "tf": "H4",  "preset": "JPY_H4_highWR_combo",   "variant": "highWR_combo",   "expr": 2.765, "wr": 56.9, "n": 109, "pf": 7.41, "dd": 6.0},
    {"market": "XAUUSD", "tf": "H1",  "preset": "XAU_H1_wick45_confirm", "variant": "wick45_confirm", "expr": 2.677, "wr": 66.0, "n": 477, "pf": 8.88, "dd": 7.0},
    {"market": "USDJPY", "tf": "H4",  "preset": "JPY_H4_wick45_confirm", "variant": "wick45_confirm", "expr": 2.643, "wr": 61.9, "n": 134, "pf": 7.94, "dd": 8.0},
    {"market": "XAUUSD", "tf": "H4",  "preset": "XAU_H4_highWR_combo",   "variant": "highWR_combo",   "expr": 2.640, "wr": 55.3, "n": 94,  "pf": 6.91, "dd": 8.0},
    {"market": "XAUUSD", "tf": "H1",  "preset": "XAU_H1_wick40_confirm", "variant": "wick40_confirm", "expr": 2.621, "wr": 65.2, "n": 563, "pf": 8.53, "dd": 6.0},
    {"market": "USDJPY", "tf": "H4",  "preset": "JPY_H4_wick40_confirm", "variant": "wick40_confirm", "expr": 2.567, "wr": 61.1, "n": 149, "pf": 7.59, "dd": 5.0},
]

# S40 markets (research core)
S40_MARKETS = [
    # Majors
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    # Minors / crosses
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURAUD", "EURCHF", "GBPCHF",
    "CADJPY", "CHFJPY", "AUDCAD", "AUDNZD", "NZDJPY",
    # Gold
    "XAUUSD",
]
# LTF charts we watch (HTF is mapped inside detector)
S40_LTFS = ["H4", "H1", "M30", "M15", "M5"]  # full v4 stack

FRESH = {"M5": 2, "M15": 2, "M30": 2, "H1": 1, "H4": 1}


def _build_s19_modes():
    """S-tier only = research Tier 1 and Tier 2."""
    modes = []
    try:
        routes = portfolio_routes()
    except Exception as e:
        print(f"[APEX] S19 portfolio_routes failed: {e}", flush=True)
        return []
    s_routes = [r for r in routes if int(r.get("tier", 99)) <= 2]
    for i, r in enumerate(s_routes, start=1):
        preset = r.get("preset") or r["route"]
        m = r.get("metrics") or {}
        modes.append({
            "rank": i, "tier": r["tier"], "role": r["role"],
            "id": f"S19_T{r['tier']}_{r['symbol']}_{preset}",
            "strategy": "S19", "market": r["symbol"], "tf": r["tf"],
            "preset": preset, "rr": float(r["rr"]),
            "grade": "S",
            "expr": m.get("ExpR", 0), "wr": m.get("WR", 0), "n": int(m.get("N", 0)),
            "oos": m.get("OOS"), "maxdd": m.get("MaxDD"),
            "setup": f"{r['symbol']} {r['tf']} {preset}",
            "priority": 2000 - i,
        })
    return modes


def _build_s29_modes():
    modes = []
    for i, b in enumerate(S29_BOOK, start=1):
        modes.append({
            "rank": 50 + i, "tier": 1, "role": f"S29 {b['variant']}",
            "id": f"S29_{b['market']}_{b['tf']}_{b['variant']}",
            "strategy": "S29", "market": b["market"], "tf": b["tf"],
            "preset": b["preset"], "rr": None,
            "grade": "S",
            "expr": b["expr"], "wr": b["wr"], "n": b["n"],
            "oos": None, "maxdd": b["dd"], "pf": b["pf"],
            "setup": f"{b['market']} {b['tf']} {b['variant']}",
            "priority": 1800 - i, "variant": b["variant"],
        })
    return modes


def _build_s40_modes():
    modes = []
    rank = 100
    # Priority: H4 > H1 > M30
    pri = {"H4": 1900, "H1": 1750, "M30": 1600, "M15": 1500, "M5": 1400}
    for market in S40_MARKETS:
        for tf in S40_LTFS:
            rank += 1
            htf = HTF_MAP.get(tf, "H4")
            modes.append({
                "rank": rank, "tier": 1, "role": f"Sweep→MSS ({htf}→{tf})",
                "id": f"S40_{market}_{tf}_MSS_v4",
                "strategy": "S40", "market": market, "tf": tf, "htf": htf,
                "preset": "MSS_v4_STRONG", "rr": None, "grade": "S",
                "expr": 0.0, "wr": 0.0, "n": 0,
                "oos": None, "maxdd": None,
                "setup": f"{market} {tf} HTF-Sweep + MSS [v4]",
                "priority": pri.get(tf, 1500),
            })
    return modes


try:
    MODES = _build_s19_modes() + _build_s29_modes() + _build_s40_modes()
except Exception as e:
    print(f"[APEX] mode build error: {e}", flush=True)
    MODES = []


def _digits(market: str) -> int:
    if market == "XAUUSD":
        return 2
    if "JPY" in market:
        return 3
    return 5


def _stop_still_valid(entry_bar, stop, direction, high, low, close) -> bool:
    stop = float(stop)
    if direction == 1:
        for i in range(entry_bar + 1, len(close)):
            if low[i] <= stop:
                return False
        return float(close[-1]) > stop
    for i in range(entry_bar + 1, len(close)):
        if high[i] >= stop:
            return False
    return float(close[-1]) < stop


def _pack_s19(mode, s, bars_ago):
    d = _digits(mode["market"])
    entry = float(s.entry_price)
    rr = float(mode.get("rr") or 2.5)
    risk = abs(entry - float(s.stop)) or 1e-9
    if s.direction == 1:
        sl, tp = float(s.stop), entry + rr * risk
    else:
        sl, tp = float(s.stop), entry - rr * risk
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"], "rank": mode["rank"], "tier": mode["tier"],
        "role": mode["role"], "grade": "S", "strategy": "S19",
        "market": mode["market"], "tf": mode["tf"], "preset": mode["preset"],
        "setup": mode["setup"],
        "entry": round(entry, d), "sl": round(sl, d), "tp": round(tp, d),
        "tp2": None, "risk": risk, "rr": rr, "bars_ago": bars_ago,
        "priority": mode["priority"], "expr": mode["expr"], "wr": mode["wr"],
        "n_research": mode["n"], "oos": mode.get("oos"), "maxdd": mode.get("maxdd"),
        "poi_type": "OB", "bias": "",
    }


def _pack_s29(mode, s, bars_ago):
    d = _digits(mode["market"])
    entry = float(s.entry_price)
    sl, tp, tp2 = float(s.stop), float(s.target), float(s.target2)
    risk = abs(entry - sl) or 1e-9
    rr = float(getattr(s, "rr_to_mid", abs(tp - entry) / risk))
    return {
        "direction": "LONG" if s.direction == 1 else "SHORT",
        "mode": mode["id"], "rank": mode["rank"], "tier": mode["tier"],
        "role": mode["role"], "grade": "S", "strategy": "S29",
        "market": mode["market"], "tf": mode["tf"], "preset": mode["preset"],
        "setup": mode["setup"],
        "entry": round(entry, d), "sl": round(sl, d), "tp": round(tp, d),
        "tp2": round(tp2, d), "risk": risk, "rr": round(rr, 2),
        "bars_ago": bars_ago, "priority": mode["priority"],
        "expr": mode["expr"], "wr": mode["wr"], "n_research": mode["n"],
        "oos": None, "maxdd": mode.get("maxdd"), "pf": mode.get("pf"),
        "poi_type": "maj", "bias": "", "variant": mode.get("variant", ""),
    }


def _pack_s40(mode, e, bars_ago):
    d = _digits(mode["market"])
    return {
        "direction": "LONG" if e.direction == 1 else "SHORT",
        "mode": mode["id"], "rank": mode["rank"], "tier": mode["tier"],
        "role": mode["role"], "grade": "S", "strategy": "S40",
        "market": mode["market"], "tf": mode["tf"], "htf": mode.get("htf", e.htf),
        "preset": mode["preset"], "setup": mode["setup"],
        "entry": round(float(e.entry), d),
        "sl": round(float(e.stop), d),
        "tp": None, "tp2": None,
        "htf_level": round(float(e.htf_level), d),
        "zone_low": round(float(e.htf_zone_low), d),
        "zone_high": round(float(e.htf_zone_high), d),
        "extreme": round(float(e.sweep_extreme), d),
        "mss_level": round(float(e.mss_level), d),
        "risk": abs(float(e.entry) - float(e.stop)),
        "rr": None,
        "bars_ago": bars_ago,
        "priority": mode["priority"] + int(20 * float(e.quality)),
        "expr": 0.0, "wr": 0.0, "n_research": 0,
        "wick_atr": round(float(e.wick_atr), 2),
        "range_atr": round(float(e.range_atr), 2),
        "structure_atr": round(float(e.structure_atr), 2),
        "bars_sweep_to_mss": int(e.bars_sweep_to_mss),
        "quality": round(float(e.quality), 2),
        "strong": bool(e.strong),
        "poi_type": "SWEEP_MSS",
        "bias": "bullish" if e.direction == 1 else "bearish",
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
    if bars_ago > FRESH.get(mode["tf"], 2):
        return None, f"stale (bars_ago={bars_ago})"
    if not _stop_still_valid(s.entry_bar, s.stop, s.direction, high, low, close):
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
    if bars_ago > FRESH.get(mode["tf"], 2):
        return None, f"stale (bars_ago={bars_ago})"
    if not _stop_still_valid(s.entry_bar, s.stop, s.direction, high, low, close):
        return None, "stop_already_hit"
    return _pack_s29(mode, s, bars_ago), "ok"


def run_s40(mode, get_ohlc_func):
    market, tf = mode["market"], mode["tf"]
    htf = mode.get("htf") or HTF_MAP.get(tf, "H4")
    ltf = get_ohlc_func(market, tf)
    htf_ohlc = get_ohlc_func(market, htf)
    if ltf is None or htf_ohlc is None:
        return None, "no_data"
    if "open" not in ltf:
        ltf["open"] = ltf["close"]
    if "open" not in htf_ohlc:
        htf_ohlc["open"] = htf_ohlc["close"]
    if len(ltf["close"]) < 120 or len(htf_ohlc["close"]) < 80:
        return None, "no_data"
    try:
        events = detect_live(ltf, htf_ohlc, symbol=market, tf=tf, strong_only=True)
    except Exception as e:
        return None, f"detect_error({e})"
    if not events:
        return None, "no_signal"
    n = len(ltf["close"])
    max_age = FRESH.get(tf, 1)
    fresh = [e for e in events if (n - 1 - e.bar) <= max_age]
    if not fresh:
        newest = max(events, key=lambda x: x.bar)
        return None, f"stale (bars_ago={n - 1 - newest.bar})"
    e = max(fresh, key=lambda x: (x.bar, x.quality))
    bars_ago = n - 1 - e.bar
    return _pack_s40(mode, e, bars_ago), "ok"


def check_modes(modes, get_ohlc_func):
    results = []
    stats = {}

    def bump(k):
        stats[k] = stats.get(k, 0) + 1

    for mode in modes:
        tag = f"#{mode['rank']:03d} {mode['strategy']} [S] {mode['market']} {mode['tf']}"
        print(f"  → {tag}  {mode.get('preset', '')}", flush=True)
        try:
            if mode["strategy"] == "S40":
                sig, reason = run_s40(mode, get_ohlc_func)
            else:
                ohlc = get_ohlc_func(mode["market"], mode["tf"])
                if ohlc is None or len(ohlc["close"]) < 80:
                    print("     ✗ [no_data]", flush=True)
                    bump("no_data")
                    continue
                if "open" not in ohlc:
                    ohlc["open"] = ohlc["close"]
                if mode["strategy"] == "S29":
                    sig, reason = run_s29(mode, ohlc)
                else:
                    sig, reason = run_s19(mode, ohlc)

            key = reason.split()[0] if reason else "other"
            bump(key)
            if sig is None:
                print(f"     ✗ [{reason}]", flush=True)
                continue

            if sig["strategy"] == "S40":
                print(
                    f"     ★ S40 MSS {sig['direction']} {sig['market']} {sig['tf']} "
                    f"HTF={sig.get('htf_level')} MSS={sig.get('mss_level')} "
                    f"q={sig.get('quality')} bars_ago={sig['bars_ago']}",
                    flush=True,
                )
            else:
                print(
                    f"     ★ {sig['strategy']} {sig['direction']} @ {sig['entry']} "
                    f"SL={sig['sl']} TP={sig.get('tp')} bars_ago={sig['bars_ago']}",
                    flush=True,
                )
            results.append(sig)
        except Exception as e:
            bump("error")
            print(f"     ✗ [error] {e}", flush=True)

    print("  == " + " ".join(f"{k}={v}" for k, v in sorted(stats.items())), flush=True)
    return results


def select_highest_modes(signals):
    """
    S40: one alert per market + direction (prefer higher TF / quality).
    Others: strategy + market + direction + entry.
    """
    if not signals:
        return []
    groups = {}
    for s in signals:
        if s["strategy"] == "S40":
            key = f"S40|{s['market']}|{s['direction']}"
        else:
            key = f"{s['strategy']}|{s['market']}|{s['direction']}|{s['entry']}"
        if key not in groups or s["priority"] > groups[key]["priority"]:
            groups[key] = s
    selected = list(groups.values())
    if len(signals) != len(selected):
        print(f"  → Dedup {len(signals)} → {len(selected)}", flush=True)
    return selected
