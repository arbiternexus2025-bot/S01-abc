from flask import Flask
import time
import threading
from telegram_bot import send_alert
from data_feed import get_ohlc
from strategy_runner import MODES, check_modes

app = Flask(__name__)

@app.route("/health")
def health():
    return "OK", 200

def format_signal(s):
    emoji = "🟢 LONG" if s["direction"] == "LONG" else "🔴 SHORT"
    return f"""
🚨 <b>{s['family']} SIGNAL</b>

Mode: <b>{s['mode']}</b>
Market: <b>{s['market']} {s['tf']}</b>
Direction: {emoji}

Entry: <code>{s['entry']}</code>
Stop Loss: <code>{s['sl']}</code>
Take Profit: <code>{s['tp']}</code>
""".strip()

def run_loop():
    print("=== FULL TOP-15 ENGINE (Prioritised) ===", flush=True)
    print("M5 modes  → every 3 minutes", flush=True)
    print("M30/H4    → every 9 minutes", flush=True)
    print("-" * 50, flush=True)

    m5_modes = [m for m in MODES if m["group"] == "M5"]
    htf_modes = [m for m in MODES if m["group"] == "HTF"]

    last_alert = {}          # key = "MODE|DIRECTION|ENTRY"
    last_m5_scan = 0
    last_htf_scan = 0

    while True:
        try:
            now = time.time()
            signals = []

            # ----- M5 group (every 3 min) -----
            if now - last_m5_scan >= 180:
                print("\n[M5] Scanning S-tier modes...", flush=True)
                signals += check_modes(m5_modes, get_ohlc)
                last_m5_scan = now

            # ----- HTF group (every 9 min) -----
            if now - last_htf_scan >= 540:
                print("\n[HTF] Scanning M30/H4 modes...", flush=True)
                signals += check_modes(htf_modes, get_ohlc)
                last_htf_scan = now

            # ----- Process signals -----
            if signals:
                print(f"Found {len(signals)} signal(s) this cycle.", flush=True)
                for s in signals:
                    key = f"{s['mode']}|{s['direction']}|{s['entry']}"
                    if now - last_alert.get(key, 0) > 7200:  # 2-hour cooldown
                        if send_alert(format_signal(s)):
                            last_alert[key] = now
                            print(f"ALERT SENT → {s['mode']} {s['direction']} @ {s['entry']}", flush=True)
                    else:
                        print(f"Skipped duplicate → {s['mode']} {s['direction']} @ {s['entry']}", flush=True)
            else:
                print("No new signals this cycle.", flush=True)

            # Sleep a short time so we can check the timers often
            time.sleep(30)

        except Exception as e:
            print("Loop error:", str(e), flush=True)
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=10000)
