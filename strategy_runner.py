"""
EDGE LAB LIVE — MARIO + S43
===========================
MARIO  : structure entries  · majors + XAU · M30/H1/H4
S43    : PSAR trail champions — XAUUSD only
         H4_PURE · H1_VOL50 · M5_VOL40
"""
from __future__ import annotations
from data_feed import get_ohlc, clear_cache
from mario_engine import scan_mario
from s43_engine import scan_s43

MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
ALL_MARKETS = MAJORS + ["XAUUSD"]

MARIO_TFS = ["M30", "H1", "H4"]

# S43 routes: (mode, markets)
S43_ROUTES = [
    # Research-locked on gold only — do not run S43 on FX
    ("H4_PURE", ["XAUUSD"]),   # Best Overall
    ("H1_VOL50", ["XAUUSD"]),  # Best Balance
    ("M5_VOL40", ["XAUUSD"]),  # Best Higher-Frequency
]


def check_all():
    results = []
    stats = {
        "MARIO": 0, "S43": 0, "no_data": 0, "no_setup": 0, "error": 0, "scanned": 0,
    }
    clear_cache()

    # ── MARIO ──
    print("  ── MARIO STRUCTURE ──", flush=True)
    total_m = len(ALL_MARKETS) * len(MARIO_TFS)
    idx = 0
    for market in ALL_MARKETS:
        for tf in MARIO_TFS:
            idx += 1
            stats["scanned"] += 1
            tag = f"[M {idx:02d}/{total_m}] {market:7s} {tf:3s}"
            try:
                ohlc = get_ohlc(market, tf)
                if ohlc is None:
                    print(f"  {tag}  ·  NO DATA", flush=True)
                    stats["no_data"] += 1
                    continue
                sigs = scan_mario(ohlc, market, tf)
                if not sigs:
                    print(f"  {tag}  ·  NO ENTRY  ({len(ohlc['close'])} bars)", flush=True)
                    stats["no_setup"] += 1
                    continue
                for s in sigs:
                    print(
                        f"  {tag}  🎯 MARIO {s['direction']:5s}  "
                        f"{s['entry']} → SL {s['stop']} TP {s['target']}  RR={s['rr']}",
                        flush=True,
                    )
                    results.append(s)
                    stats["MARIO"] += 1
            except Exception as e:
                print(f"  {tag}  ·  ERROR  {e}", flush=True)
                stats["error"] += 1

    # ── S43 ──
    print("  ── S43 PSAR TRAIL ──", flush=True)
    total_s = sum(len(ms) for _, ms in S43_ROUTES)
    idx = 0
    for mode, markets in S43_ROUTES:
        tf = {"H4_PURE": "H4", "H1_VOL50": "H1", "M5_VOL40": "M5"}[mode]
        for market in markets:
            idx += 1
            stats["scanned"] += 1
            tag = f"[S {idx:02d}/{total_s}] {market:7s} {mode}"
            try:
                ohlc = get_ohlc(market, tf)
                if ohlc is None:
                    print(f"  {tag}  ·  NO DATA", flush=True)
                    stats["no_data"] += 1
                    continue
                sigs = scan_s43(ohlc, market, mode)
                if not sigs:
                    print(f"  {tag}  ·  NO ENTRY  ({len(ohlc['close'])} bars)", flush=True)
                    stats["no_setup"] += 1
                    continue
                for s in sigs:
                    print(
                        f"  {tag}  🎯 S43 {s['direction']:5s}  "
                        f"{s['entry']}  PSAR/SL {s['stop']}  "
                        f"ATR%={s.get('atr_pct', 0):.2f}",
                        flush=True,
                    )
                    results.append(s)
                    stats["S43"] += 1
            except Exception as e:
                print(f"  {tag}  ·  ERROR  {e}", flush=True)
                stats["error"] += 1

    print("-" * 64, flush=True)
    print(
        f"  SUMMARY  scanned={stats['scanned']}  "
        f"MARIO={stats['MARIO']}  S43={stats['S43']}  "
        f"no_setup={stats['no_setup']}  no_data={stats['no_data']}  error={stats['error']}",
        flush=True,
    )
    print("-" * 64, flush=True)
    return results


def select_best(signals):
    """
    Dedup rules (keep premium, kill spam):
      • Same strategy + market + direction → keep highest priority / freshest
      • Mario and S43 may both fire (different edge families)
    """
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['strategy']}|{s['market']}|{s['direction']}"
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
        print(f"  DEDUP  {len(signals)} → {len(out)}", flush=True)
    return out
