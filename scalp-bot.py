
"""
EMA9-EMA21 Cross + Wait-for-Pullback Scalper with M5 Filter, BreakEven Option, and Dollar Risk Lot Sizing.
--------------------------------------------------------------------
Logic:
  1. Detect EMA9/EMA21 cross (M1 or M2 timeframe).
  2. Mark cross as pending (no immediate entry).
  3. Wait until first candle touches EMA9 again and closes in cross direction → then enter.
  4. Apply higher-timeframe (M5) EMA trend filter with adjustable parameters.
  5. Manage position with ATR-based SL/TP, optional BreakEven, and risk-based lot sizing.
"""

import time
import logging
import pandas as pd
import MetaTrader5 as mt5
import ta
import math

# ---------------- CONFIG ----------------

MT5_LOGIN = 12345678
MT5_PASSWORD = "your_pass"
MT5_SERVER = "YourBroker-Server"

SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
M5_TIMEFRAME = mt5.TIMEFRAME_M5

ENABLE_M5_FILTER = False
M5_EMA_FAST = 9
M5_EMA_SLOW = 21

ENABLE_BREAK_EVEN = True

ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5
ATR_TP_MULTIPLIER = 3.0
ATR_BREAK_EVEN_TRIGGER = 1.0

EMA_FAST = 3
EMA_SLOW = 5

RISK_AMOUNT_USD = 20   # per trade risk

POLL_INTERVAL = 1
MAGIC = 123999
MAX_ORDERS = 1

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# ---------------- HELPERS ----------------

def init_mt5():
    if mt5.initialize():
        try:
            _ = mt5.account_info()
            return True
        except Exception:
            mt5.shutdown()
    if not mt5.initialize():
        return False
    return mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)

def shutdown_mt5():
    try:
        mt5.shutdown()
    except Exception:
        pass

def fetch_ohlc(symbol, timeframe, n=500):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def fetch_ohlc_m5(symbol, n=200):
    return fetch_ohlc(symbol, M5_TIMEFRAME, n)

def calculate_lot(symbol, sl_distance, risk_amount_usd=RISK_AMOUNT_USD):
    info = mt5.symbol_info(symbol)
    if not info:
        return 0.1

    contract_size = info.trade_contract_size or 100.0  # برای گلد = 100
    vol_min  = info.volume_min or 0.01
    vol_max  = info.volume_max or 100.0
    vol_step = info.volume_step or 0.01

    # ریسک واقعی برای هر لات (StopDistance * contract_size)
    risk_per_lot = abs(sl_distance) * contract_size

    if risk_per_lot <= 0:
        logging.warning(f"[LotCalc] Invalid sl_distance={sl_distance}, fallback {vol_min}")
        return vol_min

    lot = risk_amount_usd / risk_per_lot

    # محدودسازی و گرد کردن به استپ بروکر
    lot = max(vol_min, min(lot, vol_max))
    lot = round(lot / vol_step) * vol_step
    lot = max(vol_min, min(lot, vol_max))

    logging.info(
        f"[LotCalc] Risk=${risk_amount_usd:.2f}, SL={sl_distance:.2f}, "
        f"Contract={contract_size}, risk/lot={risk_per_lot:.2f}, lot={lot:.3f}"
    )
    return lot



# ---------------- STRATEGY ----------------

def ema_signals(df, df_m5=None):
    df = df.copy()
    df['ema9'] = ta.trend.EMAIndicator(df['close'], window=EMA_FAST).ema_indicator()
    df['ema21'] = ta.trend.EMAIndicator(df['close'], window=EMA_SLOW).ema_indicator()
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=ATR_PERIOD).average_true_range()

    if df_m5 is not None and ENABLE_M5_FILTER:
        df_m5['ema9'] = ta.trend.EMAIndicator(df_m5['close'], window=M5_EMA_FAST).ema_indicator()
        df_m5['ema21'] = ta.trend.EMAIndicator(df_m5['close'], window=M5_EMA_SLOW).ema_indicator()
        trend_up = df_m5['ema9'].iat[-1] > df_m5['ema21'].iat[-1]
        trend_down = df_m5['ema9'].iat[-1] < df_m5['ema21'].iat[-1]
    else:
        trend_up = trend_down = True

    df['signal'] = 0
    df['sl'] = pd.NA
    df['tp'] = pd.NA

    # --- track cross state ---
    static = getattr(ema_signals, 'cross_pending', {'up': False, 'down': False})

    i = len(df) - 1
    ema9_now = df['ema9'].iat[i]
    ema21_now = df['ema21'].iat[i]
    ema9_prev = df['ema9'].iat[i - 1]
    ema21_prev = df['ema21'].iat[i - 1]
    atr = df['atr'].iat[i]

    # Detect cross
    cross_up = ema9_prev < ema21_prev and ema9_now > ema21_now
    cross_down = ema9_prev > ema21_prev and ema9_now < ema21_now

    if cross_up:
        static['up'] = True
        static['down'] = False
    elif cross_down:
        static['down'] = True
        static['up'] = False

    close_now = df['close'].iat[i]
    low_now = df['low'].iat[i]
    high_now = df['high'].iat[i]

    # If pending BUY cross and touch ema9 later
    if static['up'] and trend_up:
        if low_now <= ema9_now and close_now > ema9_now and close_now > ema21_now:
            entry = close_now
            sl = entry - ATR_SL_MULTIPLIER * atr
            tp = entry + ATR_TP_MULTIPLIER * atr
            df.at[df.index[i], 'signal'] = 1
            df.at[df.index[i], 'sl'] = sl
            df.at[df.index[i], 'tp'] = tp
            static['up'] = False

    # If pending SELL cross and touch back ema9 later
    if static['down'] and trend_down:
        if high_now >= ema9_now and close_now < ema9_now and close_now < ema21_now:
            entry = close_now
            sl = entry + ATR_SL_MULTIPLIER * atr
            tp = entry - ATR_TP_MULTIPLIER * atr
            df.at[df.index[i], 'signal'] = -1
            df.at[df.index[i], 'sl'] = sl
            df.at[df.index[i], 'tp'] = tp
            static['down'] = False

    ema_signals.cross_pending = static
    return df

