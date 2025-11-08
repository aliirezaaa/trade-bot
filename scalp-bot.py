import time, logging, pandas as pd, MetaTrader5 as mt5, ta, numpy as np

# ---------------- CONFIG ----------------
MT5_LOGIN, MT5_PASSWORD, MT5_SERVER = 12345678, 'your_pass', 'YourBroker-Server'
SYMBOL = 'XAUUSD'
TIMEFRAME = mt5.TIMEFRAME_M1
ENABLE_BREAK_EVEN = True

ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5
ATR_TP_MULTIPLIER = 3.0
ATR_BREAK_EVEN_TRIGGER = 1.0

LOOKBACK = 2
MIN_PULLBACK_WAIT = 1
MAX_PULLBACK_WAIT = 6

PULLBACK_DEPTH = 2        # ATR multiples for depth check
RISK_AMOUNT_USD = 20
MAGIC = 123999
MAX_ORDERS = 1
POLL_INTERVAL = 1

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# ---------------- MT5 CONNECTION ----------------
def init_mt5():
    if mt5.initialize():
        try:
            _ = mt5.account_info()
            return True
        except:
            mt5.shutdown()
    if not mt5.initialize():
        return False
    return mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)

def shutdown_mt5():
    try:
        mt5.shutdown()
    except:
        pass

# ---------------- DATA ----------------
def fetch_ohlc(symbol, timeframe, n=500):
    """
    کندل‌های در حال شکل‌گیری را نادیده می‌گیرد و فقط کندل‌های بسته‌شده را برمی‌گرداند.
    """
    # pos=1 شروع می‌کند تا آخرین کندل (pos=0) که هنوز کامل نشده خوانده نشود
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, n)
    if rates is None or len(rates) == 0:
        logging.warning(f"No data for {symbol}")
        return None
    df = pd.DataFrame(rates, dtype=float)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df[['open','high','low','close']].astype(float)

# ---------------- LOT CALCULATOR ----------------
def calculate_lot(symbol, sl_distance, risk_amount_usd=RISK_AMOUNT_USD):
    info = mt5.symbol_info(symbol)
    if not info:
        return 0.1
    contract_size = info.trade_contract_size or 100.0
    vol_min  = info.volume_min or 0.01
    vol_max  = info.volume_max or 100.0
    vol_step = info.volume_step or 0.01

    risk_per_lot = abs(sl_distance) * contract_size
    if risk_per_lot <= 0:
        return vol_min

    lot = risk_amount_usd / risk_per_lot
    lot = max(vol_min, min(lot, vol_max))
    lot = round(lot / vol_step) * vol_step
    return lot

# ---------------- STRUCTURE LOGIC ----------------
def detect_new_choch(df, lookback=2):
    """Close-Validated CHoCH detector"""
    if len(df) < lookback * 3:
        return getattr(detect_new_choch, 'last_lvl', None), None

    highs = [i for i in range(lookback, len(df)-lookback)
             if df['high'].iat[i] == df['high'].iloc[i-lookback:i+lookback+1].max()]
    lows = [i for i in range(lookback, len(df)-lookback)
            if df['low'].iat[i]  == df['low'].iloc[i-lookback:i+lookback+1].min()]
    if not highs or not lows:
        return getattr(detect_new_choch, 'last_lvl', None), None

    last_high, last_low = df['high'].iat[highs[-1]], df['low'].iat[lows[-1]]
    prev_close, last_close = df['close'].iat[-2], df['close'].iat[-1]
    lvl = getattr(detect_new_choch, 'last_lvl', None)
    new_pending = None

    # --- bullish ---
    if prev_close <= last_high and last_close > last_high:
        if lvl is None or abs(lvl - last_high) > 1e-8:
            lvl = last_high
            new_pending = {'dir': 1, 'level': lvl, 'candles_ago': 0}
            logging.info(f"[CHoCH] 🟩 Bullish Break(Close) @ {df.index[-1]} lvl={lvl:.3f}")

    # --- bearish ---
    elif prev_close >= last_low and last_close < last_low:
        if lvl is None or abs(lvl - last_low) > 1e-8:
            lvl = last_low
            new_pending = {'dir': -1, 'level': lvl, 'candles_ago': 0}
            logging.info(f"[CHoCH] 🔻 Bearish Break(Close) @ {df.index[-1]} lvl={lvl:.3f}")

    detect_new_choch.last_lvl = lvl
    return lvl, new_pending


    

