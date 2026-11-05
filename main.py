"""
APEX-19 Live Engine — S-tier S19/S29 + S40 MSS v4 Refined
=========================================================
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
    "M5": 45,     # v4 LTF — faster
    "M15": 60,
    "M30": 120,
    "H1": 180,
    "H4": 300,
}

S40_COOLDOWN = 4 * 3600
OTHER_COOLDOWN = 90 * 60


def format_s40(s):
    """Beginner-friendly, professional sweep + MSS alert."""
    is_long = s["direction"] == "LONG"
    bias = "BUY bias (bullish)" if is_long else "SELL bias (bearish)"
    emoji = "🟢 LONG" if is_long else "🔴 SHORT"

    if is_long:
        story = (
            "Price swept below a higher-timeframe support (liquidity grab), "
            "rejected back up, built structure, then broke that structure upward (MSS). "
            "This is a classic bullish reversal sequence."
        )
        action = "Look for longs above the MSS level. Invalidation is below the sweep extreme."
    else:
        story = (
            "Price swept above a higher-timeframe resistance (liquidity grab), "
            "rejected back down, built structure, then broke that structure downward (MSS). "
            "This is a classic bearish reversal sequence."
        )
        action = "Look for shorts below the MSS level. Invalidation is above the sweep extreme."

    return f"""
🚨 <b>APEX-19 · S40 SETUP</b> ⭐⭐⭐

<b>{s['market']}</b> · Chart: <b>{s['tf']}</b> · Key level from: <b>{s.get('htf', 'H4')}</b>
Direction: {emoji}
Bias: <b>{bias}</b>

━━━━━━━━━━━━━━━━━━━━
<b>What happened (plain English)</b>
{story}

━━━━━━━━━━━━━━━━━━━━
<b>Key prices</b>
• HTF key level: <code>{s.get('htf_level')}</code>
• Zone: <code>{s.get('zone_low')}</code> → <code>{s.get('zone_high')}</code>
• Sweep extreme: <code>{s.get('extreme')}</code>
• MSS break level: <code>{s.get('mss_level')}</code>
• Reference close: <code>{s['entry']}</code>
• Suggested stop: <code>{s['sl']}</code>

━━━━━━━━━━━━━━━━━━━━
<b>Quality snapshot</b>
• Rejection wick: <b>{s.get('wick_atr', '?')} ATR</b>
• Sweep candle range: {s.get('range_atr', '?')} ATR
• Structure size: {s.get('structure_atr', '?')} ATR
• Bars sweep → MSS: {s.get('bars_sweep_to_mss', '?')}
• Quality score: <b>{s.get('quality', '—')}</b> · Strong: YES
• Freshness: {s.get('bars_ago', '?')} bar(s) ago

━━━━━━━━━━━━━━━━━━━━
<b>How to use this</b>
{action}

Mode: <code>{s['mode']}</code>
""".strip()


def format_signal(s):
    if s.get("strategy") == "S40":
        return format_s40(s)

    emoji = "🟢 LONG" if s["direction"] == "LONG" else "🔴 SHORT"
    strat = s.get("strategy", "S19")
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
🚨 <b>APEX-19 · {strat} S-TIER</b> ⭐⭐⭐

<b>#{s.get('rank', '?')} · Grade S</b>
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
    print("  APEX-19  ·  S-tier S19/S29 + S40 MSS v4 Refined", flush=True)
    print("  S40: HTF level → Sweep → Structure → MSS (strong only)", flush=True)
    print("=" * 64, flush=True)
    print(f"Modes loaded: {len(MODES)}", flush=True)
    by_strat = {}
    for m in MODES:
        by_strat[m["strategy"]] = by_strat.get(m["strategy"], 0) + 1
    print(f"By strategy: {by_strat}", flush=True)
    for m in MODES:
        print(
            f"  #{m['rank']:03d} {m['strategy']} [S] {m['market']:7s} {m['tf']:3s}  {m.get('preset','')[:28]}",
            flush=True,
        )
    print("-" * 64, flush=True)

    last_alert = {}
    last_scan = {}
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
                        key = f"S40|{s['market']}|{s['direction']}"
                        cool = S40_COOLDOWN
                    else:
                        key = f"{s['strategy']}|{s['market']}|{s['direction']}|{s['entry']}"
                        cool = OTHER_COOLDOWN

                    if now - last_alert.get(key, 0) > cool:
                        if send_alert(format_signal(s)):
                            last_alert[key] = now
                            print(f"ALERT → {s['strategy']} {s['mode']} {s['direction']}", flush=True)
                            if s["strategy"] != "S40" and s.get("tp") is not None:
                                add_open_trade(s)
                            daily["total"] += 1
                            daily["by_market"][s["market"]] = daily["by_market"].get(s["market"], 0) + 1
                    else:
                        remain = int(cool - (now - last_alert.get(key, 0)))
                        print(f"  skip cooldown {key} ({remain}s left)", flush=True)

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
