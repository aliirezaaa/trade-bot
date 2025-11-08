import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from enum import Enum
import logging
import getpass

# ==============================================================================
# 1. تنظیمات و پیکربندی ربات (Configuration)
# ==============================================================================
# --- تنظیمات اصلی معامله ---
SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_M5
RISK_PER_TRADE_USD = 10.00  # میزان ریسک به دلار برای هر ستاپ معاملاتی
TRADE_COMMENT = "CHoCH_Scalper_v2"

# --- پارامترهای استراتژی ---
# پارامترهای ZigZag برای تشخیص ساختار
ZIGZAG_DEPTH = 12
ZIGZAG_DEVIATION = 5
ZIGZAG_BACKSTEP = 3

# پارامترهای ورود پلکانی (Scale-in)
NUM_SCALE_IN_ORDERS = 3       # تعداد سفارشات لیمیت برای ورود
SCALE_IN_ZONE_ATR_MULTIPLIER = 0.5 # ضریب ATR برای تعیین محدوده ورود (فاصله بین اولین و آخرین پله)

# پارامتر ابطال ستاپ در صورت پولبک عمیق
PULLBACK_DEPTH_ATR_MULTIPLIER = 1.5 # اگر قیمت بیش از این مقدار (ضربدر ATR) از سطح سیگنال نفوذ کند، ستاپ باطل است

# --- تنظیمات فنی ---
MAX_CANDLES = 500  # حداکثر تعداد کندل برای نگهداری در حافظه
LOG_LEVEL = logging.INFO
LOG_FILE = "choch_bot_v2.log"

# ==============================================================================
# 2. راه‌اندازی و وضعیت‌های ربات (Setup & State Machine)
# ==============================================================================
# --- راه‌اندازی لاگین ---
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# --- تعریف ماشین حالت ---
class State(Enum):
    SEARCHING = 1    # در جستجوی ستاپ معاملاتی جدید
    SCALING_IN = 2   # سفارشات لیمیت کاشته شده و منتظر فعال شدن هستند

# --- متغیرهای گلوبال برای نگهداری وضعیت ---
state = State.SEARCHING
df = pd.DataFrame()
active_setup = {}  # برای نگهداری اطلاعات ستاپ فعال (magic_number, sl, tickets, ...)
mt5_connection = None

# ==============================================================================
# 3. توابع کمکی و اصلی (Core & Helper Functions)
# ==============================================================================

def connect_to_mt5():
    """
    ابتدا سعی می‌کند به ترمینال باز متاتریدر متصل شود.
    در صورت عدم موفقیت، اطلاعات ورود را از کاربر درخواست می‌کند.
    """
    global mt5_connection
    logging.info("در حال تلاش برای اتصال به ترمینال متاتریدر 5...")
    if mt5.initialize():
        logging.info("اتصال به ترمینال متاتریدر با موفقیت برقرار شد.")
        mt5_connection = mt5
        return True
    else:
        logging.warning("اتصال به ترمینال باز ناموفق بود. لطفاً اطلاعات حساب را وارد کنید.")
        try:
            login = int(input("شماره حساب (Login): "))
            password = getpass.getpass("رمز عبور (Password): ")
            server = input("نام سرور (Server): ")
            if mt5.initialize(login=login, password=password, server=server):
                logging.info(f"اتصال به حساب {login} در سرور {server} با موفقیت برقرار شد.")
                mt5_connection = mt5
                return True
            else:
                logging.error(f"اتصال ناموفق بود. کد خطا: {mt5.last_error()}")
                return False
        except ValueError:
            logging.error("شماره حساب باید یک عدد صحیح باشد.")
            return False
        except Exception as e:
            logging.error(f"خطای غیرمنتظره در هنگام اتصال: {e}")
            return False