def commit_state(pending):
    detect_structure.pending = pending

# --- 1) به‌روزرسانی update_pending_state ---
def update_pending_state(df, pending):
    """
    ورودی: 
      df      : دیتافریم با ستون high, low, close و atr
      pending : دیکشنری یا None
    خروجی:
      pending2 : Pending به‌روز‌شده یا None
      signal   :  1=Long Entry, -1=Short Entry, 0=None
    """
    if not pending:
        return None, 0

    # ۱) افزایش تعداد کندل‌های گذشته
    pending['candles_ago'] += 1
    age, dir_, lvl = pending['candles_ago'], pending['dir'], pending['level']

    # ۲) ATR را فرض می‌کنیم قبلاً در df محاسبه شده
    atr = df['atr'].iat[-1] if df['atr'].iat[-1] > 0 else 1.0

    # ۳) فقط پس از رسیدن به حداقل کندل انتظار، Entry را بررسی کن
    if age >= MIN_PULLBACK_WAIT:
        # Bullish Touch-Entry
        if dir_ == 1:
            prev_high = df['high'].iat[-2]
            curr_low  = df['low'].iat[-1]
            if prev_high > lvl and curr_low <= lvl:
                depth_ok = (prev_high - curr_low) >= (PULLBACK_DEPTH * atr)
                if depth_ok:
                    logging.info(f"[ENTRY] 🟢 Bullish TouchEntry @{df.index[-1]}")
                    # پس از ورود، Pending منقضی می‌شود و سیگنال = 1
                    return None, 1

        # Bearish Touch-Entry
        elif dir_ == -1:
            prev_low  = df['low'].iat[-2]
            curr_high = df['high'].iat[-1]
            if prev_low < lvl and curr_high >= lvl:
                depth_ok = (curr_high - prev_low) >= (PULLBACK_DEPTH * atr)
                if depth_ok:
                    logging.info(f"[ENTRY] 🔴 Bearish TouchEntry @{df.index[-1]}")
                    return None, -1

    # ۴) اگر بیش از حداکثر انتظار گذشت، Pending را پاک کن
    if age > MAX_PULLBACK_WAIT:
        logging.info(f"[STATE] Pending expired age={age} lvl={lvl:.3f}")
        return None, 0

    # هنوز پولبک کامل نشده، هیچ سیگنالی نداریم
    return pending, 0


# --- 2) به‌روزرسانی detect_structure ---
def detect_structure(df, lookback=2):
    # ستون‌های اولیه
    df['signal'] = 0
    df['sl']     = np.nan
    df['tp']     = np.nan

    # محاسبه ATR اگر لازم باشد
    if 'atr' not in df:
        df['atr'] = ta.volatility.AverageTrueRange(
            df['high'], df['low'], df['close'],
            window=ATR_PERIOD
        ).average_true_range()

    # ۱) به‌روزرسانی Pending فعلی و تولید سیگنال (در صورت Touch-Entry)
    old_pending = getattr(detect_structure, 'pending', None)
    pending, entry_signal = update_pending_state(df, old_pending)

    # ۲) اگر سیگنال ورود صادر شد، آن را در df بنویس
    if entry_signal != 0:
        df.at[df.index[-1], 'signal'] = entry_signal
        sl, tp = compute_sl_tp(
            df['high'].tolist(),
            df['low'].tolist(),
            df['close'].tolist(),
            entry_signal,
            atr=df['atr'].iat[-1]
        )
        df.at[df.index[-1], 'sl'] = sl
        df.at[df.index[-1], 'tp'] = tp
        # پس از ورود، Pending منقضی می‌شود
        pending = None

    # ۳) نگهداری pending تازه (ممکن است None یا همان pending به‌روزشده باشد)
    detect_structure.pending = pending

    # ۴) حالا فقط وقتی هیچ pending فعالی نداریم، شکست جدید را بگیریم
    #    تا بیش از MAX_PULLBACK_WAIT صبر کنیم و pending روی هم نریزد
    if detect_structure.pending is None:
        lvl, new_pending = detect_new_choch(df, lookback)
        if new_pending:
            logging.info(f"[STATE] New pending set after CHoCH, dir={new_pending['dir']}, lvl={new_pending['level']:.3f}")
            detect_structure.pending = new_pending

    return df


