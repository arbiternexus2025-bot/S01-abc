"""
================================================================================
  EDGE LAB LIVE  ·  MARIO STRIKE + S43 HTF→M1 LIMIT TRAIL
  S43 XAUUSD: M5_LIM070 · M30_LIM050 · H1_LIM040
================================================================================
"""
from flask import Flask
import time
import threading
from datetime import datetime, timezone
from telegram_bot import send_alert
from strategy_runner import check_all, select_best, ALL_MARKETS, MARIO_TFS
from S43_HTF_M1_Limit_detection import S43Detector

app = Flask(__name__)


@app.route("/")
@app.route("/health")
def health():
    return "EDGE LAB · MARIO + S43 HTF→M1 OK", 200


SCAN_EVERY = 40
ENTRY_COOLDOWN = 2 * 3600  # limit fills can re-arm; 2h cooldown


def _fmt(x):
    return f"<code>{x}</code>"


def format_mario(s):
    is_long = s["direction"] == "LONG"
    arrow = "▲ LONG" if is_long else "▼ SHORT"
    colour = "🟢" if is_long else "🔴"
    side = "BUY" if is_long else "SELL"
    zone = "DEMAND" if is_long else "SUPPLY"
    return f"""
🎯 <b>MARIO STRIKE</b>  ·  <b>ENTRY</b>

━━━━━━━━━━━━━━━━━━━━
<b>{s['market']}</b>   ·   <b>{s['tf']}</b>
{colour}  <b>{arrow}</b>
━━━━━━━━━━━━━━━━━━━━

Liquidity swept, structure broken, rejection at the zone.

✅ <b>TRADE PLAN</b>
• Entry: {_fmt(s['entry'])}
• Stop: {_fmt(s['stop'])}
• Target: {_fmt(s['target'])}
• R:R = 1 : {s['rr']:.1f}

📍 {zone}: {_fmt(s.get('poi_bot', '—'))} → {_fmt(s.get('poi_top', '—'))}

🔥 Prefer a {side} near the entry. Do not chase.
""".strip()


def format_s43(s):
    is_long = s["direction"] == "LONG"
    arrow = "▲ LONG" if is_long else "▼ SHORT"
    colour = "🟢" if is_long else "🔴"
    side = "BUY" if is_long else "SELL"
    return f"""
🚀 <b>S43 LIMIT TRAIL</b>  ·  <b>ENTRY</b>

━━━━━━━━━━━━━━━━━━━━
<b>XAUUSD</b>   ·   <b>{s['tf']}</b>
{colour}  <b>{arrow}</b>
━━━━━━━━━━━━━━━━━━━━

Mode: <b>{s['mode']}</b>  ·  Grade <b>{s['grade']}</b>
HTF PSAR flip → M1 limit fill at {_fmt(s['limit_price'])}
(offset {s['limit_off']:.2f} × HTF ATR)

✅ <b>TRADE PLAN</b>
• Fill / Entry: {_fmt(s['entry'])}
• Initial trail stop (M1 PSAR): {_fmt(s['stop'])}
• Reference target (RR {s['rr']:.1f}): {_fmt(s['target'])}
• HTF signal price: {_fmt(s['htf_sig_price'])}

🔥 {side} was filled at the limit.
Trail the stop with <b>M1 Parabolic SAR</b> (previous bar).
Do not use a static stop only.
""".strip()


def format_alert(s):
    return format_s43(s) if s.get("strategy") == "S43" else format_mario(s)


def run_loop():
    labels = [S43Detector.MODES[k]["label"] for k in ("A", "B", "C")]
    print("=" * 64, flush=True)
    print("  ██  EDGE LAB LIVE  ·  MARIO + S43 HTF→M1  ██", flush=True)
    print("=" * 64, flush=True)
    print(f"  Markets : {', '.join(ALL_MARKETS)}", flush=True)
    print(f"  MARIO   : {', '.join(MARIO_TFS)}  ({len(ALL_MARKETS)*len(MARIO_TFS)} combos)", flush=True)
    print(f"  S43     : XAUUSD · {' · '.join(labels)}", flush=True)
    print(f"  Poll    : every {SCAN_EVERY}s", flush=True)
    print("=" * 64, flush=True)

    last_alert = {}
    last_scan = 0.0
    cycle = 0

    while True:
        try:
            now = time.time()
            utc = datetime.now(timezone.utc)
            if now - last_scan >= SCAN_EVERY:
                cycle += 1
                print(f"\n{'═' * 64}", flush=True)
                print(f"  CYCLE #{cycle}  ·  {utc.strftime('%Y-%m-%d %H:%M:%S')} UTC", flush=True)
                print(f"{'═' * 64}", flush=True)
                t0 = time.time()
                signals = select_best(check_all())
                print(f"  Cycle time: {time.time()-t0:.1f}s", flush=True)
                last_scan = now

                if not signals:
                    print("  No new ENTRY this cycle.", flush=True)
                for s in signals:
                    key = s["key"]
                    if now - last_alert.get(key, 0) > ENTRY_COOLDOWN:
                        if send_alert(format_alert(s)):
                            last_alert[key] = now
                            print(
                                f"  ★ TELEGRAM  {s['strategy']}  "
                                f"{s['market']} {s.get('mode', s.get('tf'))} {s['direction']}",
                                flush=True,
                            )
                    else:
                        remain = int(ENTRY_COOLDOWN - (now - last_alert.get(key, 0)))
                        print(
                            f"  · cooldown  {s['strategy']} {s['market']} "
                            f"{s['direction']}  {remain//60}m",
                            flush=True,
                        )
                print(f"  Next poll in ~{SCAN_EVERY}s", flush=True)
            time.sleep(8)
        except Exception as e:
            print(f"  LOOP ERROR: {e}", flush=True)
            time.sleep(20)


if __name__ == "__main__":
    threading.Thread(target=run_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
