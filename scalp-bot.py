"""
EMA9-EMA21 ATR Scalper — Live Auto-Trader for MetaTrader5

Description
-----------
Simple, single-symbol (XAUUSD by default) M1 scalper that:
- Computes EMA(9) and EMA(21) on 1-minute bars
- Detects pullback-to-EMA9 entries confirmed by a close in the trend direction
- Uses ATR(14) to set SL and TP automatically
- Places market orders on MetaTrader5 with SL/TP

Settings (editable at top of file)
- SYMBOL: symbol to trade (default: "XAUUSD")
- TIMEFRAME: timeframe constant from mt5 (default M1)
- LOT: fixed lot size
- ATR_PERIOD: ATR period (default 14)
- ATR_SL_MULTIPLIER: SL = ATR * this
- ATR_TP_MULTIPLIER: TP = ATR * this
- ATR_PULLBACK_MULT: the pullback depth required (e.g. 0.5 means prev_close - low >= 0.5*ATR)
- POLL_INTERVAL: seconds between checks

Important
---------
- Replace MT5_LOGIN, MT5_PASSWORD, MT5_SERVER with your credentials if you want the script to login by itself.
- Test thoroughly on a demo account before using live.
"""

import time
import logging

import pandas as pd
import ta
import MetaTrader5 as mt5

# ------------------------
# Configuration (EDIT THESE)
# ------------------------
MT5_LOGIN = 12345678          # replace with your account number (or leave as-is to try connecting to running MT5)
MT5_PASSWORD = "your_pass"   # replace with your password
MT5_SERVER = "YourBroker-Server"  # replace with your broker's server name

SYMBOL = "XAUUSD"            # symbol to trade (editable)
TIMEFRAME = mt5.TIMEFRAME_M1  # 1-minute timeframe
LOT = 0.1                     # fixed lot size

# ATR / SL / TP settings
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5
ATR_TP_MULTIPLIER = 2.0
ATR_PULLBACK_MULT = 0.5      # required pullback depth relative to ATR

# Strategy / runtime
EMA_FAST = 9
EMA_SLOW = 21
POLL_INTERVAL = 10           # seconds between checks
MAGIC = 123456               # magic number to identify EA orders (best-effort)
MAX_ORDERS = 1               # max simultaneous orders for the symbol

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# ------------------------
# MT5 connection helpers
# ------------------------

def init_mt5():
    # try to connect to a running MT5 terminal first
    if mt5.initialize():
        logging.info("Connected to running MT5 instance (initialize()). Will attempt to use current terminal session.")
        try:
            _ = mt5.account_info()
            logging.info("Account access OK (using running terminal session)")
            return True
        except Exception:
            logging.warning("Running MT5 found but account access failed — will try login using provided credentials")
            mt5.shutdown()

    # fallback: initialize then login
    if not mt5.initialize():
        logging.error(f"mt5.initialize() failed, error = {mt5.last_error()}")
        return False
    logged = mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if not logged:
        logging.error(f"mt5.login() failed, error = {mt5.last_error()}")
        return False
    logging.info(f"Connected to MT5 via login — account: {MT5_LOGIN}")
    return True


def shutdown_mt5():
    try:
        mt5.shutdown()
    except Exception:
        pass
    logging.info("MT5 shutdown")

# ------------------------
# Market data helper
# ------------------------

def fetch_ohlc(symbol, timeframe, n=500):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

# ------------------------
# Strategy logic
# ------------------------

