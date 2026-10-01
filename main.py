from flask import Flask
import time
import threading
from telegram_bot import send_alert
from strategy import check_signal, MODES
from data_feed import get_m5_candles

app = Flask(__name__)

@app.route("/health")
def health():
    return "OK", 200

def format_signal(signal):
    direction_emoji = "🟢 LONG" if signal["direction"] == "LONG" else "🔴 SHORT"
    msg = f"""
🚨 <b>S01 ABC CONTINUATION</b>

Mode: <b>{signal['mode']}</b>
Symbol: <b>{signal['symbol']}</b>
Direction: {direction_emoji}

Entry: <code>{signal['entry']}</code>
Stop Loss: <code>{signal['sl']}</code>
Take Profit: <code>{signal['tp']}</code>

AB Size: {signal['ab_size']}
ATR: {signal['atr']}
"""
    return msg.strip()

def run_strategy_loop():
    print("S01 Engine started (upgraded version)...")
    last_alert = {}

    while True:
        try:
            for mode_name in MODES:
                symbol = MODES[mode_name]["symbol"]
                ohlc = get_m5_candles(symbol, limit=150)

                if ohlc is None:
                    print(f"No data for {symbol}")
                    continue

                signal = check_signal(ohlc, mode_name)

                if signal:
                    # Prevent spam (max 1 alert per mode every 45 minutes)
                    now = time.time()
                    last = last_alert.get(mode_name, 0)
                    if now - last > 2700:
                        msg = format_signal(signal)
                        success = send_alert(msg)
                        if success:
                            last_alert[mode_name] = now
                            print(f"Signal sent → {mode_name} {signal['direction']}")

            time.sleep(60)  # check every 60 seconds

        except Exception as e:
            print("Loop error:", e)
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=run_strategy_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=10000)