def _calculate_zigzag(data, depth=12, deviation=5, backstep=3):
    """
    یک پیاده‌سازی ساده از اندیکاتور ZigZag در پایتون.
    این تابع یک سری Pandas حاوی نقاط پیوت (سقف یا کف) را برمی‌گرداند.
    """
    highs = data['high']
    lows = data['low']
    points = pd.Series(index=data.index, dtype=float)

    last_pivot_price = 0
    last_pivot_idx = -1
    trend = 0  # 1 for up, -1 for down

    for i in range(depth, len(data)):
        # Find highest high and lowest low in the lookback period
        period_high = highs.iloc[i-depth:i+1].max()
        period_low = lows.iloc[i-depth:i+1].min()

        if trend == 0:
            if highs.iloc[i] == period_high:
                trend = -1 # Potential high found, look for a low now
                last_pivot_price = highs.iloc[i]
                last_pivot_idx = i
                points.iloc[i] = last_pivot_price
            elif lows.iloc[i] == period_low:
                trend = 1 # Potential low found, look for a high now
                last_pivot_price = lows.iloc[i]
                last_pivot_idx = i
                points.iloc[i] = last_pivot_price
        elif trend == 1: # Looking for a high
            if highs.iloc[i] >= last_pivot_price:
                # New high in current uptrend, update pivot
                points.iloc[last_pivot_idx] = np.nan
                last_pivot_price = highs.iloc[i]
                last_pivot_idx = i
                points.iloc[i] = last_pivot_price
            elif lows.iloc[i] < last_pivot_price * (1 - deviation / 100) and (i - last_pivot_idx) >= backstep:
                # Significant reversal down, confirm the last high and start looking for a low
                trend = -1
                last_pivot_price = lows.iloc[i]
                last_pivot_idx = i
                points.iloc[i] = last_pivot_price
        elif trend == -1: # Looking for a low
            if lows.iloc[i] <= last_pivot_price:
                # New low in current downtrend, update pivot
                points.iloc[last_pivot_idx] = np.nan
                last_pivot_price = lows.iloc[i]
                last_pivot_idx = i
                points.iloc[i] = last_pivot_price
            elif highs.iloc[i] > last_pivot_price * (1 + deviation / 100) and (i - last_pivot_idx) >= backstep:
                # Significant reversal up, confirm the last low and start looking for a high
                trend = 1
                last_pivot_price = highs.iloc[i]
                last_pivot_idx = i
                points.iloc[i] = last_pivot_price

    return points


def update_dataframe():
    """
    دیتافریم را با استفاده از روش پنجره لغزان (Sliding Window) به‌روز می‌کند.
    فقط کندل‌های جدید را درخواست و اندیکاتورها را مجدد محاسبه می‌کند.
    """
    global df
    try:
        if df.empty:
            # اولین اجرا: دریافت داده‌های اولیه
            rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, MAX_CANDLES)
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.set_index('time', inplace=True)
            logging.info(f"دیتافریم اولیه با {len(df)} کندل ایجاد شد.")
        else:
            # اجراهای بعدی: دریافت فقط کندل‌های جدید
            last_time = df.index[-1].timestamp()
            rates = mt5.copy_rates_from(SYMBOL, TIMEFRAME, int(last_time), 100) # 100 کندل برای اطمینان
            if rates is None or len(rates) == 0:
                return False # هیچ کندل جدیدی وجود ندارد

            new_df = pd.DataFrame(rates)
            new_df['time'] = pd.to_datetime(new_df['time'], unit='s')
            new_df.set_index('time', inplace=True)
            
            # حذف کندل‌های تکراری و قدیمی
            new_df = new_df[~new_df.index.isin(df.index)]
            if new_df.empty:
                return False # کندل‌ها تکراری بودند

            df = pd.concat([df, new_df])
            if len(df) > MAX_CANDLES:
                df = df.iloc[-MAX_CANDLES:] # حفظ اندازه دیتافریم
        
        # محاسبه اندیکاتورها
        df['atr'] = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        df['zigzag'] = _calculate_zigzag(df, ZIGZAG_DEPTH, ZIGZAG_DEVIATION, ZIGZAG_BACKSTEP)
        
        return True # دیتافریم به‌روز شد
    except Exception as e:
        logging.error(f"خطا در به‌روزرسانی دیتافریم: {e}")
        return False

