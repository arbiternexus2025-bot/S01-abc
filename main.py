"""
================================================================================
  MARIO STRIKE  |  Edge Lab Live Engine
  Production alert system  •  WATCH + ENTRY
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


# Scan cadence (seconds)
SCAN_EVERY = 90

# Cooldown after same zone alert
WATCH_COOLDOWN = 2 * 3600
ENTRY_COOLDOWN = 4 * 3600


def _fmt_price(x):
    return f"<code>{x}</code>"


def format_watch(s):
    is_long = s["direction"] == "LONG"
    arrow = "▲ LONG" if is_long else "▼ SHORT"
    colour = "🟢" if is_long else "🔴"
    side = "BUY" if is_long else "SELL"
    zone_word = "DEMAND" if is_long else "SUPPLY"

    if is_long:
        story = (
            "Sellers swept liquidity below a low. Buyers took structure higher. "
            "A strong demand zone is now marked. Price has <b>not</b> touched it yet."
        )
        action = (
            f"Focus only on the zone between {_fmt_price(s['poi_bot'])} and {_fmt_price(s['poi_top'])}.\n"
            f"Wait for price to arrive and show rejection before considering a {side}."
        )
        invalid = f"Idea fails if price closes clearly under {_fmt_price(s['stop'])}."
    else:
        story = (
            "Buyers swept liquidity above a high. Sellers took structure lower. "
            "A strong supply zone is now marked. Price has <b>not</b> touched it yet."
        )
        action = (
            f"Focus only on the zone between {_fmt_price(s['poi_bot'])} and {_fmt_price(s['poi_top'])}.\n"
            f"Wait for price to arrive and show rejection before considering a {side}."
        )
        invalid = f"Idea fails if price closes clearly above {_fmt_price(s['stop'])}."

    return f"""
⚡️ <b>MARIO STRIKE</b>  ·  <b>ZONE LIVE</b>

━━━━━━━━━━━━━━━━━━━━
<b>{s['market']}</b>   ·   {s['tf']}
{colour}  <b>{arrow}</b>
━━━━━━━━━━━━━━━━━━━━

{story}

📍 <b>{zone_word} ZONE</b>
{_fmt_price(s['poi_bot'])}  →  {_fmt_price(s['poi_top'])}
Type: {s['poi_type']}

📌 <b>PLAN (when price arrives)</b>
• Ideal area: {_fmt_price(s['entry'])}
• Protect below/above: {_fmt_price(s['stop'])}
• Target idea (RR {s['rr']:.1f}): {_fmt_price(s['target'])}

👀 <b>WHAT TO DO NOW</b>
{action}

{invalid}
Window left ≈ {s['bars_left']} bars on {s['tf']}.
""".strip()


def format_entry(s):
    is_long = s["direction"] == "LONG"
    arrow = "▲ LONG" if is_long else "▼ SHORT"
    colour = "🟢" if is_long else "🔴"
    side = "BUY" if is_long else "SELL"

    if is_long:
        story = (
            "Price returned into the demand zone and printed rejection. "
            "The setup is complete."
        )
        action = f"Primary focus: execute a {side} near {_fmt_price(s['entry'])}."
    else:
        story = (
            "Price returned into the supply zone and printed rejection. "
            "The setup is complete."
        )
        action = f"Primary focus: execute a {side} near {_fmt_price(s['entry'])}."

    return f"""
🎯 <b>MARIO STRIKE</b>  ·  <b>ENTRY</b>

━━━━━━━━━━━━━━━━━━━━
<b>{s['market']}</b>   ·   {s['tf']}
{colour}  <b>{arrow}</b>
━━━━━━━━━━━━━━━━━━━━

{story}

✅ <b>TRADE PLAN</b>
• Entry area: {_fmt_price(s['entry'])}
• Stop loss: {_fmt_price(s['stop'])}
• Take profit: {_fmt_price(s['target'])}
• Risk : Reward = 1 : {s['rr']:.1f}

📍 Zone used: {_fmt_price(s['poi_bot'])} → {_fmt_price(s['poi_top'])} ({s['poi_type']})

🔥 <b>ACTION</b>
{action}
Manage risk. Do not chase if price has already run far from the zone.
""".strip()


def format_alert(s):
    if s["phase"] == "ENTRY":
        return format_entry(s)
    return format_watch(s)


def run_loop():
    print("=" * 64, flush=True)
    print("  MARIO STRIKE  ·  Edge Lab Live", flush=True)
    print("  Sweep → BOS → POI → Watch → Rejection Entry", flush=True)
    print("=" * 64, flush=True)
    print(f"Markets : {len(MARKETS)}", flush=True)
    print(f"TFs     : {', '.join(TIMEFRAMES)}", flush=True)
    print(f"Combos  : {len(MARKETS) * len(TIMEFRAMES)}", flush=True)
    print("-" * 64, flush=True)

    last_alert = {}
    last_scan = 0.0

    while True:
        try:
            now = time.time()
            utc = datetime.now(timezone.utc)

            if now - last_scan >= SCAN_EVERY:
                print(f"\n[SCAN] {utc.strftime('%Y-%m-%d %H:%M')} UTC", flush=True)
                signals = check_all()
                signals = select_best(signals)
                last_scan = now

                for s in signals:
                    cool = ENTRY_COOLDOWN if s["phase"] == "ENTRY" else WATCH_COOLDOWN
                    key = s["key"]
                    if now - last_alert.get(key, 0) > cool:
                        msg = format_alert(s)
                        if send_alert(msg):
                            last_alert[key] = now
                            print(f"ALERT → {s['phase']} {s['direction']} {s['market']} {s['tf']}", flush=True)
                    else:
                        remain = int(cool - (now - last_alert.get(key, 0)))
                        print(f"  cooldown {s['market']} {s['direction']} {remain}s", flush=True)

            time.sleep(15)
        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=run_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
