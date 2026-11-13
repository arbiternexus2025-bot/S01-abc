"""
================================================================================
  MARIO STRIKE  |  Edge Lab Live
  Single-TF  ·  ENTRY only  ·  Majors + XAUUSD
================================================================================
Anti-late design:
  • detect_latest lookback: M30≤2 bars, H1/H4≤1 bar
  • Poll every 40s
  • OHLC cache 40s within cycle
  • Hard dedupe per market+direction
================================================================================
"""
from flask import Flask
import time
import threading
from datetime import datetime, timezone
from telegram_bot import send_alert
from strategy_runner import check_all, select_best, MARKETS, TIMEFRAMES

app = Flask(__name__)


@app.route("/")
@app.route("/health")
def health():
    return "MARIO STRIKE Single OK", 200


SCAN_EVERY = 40
ENTRY_COOLDOWN = 3 * 3600


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
            "Liquidity was swept under a low, structure broke higher, "
            "and price rejected from the demand zone."
        )
    else:
        story = (
            "Liquidity was swept above a high, structure broke lower, "
            "and price rejected from the supply zone."
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
    print("  ██  MARIO STRIKE  ·  Single-TF ENTRY  ██", flush=True)
    print("  Majors + XAUUSD  ·  M30 / H1 / H4", flush=True)
    print("=" * 64, flush=True)
    print(f"  Markets : {', '.join(MARKETS)}", flush=True)
    print(f"  TFs     : {', '.join(TIMEFRAMES)}", flush=True)
    print(f"  Combos  : {len(MARKETS) * len(TIMEFRAMES)}", flush=True)
    print(f"  Poll    : every {SCAN_EVERY}s", flush=True)
    print(f"  Fresh   : M30≤2 bars · H1/H4≤1 bar", flush=True)
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
