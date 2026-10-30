"""
APEX-19 — S19 + S29 + S40 Liquidity Sweep Live Engine
=====================================================
S40: Pure sweep alerts across majors, minors, and XAUUSD (H1/H4)
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


@app.route("/")
@app.route("/health")
def health():
    return "APEX-19 OK", 200


SCAN = {
    "M5": 60,
    "M15": 90,
    "M30": 120,
    "H1": 180,
    "H4": 300,
}


def format_signal(s):
    emoji = "🟢 LONG" if s["direction"] == "LONG" else "🔴 SHORT"
    stars = {"S": "⭐⭐⭐", "A/A+": "⭐⭐⭐", "A+": "⭐⭐", "A": "⭐", "B+": "·"}.get(
        s.get("grade", ""), "⭐"
    )
    strat = s.get("strategy", "S19")

    if strat == "S40":
        what = (
            "Pivot LOW swept — bullish liquidity grab"
            if s["direction"] == "LONG"
            else "Pivot HIGH swept — bearish liquidity grab"
        )
        return f"""
🚨 <b>APEX-19 S40 SWEEP</b> {stars}

<b>{s['market']} {s['tf']}</b> · {s.get('preset', '')}
Direction bias: {emoji}
{what}

Swept level: <code>{s.get('level')}</code>
Extreme: <code>{s.get('extreme')}</code>
Close: <code>{s['entry']}</code>
Stop ref: <code>{s['sl']}</code>

Wick: <b>{s.get('wick_atr', '?')} ATR</b> · Range: {s.get('range_atr', '?')} ATR
Rejection: {"YES" if s.get("is_rejection") else "NO"} · Strong: {"YES" if s.get("strong") else "NO"}
Session: {s.get("session") or "—"}

Mode: <code>{s['mode']}</code>
""".strip()

    oos = s.get("oos")
    oos_txt = f"+{oos:.3f}" if isinstance(oos, (int, float)) else "—"
    dd = s.get("maxdd")
    dd_txt = f"{dd:.1f}R" if isinstance(dd, (int, float)) else "—"
    tp2 = s.get("tp2")
    if strat == "S29" and tp2 is not None:
        tp_block = f"TP1 (mid): <code>{s['tp']}</code>\nTP2 (opp): <code>{tp2}</code>"
        rr_line = f"RR→mid: <b>{s.get('rr', '—')}</b>"
    else:
        tp_block = f"Take Profit: <code>{s.get('tp')}</code>"
        rr_line = f"RR: <b>{s.get('rr', '—')}</b>"

    return f"""
🚨 <b>APEX-19 {strat} SIGNAL</b> {stars}

<b>#{s.get('rank', '?')} · Tier {s.get('tier', '?')} · Grade {s.get('grade', '?')}</b>
Role: {s.get('role', '—')}
Mode: <code>{s['mode']}</code>
Setup: {s.get('setup', '')}
Market: <b>{s['market']} {s['tf']}</b>
Direction: {emoji}

Entry: <code>{s['entry']}</code>
Stop Loss: <code>{s['sl']}</code>
{tp_block}
{rr_line}

Research: ExpR <b>+{s.get('expr', 0):.3f}</b> · WR {s.get('wr', 0):.1f}% · N={s.get('n_research', '?')}
OOS ExpR {oos_txt} · MaxDD {dd_txt}
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
    print("=" * 64, flush=True)
    print("  APEX-19  ·  S19 + S29 + S40 Liquidity Sweep", flush=True)
    print("  S40: majors + minors + XAUUSD  |  H4/H1 sweep alerts", flush=True)
    print("=" * 64, flush=True)
    print(f"Modes loaded: {len(MODES)}", flush=True)
    by_strat = {}
    for m in MODES:
        by_strat[m["strategy"]] = by_strat.get(m["strategy"], 0) + 1
    print(f"By strategy: {by_strat}", flush=True)
    s40 = [m for m in MODES if m["strategy"] == "S40"]
    markets = sorted({m["market"] for m in s40})
    print(f"S40 markets ({len(markets)}): {', '.join(markets)}", flush=True)
    print("-" * 64, flush=True)

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
                interval = SCAN.get(tf, 180)
                if now - last_scan.get(tf, 0) >= interval:
                    print(
                        f"\n[{tf}] {utc.strftime('%Y-%m-%d %H:%M')} UTC  ({len(modes)} modes)",
                        flush=True,
                    )
                    signals += check_modes(modes, get_ohlc)
                    last_scan[tf] = now

            if signals:
                signals = select_highest_modes(signals)
                for s in signals:
                    if s["strategy"] == "S40":
                        key = f"S40|{s['market']}|{s['direction']}|{s.get('level')}"
                    else:
                        key = f"{s['strategy']}|{s['market']}|{s['direction']}|{s['entry']}"
                    cool = 5400  # 90 min
                    if now - last_alert.get(key, 0) > cool:
                        if send_alert(format_signal(s)):
                            last_alert[key] = now
                            print(
                                f"ALERT → {s['strategy']} {s['mode']} {s['direction']}",
                                flush=True,
                            )
                            # Only track SL/TP for non-S40 (S40 is informational sweep)
                            if s["strategy"] != "S40" and s.get("tp") is not None:
                                add_open_trade(s)
                            daily["total"] += 1
                            daily["by_market"][s["market"]] = (
                                daily["by_market"].get(s["market"], 0) + 1
                            )

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
