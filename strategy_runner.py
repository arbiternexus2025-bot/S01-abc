"""
MARIO STRIKE — Single-TF Runner (ENTRY only)
============================================
Markets : majors + XAUUSD
TFs     : M30 · H1 · H4
"""
from __future__ import annotations
from data_feed import get_ohlc, clear_cache
from mario_engine import scan_single

MARKETS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "USDCAD", "AUDUSD", "NZDUSD",
    "XAUUSD",
]

TIMEFRAMES = ["M30", "H1", "H4"]


def check_all():
    results = []
    stats = {"ENTRY": 0, "no_data": 0, "no_setup": 0, "error": 0, "scanned": 0}
    total = len(MARKETS) * len(TIMEFRAMES)
    idx = 0

    clear_cache()

    for market in MARKETS:
        for tf in TIMEFRAMES:
            idx += 1
            stats["scanned"] += 1
            tag = f"[{idx:02d}/{total}] {market:7s} {tf:3s}"
            try:
                ohlc = get_ohlc(market, tf)
                if ohlc is None:
                    print(f"  {tag}  ·  NO DATA", flush=True)
                    stats["no_data"] += 1
                    continue

                sigs = scan_single(ohlc, market, tf)
                if not sigs:
                    print(
                        f"  {tag}  ·  NO ENTRY  ({len(ohlc['close'])} bars)",
                        flush=True,
                    )
                    stats["no_setup"] += 1
                    continue

                for s in sigs:
                    print(
                        f"  {tag}  🎯 ENTRY  {s['direction']:5s}  "
                        f"{s['entry']}  SL {s['stop']}  TP {s['target']}  "
                        f"RR={s['rr']}  bars_ago={s['bars_ago']}",
                        flush=True,
                    )
                    results.append(s)
                    stats["ENTRY"] += 1
            except Exception as e:
                print(f"  {tag}  ·  ERROR  {e}", flush=True)
                stats["error"] += 1

    print("-" * 64, flush=True)
    print(
        f"  SUMMARY  scanned={stats['scanned']}  ENTRY={stats['ENTRY']}  "
        f"no_setup={stats['no_setup']}  no_data={stats['no_data']}  error={stats['error']}",
        flush=True,
    )
    print("-" * 64, flush=True)
    return results


def select_best(signals):
    """One ENTRY per market + direction — higher TF wins."""
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['market']}|{s['direction']}"
        cur = groups.get(key)
        if cur is None:
            groups[key] = s
            continue
        if s["priority"] > cur["priority"]:
            groups[key] = s
        elif s["priority"] == cur["priority"] and s["bars_ago"] < cur["bars_ago"]:
            groups[key] = s
    out = list(groups.values())
    if len(signals) != len(out):
        print(f"  DEDUP  {len(signals)} → {len(out)} (1 per market+direction)", flush=True)
    return out
