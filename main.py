"""
================================================================================
  EDGE LAB LIVE  ·  MARIO STRIKE + S43 PSAR TRAIL
  Structure entries + Parabolic trail champions
================================================================================
"""
from flask import Flask
import time
import threading
from datetime import datetime, timezone
from telegram_bot import send_alert
from strategy_runner import check_all, select_best, ALL_MARKETS, MARIO_TFS, S43_ROUTES

app = Flask(__name__)


@app.route("/")
@app.route("/health")
def health():
    return "EDGE LAB · MARIO + S43 OK", 200


SCAN_EVERY = 40
ENTRY_COOLDOWN = 3 * 3600


def _fmt(x):
    return f"<code>{x}</code>"


def format_mario(s):
    is_long = s["direction"] == "LONG"
    arrow = "▲ LONG" if is_long else "▼ SHORT"
    colour = "🟢" if is_long else "🔴"
    side = "BUY" if is_long else "SELL"
    zone = "DEMAND" if is_long else "SUPPLY"
    story = (
        "Liquidity swept, structure broken, rejection at the zone."
        if is_long else
        "Liquidity swept, structure broken, rejection at the zone."
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

📍 {zone}: {_fmt(s.get('poi_bot', '—'))} → {_fmt(s.get('poi_top', '—'))}

🔥 Prefer a {side} near the entry. Do not chase.
""".strip()


def format_s43(s):
    is_long = s["direction"] == "LONG"
    arrow = "▲ LONG" if is_long else "▼ SHORT"
    colour = "🟢" if is_long else "🔴"
    side = "BUY" if is_long else "SELL"
    mode_title = {
        "H4_PURE": "H4 PURE · Best Overall",
        "H1_VOL50": "H1 VOL50 · Best Balance",
        "M5_VOL40": "M5 VOL40 · Higher Frequency",
    }.get(s["mode"], s["mode"])

    return f"""
🚀 <b>S43 PSAR TRAIL</b>  ·  <b>ENTRY</b>

━━━━━━━━━━━━━━━━━━━━
<b>{s['market']}</b>   ·   <b>{s['tf']}</b>
{colour}  <b>{arrow}</b>
━━━━━━━━━━━━━━━━━━━━

Mode: <b>{mode_title}</b>
PSAR flipped with filters passed. Trail is the live stop.

✅ <b>TRADE PLAN</b>
• Entry: {_fmt(s['entry'])}
• Initial stop (PSAR): {_fmt(s['stop'])}
• Reference target (RR {s['rr']:.1f}): {_fmt(s['target'])}
• ATR regime: {s.get('atr_pct', 0):.0%}

🔥 <b>ACTION</b>
{side} near {_fmt(s['entry'])}.
Trail the stop with Parabolic SAR — do not use a static stop only.
""".strip()


def format_alert(s):
    if s.get("strategy") == "S43":
        return format_s43(s)
    return format_mario(s)


def run_loop():
    n_s43 = sum(len(m) for _, m in S43_ROUTES)
    print("=" * 64, flush=True)
    print("  ██  EDGE LAB LIVE  ·  MARIO + S43  ██", flush=True)
    print("  Structure  +  PSAR Trail Champions", flush=True)
    print("=" * 64, flush=True)
    print(f"  Markets : {', '.join(ALL_MARKETS)}", flush=True)
    print(f"  MARIO   : {', '.join(MARIO_TFS)}  ({len(ALL_MARKETS)*len(MARIO_TFS)} combos)", flush=True)
    print(f"  S43     : XAUUSD only · H4_PURE · H1_VOL50 · M5_VOL40  ({n_s43} combos)", flush=True)
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
                                f"{s['market']} {s.get('tf','')} {s['direction']}",
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
