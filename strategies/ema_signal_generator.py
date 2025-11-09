# File: ema_signal_generator.py

class EmaSignalGenerator:
    """
    این کلاس مسئول شناسایی سیگنال‌های معاملاتی بر اساس استراتژی EMA Pullback است.
    وظیفه آن صرفاً تشخیص ستاپ (ایمپالس و سپس پولبک) است.
    """

    def __init__(self, impulse_atr_multiplier: float):
        """
        Args:
            impulse_atr_multiplier (float): ضریبی از ATR که قیمت باید از EMA سریع
                                            فاصله بگیرد تا یک حرکت ایمپالس تایید شود.
        """
        self.impulse_atr_multiplier = impulse_atr_multiplier
        self.impulse_confirmed = {'BUY': False, 'SELL': False}
        print("✅ EmaSignalGenerator Initialized.")

    def reset(self):
        """
        وضعیت داخلی ژنراتور را برای جستجوی ستاپ بعدی ریست می‌کند.
        این متد باید پس از بسته شدن هر معامله فراخوانی شود.
        """
        self.impulse_confirmed = {'BUY': False, 'SELL': False}
        # print("INFO (SignalGen): State has been reset.")

    def check(self, candles) -> str | None:
        """
        دیتافریم کندل‌ها را بررسی کرده و در صورت وجود ستاپ،
        سیگنال 'BUY' یا 'SELL' را برمی‌گرداند. در غیر این صورت None برمی‌گرداند.

        Args:
            candles (pd.DataFrame): دیتافریم کندل‌ها که باید شامل ستون‌های
                                    'EMA_slow', 'EMA_fast', و 'ATR' باشد.

        Returns:
            str | None: 'BUY', 'SELL', or None.
        """
        # اطمینان از وجود داده کافی
        if len(candles) < 2:
            return None

        last = candles.iloc[-1]
        prev = candles.iloc[-2]

        # تعیین روند کلی بر اساس EMA کند
        is_uptrend = last['EMA_slow'] < last['close']
        is_downtrend = last['EMA_slow'] > last['close']

        if is_uptrend:
            # ۱. ابتدا باید یک ایمپالس صعودی تایید شود
            if not self.impulse_confirmed['BUY']:
                impulse_distance = self.impulse_atr_multiplier * last['ATR']
                # اگر قیمت به اندازه کافی از EMA سریع فاصله گرفت، ایمپالس تایید می‌شود
                if last['high'] > (last['EMA_fast'] + impulse_distance):
                    self.impulse_confirmed['BUY'] = True
                    self.impulse_confirmed['SELL'] = False  # ریست کردن جهت مخالف
                return None  # در این کندل فقط ایمپالس تایید شد، سیگنال ورود نداریم

            # ۲. اگر ایمپالس تایید شده، حالا منتظر پولبک به EMA سریع هستیم
            else:
                # شرط پولبک: کندل قبلی بالای EMA سریع بوده و کندل فعلی آن را لمس کرده یا شکسته
                if prev['low'] > prev['EMA_fast'] and last['low'] <= last['EMA_fast']:
                    return 'BUY'

        elif is_downtrend:
            # ۱. ابتدا باید یک ایمپالس نزولی تایید شود
            if not self.impulse_confirmed['SELL']:
                impulse_distance = self.impulse_atr_multiplier * last['ATR']
                # اگر قیمت به اندازه کافی از EMA سریع فاصله گرفت، ایمپالس تایید می‌شود
                if last['low'] < (last['EMA_fast'] - impulse_distance):
                    self.impulse_confirmed['SELL'] = True
                    self.impulse_confirmed['BUY'] = False  # ریست کردن جهت مخالف
                return None  # در این کندل فقط ایمپالس تایید شد، سیگنال ورود نداریم

            # ۲. اگر ایمپالس تایید شده، حالا منتظر پولبک به EMA سریع هستیم
            else:
                # شرط پولبک: کندل قبلی پایین EMA سریع بوده و کندل فعلی آن را لمس کرده یا شکسته
                if prev['high'] < prev['EMA_fast'] and last['high'] >= last['EMA_fast']:
                    return 'SELL'

        return None
