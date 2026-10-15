from flask import Flask
import time
import threading
from datetime import datetime, timezone
from telegram_bot import send_alert
from data_feed import get_ohlc
from strategy_runner import MODES, check_modes, select_highest_modes
from trade_manager import (
    add_open_trade, check_open_trades, load_open, closed_today_stats
)

app = Flask(__name__)

@app.route("/health")
def health():
    return "OK", 200

# ---------- Scan intervals (seconds) ----------
SCAN_M5  = 120   # every 2 minutes
SCAN_M15 = 180   # every 3 minutes
SCAN_M30 = 240   # every 4 minutes
# ----------------------------------------------

def format_signal(s):
    emoji = "🟢 LONG" if s["direction"] == "LONG" else "🔴 SHORT"
    return f"""
🚨 <b>S09 {s['family'].upper()} SIGNAL</b> ⭐

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

def format_daily(alert_stats, trade_stats):
    lines = ["📊 <b>DAILY SUMMARY</b>", ""]
    lines.append(f"Alerts sent: {alert_stats.get('total', 0)}")
    if alert_stats.get("by_market"):
        for m, c in sorted(alert_stats["by_market"].items()):
            lines.append(f"  {m}: {c}")
    lines.append("")
    if trade_stats:
        lines.append("<b>Closed trades (24h)</b>")
        lines.append(f"Trades: {trade_stats['n']}")
        lines.append(f"Wins / Losses: {trade_stats['wins']} / {trade_stats['losses']}")
        lines.append(f"Win Rate: {trade_stats['wr']}%")
        lines.append(f"Net: <b>{trade_stats['net_r']:+.2f}R</b>")
    else:
        lines.append("No trades closed in last 24h")
    lines.append("")
    lines.append(f"Currently open: {len(load_open())}")
    return "\n".join(lines)

def run_loop():
    print("=== 17-MODE ENGINE — Per-TF Scan Frequency ===", flush=True)
    print(f"Modes: {len(MODES)}", flush=True)
    print(f"M5  every {SCAN_M5}s | M15 every {SCAN_M15}s | M30 every {SCAN_M30}s", flush=True)
    print("-" * 55, flush=True)

    last_alert = {}
    last_m5 = 0
    last_m15 = 0
    last_m30 = 0
    last_daily_date = None
    daily_alerts = {"total": 0, "by_market": {}}

    m5_modes  = [m for m in MODES if m["tf"] == "M5"]
    m15_modes = [m for m in MODES if m["tf"] == "M15"]
    m30_modes = [m for m in MODES if m["tf"] == "M30"]

    print(f"M5 modes: {len(m5_modes)} | M15: {len(m15_modes)} | M30: {len(m30_modes)}", flush=True)

    while True:
        try:
            now = time.time()
            utc = datetime.now(timezone.utc)
            today = utc.date()
            hour = utc.hour

            # 1. Safe trade check (always)
            closed = check_open_trades()
            for t in closed:
                send_alert(format_closed(t))

            signals = []

            # 2. M5 scan
            if now - last_m5 >= SCAN_M5:
                print("\n[M5] Scanning...", flush=True)
                signals += check_modes(m5_modes, get_ohlc)
                last_m5 = now

            # 3. M15 scan
            if now - last_m15 >= SCAN_M15:
                print("\n[M15] Scanning...", flush=True)
                signals += check_modes(m15_modes, get_ohlc)
                last_m15 = now

            # 4. M30 scan
            if now - last_m30 >= SCAN_M30:
                print("\n[M30] Scanning...", flush=True)
                signals += check_modes(m30_modes, get_ohlc)
                last_m30 = now

            # 5. Highest-mode filter + alert
            if signals:
                signals = select_highest_modes(signals)
                for s in signals:
                    key = f"{s['market']}|{s['direction']}|{s['entry']}"
                    if now - last_alert.get(key, 0) > 7200:
                        if send_alert(format_signal(s)):
                            last_alert[key] = now
                            print(f"ALERT SENT → {s['mode']} {s['direction']}", flush=True)
                            add_open_trade(s)
                            daily_alerts["total"] += 1
                            daily_alerts["by_market"][s["market"]] = \
                                daily_alerts["by_market"].get(s["market"], 0) + 1
                    else:
                        print(f"Skipped (cooldown) → {s['mode']}", flush=True)

            # 6. Daily summary
            if hour >= 21 and last_daily_date != today:
                trade_stats = closed_today_stats()
                send_alert(format_daily(daily_alerts, trade_stats))
                print("Daily summary sent", flush=True)
                daily_alerts = {"total": 0, "by_market": {}}
                last_daily_date = today

            print(f"Open: {len(load_open())} | Sleep 20s", flush=True)
            time.sleep(20)

        except Exception as e:
            print("Loop error:", str(e), flush=True)
            time.sleep(30)

if __name__ == "__main__":
    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=10000)
