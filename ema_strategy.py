# File: ema_strategy.py (نسخه نهایی و کاملاً اصلاح شده بر اساس کد شما)

import pandas as pd
import pandas_ta as ta

class EmaPullbackStrategy:
    """
    استراتژی معاملاتی بر اساس پولبک به EMA در جهت روند کلی.
    این استراتژی ابتدا منتظر یک حرکت قدرتمند (Impulse) می‌ماند و سپس
    در اولین پولبک وارد معامله می‌شود.
    """

    def __init__(self, broker, risk_to_reward: float, atr_period=14, ema_slow=21, ema_fast=9, impulse_atr_multiplier=0.4, sl_atr_multiplier=0.5):
        """
        سازنده کلاس استراتژی.
        """
        self.broker = broker
        
        # --- پارامترهای استراتژی ---
        self.risk_to_reward = risk_to_reward
        self.atr_period = atr_period
        self.ema_slow_period = ema_slow
        self.ema_fast_period = ema_fast
        self.impulse_atr_multiplier = impulse_atr_multiplier
        self.sl_atr_multiplier = sl_atr_multiplier

        # تعداد کندل‌های مورد نیاز برای محاسبه اندیکاتورها
        self.N_BARS_FOR_ENTRY = 100 

        # --- مدیریت وضعیت داخلی استراتژی ---
        self.impulse_confirmed = {'BUY': False, 'SELL': False}

        print("✅ EmaPullbackStrategy Initialized.")

    def signal_position_closed(self, trade):
        """این متد توسط موتور بک‌تست فراخوانی می‌شود تا به استراتژی اطلاع دهد معامله بسته شده است."""
        # ریست کردن وضعیت برای جستجوی ستاپ بعدی
        self.impulse_confirmed = {'BUY': False, 'SELL': False} 
        print(f"  STRATEGY NOTIFIED: Position closed. PnL: ${trade.get('pnl', 0):.2f}. Ready for new setup.")

    def on_bar(self, current_bar):
        """
        این متد اصلی استراتژی است که به ازای هر کندل جدید توسط موتور بک‌تست فراخوانی می‌شود.
        """
        # <<< تغییر ۱: چک کردن معامله باز از طریق بروکر >>>
        # به جای self.position_open از self.broker.open_positions استفاده می‌کنیم
        if self.broker.open_positions:
            return

        # دریافت داده‌های تاریخی برای تحلیل
        candles = self.broker.get_historical_data(self.N_BARS_FOR_ENTRY)
        if candles.empty or len(candles) < self.N_BARS_FOR_ENTRY:
            return

        # ۱. محاسبه اندیکاتورها
        self._calculate_indicators(candles)
        
        # اطمینان از اینکه داده کافی برای تحلیل وجود دارد
        if len(candles) < 2:
            return
            
        last_candle = candles.iloc[-1]
        prev_candle = candles.iloc[-2]
        
        # اطمینان از وجود مقادیر اندیکاتور
        required_cols = [f'EMA_{self.ema_slow_period}', f'EMA_{self.ema_fast_period}', 'ATR']
        if any(col not in last_candle or pd.isna(last_candle[col]) for col in required_cols):
            return

        # ۲. بررسی شرایط روند کلی
        is_uptrend = last_candle[f'EMA_{self.ema_slow_period}'] < last_candle['close']
        is_downtrend = last_candle[f'EMA_{self.ema_slow_period}'] > last_candle['close']
        
        trade_signal = None

        # ۳. منطق استراتژی
        if is_uptrend:
            trade_signal = self._check_buy_setup(last_candle, prev_candle)
        elif is_downtrend:
            trade_signal = self._check_sell_setup(last_candle, prev_candle)
        
        # <<< تغییر ۲: اجرای مستقیم سیگنال به جای return کردن آن >>>
        if trade_signal:
            print(f"  => SIGNAL FOUND: {trade_signal['type']}. Placing order.")
            # به جای return کردن دیکشنری، مستقیماً به بروکر دستور می‌دهیم
            # حجم معامله دیگر اینجا مشخص نمی‌شود و موتور آن را محاسبه می‌کند
            self.broker.place_market_order(
                direction=trade_signal['type'],
                sl=trade_signal['sl'],
                tp=trade_signal['tp']
            )

    def _calculate_indicators(self, candles: pd.DataFrame):
        """محاسبه و افزودن اندیکاتورهای مورد نیاز به دیتافریم."""
        candles['ATR'] = ta.atr(candles['high'], candles['low'], candles['close'], length=self.atr_period)
        # <<< تغییر ۳: استفاده از نام‌های داینامیک برای EMA >>>
        candles[f'EMA_{self.ema_slow_period}'] = ta.ema(candles['close'], length=self.ema_slow_period)
        candles[f'EMA_{self.ema_fast_period}'] = ta.ema(candles['close'], length=self.ema_fast_period)
        candles.dropna(inplace=True)

    def _check_buy_setup(self, last, prev):
        """بررسی شرایط برای یک ستاپ خرید."""
        ema_fast = last[f'EMA_{self.ema_fast_period}']
        ema_slow = last[f'EMA_{self.ema_slow_period}']

        if not self.impulse_confirmed['BUY']:
            impulse_distance = self.impulse_atr_multiplier * last['ATR']
            if last['high'] > (ema_fast + impulse_distance):
                self.impulse_confirmed['BUY'] = True
                self.impulse_confirmed['SELL'] = False
            return None

        if prev['low'] > ema_fast and last['low'] <= ema_fast:
            entry_price = ema_fast
            sl = ema_slow - (self.sl_atr_multiplier * last['ATR'])
            
            if entry_price <= sl:
                return None

            tp = entry_price + (self.risk_to_reward * (entry_price - sl))
            return {'type': 'BUY', 'entry_price': entry_price, 'sl': sl, 'tp': tp}
        
        return None

    def _check_sell_setup(self, last, prev):
        """بررسی شرایط برای یک ستاپ فروش."""
        ema_fast = last[f'EMA_{self.ema_fast_period}']
        ema_slow = last[f'EMA_{self.ema_slow_period}']

        if not self.impulse_confirmed['SELL']:
            impulse_distance = self.impulse_atr_multiplier * last['ATR']
            if last['low'] < (ema_fast - impulse_distance):
                self.impulse_confirmed['SELL'] = True
                self.impulse_confirmed['BUY'] = False
            return None

        if prev['high'] < ema_fast and last['high'] >= ema_fast:
            entry_price = ema_fast
            sl = ema_slow + (self.sl_atr_multiplier * last['ATR'])

            if entry_price >= sl:
                return None

            tp = entry_price - (self.risk_to_reward * (sl - entry_price))
            return {'type': 'SELL', 'entry_price': entry_price, 'sl': sl, 'tp': tp}
        
        return None
