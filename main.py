"""
APEX-19 Live — S19 Lethal Edge Watch
====================================
Alerts when a setup is ARMED (before POI touch) so you can analyse it.
"""
from flask import Flask
import time
import threading
from datetime import datetime, timezone
from telegram_bot import send_alert
from data_feed import get_ohlc
from strategy_runner import MODES, check_modes, select_highest_modes

app = Flask(__name__)


@app.route("/")
@app.route("/health")
def health():
    return "APEX-19 OK", 200


SCAN = {
    "M30": 120,
    "H1": 180,
    "H4": 300,
}

# Same market+direction cooldown
COOLDOWN = 3 * 3600  # 3 hours


def format_armed(s):
    is_long = s["direction"] == "LONG"
    emoji = "🟢 LONG" if is_long else "🔴 SHORT"
    side = "BUY" if is_long else "SELL"
    poi = s.get("poi_type", "OB")

    if is_long:
        story = (
            "Liquidity under a low was taken, structure broke higher, "
            "and a strong demand zone (order block) is now active. "
            "Price has not touched that zone yet."
        )
        watch = (
            f"Watch for price to come down into the zone "
            f"({s['poi_bot']} – {s['poi_top']}). "
            f"A reaction there is the potential {side} area."
        )
        invalid = f"Idea is weaker if price closes clearly below {s['sl']}."
    else:
        story = (
            "Liquidity above a high was taken, structure broke lower, "
            "and a strong supply zone (order block) is now active. "
            "Price has not touched that zone yet."
        )
        watch = (
            f"Watch for price to come up into the zone "
            f"({s['poi_bot']} – {s['poi_top']}). "
            f"A reaction there is the potential {side} area."
        )
        invalid = f"Idea is weaker if price closes clearly above {s['sl']}."

    return f"""
🔔 <b>APEX-19 · SETUP READY</b> ⭐⭐⭐

<b>{s['market']}</b> · {s['tf']} · {s.get('role', s['preset'])}
Direction: {emoji}

━━━━━━━━━━━━━━━━━━━━
<b>What this means</b>
{story}

━━━━━━━━━━━━━━━━━━━━
<b>Zone to watch</b>
• Zone (POI): <code>{s['poi_bot']}</code> → <code>{s['poi_top']}</code>
• Type: {poi}
• Reference mid: <code>{s['entry_ref']}</code>
• Suggested stop: <code>{s['sl']}</code>
• Target idea (RR {s['rr']:.0f}): <code>{s['tp_ref']}</code>

━━━━━━━━━━━━━━━━━━━━
<b>What to do</b>
{watch}

This is <b>not</b> an automatic entry. Use it to prepare and analyse.
{invalid}

Window left: ~{s.get('bars_until_expiry', '?')} bars on this timeframe.
Mode: <code>{s['mode']}</code>
""".strip()


def run_loop():
    print("=" * 64, flush=True)
    print("  APEX-19  ·  S19 Lethal Edge WATCH", flush=True)
    print("  Armed alerts before POI touch · M30/H1/H4", flush=True)
    print("  Markets: majors + minors + XAUUSD", flush=True)
    print("=" * 64, flush=True)
    print(f"Modes loaded: {len(MODES)}", flush=True)
    by_tf = {}
    for m in MODES:
        by_tf.setdefault(m["tf"], []).append(m)
    for tf, ms in by_tf.items():
        print(f"  {tf}: {len(ms)} modes", flush=True)
    print("-" * 64, flush=True)

    last_alert = {}
    last_scan = {}

    while True:
        try:
            now = time.time()
            utc = datetime.now(timezone.utc)
            signals = []

            for tf, modes in by_tf.items():
                interval = SCAN.get(tf, 180)
                if now - last_scan.get(tf, 0) >= interval:
                    print(
                        f"\n[{tf}] {utc.strftime('%Y-%m-%d %H:%M')} UTC  ({len(modes)} modes)",
                        flush=True,
                    )
                    signals += check_modes(modes, get_ohlc)
                    last_scan[tf] = now

            if signals:
                signals = select_highest_modes(signals)
                for s in signals:
                    key = f"{s['market']}|{s['direction']}|{s['poi_bot']}|{s['poi_top']}"
                    if now - last_alert.get(key, 0) > COOLDOWN:
                        if send_alert(format_armed(s)):
                            last_alert[key] = now
                            print(
                                f"ALERT → ARMED {s['direction']} {s['market']} {s['tf']}",
                                flush=True,
                            )
                    else:
                        remain = int(COOLDOWN - (now - last_alert.get(key, 0)))
                        print(f"  skip cooldown {key[:40]}… ({remain}s)", flush=True)

            print(f"Sleep 15s", flush=True)
            time.sleep(15)
        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=run_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
