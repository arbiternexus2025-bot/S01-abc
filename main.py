"""
================================================================================
  MARIO STRIKE  |  Edge Lab Live Engine
  Production  •  WATCH + ENTRY  •  M30 · H1 · H2 · H4
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
    return "MARIO STRIKE OK", 200


SCAN_EVERY = 90
WATCH_COOLDOWN = 2 * 3600
ENTRY_COOLDOWN = 4 * 3600


def _fmt(x):
    return f"<code>{x}</code>"


def format_watch(s):
    is_long = s["direction"] == "LONG"
    arrow = "▲ LONG" if is_long else "▼ SHORT"
    colour = "🟢" if is_long else "🔴"
    side = "BUY" if is_long else "SELL"
    zone_word = "DEMAND" if is_long else "SUPPLY"

    if is_long:
        story = (
            "Sellers swept liquidity below a low. Buyers broke structure higher. "
            "A demand zone is armed. Price has <b>not</b> entered it yet."
        )
        action = (
            f"Watch only {_fmt(s['poi_bot'])} → {_fmt(s['poi_top'])}.\n"
            f"Wait for rejection in that zone before a {side}."
        )
        invalid = f"Invalidate if price closes clearly under {_fmt(s['stop'])}."
    else:
        story = (
            "Buyers swept liquidity above a high. Sellers broke structure lower. "
            "A supply zone is armed. Price has <b>not</b> entered it yet."
        )
        action = (
            f"Watch only {_fmt(s['poi_bot'])} → {_fmt(s['poi_top'])}.\n"
            f"Wait for rejection in that zone before a {side}."
        )
        invalid = f"Invalidate if price closes clearly above {_fmt(s['stop'])}."

    return f"""
⚡️ <b>MARIO STRIKE</b>  ·  <b>ZONE LIVE</b>

━━━━━━━━━━━━━━━━━━━━
<b>{s['market']}</b>   ·   <b>{s['tf']}</b>
{colour}  <b>{arrow}</b>
━━━━━━━━━━━━━━━━━━━━

{story}

📍 <b>{zone_word} ZONE</b>
{_fmt(s['poi_bot'])}  →  {_fmt(s['poi_top'])}
Type: {s['poi_type']}

📌 <b>PLAN (when price arrives)</b>
• Ideal area: {_fmt(s['entry'])}
• Stop: {_fmt(s['stop'])}
• Target (RR {s['rr']:.1f}): {_fmt(s['target'])}

👀 <b>NOW</b>
{action}
{invalid}
Window ≈ {s['bars_left']} bars left on {s['tf']}.
""".strip()


def format_entry(s):
    is_long = s["direction"] == "LONG"
    arrow = "▲ LONG" if is_long else "▼ SHORT"
    colour = "🟢" if is_long else "🔴"
    side = "BUY" if is_long else "SELL"

    if is_long:
        story = "Price hit the demand zone and rejected. Setup complete."
    else:
        story = "Price hit the supply zone and rejected. Setup complete."

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

📍 Zone: {_fmt(s['poi_bot'])} → {_fmt(s['poi_top'])} ({s['poi_type']})

🔥 <b>ACTION</b>
Prefer a {side} near {_fmt(s['entry'])}.
Size risk carefully. Do not chase if price has already left the zone.
""".strip()


def format_alert(s):
    return format_entry(s) if s["phase"] == "ENTRY" else format_watch(s)


def run_loop():
    print("=" * 64, flush=True)
    print("  ██  MARIO STRIKE  ·  EDGE LAB LIVE  ██", flush=True)
    print("  Sweep → BOS → POI → ZONE LIVE → ENTRY", flush=True)
    print("=" * 64, flush=True)
    print(f"  Markets : {len(MARKETS)}  |  TFs : {', '.join(TIMEFRAMES)}", flush=True)
    print(f"  Combos  : {len(MARKETS) * len(TIMEFRAMES)}", flush=True)
    print(f"  H2      : built from H1 (biquote has no native 2h)", flush=True)
    print(f"  Scan    : every {SCAN_EVERY}s", flush=True)
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
                print(
                    f"  CYCLE #{cycle}  ·  {utc.strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    flush=True,
                )
                print(f"{'═' * 64}", flush=True)
                signals = check_all()
                signals = select_best(signals)
                last_scan = now

                if not signals:
                    print("  No actionable WATCH/ENTRY this cycle.", flush=True)
                for s in signals:
                    cool = ENTRY_COOLDOWN if s["phase"] == "ENTRY" else WATCH_COOLDOWN
                    key = s["key"]
                    if now - last_alert.get(key, 0) > cool:
                        if send_alert(format_alert(s)):
                            last_alert[key] = now
                            print(
                                f"  ★ TELEGRAM  {s['phase']}  "
                                f"{s['market']} {s['tf']} {s['direction']}",
                                flush=True,
                            )
                    else:
                        remain = int(cool - (now - last_alert.get(key, 0)))
                        print(
                            f"  · cooldown  {s['market']} {s['direction']}  "
                            f"{remain // 60}m left",
                            flush=True,
                        )
                print(f"  Next scan in ~{SCAN_EVERY}s", flush=True)

            time.sleep(15)
        except Exception as e:
            print(f"  LOOP ERROR: {e}", flush=True)
            time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=run_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
