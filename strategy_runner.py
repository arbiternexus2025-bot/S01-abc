"""
EDGE LAB LIVE — S43 ONLY (Mario on hold)
========================================
S43 XAUUSD: M5_LIM070 · M30_LIM050 · H1_LIM040  (HTF → M1 limit trail)
"""
from __future__ import annotations
from data_feed import get_ohlc, clear_cache
from s43_engine import scan_s43_mode, MODE_ORDER
from S43_HTF_M1_Limit_detection import S43Detector

S43_MODE_META = S43Detector.MODES


def check_all():
    results = []
    stats = {"S43": 0, "no_data": 0, "no_setup": 0, "error": 0, "scanned": 0}
    clear_cache()

    print("  ── S43 HTF→M1 LIMIT TRAIL (XAUUSD) ──", flush=True)
    m1 = get_ohlc("XAUUSD", "M1", limit=1500)
    if m1 is None:
        print("  [S] XAUUSD M1  ·  NO DATA — S43 skipped this cycle", flush=True)
        stats["no_data"] += 3
        print("-" * 64, flush=True)
        print(
            f"  SUMMARY  scanned={stats['scanned']}  S43={stats['S43']}  "
            f"no_setup={stats['no_setup']}  no_data={stats['no_data']}  error={stats['error']}",
            flush=True,
        )
        print("-" * 64, flush=True)
        return results

    print(f"  M1 bars loaded: {len(m1['close'])}", flush=True)
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
                    f"SL {s['stop']}  grade={s['grade']}  bars_ago={s['bars_ago']}",
                    flush=True,
                )
                results.append(s)
                stats["S43"] += 1
        except Exception as e:
            print(f"  {tag}  ·  ERROR  {e}", flush=True)
            stats["error"] += 1

    print("-" * 64, flush=True)
    print(
        f"  SUMMARY  scanned={stats['scanned']}  S43={stats['S43']}  "
        f"no_setup={stats['no_setup']}  no_data={stats['no_data']}  error={stats['error']}",
        flush=True,
    )
    print("-" * 64, flush=True)
    return results


def select_best(signals):
    """One alert per direction (prefer higher priority mode)."""
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
