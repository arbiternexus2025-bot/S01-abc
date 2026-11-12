"""
================================================================================
  MARIO STRIKE  |  Edge Lab Live
  Version 2.0.0  ·  Dual-TF  ·  ENTRY only
================================================================================
Latency design:
  • Structure on HTF (H1 / H4)
  • Rejection on faster LTF (M30 / H1) → alert without waiting HTF close
  • Poll every 45s + OHLC cache within cycle
================================================================================
"""
from flask import Flask
import time
import threading
from datetime import datetime, timezone
from telegram_bot import send_alert
from strategy_runner import check_all, select_best, MARKETS, DUAL_ROUTES

app = Flask(__name__)


@app.route("/")
@app.route("/health")
def health():
    return "MARIO STRIKE Dual-TF OK", 200


SCAN_EVERY = 45          # faster poll (was 90)
ENTRY_COOLDOWN = 3 * 3600  # same zone / direction


def _fmt(x):
    return f"<code>{x}</code>"


def format_entry(s):
    is_long = s["direction"] == "LONG"
    arrow = "▲ LONG" if is_long else "▼ SHORT"
    colour = "🟢" if is_long else "🔴"
    side = "BUY" if is_long else "SELL"
    zone_word = "DEMAND" if is_long else "SUPPLY"

    if is_long:
        story = (
            f"Liquidity was swept on <b>{s['htf']}</b>, structure broke higher, "
            f"and <b>{s['ltf']}</b> just rejected from the demand zone."
        )
    else:
        story = (
            f"Liquidity was swept on <b>{s['htf']}</b>, structure broke lower, "
            f"and <b>{s['ltf']}</b> just rejected from the supply zone."
        )

    return f"""
🎯 <b>MARIO STRIKE</b>  ·  <b>ENTRY</b>

━━━━━━━━━━━━━━━━━━━━
<b>{s['market']}</b>   ·   <b>{s['tf']}</b>
{colour}  <b>{arrow}</b>
━━━━━━━━━━━━━━━━━━━━

{story}

✅ <b>TRADE PLAN</b>
• Entry: {_fmt(s['entry'])}
• Stop: {_fmt(s['stop'])}
• Target: {_fmt(s['target'])}
• R:R = 1 : {s['rr']:.1f}

📍 {zone_word}: {_fmt(s['poi_bot'])} → {_fmt(s['poi_top'])} ({s['poi_type']})

🔥 <b>ACTION</b>
Prefer a {side} near {_fmt(s['entry'])}.
Do not chase if price has already left the zone.
""".strip()


def run_loop():
    print("=" * 64, flush=True)
    print("  ██  MARIO STRIKE  ·  Dual-TF v2.0.0  ██", flush=True)
    print("  HTF structure + LTF rejection  ·  ENTRY only", flush=True)
    print("=" * 64, flush=True)
    print(f"  Markets : {len(MARKETS)}", flush=True)
    print(f"  Routes  : {', '.join(f'{h}→{l}' for h,l,_ in DUAL_ROUTES)}", flush=True)
    print(f"  Combos  : {len(MARKETS) * len(DUAL_ROUTES)}", flush=True)
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
                signals = check_all()
                signals = select_best(signals)
                elapsed = time.time() - t0
                last_scan = now

                print(f"  Cycle time: {elapsed:.1f}s", flush=True)

                if not signals:
                    print("  No new ENTRY this cycle.", flush=True)
                for s in signals:
                    key = s["key"]
                    if now - last_alert.get(key, 0) > ENTRY_COOLDOWN:
                        if send_alert(format_entry(s)):
                            last_alert[key] = now
                            print(
                                f"  ★ TELEGRAM  ENTRY  {s['market']} {s['tf']} {s['direction']}",
                                flush=True,
                            )
                    else:
                        remain = int(ENTRY_COOLDOWN - (now - last_alert.get(key, 0)))
                        print(
                            f"  · cooldown  {s['market']} {s['direction']}  {remain // 60}m left",
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
