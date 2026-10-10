from flask import Flask
import time
import threading
from datetime import datetime, timezone
from telegram_bot import send_alert
from data_feed import get_ohlc
from strategy_runner import MODES, check_modes
from trade_manager import (
    add_open_trade, check_open_trades, compute_stats, load_open
)

app = Flask(__name__)

@app.route("/health")
def health():
    return "OK", 200

def format_new_signal(s):
    emoji = "🟢 LONG" if s["direction"] == "LONG" else "🔴 SHORT"
    return f"""
🚨 <b>{s['family']} NEW SIGNAL</b>

Mode: <b>{s['mode']}</b>
Market: <b>{s['market']} {s['tf']}</b>
Direction: {emoji}

Entry: <code>{s['entry']}</code>
Stop Loss: <code>{s['sl']}</code>
Take Profit: <code>{s['tp']}</code>
""".strip()

def format_closed(t):
    if t["status"] == "TP":
        icon = "✅ HIT TP"
    elif t["status"] == "SL":
        icon = "❌ HIT SL"
    else:
        icon = "⏱ EXPIRED"
    return f"""
{icon}

Mode: <b>{t['mode']}</b>
Market: <b>{t['market']} {t['tf']}</b>
Direction: {t['direction']}

Entry: <code>{t['entry']}</code> → Exit: <code>{t['exit']}</code>
Result: <b>{t['r_multiple']:+.2f}R</b>
Duration: {t['duration_hours']}h
""".strip()

def format_report(st):
    if not st:
        return None
    lines = [
        f"📊 <b>{st['title']} REPORT</b>",
        "",
        f"Trades: {st['n']}",
        f"Wins / Losses: {st['wins']} / {st['losses']}",
        f"Win Rate: {st['wr']}%",
        f"Avg R: {st['avg_r']}",
        f"Profit Factor: {st['pf']}",
        f"Net: <b>{st['net_r']:+.2f}R</b>",
        f"Max DD: {st['max_dd']}R",
    ]
    if st.get("market_lines"):
        lines.append("")
        lines.append("<b>By Market</b>")
        lines.extend(st["market_lines"])
    return "\n".join(lines)

def run_loop():
    print("=== ENGINE v2.1 — Daily + Friday Weekly Reports ===", flush=True)
    print(f"Modes: {len(MODES)}", flush=True)

    last_alert = {}
    last_m30 = 0
    last_h4 = 0
    last_daily_date = None
    last_weekly_date = None

    m30_modes = [m for m in MODES if m["group"] == "M30"]
    h4_modes  = [m for m in MODES if m["group"] == "H4"]

    while True:
        try:
            now = time.time()
            utc = datetime.now(timezone.utc)
            today = utc.date()
            weekday = utc.weekday()   # 0=Mon ... 4=Fri
            hour = utc.hour

            # ----- Manage open trades -----
            closed = check_open_trades()
            for t in closed:
                send_alert(format_closed(t))
                print(f"CLOSED {t['status']} {t['mode']} → {t['r_multiple']:+.2f}R", flush=True)

            # ----- Signal scans -----
            signals = []
            if now - last_m30 >= 240:
                print("\n[M30] Scanning...", flush=True)
                signals += check_modes(m30_modes, get_ohlc)
                last_m30 = now

            if now - last_h4 >= 540:
                print("\n[H4] Scanning...", flush=True)
                signals += check_modes(h4_modes, get_ohlc)
                last_h4 = now

            for s in signals:
                key = f"{s['market']}|{s['direction']}|{round(s['entry'], 5)}"
                if now - last_alert.get(key, 0) < 7200:
                    print(f"  Skipped duplicate {s['market']} {s['direction']}", flush=True)
                    continue
                if add_open_trade(s):
                    if send_alert(format_new_signal(s)):
                        last_alert[key] = now
                        print(f"ALERT + OPENED → {s['mode']}", flush=True)
                else:
                    print(f"  Already open → {s['market']}", flush=True)

            # ----- DAILY REPORT (once per day after 21:00 UTC) -----
            if hour >= 21 and last_daily_date != today:
                st, _ = compute_stats("daily")
                msg = format_report(st)
                if msg:
                    send_alert(msg)
                    print("Daily report sent", flush=True)
                last_daily_date = today

            # ----- WEEKLY REPORT (Friday after 21:00 UTC) -----
            if weekday == 4 and hour >= 21 and last_weekly_date != today:
                st, _ = compute_stats("weekly")
                msg = format_report(st)
                if msg:
                    send_alert("📅 <b>FRIDAY WEEKLY CLOSE</b>\n\n" + msg)
                    print("Weekly report sent", flush=True)
                last_weekly_date = today

            print(f"Open: {len(load_open())} | Sleep 30s", flush=True)
            time.sleep(30)

        except Exception as e:
            print("Loop error:", str(e), flush=True)
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=10000)
