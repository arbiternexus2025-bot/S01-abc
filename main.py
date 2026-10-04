from flask import Flask
import time
import threading
import sys
from telegram_bot import send_alert
from data_feed import get_ohlc
from strategy_runner import check_all_modes, MODES

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
    print("=== FULL TOP-15 ENGINE (biquote) ===", flush=True)
    print(f"Monitoring {len(MODES)} modes", flush=True)
    print("Data source: biquote.io (no API key)", flush=True)
    print("Scan interval: every 3 minutes", flush=True)
    last_alert = {}

    while True:
        try:
            print("Scanning all modes...", flush=True)
            sys.stdout.flush()

            signals = check_all_modes(get_ohlc)

            print(f"Scan finished. Found {len(signals)} signals.", flush=True)

            now = time.time()
            for s in signals:
                key = s["mode"]
                if now - last_alert.get(key, 0) > 2700:
                    if send_alert(format_signal(s)):
                        last_alert[key] = now
                        print(f"ALERT SENT → {s['mode']} {s['direction']}", flush=True)

            print("Sleeping 3 minutes...", flush=True)
            time.sleep(180)

        except Exception as e:
            print("Loop error:", str(e), flush=True)
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=10000)
