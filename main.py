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

SCAN_M5, SCAN_M15, SCAN_M30 = 120, 180, 240

def format_signal(s):
    emoji = "🟢 LONG" if s["direction"] == "LONG" else "🔴 SHORT"
    return f"""
🚨 <b>S09 {s['family'].upper()} SIGNAL</b> ⭐

Mode: <b>{s['mode']}</b>
Market: <b>{s['market']} {s['tf']}</b>
Direction: {emoji}
Bias: {s.get('bias', '?')}

Entry: <code>{s['entry']}</code>
Stop Loss: <code>{s['sl']}</code>
Take Profit: <code>{s['tp']}</code>
RR: 2.0
""".strip()

def format_closed(t):
    icon = {"TP": "✅ HIT TP", "SL": "❌ HIT SL"}.get(t["status"], "⏱ EXPIRED")
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
    lines = ["📊 <b>DAILY SUMMARY</b>", "", f"Alerts: {alert_stats.get('total', 0)}"]
    for m, c in sorted(alert_stats.get("by_market", {}).items()):
        lines.append(f"  {m}: {c}")
    lines.append("")
    if trade_stats:
        lines += [
            "<b>Closed (24h)</b>",
            f"N={trade_stats['n']}  W/L={trade_stats['wins']}/{trade_stats['losses']}",
            f"WR={trade_stats['wr']}%  Net=<b>{trade_stats['net_r']:+.2f}R</b>",
        ]
    else:
        lines.append("No closes in 24h")
    lines += ["", f"Open now: {len(load_open())}"]
    return "\n".join(lines)

def run_loop():
    print("=== S09 OFFICIAL SPEC ENGINE ===", flush=True)
    print(f"Modes: {len(MODES)} | RR=2.0 | H4 bias ON | timestamps ON", flush=True)
    print("Exit: bars after entry only | no 35min lock", flush=True)
    print(f"Scan M5={SCAN_M5}s M15={SCAN_M15}s M30={SCAN_M30}s", flush=True)
    print("-" * 60, flush=True)

    last_alert = {}
    last_m5 = last_m15 = last_m30 = 0
    last_daily = None
    daily = {"total": 0, "by_market": {}}

    m5  = [m for m in MODES if m["tf"] == "M5"]
    m15 = [m for m in MODES if m["tf"] == "M15"]
    m30 = [m for m in MODES if m["tf"] == "M30"]

    while True:
        try:
            now = time.time()
            utc = datetime.now(timezone.utc)
            today = utc.date()

            for t in check_open_trades():
                send_alert(format_closed(t))

            signals = []
            if now - last_m5 >= SCAN_M5:
                print(f"\n[M5] {utc.strftime('%H:%M')} UTC", flush=True)
                signals += check_modes(m5, get_ohlc)
                last_m5 = now
            if now - last_m15 >= SCAN_M15:
                print(f"\n[M15] {utc.strftime('%H:%M')} UTC", flush=True)
                signals += check_modes(m15, get_ohlc)
                last_m15 = now
            if now - last_m30 >= SCAN_M30:
                print(f"\n[M30] {utc.strftime('%H:%M')} UTC", flush=True)
                signals += check_modes(m30, get_ohlc)
                last_m30 = now

            if signals:
                signals = select_highest_modes(signals)
                for s in signals:
                    key = f"{s['market']}|{s['direction']}|{s['entry']}"
                    if now - last_alert.get(key, 0) > 7200:
                        if send_alert(format_signal(s)):
                            last_alert[key] = now
                            print(f"ALERT → {s['mode']} {s['direction']}", flush=True)
                            add_open_trade(s)
                            daily["total"] += 1
                            daily["by_market"][s["market"]] = daily["by_market"].get(s["market"], 0) + 1
                    else:
                        print(f"Cooldown → {s['mode']}", flush=True)

            if utc.hour >= 21 and last_daily != today:
                send_alert(format_daily(daily, closed_today_stats()))
                daily = {"total": 0, "by_market": {}}
                last_daily = today

            print(f"Open: {len(load_open())} | Sleep 20s", flush=True)
            time.sleep(20)
        except Exception as e:
            print("Loop error:", e, flush=True)
            time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=run_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