# ---------------- TRADE HELPERS ----------------

def get_open_positions(symbol, magic=MAGIC):
    try:
        positions = mt5.positions_get(symbol=symbol)
    except Exception:
        return []
    if positions is None:
        return []
    result = []
    for p in positions:
        if int(getattr(p, 'magic', -1)) == int(magic):
            result.append(p)
    return result


def place_trade(symbol, signal, sl, tp, lot, magic=MAGIC):
    info = mt5.symbol_info(symbol)
    if not info:
        logging.error(f"Symbol info unavailable for {symbol}")
        return None

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        logging.error(f"No tick data for {symbol}")
        return None

    point = info.point if info.point>0 else 0.01
    digits = info.digits if info.digits>0 else 3
    min_gap = max((info.trade_stops_level or 0)*point, 5*point)

    if signal == 1:
        order_type = mt5.ORDER_TYPE_BUY
        price = float(tick.ask)
        if sl >= price:
            sl = round(price - (ATR_SL_MULTIPLIER * min_gap), digits)
        if tp <= price:
            tp = round(price + (ATR_TP_MULTIPLIER * min_gap), digits)
    elif signal == -1:
        order_type = mt5.ORDER_TYPE_SELL
        price = float(tick.bid)
        if sl <= price:
            sl = round(price + (ATR_SL_MULTIPLIER * min_gap), digits)
        if tp >= price:
            tp = round(price - (ATR_TP_MULTIPLIER * min_gap), digits)
    else:
        logging.warning("Invalid signal passed to place_trade")
        return None

    sl, tp, price = round(sl, digits), round(tp, digits), round(price, digits)

    request = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': lot,
        'type': order_type,
        'price': price,
        'sl': sl,
        'tp': tp,
        'deviation': 20,
        'magic': magic,
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
        'comment': 'EMA_Cross_Retest_RiskBased'
    }

    result = mt5.order_send(request)
    if result is None:
        logging.error(f"order_send returned None: {mt5.last_error()}")
    elif result.retcode != mt5.TRADE_RETCODE_DONE:
        logging.error(f"Order failed retcode={result.retcode} comment={result.comment}")
    else:
        logging.info(f"Order placed OK: type={'BUY' if signal==1 else 'SELL'} lot={lot} sl={sl} tp={tp}")
    return result


def check_and_move_breakeven(symbol, magic=MAGIC):
    if not ENABLE_BREAK_EVEN:
        return
    positions = get_open_positions(symbol, magic)
    if not positions:
        return
    df = fetch_ohlc(symbol, TIMEFRAME, 100)
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=ATR_PERIOD).average_true_range()
    atr = df['atr'].iat[-1]
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return
    for pos in positions:
        ticket = pos.ticket
        pos_type = pos.type
        price_open = pos.price_open
        sl = pos.sl
        tp = pos.tp
        if pos_type == mt5.ORDER_TYPE_BUY:
            current = tick.bid
            profit_move = current - price_open
            if profit_move >= atr * ATR_BREAK_EVEN_TRIGGER and sl < price_open:
                new_sl = price_open
            else:
                continue
        else:
            current = tick.ask
            profit_move = price_open - current
            if profit_move >= atr * ATR_BREAK_EVEN_TRIGGER and sl > price_open:
                new_sl = price_open
            else:
                continue
        req = {
            'action': mt5.TRADE_ACTION_SLTP,
            'symbol': symbol,
            'position': ticket,
            'sl': new_sl,
            'tp': tp,
        }
        mt5.order_send(req)

# ---------------- MAIN LOOP ----------------

def main_loop():
    if not init_mt5():
        logging.error('MT5 init failed.')
        return
    sym = mt5.symbol_info(SYMBOL)
    if sym is None or not sym.visible:
        mt5.symbol_select(SYMBOL, True)
    logging.info('Start Cross+Pullback Scalper with Wait-for-Pullback Mode')

    while True:
        df = fetch_ohlc(SYMBOL, TIMEFRAME, 500)
        if df is None or len(df) < 50:
            time.sleep(POLL_INTERVAL)
            continue
        df_m5 = fetch_ohlc_m5(SYMBOL, 300)

        df = ema_signals(df, df_m5)
        last = df.iloc[-1]
        signal = last['signal']

        # Break-even management
        try:
            check_and_move_breakeven(SYMBOL)
        except Exception as e:
            logging.warning(f"BE check error: {e}")

        if signal == 0:
            time.sleep(POLL_INTERVAL)
            continue

        if len(get_open_positions(SYMBOL)) >= MAX_ORDERS:
            time.sleep(POLL_INTERVAL)
            continue

        sl, tp = float(last['sl']), float(last['tp'])
        sl_distance = abs(last['close'] - sl)
        lot = calculate_lot(SYMBOL, sl_distance)

        res = place_trade(SYMBOL, signal, sl, tp, lot)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logging.info(f"Trade opened ({'BUY' if signal==1 else 'SELL'}) lot={lot:.3f}")
        else:
            logging.warning(f"Trade failed: {res.retcode if res else 'None'}")

        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    try:
        main_loop()
    except KeyboardInterrupt:
        shutdown_mt5()
        logging.info('Stopped by user')
