"""
MARIO STRIKE — Strategy Runner
==============================
Markets : majors + minors + gold
TFs     : M30 · H1 · H2 · H4
Phases  : WATCH (zone armed) → ENTRY (rejection confirmed)
"""
from __future__ import annotations
from data_feed import get_ohlc
from mario_engine import scan

MARKETS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURAUD", "EURCHF", "GBPCHF",
    "CADJPY", "CHFJPY", "AUDCAD", "AUDNZD", "NZDJPY",
    "XAUUSD",
]

TIMEFRAMES = ["M30", "H1", "H2", "H4"]

# Freshness window (bars)
FRESH = {"M30": 2, "H1": 1, "H2": 1, "H4": 1}

# Priority for de-dupe: H4 > H1 > M30 ; ENTRY > WATCH
TF_PRI = {"H4": 400, "H2": 300, "H1": 200, "M30": 100}


def _digits(market: str) -> int:
    if market == "XAUUSD":
        return 2
    if "JPY" in market:
        return 3
    return 5


def _pack(ev) -> dict:
    d = _digits(ev.market)
    return {
        "phase": ev.phase,
        "market": ev.market,
        "tf": ev.timeframe,
        "direction": ev.direction,
        "poi_type": ev.poi_type,
        "poi_top": round(ev.poi_top, d),
        "poi_bot": round(ev.poi_bot, d),
        "entry": round(ev.entry, d),
        "stop": round(ev.stop, d),
        "target": round(ev.target, d),
        "risk": round(ev.risk, d + 1),
        "rr": float(ev.rr),
        "sweep_level": round(ev.sweep_level, d),
        "bars_ago": ev.bars_ago,
        "bars_left": ev.bars_left,
        "priority": TF_PRI.get(ev.timeframe, 0) + (50 if ev.phase == "ENTRY" else 0),
        "key": ev.key(),
    }


def check_all(get_ohlc_func=get_ohlc):
    results = []
    stats = {"ok": 0, "no_data": 0, "no_setup": 0, "stale": 0, "error": 0}

    for market in MARKETS:
        for tf in TIMEFRAMES:
            tag = f"{market} {tf}"
            print(f"  → {tag}", flush=True)
            try:
                ohlc = get_ohlc_func(market, tf)
                if ohlc is None:
                    print("     ✗ no_data", flush=True)
                    stats["no_data"] += 1
                    continue
                events = scan(ohlc, market, tf)
                if not events:
                    print("     · quiet", flush=True)
                    stats["no_setup"] += 1
                    continue
                max_age = FRESH.get(tf, 2)
                for ev in events:
                    if ev.bars_ago > max_age:
                        print(f"     ✗ stale {ev.phase} bars_ago={ev.bars_ago}", flush=True)
                        stats["stale"] += 1
                        continue
                    packed = _pack(ev)
                    print(
                        f"     ★ {ev.phase} {ev.direction} "
                        f"zone {packed['poi_bot']}–{packed['poi_top']} "
                        f"RR={ev.rr}",
                        flush=True,
                    )
                    results.append(packed)
                    stats["ok"] += 1
            except Exception as e:
                print(f"     ✗ error {e}", flush=True)
                stats["error"] += 1

    print("  == " + " ".join(f"{k}={v}" for k, v in stats.items()), flush=True)
    return results


def select_best(signals):
    """One alert per market+direction — prefer ENTRY and higher TF."""
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['market']}|{s['direction']}"
        if key not in groups or s["priority"] > groups[key]["priority"]:
            groups[key] = s
    out = list(groups.values())
    if len(signals) != len(out):
        print(f"  → Dedup {len(signals)} → {len(out)}", flush=True)
    return out