def ema_atr_signals(df):
    df = df.copy()
    df['ema_fast'] = ta.trend.EMAIndicator(df['close'], window=EMA_FAST).ema_indicator()
    df['ema_slow'] = ta.trend.EMAIndicator(df['close'], window=EMA_SLOW).ema_indicator()
    df['atr'] = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'], window=ATR_PERIOD).average_true_range()

    # default columns
    df['signal'] = 0
    df['sl'] = pd.NA
    df['tp'] = pd.NA

    i = len(df) - 1
    if i < 2:
        return df

    ema9 = df['ema_fast'].iat[i]
    ema21 = df['ema_slow'].iat[i]
    atr = df['atr'].iat[i]
    last_close = df['close'].iat[i]
    prev_close = df['close'].iat[i-1]
    last_low = df['low'].iat[i]
    last_high = df['high'].iat[i]

    # BUY condition: uptrend, touch EMA9, pullback depth and confirm close above EMA9
    if ema9 > ema21:
        touched = last_low <= ema9
        pullback_ok = (prev_close - last_low) >= (ATR_PULLBACK_MULT * atr)
        confirmation = last_close > ema9
        if touched and pullback_ok and confirmation:
            entry = last_close
            sl = entry - ATR_SL_MULTIPLIER * atr
            tp = entry + ATR_TP_MULTIPLIER * atr
            df.at[df.index[i], 'signal'] = 1
            df.at[df.index[i], 'sl'] = sl
            df.at[df.index[i], 'tp'] = tp

    # SELL condition: downtrend, touch EMA9, pullback depth and confirm close below EMA9
    elif ema9 < ema21:
        touched = last_high >= ema9
        pullback_ok = (last_high - prev_close) >= (ATR_PULLBACK_MULT * atr)
        confirmation = last_close < ema9
        if touched and pullback_ok and confirmation:
            entry = last_close
            sl = entry + ATR_SL_MULTIPLIER * atr
            tp = entry - ATR_TP_MULTIPLIER * atr
            df.at[df.index[i], 'signal'] = -1
            df.at[df.index[i], 'sl'] = sl
            df.at[df.index[i], 'tp'] = tp

    return df

# ------------------------
# Trading helpers
# ------------------------

def get_open_positions(symbol, magic=MAGIC):
    try:
        positions = mt5.positions_get(symbol=symbol)
    except Exception:
        return []
    if positions is None:
        return []
    filtered = []
    for p in positions:
        try:
            if int(p.magic) == int(magic):
                filtered.append(p)
        except Exception:
            # broker might not provide magic — include all positions for symbol
            filtered.append(p)
    return filtered


def place_trade(symbol, signal, sl, tp, lot=LOT, deviation=20, magic=MAGIC):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logging.error(f"No tick for {symbol}")
        return None

    if signal == 1:
        price = float(tick.ask)
        order_type = mt5.ORDER_TYPE_BUY
    elif signal == -1:
        price = float(tick.bid)
        order_type = mt5.ORDER_TYPE_SELL
    else:
        return None

    # Build request
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": order_type,
        "price": price,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": deviation,
        "magic": int(magic),
        "comment": "EMA_ATR_Scalper",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        logging.error(f"order_send returned None: {mt5.last_error()}")
        return None
    # result contains retcode and order information
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logging.error(f"Order failed, retcode={result.retcode}, comment={result.comment}")
    else:
        logging.info(f"Order placed: ticket={getattr(result, 'order', 'N/A')}, type={'BUY' if signal==1 else 'SELL'}, volume={lot}, sl={sl}, tp={tp}")
    return result

# ------------------------
# Main loop
# ------------------------

def main_loop():
    if not init_mt5():
        logging.error("MT5 init/login failed — exiting")
        return

    # Ensure symbol exists in Market Watch
    sym = mt5.symbol_info(SYMBOL)
    if sym is None:
        logging.error(f"Symbol {SYMBOL} not found in MT5 market watch. Please add it and restart the script.")
        shutdown_mt5()
        return
    if not sym.visible:
        mt5.symbol_select(SYMBOL, True)
        logging.info(f"Selected {SYMBOL} in Market Watch")

    logging.info("Starting EMA9-EMA21 ATR Scalper main loop — CTRL+C to stop")

    try:
        while True:
            df = fetch_ohlc(SYMBOL, TIMEFRAME, n=500)
            if df is None:
                logging.warning("No data fetched — retrying")
                time.sleep(POLL_INTERVAL)
                continue

            df = ema_atr_signals(df)
            last = df.iloc[-1]

            if int(last['signal']) != 0:
                positions = get_open_positions(SYMBOL, MAGIC)
                if len(positions) >= MAX_ORDERS:
                    logging.info(f"Max positions reached for {SYMBOL} — skipping signal")
                else:
                    signal = int(last['signal'])
                    sl = float(last['sl'])
                    tp = float(last['tp'])
                    logging.info(f"Signal detected: {signal} — placing order with SL={sl} TP={tp}")
                    place_trade(SYMBOL, signal, sl, tp)
            else:
                logging.debug("No signal on last candle")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Interrupted by user — shutting down")
    except Exception as e:
        logging.exception(f"Unexpected error in main loop: {e}")
    finally:
        shutdown_mt5()


if __name__ == '__main__':
    main_loop()
