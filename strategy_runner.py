"""
EDGE LAB LIVE — MARIO + S43 (XAU)
=================================
MARIO  : majors + XAU · M30/H1/H4 structure
S43    : XAUUSD only
         M5_H4_ALIGN · H1_H4_ALIGN · H4_PURE
"""
from __future__ import annotations
from data_feed import get_ohlc, clear_cache
from mario_engine import scan_mario
from s43_engine import scan_s43
from S43_PSAR_Trail_detection import MODE_CONFIG, Mode

MAJORS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
ALL_MARKETS = MAJORS + ["XAUUSD"]
MARIO_TFS = ["M30", "H1", "H4"]

# Gold-only S43 champions
S43_MODES = ["M5_H4_ALIGN", "H1_H4_ALIGN", "H4_PURE"]


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
                        f"{s['entry']} SL {s['stop']} TP {s['target']} RR={s['rr']}",
                        flush=True,
                    )
                    results.append(s)
                    stats["MARIO"] += 1
            except Exception as e:
                print(f"  {tag}  ·  ERROR  {e}", flush=True)
                stats["error"] += 1

    # ── S43 XAU only ──
    print("  ── S43 PSAR TRAIL (XAUUSD) ──", flush=True)
    # Prefetch H4 once for align modes
    xau_h4 = get_ohlc("XAUUSD", "H4", limit=280)
    xau_h1 = get_ohlc("XAUUSD", "H1", limit=320)
    xau_m5 = get_ohlc("XAUUSD", "M5", limit=600)

    for mode in S43_MODES:
        stats["scanned"] += 1
        cfg = MODE_CONFIG[Mode(mode)]
        ltf = cfg.get("ltf") or "H4"
        tag = f"[S] XAUUSD  {mode}"
        try:
            if ltf == "M5":
                ohlc_ltf = xau_m5
            elif ltf == "H1":
                ohlc_ltf = xau_h1
            else:
                ohlc_ltf = xau_h4

            if ohlc_ltf is None:
                print(f"  {tag}  ·  NO DATA (LTF {ltf})", flush=True)
                stats["no_data"] += 1
                continue

            ohlc_htf = xau_h4 if cfg.get("htf_align") else None
            if cfg.get("htf_align") and ohlc_htf is None:
                print(f"  {tag}  ·  NO DATA (H4 align feed)", flush=True)
                stats["no_data"] += 1
                continue

            sigs = scan_s43(ohlc_ltf, "XAUUSD", mode, ohlc_htf=ohlc_htf)
            if not sigs:
                print(f"  {tag}  ·  NO ENTRY  (LTF={len(ohlc_ltf['close'])} bars)", flush=True)
                stats["no_setup"] += 1
                continue
            for s in sigs:
                print(
                    f"  {tag}  🎯 S43 {s['direction']:5s}  "
                    f"{s['entry']}  PSAR {s['stop']}  {s['tf']}",
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
    if not signals:
        return []
    groups = {}
    for s in signals:
        key = f"{s['strategy']}|{s['market']}|{s['direction']}|{s.get('mode', s.get('tf',''))}"
        # tighter: one per strategy+market+direction (mode absorbed)
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
