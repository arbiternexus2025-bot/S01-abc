from flask import Flask
import time
import threading
from telegram_bot import send_alert
from strategy import check_signal, MODES
import requests

app = Flask(__name__)

@app.route("/health")
def health():
    return "OK", 200

def get_simple_ohlc(symbol):
    """Temporary simple data - we will upgrade later"""
    try:
        # Using a free public source for demo
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=100&apikey=demo"
        r = requests.get(url, timeout=10)
        data = r.json()
        if "values" in data:
            values = data["values"][::-1]  # oldest first
            return {
                "open":  [float(x["open"]) for x in values],
                "high":  [float(x["high"]) for x in values],
                "low":   [float(x["low"]) for x in values],
                "close": [float(x["close"]) for x in values]
            }
    except Exception as e:
        print("Data fetch error:", e)
    return None

def run_strategy_loop():
    print("S01 Engine started...")
    last_signal_time = {}
    
    while True:
        try:
            for mode_name in MODES:
                symbol = MODES[mode_name]["symbol"]
                ohlc = get_simple_ohlc(symbol)
                
                if ohlc is None:
                    continue
                
                signal = check_signal(ohlc, mode_name)
                
                if signal:
                    # Avoid spam - only alert once every 30 minutes per mode
                    now = time.time()
                    key = mode_name
                    if key not in last_signal_time or (now - last_signal_time[key]) > 1800:
                        msg = f"""
🚨 <b>S01 SIGNAL</b>

Mode: <b>{signal['mode']}</b>
Direction: <b>{signal['direction']}</b>
Entry: {signal['entry']:.5f}
SL: {signal['sl']:.5f}
TP: {signal['tp']:.5f}
"""
                        send_alert(msg)
                        last_signal_time[key] = now
                        print("Signal sent:", signal['mode'], signal['direction'])
            
            time.sleep(60)  # check every 1 minute
            
        except Exception as e:
            print("Loop error:", e)
            time.sleep(30)

if __name__ == "__main__":
    # Start strategy in background
    t = threading.Thread(target=run_strategy_loop, daemon=True)
    t.start()
    
    # Start health server (needed for Render free keep-alive)
    app.run(host="0.0.0.0", port=10000)