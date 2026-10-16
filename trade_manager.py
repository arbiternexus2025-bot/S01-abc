import json
import os
import time
from datetime import datetime, timezone
from data_feed import get_ohlc

OPEN_FILE = "open_trades.json"
CLOSED_FILE = "closed_trades.json"
MAX_AGE_HOURS = 72

def _load(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
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

def append_closed(trade):
    closed = _load(CLOSED_FILE)
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
        "mode": sig["mode"], "market": sig["market"], "tf": sig["tf"],
        "direction": sig["direction"],
        "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
        "risk": sig.get("risk", abs(sig["entry"] - sig["sl"])),
        "status": "OPEN",
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "opened_ts": time.time(),
    }
    trades.append(trade)
    save_open(trades)
    print(f"  [TRACK] OPENED {trade['id']}", flush=True)
    return True

def check_open_trades():
    """
    R1: only bars with time > opened_ts
    R2: no min-age lock — check every cycle on closed bars after entry
    First level hit chronologically wins. True duration.
    """
    trades = load_open()
    still_open, newly = [], []

    for t in trades:
        age_h = (time.time() - t["opened_ts"]) / 3600

        if age_h >= MAX_AGE_HOURS:
            ohlc = get_ohlc(t["market"], t["tf"], limit=50)
            exit_px = float(ohlc["close"][-1]) if ohlc is not None else t["entry"]
            risk = t["risk"] if t["risk"] > 1e-9 else 1e-9
            r = ((exit_px - t["entry"]) if t["direction"] == "LONG"
                 else (t["entry"] - exit_px)) / risk
            closed = dict(t)
            closed.update(
                status="EXPIRED", exit=round(exit_px, 5),
                r_multiple=round(r, 3),
                closed_at=datetime.now(timezone.utc).isoformat(),
                duration_hours=round(age_h, 2)
            )
            newly.append(closed)
            append_closed(closed)
            print(f"  [TRACK] EXPIRED {t['mode']} {r:+.2f}R after {age_h:.1f}h", flush=True)
            continue

        ohlc = get_ohlc(t["market"], t["tf"], limit=150)
        if ohlc is None or "time" not in ohlc:
            still_open.append(t)
            continue

        high, low, close, tms = ohlc["high"], ohlc["low"], ohlc["close"], ohlc["time"]
        hit, exit_px, exit_ts = None, None, None

        for i in range(len(close)):
            # R1: strictly after entry time
            if float(tms[i]) <= t["opened_ts"]:
                continue
            if t["direction"] == "LONG":
                if low[i] <= t["sl"]:
                    hit, exit_px, exit_ts = "SL", t["sl"], float(tms[i])
                    break
                if high[i] >= t["tp"]:
                    hit, exit_px, exit_ts = "TP", t["tp"], float(tms[i])
                    break
            else:
                if high[i] >= t["sl"]:
                    hit, exit_px, exit_ts = "SL", t["sl"], float(tms[i])
                    break
                if low[i] <= t["tp"]:
                    hit, exit_px, exit_ts = "TP", t["tp"], float(tms[i])
                    break

        if hit:
            risk = t["risk"] if t["risk"] > 1e-9 else 1e-9
            r = -1.0 if hit == "SL" else (
                ((exit_px - t["entry"]) if t["direction"] == "LONG"
                 else (t["entry"] - exit_px)) / risk
            )
            dur = (exit_ts - t["opened_ts"]) / 3600 if exit_ts else age_h
            closed = dict(t)
            closed.update(
                status=hit, exit=round(exit_px, 5),
                r_multiple=round(r, 3),
                closed_at=datetime.now(timezone.utc).isoformat(),
                duration_hours=round(max(dur, 0.01), 2)
            )
            newly.append(closed)
            append_closed(closed)
            print(
                f"  [TRACK] {hit} {t['mode']} → {r:+.2f}R "
                f"dur={closed['duration_hours']}h exit={exit_px}",
                flush=True
            )
        else:
            still_open.append(t)

    save_open(still_open)
    return newly

def closed_today_stats():
    closed = _load(CLOSED_FILE)
    if not closed:
        return None
    now = datetime.now(timezone.utc)
    today = []
    for t in closed:
        try:
            ca = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
            if (now - ca).total_seconds() <= 86400:
                today.append(t)
        except Exception:
            pass
    if not today:
        return None
    rs = [t["r_multiple"] for t in today]
    wins = [r for r in rs if r > 0]
    n = len(rs)
    return {
        "n": n, "wins": len(wins), "losses": n - len(wins),
        "wr": round(100.0 * len(wins) / n, 1), "net_r": round(sum(rs), 2)
    }