def detect_significant_structure(data):
    """
    با استفاده از ZigZag، آخرین ساختار بازار و سیگنال CHoCH را تشخیص می‌دهد.
    """
    pivots = data['zigzag'].dropna()
    if len(pivots) < 4:
        return None # ساختار کافی برای تحلیل وجود ندارد

    # آخرین 4 پیوت را جدا کن
    last_pivots = pivots.tail(4)
    
    # شناسایی سقف و کف‌ها
    highs = last_pivots[last_pivots > data['open'][last_pivots.index]]
    lows = last_pivots[last_pivots < data['open'][last_pivots.index]]

    if len(highs) < 2 or len(lows) < 2:
        return None

    last_high = highs.index[-1]
    prev_high = highs.index[-2]
    last_low = lows.index[-1]
    prev_low = lows.index[-2]
    
    # آخرین کندل
    latest_close = data['close'].iloc[-1]

    # --- تشخیص روند و CHoCH ---
    # روند نزولی (Lower Highs, Lower Lows)
    if highs[last_high] < highs[prev_high] and lows[last_low] < lows[prev_low]:
        # به دنبال CHoCH صعودی (شکست آخرین سقف معتبر)
        if latest_close > highs[last_high]:
            return {
                "type": "BULLISH_CHOCH",
                "signal_price": highs[last_high],
                "sl_price": lows[last_low],
                "invalidation_point": lows[last_low]
            }

    # روند صعودی (Higher Highs, Higher Lows)
    if highs[last_high] > highs[prev_high] and lows[last_low] > lows[prev_low]:
        # به دنبال CHoCH نزولی (شکست آخرین کف معتبر)
        if latest_close < lows[last_low]:
            return {
                "type": "BEARISH_CHOCH",
                "signal_price": lows[last_low],
                "sl_price": highs[last_high],
                "invalidation_point": highs[last_high]
            }
            
    return None

def calculate_lot_size_robust(symbol, risk_usd, avg_entry_price, sl_price):
    """
    محاسبه حجم معامله بر اساس ریسک دلاری، با در نظر گرفتن ارز حساب و مشخصات نماد.
    """
    try:
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"اطلاعات نماد {symbol} دریافت نشد.")
            return None

        point = symbol_info.point
        volume_step = symbol_info.volume_step
        
        sl_points = abs(avg_entry_price - sl_price) / point
        if sl_points == 0:
            logging.warning("فاصله حد ضرر صفر است. حجم قابل محاسبه نیست.")
            return None
        
        # دریافت ارزش هر تیک (سود یا زیان به ازای هر لات در یک تیک حرکت)
        tick_value_info = mt5.symbol_info_tick(symbol)
        if tick_value_info is None:
             logging.error(f"اطلاعات تیک برای نماد {symbol} دریافت نشد.")
             return None
        
        # ارزش هر تیک برای یک لات کامل
        tick_value = tick_value_info.bid if sl_price < avg_entry_price else tick_value_info.ask
        
        # ارزش هر پوینت
        point_value_per_lot = tick_value * (point / symbol_info.trade_tick_size)

        # محاسبه حجم
        lot_size = risk_usd / (sl_points * point_value_per_lot)
        
        # گرد کردن حجم بر اساس گام مجاز بروکر
        lot_size = round(lot_size / volume_step) * volume_step
        
        if lot_size < symbol_info.volume_min:
            logging.warning(f"حجم محاسبه شده ({lot_size}) کمتر از حداقل مجاز ({symbol_info.volume_min}) است.")
            return symbol_info.volume_min
            
        return lot_size
    except Exception as e:
        logging.error(f"خطا در محاسبه حجم: {e}")
        return None

def place_limit_order_robust(symbol, order_type, volume, price, sl, tp, magic, comment):
    """
    یک سفارش لیمیت با مدیریت خطا ارسال می‌کند.
    """
    point = mt5.symbol_info(symbol).point
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 5,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC, # یا FOK بر اساس بروکر
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logging.error(f"ارسال سفارش ناموفق بود. Retcode={result.retcode}, Comment={result.comment}")
        return None
    
    logging.info(f"سفارش با موفقیت کاشته شد: Ticket #{result.order}")
    return result.order

