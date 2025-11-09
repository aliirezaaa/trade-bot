# File: ema_order_calculator.py

class EmaOrderCalculator:
    """
    این کلاس مسئولیت محاسبه پارامترهای سفارش (SL/TP) را بر عهده دارد.
    این کلاس کاملاً مستقل از منطق تولید سیگنال است.
    """

    def __init__(self, risk_to_reward: float, sl_atr_multiplier: float):
        """
        Args:
            risk_to_reward (float): نسبت ریسک به ریوارد برای تعیین حد سود.
            sl_atr_multiplier (float): ضریبی از ATR برای محاسبه فاصله حد ضرر از EMA کند.
        """
        self.risk_to_reward = risk_to_reward
        self.sl_atr_multiplier = sl_atr_multiplier
        print("✅ EmaOrderCalculator Initialized.")

    def calculate_buy_order(self, last_candle) -> dict | None:
        """
        پارامترهای یک سفارش خرید را بر اساس آخرین کندل محاسبه می‌کند.

        Args:
            last_candle (pd.Series): سطر مربوط به آخرین کندل دیتافریم.

        Returns:
            dict | None: دیکشنری شامل 'sl' و 'tp' یا None در صورت نامعتبر بودن سفارش.
        """
        # برای سفارش مارکت، قیمت ورود همان قیمت بسته شدن کندل سیگنال است
        entry_price = last_candle['close']
        
        # حد ضرر کمی پایین‌تر از EMA کند قرار می‌گیرد
        sl = last_candle['EMA_slow'] - (self.sl_atr_multiplier * last_candle['ATR'])

        # اگر حد ضرر بالاتر از قیمت ورود باشد، ستاپ نامعتبر است
        if entry_price <= sl:
            return None

        risk_amount = entry_price - sl
        tp = entry_price + (risk_amount * self.risk_to_reward)

        return {'sl': sl, 'tp': tp}

    def calculate_sell_order(self, last_candle) -> dict | None:
        """
        پارامترهای یک سفارش فروش را بر اساس آخرین کندل محاسبه می‌کند.

        Args:
            last_candle (pd.Series): سطر مربوط به آخرین کندل دیتافریم.

        Returns:
            dict | None: دیکشنری شامل 'sl' و 'tp' یا None در صورت نامعتبر بودن سفارش.
        """
        # برای سفارش مارکت، قیمت ورود همان قیمت بسته شدن کندل سیگنال است
        entry_price = last_candle['close']

        # حد ضرر کمی بالاتر از EMA کند قرار می‌گیرد
        sl = last_candle['EMA_slow'] + (self.sl_atr_multiplier * last_candle['ATR'])

        # اگر حد ضرر پایین‌تر از قیمت ورود باشد، ستاپ نامعتبر است
        if entry_price >= sl:
            return None

        risk_amount = sl - entry_price
        tp = entry_price - (risk_amount * self.risk_to_reward)

        return {'sl': sl, 'tp': tp}
