import numpy as np

# Exact parameters from your validated Pine Script
MODES = {
    "GBPUSD_M15_5": {
        "symbol": "GBPUSD",
        "pivot_len": 5,
        "min_imp": 1.00,
        "max_retr": 0.90,
        "vol_mult": 1.0,
        "tp_mult": 0.55
    },
    "USDJPY_M15_7": {
        "symbol": "USDJPY",
        "pivot_len": 7,
        "min_imp": 1.00,
        "max_retr": 0.90,
        "vol_mult": 1.0,
        "tp_mult": 0.55
    }
}

def calculate_atr(high, low, close, period=14):
    high = np.array(high, dtype=float)
    low  = np.array(low, dtype=float)
    close = np.array(close, dtype=float)

    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    if len(tr) < period:
        return None
    atr = np.convolve(tr, np.ones(period)/period, mode='valid')
    return atr

def find_pivots(high, low, pivot_len):
    high = np.array(high)
    low  = np.array(low)
    pivots = []  # (index, price, type)   1 = high, -1 = low

    for i in range(pivot_len, len(high) - pivot_len):
        is_high = all(high[i] >= high[i-j] for j in range(1, pivot_len+1)) and \
                  all(high[i] >= high[i+j] for j in range(1, pivot_len+1))
        is_low  = all(low[i]  <= low[i-j]  for j in range(1, pivot_len+1)) and \
                  all(low[i]  <= low[i+j]  for j in range(1, pivot_len+1))

        if is_high:
            if not pivots or pivots[-1][2] != 1:
                pivots.append((i, float(high[i]), 1))
            elif high[i] > pivots[-1][1]:
                pivots[-1] = (i, float(high[i]), 1)

        if is_low:
            if not pivots or pivots[-1][2] != -1:
                pivots.append((i, float(low[i]), -1))
            elif low[i] < pivots[-1][1]:
                pivots[-1] = (i, float(low[i]), -1)

    return pivots

def check_signal(ohlc, mode_name):
    mode = MODES[mode_name]
    high  = ohlc["high"]
    low   = ohlc["low"]
    close = ohlc["close"]

    if len(close) < 80:
        return None

    atr_values = calculate_atr(high, low, close)
    if atr_values is None or len(atr_values) == 0:
        return None

    current_atr = atr_values[-1]
    atr_med = np.mean(atr_values[-40:]) if len(atr_values) >= 40 else current_atr

    pivots = find_pivots(high, low, mode["pivot_len"])
    if len(pivots) < 3:
        return None

    a = pivots[-3]
    b = pivots[-2]
    c = pivots[-1]

    # ========== SHORT : High - Low - High ==========
    if a[2] == 1 and b[2] == -1 and c[2] == 1:
        ab = a[1] - b[1]
        if ab > 0 and current_atr > 0:
            retr = (c[1] - b[1]) / ab
            impulse_ok = ab >= mode["min_imp"] * current_atr
            retr_ok    = retr <= mode["max_retr"]
            vol_ok     = current_atr >= mode["vol_mult"] * atr_med

            if impulse_ok and retr_ok and vol_ok:
                entry = close[-1]
                sl    = c[1] + 0.25 * current_atr
                tp    = entry - mode["tp_mult"] * ab

                return {
                    "direction": "SHORT",
                    "mode": mode_name,
                    "symbol": mode["symbol"],
                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "tp": round(tp, 5),
                    "ab_size": round(ab, 5),
                    "atr": round(current_atr, 5)
                }

    # ========== LONG : Low - High - Low ==========
    if a[2] == -1 and b[2] == 1 and c[2] == -1:
        ab = b[1] - a[1]
        if ab > 0 and current_atr > 0:
            retr = (b[1] - c[1]) / ab
            impulse_ok = ab >= mode["min_imp"] * current_atr
            retr_ok    = retr <= mode["max_retr"]
            vol_ok     = current_atr >= mode["vol_mult"] * atr_med

            if impulse_ok and retr_ok and vol_ok:
                entry = close[-1]
                sl    = c[1] - 0.25 * current_atr
                tp    = entry + mode["tp_mult"] * ab

                return {
                    "direction": "LONG",
                    "mode": mode_name,
                    "symbol": mode["symbol"],
                    "entry": round(entry, 5),
                    "sl": round(sl, 5),
                    "tp": round(tp, 5),
                    "ab_size": round(ab, 5),
                    "atr": round(current_atr, 5)
                }

    return None
