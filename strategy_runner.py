"""
MARIO STRIKE — Dual-TF Runner (ENTRY only)
==========================================
Routes (research preferred):
  H1  → M30   RR 3.5   primary (lowest latency)
  H4  → M30   RR 4.5
  H4  → H1    RR 4.5
"""
from __future__ import annotations
from data_feed import get_ohlc, clear_cache
from mario_engine import scan_dual

MARKETS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "EURAUD", "EURCHF", "GBPCHF",
    "CADJPY", "CHFJPY", "AUDCAD", "AUDNZD", "NZDJPY",
    "XAUUSD",
]

# (htf, ltf, lookback_ltf_bars)
DUAL_ROUTES = [
    ("H1", "M30", 3),   # primary — M30 rejection on H1 POI
    ("H4", "M30", 4),
    ("H4", "H1", 2),
]


def check_all():
    results = []
    stats = {"ENTRY": 0, "no_data": 0, "no_setup": 0, "error": 0, "scanned": 0}
    total = len(MARKETS) * len(DUAL_ROUTES)
    idx = 0

    # Fresh cache each full cycle so we don't reuse stale bars across cycles
    clear_cache()

    for market in MARKETS:
        for htf, ltf, lookback in DUAL_ROUTES:
            idx += 1
            stats["scanned"] += 1
            tag = f"[{idx:02d}/{total}] {market:7s} {htf}→{ltf}"
            try:
                ohlc_htf = get_ohlc(market, htf, limit=280)
                ohlc_ltf = get_ohlc(market, ltf, limit=320)
                if ohlc_htf is None or ohlc_ltf is None:
                    print(f"  {tag}  ·  NO DATA", flush=True)
                    stats["no_data"] += 1
                    continue

                sigs = scan_dual(ohlc_htf, ohlc_ltf, market, htf, ltf, lookback_bars=lookback)
                if not sigs:
                    print(
                        f"  {tag}  ·  NO ENTRY  "
                        f"(HTF={len(ohlc_htf['close'])} LTF={len(ohlc_ltf['close'])} bars)",
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
    """
    Hard de-dupe: one ENTRY per market + direction.
    Prefer higher priority (H4 routes > H1→M30 when both fire).
    """
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['market']}|{s['direction']}"
        if key not in groups or s["priority"] > groups[key]["priority"]:
            groups[key] = s
        elif s["priority"] == groups[key]["priority"] and s["bars_ago"] < groups[key]["bars_ago"]:
            groups[key] = s
    out = list(groups.values())
    if len(signals) != len(out):
        print(f"  DEDUP  {len(signals)} → {len(out)} (1 per market+direction)", flush=True)
    return out
