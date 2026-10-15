import json
import os
import time
from datetime import datetime, timezone
from data_feed import get_ohlc

OPEN_FILE = "open_trades.json"
CLOSED_FILE = "closed_trades.json"

MIN_AGE_SECONDS = 35 * 60
MAX_AGE_HOURS = 72
LOOKBACK_BARS = 40

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
        if t["market"] == sig["market"]:
            print(f"  [TRACK] Already open on {sig['market']} → skip", flush=True)
            return False

    trade = {
        "id": f"{sig['market']}_{sig['direction']}_{sig['entry']}_{int(time.time())}",
        "mode": sig["mode"],
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
    print(f"  [TRACK] OPENED {trade['id']}", flush=True)
    return True

def check_open_trades():
    trades = load_open()
    still_open = []
    newly_closed = []

    for t in trades:
        age_sec = time.time() - t["opened_ts"]
        age_hours = age_sec / 3600

        if age_sec < MIN_AGE_SECONDS:
            still_open.append(t)
            continue

        if age_hours >= MAX_AGE_HOURS:
            ohlc = get_ohlc(t["market"], t["tf"], limit=50)
            exit_price = float(ohlc["close"][-1]) if ohlc is not None else t["entry"]
            risk = t["risk"] if t["risk"] > 1e-9 else 1e-9
            if t["direction"] == "LONG":
                r_mult = (exit_price - t["entry"]) / risk
            else:
                r_mult = (t["entry"] - exit_price) / risk

            closed = dict(t)
            closed["status"] = "EXPIRED"
            closed["exit"] = round(exit_price, 5)
            closed["r_multiple"] = round(r_mult, 3)
            closed["closed_at"] = datetime.now(timezone.utc).isoformat()
            closed["duration_hours"] = round(age_hours, 1)
            newly_closed.append(closed)
            append_closed(closed)
            print(f"  [TRACK] EXPIRED {t['mode']} → {r_mult:+.2f}R", flush=True)
            continue

        ohlc = get_ohlc(t["market"], t["tf"], limit=100)
        if ohlc is None:
            still_open.append(t)
            continue

        high, low, close = ohlc["high"], ohlc["low"], ohlc["close"]
        start = max(0, len(close) - LOOKBACK_BARS)

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

        if hit:
            risk = t["risk"] if t["risk"] > 1e-9 else 1e-9
            if hit == "SL":
                r_mult = -1.0
            else:
                if t["direction"] == "LONG":
                    r_mult = (exit_price - t["entry"]) / risk
                else:
                    r_mult = (t["entry"] - exit_price) / risk

            closed = dict(t)
            closed["status"] = hit
            closed["exit"] = round(exit_price, 5)
            closed["r_multiple"] = round(r_mult, 3)
            closed["closed_at"] = datetime.now(timezone.utc).isoformat()
            closed["duration_hours"] = round(age_hours, 1)
            newly_closed.append(closed)
            append_closed(closed)
            print(f"  [TRACK] {hit} {t['mode']} → {r_mult:+.2f}R ({age_hours:.1f}h)", flush=True)
        else:
            still_open.append(t)

    save_open(still_open)
    return newly_closed

def closed_today_stats():
    closed = load_closed()
    if not closed:
        return None
    now = datetime.now(timezone.utc)
    today = []
    for t in closed:
        try:
            closed_at = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
            if (now - closed_at).total_seconds() <= 24 * 3600:
                today.append(t)
        except Exception:
            continue
    if not today:
        return None
    rs = [t["r_multiple"] for t in today]
    wins = [r for r in rs if r > 0]
    n = len(rs)
    return {
        "n": n,
        "wins": len(wins),
        "losses": n - len(wins),
        "wr": round(100.0 * len(wins) / n, 1),
        "net_r": round(sum(rs), 2)
    }
