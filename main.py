"""
APEX-19 — Legendary S19 Top-50 Live Engine
==========================================
S09 removed. Top-50 research modes only.
Faster scans + tight freshness for earlier alerts.
Detailed reject logging. Grades on every signal.
"""
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
    return "APEX-19 OK", 200


# Faster cadence so signals fire closer to bar close
SCAN = {
    "M5": 60,    # every 1 min
    "M15": 90,   # every 1.5 min
    "M30": 120,  # every 2 min
    "H1": 180,   # every 3 min
    "H4": 300,   # every 5 min
}


def format_signal(s):
    emoji = "🟢 LONG" if s["direction"] == "LONG" else "🔴 SHORT"
    stars = {"S": "⭐⭐⭐", "A+": "⭐⭐", "A": "⭐"}.get(s.get("grade", ""), "⭐")
    return f"""
🚨 <b>APEX-19 SIGNAL</b> {stars}

<b>Rank #{s.get('rank', '?')} · Grade {s.get('grade', '?')}</b>
Mode: <code>{s['mode']}</code>
Setup: {s.get('setup', s.get('preset', ''))}
Market: <b>{s['market']} {s['tf']}</b>
Direction: {emoji}

Entry: <code>{s['entry']}</code>
Stop Loss: <code>{s['sl']}</code>
Take Profit: <code>{s['tp']}</code>
RR: <b>{s.get('rr', 2.5)}</b>

Research: ExpR <b>+{s.get('expr', 0):.2f}</b> · WR {s.get('wr', 0):.1f}% · N={s.get('n_research', '?')}
""".strip()


def format_closed(t):
    icon = {"TP": "✅ HIT TP", "SL": "❌ HIT SL"}.get(t["status"], "⏱ EXPIRED")
    return f"""
{icon}

Mode: <b>{t['mode']}</b>
Grade: {t.get('grade', '—')} · Rank #{t.get('rank', '—')}
Market: <b>{t['market']} {t['tf']}</b>
Direction: {t['direction']}

Entry: <code>{t['entry']}</code> → Exit: <code>{t['exit']}</code>
Result: <b>{t['r_multiple']:+.2f}R</b>
Duration: {t['duration_hours']}h
""".strip()


def format_daily(alert_stats, trade_stats):
    lines = [
        "📊 <b>APEX-19 DAILY SUMMARY</b>",
        "",
        f"Alerts fired: <b>{alert_stats.get('total', 0)}</b>",
    ]
    for m, c in sorted(alert_stats.get("by_market", {}).items()):
        lines.append(f"  · {m}: {c}")
    lines.append("")
    if trade_stats:
        lines += [
            "<b>Closed (24h)</b>",
            f"N={trade_stats['n']}  W/L={trade_stats['wins']}/{trade_stats['losses']}",
            f"WR={trade_stats['wr']}%  Net=<b>{trade_stats['net_r']:+.2f}R</b>",
        ]
    else:
        lines.append("No closes in last 24h")
    lines += ["", f"Open now: {len(load_open())}"]
    return "\n".join(lines)


def run_loop():
    print("=" * 60, flush=True)
    print("  APEX-19  ·  S19 Top-50 Live Engine", flush=True)
    print("  S09 removed  ·  Research-grade only", flush=True)
    print("=" * 60, flush=True)
    print(f"Modes loaded: {len(MODES)}", flush=True)
    by_grade = {}
    for m in MODES:
        by_grade[m["grade"]] = by_grade.get(m["grade"], 0) + 1
    print(f"Grades: {by_grade}", flush=True)
    for m in MODES:
        print(
            f"  #{m['rank']:02d} [{m['grade']:2s}] {m['market']:7s} {m['tf']:3s}  "
            f"{m['preset']:18s}  ExpR+{m['expr']:.2f}  WR{m['wr']:.0f}%",
            flush=True,
        )
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

            # Track open trades every loop
            for t in check_open_trades():
                send_alert(format_closed(t))

            signals = []
            for tf, modes in by_tf.items():
                interval = SCAN.get(tf, 180)
                if now - last_scan[tf] >= interval:
                    print(f"\n[{tf}] {utc.strftime('%Y-%m-%d %H:%M')} UTC  ({len(modes)} modes)", flush=True)
                    signals += check_modes(modes, get_ohlc)
                    last_scan[tf] = now

            if signals:
                signals = select_highest_modes(signals)
                for s in signals:
                    key = f"{s['market']}|{s['direction']}|{s['entry']}"
                    # 90 min cooldown same key
                    if now - last_alert.get(key, 0) > 5400:
                        if send_alert(format_signal(s)):
                            last_alert[key] = now
                            print(f"ALERT → #{s['rank']} {s['mode']} {s['direction']} grade={s['grade']}", flush=True)
                            add_open_trade(s)
                            daily["total"] += 1
                            daily["by_market"][s["market"]] = daily["by_market"].get(s["market"], 0) + 1

            # Daily summary ~21:00 UTC
            if utc.hour >= 21 and last_daily != today:
                send_alert(format_daily(daily, closed_today_stats()))
                daily = {"total": 0, "by_market": {}}
                last_daily = today

            print(f"Open: {len(load_open())} | Sleep 15s", flush=True)
            time.sleep(15)
        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=run_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
