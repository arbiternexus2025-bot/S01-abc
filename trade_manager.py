import json
import os
import time
from datetime import datetime, timezone, timedelta
from data_feed import get_ohlc

OPEN_FILE = "open_trades.json"
CLOSED_FILE = "closed_trades.json"

def _load(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []

def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_open():
    return _load(OPEN_FILE)

def save_open(trades):
    _save(OPEN_FILE, trades)

def load_closed():
    return _load(CLOSED_FILE)

def append_closed(trade):
    closed = load_closed()
    closed.append(trade)
    _save(CLOSED_FILE, closed)

def add_open_trade(sig):
    trades = load_open()
    for t in trades:
        if (t["market"] == sig["market"] and
            t["direction"] == sig["direction"] and
            abs(t["entry"] - sig["entry"]) < 1e-6):
            return False

    trade = {
        "id": f"{sig['market']}_{sig['direction']}_{sig['entry']}_{int(time.time())}",
        "mode": sig["mode"],
        "family": sig["family"],
        "market": sig["market"],
        "tf": sig["tf"],
        "direction": sig["direction"],
        "entry": sig["entry"],
        "sl": sig["sl"],
        "tp": sig["tp"],
        "risk": sig.get("risk", abs(sig["entry"] - sig["sl"])),
        "status": "OPEN",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "opened_ts": time.time()
    }
    trades.append(trade)
    save_open(trades)
    return True

def check_open_trades():
    trades = load_open()
    still_open = []
    newly_closed = []

    for t in trades:
        ohlc = get_ohlc(t["market"], t["tf"], limit=100)
        if ohlc is None:
            still_open.append(t)
            continue

        high, low, close = ohlc["high"], ohlc["low"], ohlc["close"]
        start = max(0, len(close) - 50)

        hit = None
        exit_price = None
        for i in range(start, len(close)):
            if t["direction"] == "LONG":
                if low[i] <= t["sl"]:
                    hit, exit_price = "SL", t["sl"]
                    break
                if high[i] >= t["tp"]:
                    hit, exit_price = "TP", t["tp"]
                    break
            else:
                if high[i] >= t["sl"]:
                    hit, exit_price = "SL", t["sl"]
                    break
                if low[i] <= t["tp"]:
                    hit, exit_price = "TP", t["tp"]
                    break

        age_hours = (time.time() - t["opened_ts"]) / 3600
        if hit is None and age_hours > 72:
            hit, exit_price = "EXPIRED", float(close[-1])

        if hit:
            risk = t["risk"] if t["risk"] > 1e-9 else 1e-9
            if t["direction"] == "LONG":
                r_mult = (exit_price - t["entry"]) / risk
            else:
                r_mult = (t["entry"] - exit_price) / risk
            if hit == "SL":
                r_mult = -1.0

            closed = dict(t)
            closed["status"] = hit
            closed["exit"] = round(exit_price, 5)
            closed["r_multiple"] = round(r_mult, 3)
            closed["closed_at"] = datetime.now(timezone.utc).isoformat()
            closed["duration_hours"] = round(age_hours, 1)
            newly_closed.append(closed)
            append_closed(closed)
        else:
            still_open.append(t)

    save_open(still_open)
    return newly_closed

def _filter_closed(hours_back=None, days_back=None):
    closed = load_closed()
    if not closed:
        return []
    now = datetime.now(timezone.utc)
    out = []
    for t in closed:
        try:
            closed_at = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if hours_back is not None:
            if (now - closed_at).total_seconds() <= hours_back * 3600:
                out.append(t)
        elif days_back is not None:
            if (now - closed_at).days < days_back:
                out.append(t)
        else:
            out.append(t)
    return out

def compute_stats(period="all"):
    """
    period: "daily" (last 24h), "weekly" (last 7 days), "all"
    """
    if period == "daily":
        closed = _filter_closed(hours_back=24)
        title = "DAILY"
    elif period == "weekly":
        closed = _filter_closed(days_back=7)
        title = "WEEKLY"
    else:
        closed = load_closed()
        title = "ALL-TIME"

    if not closed:
        return None, title

    rs = [t["r_multiple"] for t in closed]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    n = len(rs)
    wr = 100.0 * len(wins) / n if n else 0
    avg_r = sum(rs) / n if n else 0
    gross_win = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 1e-9
    pf = gross_win / gross_loss

    eq = peak = max_dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)

    by_market = {}
    for t in closed:
        m = t["market"]
        by_market.setdefault(m, []).append(t["r_multiple"])

    market_lines = []
    for m, vals in sorted(by_market.items()):
        m_wr = 100 * sum(1 for v in vals if v > 0) / len(vals)
        market_lines.append(f"{m}: {len(vals)} trades | WR {m_wr:.0f}% | Net {sum(vals):+.1f}R")

    return {
        "title": title,
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "wr": round(wr, 1),
        "avg_r": round(avg_r, 3),
        "pf": round(pf, 2),
        "net_r": round(sum(rs), 2),
        "max_dd": round(max_dd, 2),
        "market_lines": market_lines
    }, title
