import pandas as pd
import pandas_ta as ta

class EmaPullbackStrategy:
    """
    استراتژی معاملاتی بر اساس پولبک به EMA 20 در جهت روند EMA 50.
    این استراتژی ابتدا منتظر یک حرکت قدرتمند (Impulse) می‌ماند و سپس
    در اولین پولبک به EMA 20 وارد معامله می‌شود.
    """

    def __init__(self, broker, risk_to_reward: float, atr_period=14, ema_slow=21, ema_fast=9, impulse_atr_multiplier=0.4, sl_atr_multiplier=0.5):
        """
        سازنده کلاس استراتژی.

        Args:
            broker: یک نمونه از کلاس BacktestBroker برای دسترسی به داده‌ها و اجرای معاملات.
            risk_to_reward (float): نسبت ریسک به ریوارد برای تعیین حد سود.
            atr_period (int): دوره زمانی برای محاسبه ATR.
            ema_slow (int): دوره زمانی برای EMA کند (تعیین روند).
            ema_fast (int): دوره زمانی برای EMA سریع (نقطه ورود).
            impulse_atr_multiplier (float): ضریبی از ATR که قیمت باید از EMA سریع فاصله بگیرد تا Impulse تایید شود.
            sl_atr_multiplier (float): ضریبی از ATR برای محاسبه فاصله حد ضرر از EMA کند.
        """
        # ۱. [اصلاح اصلی] پارامتر broker اضافه و ذخیره شد
        self.broker = broker
        
        # --- پارامترهای استراتژی ---
        self.risk_to_reward = risk_to_reward
        self.atr_period = atr_period
        self.ema_slow_period = ema_slow
        self.ema_fast_period = ema_fast
        self.impulse_atr_multiplier = impulse_atr_multiplier
        self.sl_atr_multiplier = sl_atr_multiplier

        # ۲. [اصلاح اصلی] متغیر N_BARS_FOR_ENTRY برای موتور بک‌تست اضافه شد
        # باید به اندازه کافی بزرگ باشد تا طولانی‌ترین اندیکاتور (EMA 50) محاسبه شود
        self.N_BARS_FOR_ENTRY = 100 

        # --- مدیریت وضعیت ---
        self.position_open = False
        self.impulse_confirmed = {'BUY': False, 'SELL': False}

        print("✅ EmaPullbackStrategy Initialized.")

    def signal_position_closed(self):
        """این متد توسط موتور بک‌تست فراخوانی می‌شود تا به استراتژی اطلاع دهد معامله بسته شده است."""
        self.position_open = False
        self.impulse_confirmed = {'BUY': False, 'SELL': False} # ریست کردن وضعیت برای ستاپ بعدی
        # print("INFO (EMA Strategy): Position closed signal received. Ready for new setups.")


    def on_bar(self, candles: pd.DataFrame):
        """
        این متد اصلی استراتژی است که به ازای هر کندل جدید توسط موتور بک‌تست فراخوانی می‌شود.
        """
        # اگر معامله باز داریم، هیچ کاری انجام نده
        if self.position_open:
            return None

        # ۱. محاسبه اندیکاتورها
        self._calculate_indicators(candles)
        
        last_candle = candles.iloc[-1]
        prev_candle = candles.iloc[-2]

        # ۲. بررسی شرایط روند کلی
        is_uptrend = last_candle['EMA_50'] < last_candle['close']
        is_downtrend = last_candle['EMA_50'] > last_candle['close']
        
        trade_signal = None

        # ۳. منطق استراتژی
        if is_uptrend:
            trade_signal = self._check_buy_setup(last_candle, prev_candle)
        elif is_downtrend:
            trade_signal = self._check_sell_setup(last_candle, prev_candle)
        
        # اگر سیگنالی تولید شد، آن را برگردان
        if trade_signal:
            self.position_open = True # قفل کردن استراتژی تا زمان بسته شدن معامله
        
        return trade_signal

    def _calculate_indicators(self, candles: pd.DataFrame):
        """محاسبه و افزودن اندیکاتورهای مورد نیاز به دیتافریم."""
        candles['ATR'] = ta.atr(candles['high'], candles['low'], candles['close'], length=self.atr_period)
        candles['EMA_50'] = ta.ema(candles['close'], length=self.ema_slow_period)
        candles['EMA_20'] = ta.ema(candles['close'], length=self.ema_fast_period)
        candles.dropna(inplace=True)

    def _check_buy_setup(self, last, prev):
        """بررسی شرایط برای یک ستاپ خرید."""
        # ابتدا باید یک حرکت ایمپالس تایید شود
        if not self.impulse_confirmed['BUY']:
            impulse_distance = self.impulse_atr_multiplier * last['ATR']
            # اگر قیمت به اندازه کافی از EMA 20 فاصله گرفت، ایمپالس تایید می‌شود
            if last['high'] > (last['EMA_20'] + impulse_distance):
                self.impulse_confirmed['BUY'] = True
                self.impulse_confirmed['SELL'] = False # ریست کردن جهت مخالف
                # print(f"IMPULSE BUY Confirmed at {last.name}")
            return None

        # اگر ایمپالس تایید شده است، حالا منتظر پولبک هستیم
        # شرط پولبک: قیمت از بالای EMA 20 عبور کرده و به آن برگردد
        if prev['low'] > prev['EMA_20'] and last['low'] <= last['EMA_20']:
            entry_price = last['EMA_20']
            sl = last['EMA_50'] - (self.sl_atr_multiplier * last['ATR'])
            
            # اطمینان از اینکه حد ضرر منطقی است
            if entry_price <= sl:
                return None

            tp = entry_price + (self.risk_to_reward * (entry_price - sl))
            
            # print(f"BUY Signal at {last.name}: Entry={entry_price:.2f}, SL={sl:.2f}, TP={tp:.2f}")
            return {'type': 'BUY', 'entry_price': entry_price, 'sl': sl, 'tp': tp}
        
        return None

    def _check_sell_setup(self, last, prev):
        """بررسی شرایط برای یک ستاپ فروش."""
        # ابتدا باید یک حرکت ایمپالس تایید شود
        if not self.impulse_confirmed['SELL']:
            impulse_distance = self.impulse_atr_multiplier * last['ATR']
            # اگر قیمت به اندازه کافی از EMA 20 فاصله گرفت، ایمپالس تایید می‌شود
            if last['low'] < (last['EMA_20'] - impulse_distance):
                self.impulse_confirmed['SELL'] = True
                self.impulse_confirmed['BUY'] = False # ریست کردن جهت مخالف
                # print(f"IMPULSE SELL Confirmed at {last.name}")
            return None

        # اگر ایمپالس تایید شده است، حالا منتظر پولبک هستیم
        # شرط پولبک: قیمت از پایین EMA 20 عبور کرده و به آن برگردد
        if prev['high'] < prev['EMA_20'] and last['high'] >= last['EMA_20']:
            entry_price = last['EMA_20']
            sl = last['EMA_50'] + (self.sl_atr_multiplier * last['ATR'])

            # اطمینان از اینکه حد ضرر منطقی است
            if entry_price >= sl:
                return None

            tp = entry_price - (self.risk_to_reward * (sl - entry_price))
            
            # print(f"SELL Signal at {last.name}: Entry={entry_price:.2f}, SL={sl:.2f}, TP={tp:.2f}")
            return {'type': 'SELL', 'entry_price': entry_price, 'sl': sl, 'tp': tp}
        
        return None