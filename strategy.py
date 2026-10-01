import numpy as np

# Exact parameters from your Pine Script
MODES = {
    "GBPUSD_M15_5": {
        "symbol": "GBPUSD",
        "pivot_len": 5,
        "min_imp": 1.00,
        "max_retr": 0.90,
        "vol_mult": 1.0,
        "use_session": False,
        "tp_mult": 0.55
    },
    "USDJPY_M15_7": {
        "symbol": "USDJPY",
        "pivot_len": 7,
        "min_imp": 1.00,
        "max_retr": 0.90,
        "vol_mult": 1.0,
        "use_session": False,
        "tp_mult": 0.55
    }
}

def calculate_atr(high, low, close, period=14):
    tr = np.maximum(high[1:] - low[1:], 
                    np.maximum(abs(high[1:] - close[:-1]), 
                               abs(low[1:] - close[:-1])))
    atr = np.convolve(tr, np.ones(period)/period, mode='valid')
    return atr

def find_pivots(high, low, pivot_len):
    """Simplified alternating pivots"""
    pivots = []  # list of (index, price, type)  type: 1=high, -1=low
    for i in range(pivot_len, len(high) - pivot_len):
        is_high = all(high[i] >= high[i-j] for j in range(1, pivot_len+1)) and \
                  all(high[i] >= high[i+j] for j in range(1, pivot_len+1))
        is_low  = all(low[i]  <= low[i-j]  for j in range(1, pivot_len+1)) and \
                  all(low[i]  <= low[i+j]  for j in range(1, pivot_len+1))
        
        if is_high:
            if not pivots or pivots[-1][2] != 1:
                pivots.append((i, high[i], 1))
            elif high[i] > pivots[-1][1]:
                pivots[-1] = (i, high[i], 1)
        if is_low:
            if not pivots or pivots[-1][2] != -1:
                pivots.append((i, low[i], -1))
            elif low[i] < pivots[-1][1]:
                pivots[-1] = (i, low[i], -1)
    return pivots

def check_signal(ohlc, mode_name):
    """
    ohlc = dict with keys: high, low, close, open (numpy arrays or lists)
    Returns: None or signal dict
    """
    mode = MODES[mode_name]
    high = np.array(ohlc["high"])
    low  = np.array(ohlc["low"])
    close = np.array(ohlc["close"])
    
    if len(close) < 100:
        return None
    
    atr = calculate_atr(high, low, close)
    if len(atr) == 0:
        return None
    current_atr = atr[-1]
    atr_med = np.mean(atr[-40:]) if len(atr) >= 40 else current_atr
    
    pivots = find_pivots(high, low, mode["pivot_len"])
    
    if len(pivots) < 3:
        return None
    
    a = pivots[-3]
    b = pivots[-2]
    c = pivots[-1]
    
    # SHORT: High - Low - High
    if a[2] == 1 and b[2] == -1 and c[2] == 1:
        ab = a[1] - b[1]
        if ab > 0 and current_atr > 0:
            retr = (c[1] - b[1]) / ab
            impulse_ok = ab >= mode["min_imp"] * current_atr
            retr_ok = retr <= mode["max_retr"]
            vol_ok = current_atr >= mode["vol_mult"] * atr_med
            
            if impulse_ok and retr_ok and vol_ok:
                # Simple break of BC for now
                return {
                    "direction": "SHORT",
                    "mode": mode_name,
                    "entry": close[-1],
                    "sl": c[1] + 0.25 * current_atr,
                    "tp": close[-1] - mode["tp_mult"] * ab,
                    "ab_size": ab
                }
    
    # LONG: Low - High - Low
    if a[2] == -1 and b[2] == 1 and c[2] == -1:
        ab = b[1] - a[1]
        if ab > 0 and current_atr > 0:
            retr = (b[1] - c[1]) / ab
            impulse_ok = ab >= mode["min_imp"] * current_atr
            retr_ok = retr <= mode["max_retr"]
            vol_ok = current_atr >= mode["vol_mult"] * atr_med
            
            if impulse_ok and retr_ok and vol_ok:
                return {
                    "direction": "LONG",
                    "mode": mode_name,
                    "entry": close[-1],
                    "sl": c[1] - 0.25 * current_atr,
                    "tp": close[-1] + mode["tp_mult"] * ab,
                    "ab_size": ab
                }
    
    return None