# ---------------- ATR-BASED SL/TP ----------------
def compute_sl_tp(highs, lows, closes, signal, atr=1.0,
                  sl_mult=ATR_SL_MULTIPLIER, tp_mult=ATR_TP_MULTIPLIER):
    if not highs or not lows or not closes or signal == 0:
        return None, None
    price = closes[-1]
    if atr <= 0:
        atr = abs(highs[-1] - lows[-1])
    if signal == 1:
        sl, tp = price - sl_mult * atr, price + tp_mult * atr
    else:
        sl, tp = price + sl_mult * atr, price - tp_mult * atr
    return round(sl, 3), round(tp, 3)

# ---------------- TRADE + BE ----------------
def get_open_positions(symbol, magic=MAGIC):
    try:
        positions = mt5.positions_get(symbol=symbol)
    except:
        return []
    if positions is None:
        return []
    return [p for p in positions if int(getattr(p, 'magic', -1)) == int(magic)]

def place_trade(symbol, signal, sl, tp, lot, magic=MAGIC):
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return None
    price = float(tick.ask) if signal == 1 else float(tick.bid)
    order_type = mt5.ORDER_TYPE_BUY if signal == 1 else mt5.ORDER_TYPE_SELL
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': float(lot),
        'type': order_type,
        'price': price,
        'sl': float(sl),
        'tp': float(tp),
        'deviation': 20,
        'magic': magic,
        'comment': 'CHoCH_Scalper',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"Order OK: {'BUY' if signal==1 else 'SELL'} lot={lot}")
    else:
        logging.warning(f"Order failed: {getattr(res,'retcode',None)}")
    return res

def check_and_move_breakeven(symbol, magic=MAGIC):
    if not ENABLE_BREAK_EVEN:
        return
    poss = get_open_positions(symbol, magic)
    if not poss:
        return
    df = fetch_ohlc(symbol, TIMEFRAME, 100)
    if df is None:
        return
    df['atr'] = ta.volatility.AverageTrueRange(
        df['high'], df['low'], df['close'],
        window=ATR_PERIOD
    ).average_true_range()
    atr = df['atr'].iat[-1]
    tick = mt5.symbol_info_tick(symbol)
    for p in poss:
        po = float(p.price_open)
        sl = float(p.sl)
        tp = float(p.tp)
        cur = float(tick.bid if p.type == 0 else tick.ask)
        move = (cur - po) if p.type == 0 else (po - cur)
        if move >= atr * ATR_BREAK_EVEN_TRIGGER and (
           (sl < po and p.type == 0) or (sl > po and p.type == 1)
        ):
            req = {
                'action': mt5.TRADE_ACTION_SLTP,
                'symbol': symbol,
                'position': p.ticket,
                'sl': po,
                'tp': tp
            }
            mt5.order_send(req)
            logging.info(f"[BE] SL moved to BE for {p.ticket}")

# ---------------- MAIN LOOP ----------------
def main_loop():
    if not init_mt5():
        logging.error("MT5 init failed.")
        return
    sym = mt5.symbol_info(SYMBOL)
    if sym is None or not sym.visible:
        mt5.symbol_select(SYMBOL, True)
    logging.info("🚀 Start Structure-Based CHoCH-Pullback Scalper")

    while True:
        df = fetch_ohlc(SYMBOL, TIMEFRAME, 500)
        if df is None or len(df) < 50:
            time.sleep(POLL_INTERVAL)
            continue

        df = detect_structure(df)
        last = df.iloc[-1]

        try:
            check_and_move_breakeven(SYMBOL)
        except Exception as e:
            logging.warning(f"[BE] {e}")

        if int(last['signal']) == 0:
            time.sleep(POLL_INTERVAL)
            continue

        if len(get_open_positions(SYMBOL)) >= MAX_ORDERS:
            time.sleep(POLL_INTERVAL)
            continue

        highs, lows, closes = df['high'].tolist(), df['low'].tolist(), df['close'].tolist()
        sl, tp = compute_sl_tp(highs, lows, closes, int(last['signal']))
        if sl is None or tp is None:
            time.sleep(POLL_INTERVAL)
            continue

        lot = calculate_lot(SYMBOL, abs(closes[-1] - sl))
        place_trade(SYMBOL, int(last['signal']), sl, tp, lot)

        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    try:
        main_loop()
    except KeyboardInterrupt:
        shutdown_mt5()
        logging.info("Stopped by user")
