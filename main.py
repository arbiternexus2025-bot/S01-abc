from flask import Flask
import time
import threading
from datetime import datetime, timezone
from telegram_bot import send_alert
from data_feed import get_ohlc
from strategy_runner import MODES, check_modes, select_highest_modes
from trade_manager import add_open_trade, check_open_trades, load_open, closed_today_stats

app = Flask(__name__)


@app.route("/health")
def health():
    return "OK", 200


SCAN = {"M5": 120, "M15": 180, "M30": 240, "H1": 300, "H4": 600}


def format_signal(s):
    emoji = "🟢 LONG" if s["direction"] == "LONG" else "🔴 SHORT"
    return f"""
🚨 <b>{s['strategy']} {s['family']} SIGNAL</b> ⭐

Mode: <b>{s['mode']}</b>
Market: <b>{s['market']} {s['tf']}</b>
Direction: {emoji}

Entry: <code>{s['entry']}</code>
Stop Loss: <code>{s['sl']}</code>
Take Profit: <code>{s['tp']}</code>
RR: {s.get('rr', 2.0)}
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
            f"N={trade_stats['n']} W/L={trade_stats['wins']}/{trade_stats['losses']}",
            f"WR={trade_stats['wr']}% Net=<b>{trade_stats['net_r']:+.2f}R</b>",
        ]
    else:
        lines.append("No closes in 24h")
    lines += ["", f"Open now: {len(load_open())}"]
    return "\n".join(lines)


def run_loop():
    print("=== S09 + S19 DUAL ENGINE (self-contained S19) ===", flush=True)
    s09 = [m for m in MODES if m.get("strategy") == "S09"]
    s19 = [m for m in MODES if m.get("strategy") == "S19"]
    print(f"S09: {len(s09)} | S19: {len(s19)} | Total: {len(MODES)}", flush=True)
    for m in MODES:
        extra = f" preset={m['preset']}" if m.get("preset") else ""
        print(f"  [{m.get('strategy'):3}] {m['id']}{extra}", flush=True)
    print("-" * 60, flush=True)

    last_alert = {}
    last_scan = {tf: 0 for tf in SCAN}
    last_daily = None
    daily = {"total": 0, "by_market": {}}
    by_tf = {}
    for m in MODES:
        by_tf.setdefault(m["tf"], []).append(m)

    while True:
        try:
            now = time.time()
            utc = datetime.now(timezone.utc)
            today = utc.date()

            for t in check_open_trades():
                send_alert(format_closed(t))

            signals = []
            for tf, modes in by_tf.items():
                interval = SCAN.get(tf, 240)
                if now - last_scan[tf] >= interval:
                    print(f"\n[{tf}] {utc.strftime('%H:%M')} UTC ({len(modes)} modes)", flush=True)
                    signals += check_modes(modes, get_ohlc)
                    last_scan[tf] = now

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
