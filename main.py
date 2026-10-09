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
    print("=== NEW TOP-15 ENGINE (S09 Wick Dominant) ===", flush=True)
    print("M30 modes → every 4 minutes", flush=True)
    print("H4 modes  → every 9 minutes", flush=True)
    print("-" * 55, flush=True)

    m30_modes = [m for m in MODES if m["group"] == "M30"]
    h4_modes  = [m for m in MODES if m["group"] == "H4"]

    last_alert = {}
    last_m30 = 0
    last_h4  = 0

    while True:
        try:
            now = time.time()
            signals = []

            if now - last_m30 >= 240:          # 4 min
                print("\n[M30] Scanning...", flush=True)
                signals += check_modes(m30_modes, get_ohlc)
                last_m30 = now

            if now - last_h4 >= 540:           # 9 min
                print("\n[H4] Scanning...", flush=True)
                signals += check_modes(h4_modes, get_ohlc)
                last_h4 = now

            if signals:
                print(f"Found {len(signals)} signal(s).", flush=True)
                for s in signals:
                    key = f"{s['mode']}|{s['direction']}|{s['entry']}"
                    if now - last_alert.get(key, 0) > 7200:  # 2 h cooldown
                        if send_alert(format_signal(s)):
                            last_alert[key] = now
                            print(f"ALERT SENT → {s['mode']} {s['direction']} @ {s['entry']}", flush=True)
                    else:
                        print(f"Skipped duplicate → {s['mode']}", flush=True)
            else:
                print("No new signals this cycle.", flush=True)

            time.sleep(30)

        except Exception as e:
            print("Loop error:", str(e), flush=True)
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=10000)
