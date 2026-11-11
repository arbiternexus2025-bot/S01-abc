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

FRESH = {"M30": 2, "H1": 1, "H2": 1, "H4": 1}
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
    stats = {
        "ENTRY": 0,
        "WATCH": 0,
        "no_data": 0,
        "no_setup": 0,
        "stale": 0,
        "error": 0,
        "scanned": 0,
    }

    total = len(MARKETS) * len(TIMEFRAMES)
    idx = 0

    for market in MARKETS:
        for tf in TIMEFRAMES:
            idx += 1
            stats["scanned"] += 1
            tag = f"[{idx:02d}/{total}] {market:7s} {tf:3s}"
            try:
                ohlc = get_ohlc_func(market, tf)
                if ohlc is None:
                    print(f"  {tag}  ·  NO DATA  (feed empty or pair not listed)", flush=True)
                    stats["no_data"] += 1
                    continue

                n_bars = len(ohlc["close"])
                events = scan(ohlc, market, tf)
                if not events:
                    print(
                        f"  {tag}  ·  NO SETUP  "
                        f"({n_bars} bars — no live Sweep→BOS→POI sequence)",
                        flush=True,
                    )
                    stats["no_setup"] += 1
                    continue

                max_age = FRESH.get(tf, 2)
                kept = 0
                for ev in events:
                    if ev.bars_ago > max_age:
                        print(
                            f"  {tag}  ·  STALE {ev.phase}  "
                            f"(bars_ago={ev.bars_ago} > max {max_age})",
                            flush=True,
                        )
                        stats["stale"] += 1
                        continue
                    packed = _pack(ev)
                    icon = "🎯" if ev.phase == "ENTRY" else "⚡️"
                    print(
                        f"  {tag}  {icon} {ev.phase:5s}  {ev.direction:5s}  "
                        f"zone {packed['poi_bot']}→{packed['poi_top']}  "
                        f"RR={ev.rr}  bars_ago={ev.bars_ago}",
                        flush=True,
                    )
                    results.append(packed)
                    stats[ev.phase] = stats.get(ev.phase, 0) + 1
                    kept += 1
                if kept == 0 and events:
                    pass  # already logged stale
            except Exception as e:
                print(f"  {tag}  ·  ERROR  {e}", flush=True)
                stats["error"] += 1

    print("-" * 64, flush=True)
    print(
        f"  SCAN SUMMARY  |  scanned={stats['scanned']}  "
        f"ENTRY={stats['ENTRY']}  WATCH={stats['WATCH']}  "
        f"no_setup={stats['no_setup']}  no_data={stats['no_data']}  "
        f"stale={stats['stale']}  error={stats['error']}",
        flush=True,
    )
    print("-" * 64, flush=True)
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
        print(f"  DEDUP  {len(signals)} signals → {len(out)} (best TF / phase kept)", flush=True)
    return out
