# File: ema_strategy.py (Version 2 - With Impulse Detection)

import pandas as pd
import pandas_ta as ta

class EmaPullbackStrategy:
    """
    این کلاس استراتژی معاملاتی مبتنی بر پولبک به EMA را پیاده‌سازی می‌کند.
    **نسخه ۲: این نسخه ابتدا منتظر یک حرکت قوی (Impulse) می‌ماند و سپس به دنبال پولبک می‌گردد.**
    """
    def __init__(self, risk_to_reward: float):
        """
        مقادیر اولیه و پارامترهای استراتژی را تنظیم می‌کند.
        """
        # --- پارامترهای استراتژی ---
        self.EMA_SHORT_PERIOD = 20
        self.EMA_LONG_PERIOD = 50
        self.ATR_PERIOD = 14
        self.ATR_SL_MULTIPLIER = 0.5
        self.RISK_TO_REWARD = risk_to_reward
        self.N_BARS_FOR_ENTRY = 100
        # *** پارامتر جدید برای تشخیص فاصله گرفتن از EMA ***
        self.ATR_DISTANCE_MULTIPLIER = 0.8  # قیمت باید حداقل 0.8 برابر ATR از EMA فاصله بگیرد

        # --- مدیریت وضعیت ---
        self.position_open = False
        # این متغیرها وضعیت جستجو برای ستاپ را مدیریت می‌کنند
        self.impulse_up_confirmed = False
        self.impulse_down_confirmed = False
        
        print("✅ EMA Pullback Strategy V2 (Impulse-Aware) Initialized.")
        print(f"   - EMA Periods: {self.EMA_SHORT_PERIOD} / {self.EMA_LONG_PERIOD}")
        print(f"   - ATR Distance Multiplier for Impulse: {self.ATR_DISTANCE_MULTIPLIER}")
        print(f"   - Risk to Reward Ratio: 1:{self.RISK_TO_REWARD}")

    def on_bar(self, candles: pd.DataFrame):
        """
        این متد اصلی استراتژی است که با هر کندل جدید فراخوانی می‌شود.
        """
        if self.position_open:
            return None

        if len(candles) < self.EMA_LONG_PERIOD:
            return None

        # --- ۱. محاسبه اندیکاتورها ---
        ema_short = ta.ema(candles['close'], length=self.EMA_SHORT_PERIOD)
        ema_long = ta.ema(candles['close'], length=self.EMA_LONG_PERIOD)
        atr = ta.atr(candles['high'], candles['low'], candles['close'], length=self.ATR_PERIOD)

        current_candle = candles.iloc[-1]
        current_ema_short = ema_short.iloc[-1]
        current_ema_long = ema_long.iloc[-1]
        current_atr = atr.iloc[-1]

        # --- ۲. بررسی شرایط روند ---
        is_uptrend = current_ema_short > current_ema_long
        is_downtrend = current_ema_short < current_ema_long
        
        # اگر روند عوض شد، وضعیت تشخیص Impulse را ریست می‌کنیم
        if not is_uptrend:
            self.impulse_up_confirmed = False
        if not is_downtrend:
            self.impulse_down_confirmed = False

        # --- ۳. منطق تشخیص Impulse و Pullback ---
        trade = None
        
        # --- بخش خرید (BUY) ---
        if is_uptrend:
            # گام اول: آیا یک حرکت Impulse (فاصله گرفتن) تایید شده است؟
            if not self.impulse_up_confirmed:
                # به دنبال کندلی می‌گردیم که کاملا بالای منطقه ممنوعه باشد
                impulse_threshold = current_ema_short + (current_atr * self.ATR_DISTANCE_MULTIPLIER)
                if current_candle['low'] > impulse_threshold:
                    self.impulse_up_confirmed = True
                    print(f"   - INFO @ {current_candle.name}: Upward Impulse Confirmed. Waiting for pullback.")
            else:
                # گام دوم: حالا که Impulse داریم، منتظر پولبک هستیم
                is_buy_pullback = current_candle['low'] <= current_ema_short
                if is_buy_pullback:
                    entry_price = current_ema_short
                    sl = current_ema_long - (current_atr * self.ATR_SL_MULTIPLIER)
                    risk_distance = entry_price - sl
                    
                    if risk_distance > 0:
                        reward_distance = risk_distance * self.RISK_TO_REWARD
                        tp = entry_price + reward_distance
                        trade = {'type': 'BUY', 'entry_price': entry_price, 'sl': sl, 'tp': tp}
                        print(f"📈 BUY Signal @ {current_candle.name} | Entry: {entry_price:.5f}, SL: {sl:.5f}, TP: {tp:.5f}")

        # --- بخش فروش (SELL) ---
        if is_downtrend:
            # گام اول: آیا یک حرکت Impulse (فاصله گرفتن) تایید شده است؟
            if not self.impulse_down_confirmed:
                impulse_threshold = current_ema_short - (current_atr * self.ATR_DISTANCE_MULTIPLIER)
                if current_candle['high'] < impulse_threshold:
                    self.impulse_down_confirmed = True
                    print(f"   - INFO @ {current_candle.name}: Downward Impulse Confirmed. Waiting for pullback.")
            else:
                # گام دوم: حالا که Impulse داریم، منتظر پولبک هستیم
                is_sell_pullback = current_candle['high'] >= current_ema_short
                if is_sell_pullback:
                    entry_price = current_ema_short
                    sl = current_ema_long + (current_atr * self.ATR_SL_MULTIPLIER)
                    risk_distance = sl - entry_price
                    
                    if risk_distance > 0:
                        reward_distance = risk_distance * self.RISK_TO_REWARD
                        tp = entry_price - reward_distance
                        trade = {'type': 'SELL', 'entry_price': entry_price, 'sl': sl, 'tp': tp}
                        print(f"📉 SELL Signal @ {current_candle.name} | Entry: {entry_price:.5f}, SL: {sl:.5f}, TP: {tp:.5f}")

        if trade:
            self.position_open = True
            # پس از گرفتن سیگنال، وضعیت Impulse را ریست می‌کنیم تا برای ستاپ بعدی آماده شود
            self.impulse_up_confirmed = False
            self.impulse_down_confirmed = False
            return trade

        return None

    def signal_position_closed(self):
        """
        این متد توسط runner فراخوانی می‌شود تا به استراتژی اطلاع دهد که معامله بسته شده
        و می‌تواند برای یافتن ستاپ جدید جستجو کند.
        """
        self.position_open = False
