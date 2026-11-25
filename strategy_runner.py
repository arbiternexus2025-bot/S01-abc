"""
EDGE LAB LIVE — MARIO + S43 HTF→M1 Limit Trail
==============================================
MARIO  : majors + XAU · M30/H1/H4 structure ENTRY
S43    : XAUUSD only · M5/M30/H1 → M1 limit trail champions
"""
from __future__ import annotations
from data_feed import get_ohlc, clear_cache
from mario_engine import scan_mario
from s43_engine import scan_s43_mode, MODE_ORDER
from S43_HTF_M1_Limit_detection import S43Detector

MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
ALL_MARKETS = MAJORS + ["XAUUSD"]
MARIO_TFS = ["M30", "H1", "H4"]

S43_MODE_META = S43Detector.MODES  # A/B/C


def check_all():
    results = []
    stats = {"MARIO": 0, "S43": 0, "no_data": 0, "no_setup": 0, "error": 0, "scanned": 0}
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
                        f"{s['entry']} SL {s['stop']} TP {s['target']}",
                        flush=True,
                    )
                    results.append(s)
                    stats["MARIO"] += 1
            except Exception as e:
                print(f"  {tag}  ·  ERROR  {e}", flush=True)
                stats["error"] += 1

    # ── S43 XAU HTF→M1 ──
    print("  ── S43 HTF→M1 LIMIT TRAIL (XAUUSD) ──", flush=True)
    m1 = get_ohlc("XAUUSD", "M1", limit=1500)
    if m1 is None:
        print("  [S] XAUUSD M1  ·  NO DATA — S43 skipped this cycle", flush=True)
        stats["no_data"] += 3
    else:
        htf_cache = {}
        for code in MODE_ORDER:
            stats["scanned"] += 1
            meta = S43_MODE_META[code]
            htf_tf = meta["htf"]
            tag = f"[S] XAUUSD  {meta['label']} ({htf_tf}→M1)"
            try:
                if htf_tf not in htf_cache:
                    htf_cache[htf_tf] = get_ohlc("XAUUSD", htf_tf)
                htf = htf_cache[htf_tf]
                if htf is None:
                    print(f"  {tag}  ·  NO DATA (HTF {htf_tf})", flush=True)
                    stats["no_data"] += 1
                    continue
                sigs = scan_s43_mode(htf, m1, code)
                if not sigs:
                    print(
                        f"  {tag}  ·  NO ENTRY  "
                        f"(HTF={len(htf['close'])} M1={len(m1['close'])})",
                        flush=True,
                    )
                    stats["no_setup"] += 1
                    continue
                for s in sigs:
                    print(
                        f"  {tag}  🎯 S43 {s['direction']:5s}  "
                        f"limit {s['limit_price']} fill {s['entry']}  "
                        f"SL {s['stop']}  grade={s['grade']}",
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
    """One alert per strategy + market + direction (prefer higher priority)."""
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['strategy']}|{s['market']}|{s['direction']}"
        cur = groups.get(key)
        if cur is None or s["priority"] > cur["priority"] or (
            s["priority"] == cur["priority"] and s["bars_ago"] < cur["bars_ago"]
        ):
            groups[key] = s
    out = list(groups.values())
    if len(signals) != len(out):
        print(f"  DEDUP  {len(signals)} → {len(out)}", flush=True)
    return out