def cancel_pending_order(ticket):
    """یک سفارش در حال انتظار را لغو می‌کند."""
    request = {
        "action": mt5.TRADE_ACTION_REMOVE,
        "order": ticket,
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logging.info(f"سفارش {ticket} با موفقیت لغو شد.")
        return True
    else:
        logging.error(f"لغو سفارش {ticket} ناموفق بود. Retcode: {result.retcode}, Comment: {result.comment}")
        return False
        
# ==============================================================================
# 4. منطق ماشین حالت (State Machine Logic)
# ==============================================================================

def handle_searching_state():
    """
    منطق اصلی ربات در حالت جستجو برای یافتن ستاپ معاملاتی.
    """
    global state, active_setup
    
    logging.info("حالت: SEARCHING. در حال جستجو برای ستاپ جدید...")
    
    signal = detect_significant_structure(df)
    
    if signal:
        logging.info(f"سیگنال جدید یافت شد: {signal['type']} در قیمت {signal['signal_price']:.5f}")
        
        # --- آماده‌سازی برای ورود پلکانی ---
        magic_number = int(time.time())
        current_atr = df['atr'].iloc[-1]
        
        # محاسبه محدوده ورود (Entry Zone)
        entry_zone_start = signal['signal_price']
        if signal['type'] == 'BULLISH_CHOCH':
            entry_zone_end = signal['signal_price'] - (current_atr * SCALE_IN_ZONE_ATR_MULTIPLIER)
            order_type = mt5.ORDER_TYPE_BUY_LIMIT
        else: # BEARISH_CHOCH
            entry_zone_end = signal['signal_price'] + (current_atr * SCALE_IN_ZONE_ATR_MULTIPLIER)
            order_type = mt5.ORDER_TYPE_SELL_LIMIT
            
        # تولید قیمت‌های ورود برای هر پله
        entry_prices = np.linspace(entry_zone_start, entry_zone_end, NUM_SCALE_IN_ORDERS)
        avg_entry_price = np.mean(entry_prices)
        sl_price = signal['sl_price']

        # محاسبه حجم کل بر اساس میانگین قیمت ورود
        total_lot_size = calculate_lot_size_robust(SYMBOL, RISK_PER_TRADE_USD, avg_entry_price, sl_price)
        if total_lot_size is None or total_lot_size == 0:
            logging.error("محاسبه حجم ناموفق بود. ستاپ نادیده گرفته شد.")
            return

        lot_per_order = round(total_lot_size / NUM_SCALE_IN_ORDERS, 2)
        if lot_per_order < mt5.symbol_info(SYMBOL).volume_min:
            logging.warning(f"حجم هر پله ({lot_per_order}) کمتر از حد مجاز است. از حداقل حجم استفاده می‌شود.")
            lot_per_order = mt5.symbol_info(SYMBOL).volume_min
        
        # کاشت سفارشات Limit
        placed_tickets = []
        for price in entry_prices:
            # TODO: TP logic can be added here
            tp_price = 0.0 
            ticket = place_limit_order_robust(SYMBOL, order_type, lot_per_order, price, sl_price, tp_price, magic_number, TRADE_COMMENT)
            if ticket:
                placed_tickets.append(ticket)
        
        if len(placed_tickets) == NUM_SCALE_IN_ORDERS:
            logging.info(f"تمام {NUM_SCALE_IN_ORDERS} سفارش با Magic Number {magic_number} با موفقیت کاشته شدند.")
            active_setup = {
                "magic_number": magic_number,
                "type": signal['type'],
                "signal_price": signal['signal_price'],
                "sl_price": sl_price,
                "pending_tickets": placed_tickets
            }
            state = State.SCALING_IN
            logging.info("تغییر حالت به SCALING_IN.")
        else:
            logging.error("تمام سفارشات با موفقیت کاشته نشدند. در حال لغو سفارشات کاشته شده...")
            for ticket in placed_tickets:
                cancel_pending_order(ticket)

def handle_scaling_in_state():
    """
    منطق ربات در حالت مدیریت ورود پلکانی.
    """
    global state, active_setup
    
    if not active_setup:
        logging.warning("در حالت SCALING_IN هستیم اما active_setup خالی است. بازگشت به SEARCHING.")
        state = State.SEARCHING
        return

    magic = active_setup['magic_number']
    logging.info(f"حالت: SCALING_IN. در حال نظارت بر ستاپ با Magic Number {magic}...")
    
    # --- بررسی ابطال ستاپ به دلیل نفوذ عمیق ---
    current_price = mt5.symbol_info_tick(SYMBOL).ask if active_setup['type'] == 'BULLISH_CHOCH' else mt5.symbol_info_tick(SYMBOL).bid
    signal_price = active_setup['signal_price']
    current_atr = df['atr'].iloc[-1]
    
    invalidation_depth = PULLBACK_DEPTH_ATR_MULTIPLIER * current_atr
    
    pullback_deep = False
    if active_setup['type'] == 'BULLISH_CHOCH' and (signal_price - current_price) > invalidation_depth:
        pullback_deep = True
    elif active_setup['type'] == 'BEARISH_CHOCH' and (current_price - signal_price) > invalidation_depth:
        pullback_deep = True

    if pullback_deep:
        logging.warning(f"پولبک عمیق شناسایی شد. ستاپ {magic} در حال ابطال است.")
        # لغو تمام سفارشات باقی‌مانده
        orders = mt5.orders_get(symbol=SYMBOL)
        if orders:
            for order in orders:
                if order.magic == magic:
                    cancel_pending_order(order.ticket)
        # بستن پوزیشن‌های احتمالا باز شده
        positions = mt5.positions_get(symbol=SYMBOL)
        if positions:
            for pos in positions:
                if pos.magic == magic:
                    # TODO: Add logic to close open positions
                    logging.info(f"پوزیشن {pos.ticket} مربوط به این ستاپ نیز باید بسته شود (منطق آن را اضافه کنید).")

        active_setup = {}
        state = State.SEARCHING
        logging.info("ستاپ باطل شد. بازگشت به حالت SEARCHING.")
        return

    # --- بررسی وضعیت سفارشات ---
    remaining_pending_tickets = []
    all_orders = mt5.orders_get(symbol=SYMBOL)
    if all_orders:
        for ticket in active_setup['pending_tickets']:
            is_still_pending = any(order.ticket == ticket for order in all_orders)
            if is_still_pending:
                remaining_pending_tickets.append(ticket)
    
    if not remaining_pending_tickets:
        logging.info(f"فاز ورود پلکانی برای ستاپ {magic} به پایان رسید (تمام سفارشات فعال یا منقضی شدند).")
        # اکنون مدیریت پوزیشن‌های باز شده شروع می‌شود (که در یک تابع جداگانه قابل پیاده‌سازی است)
        active_setup = {}
        state = State.SEARCHING
        logging.info("بازگشت به حالت SEARCHING برای یافتن ستاپ بعدی.")
    else:
        active_setup['pending_tickets'] = remaining_pending_tickets
        logging.info(f"{len(remaining_pending_tickets)} سفارش برای ستاپ {magic} همچنان در حالت انتظار هستند.")

# TODO: یک تابع جداگانه برای مدیریت پوزیشن‌های باز (مثل Breakeven یا Trailing SL) می‌توان نوشت
def manage_open_positions():
    """
    این تابع می‌تواند برای مدیریت تمام پوزیشن‌های باز فارغ از حالت ربات اجرا شود.
    مثلاً برای رساندن به نقطه سر به سر (Breakeven).
    """
    pass

# ==============================================================================
# 5. حلقه اصلی ربات (Main Loop)
# ==============================================================================

def main():
    if not connect_to_mt5():
        return

    while True:
        try:
            # به‌روزرسانی داده‌ها
            is_new_candle = update_dataframe()
            
            if is_new_candle:
                logging.info(f"کندل جدید برای {SYMBOL} در تایم فریم {TIMEFRAME} دریافت شد. آخرین قیمت بسته شدن: {df['close'].iloc[-1]:.5f}")
                
                # اجرای منطق بر اساس حالت فعلی
                if state == State.SEARCHING:
                    handle_searching_state()
                elif state == State.SCALING_IN:
                    handle_scaling_in_state()
            
            # مدیریت پوزیشن‌های باز در هر تیک قابل اجراست
            manage_open_positions()

            time.sleep(1) # یک ثانیه تاخیر برای جلوگیری از بار اضافی
            
        except KeyboardInterrupt:
            logging.info("ربات به درخواست کاربر متوقف شد.")
            mt5.shutdown()
            break
        except Exception as e:
            logging.critical(f"خطای بحرانی در حلقه اصلی ربات: {e}")
            time.sleep(10) # در صورت بروز خطای جدی، کمی صبر کن و دوباره تلاش کن

if __name__ == "__main__":
    main()
