# File: runner.py (نسخه جدید برای ریسک ثابت دلاری)

from backtest_engine import BacktestEngine
from ema_strategy import EmaPullbackStrategy
# اگر استراتژی‌های دیگری دارید، آنها را نیز وارد کنید
# from smc_strategy import SmcStrategy 

# ==============================================================================
# --- CONFIGURATION - تمام تنظیمات را اینجا انجام دهید ---
# ==============================================================================

# ۱. مسیر فایل داده‌ها
BACKTEST_DATA_FILE = 'XAUUSD.csv' # نام فایل داده خود را وارد کنید

# ۲. موجودی اولیه حساب
INITIAL_BALANCE = 10000.0

# ۳. [تغییر اصلی] ریسک ثابت دلاری برای هر معامله
RISK_PER_TRADE_USD = 50.0  # هر معامله حداکثر 50 دلار ریسک خواهد داشت

# ۴. مشخصات نماد معاملاتی (بسیار مهم برای محاسبه صحیح لات)
# این مقادیر باید با نمادی که بک‌تست می‌گیرید مطابقت داشته باشد
SYMBOL_PIP_SIZE = 0.01      # برای طلا (XAUUSD) معمولا 0.01 است
SYMBOL_PIP_VALUE_PER_LOT = 10.0 # برای جفت‌ارزهای XXX/USD و طلا معمولا 10 دلار است

# ==============================================================================
# --- SCRIPT EXECUTION ---
# ==============================================================================

if __name__ == "__main__":
    
    print("--- Initializing Backtest ---")
    
    # ساخت موتور بک‌تست و پاس دادن تنظیمات جدید
    engine = BacktestEngine(
        csv_filepath=BACKTEST_DATA_FILE,
        strategy_class=EmaPullbackStrategy, # استراتژی مورد نظر خود را اینجا انتخاب کنید
        initial_balance=INITIAL_BALANCE,
        risk_per_trade_usd=RISK_PER_TRADE_USD, # ارسال پارامتر جدید
        pip_size=SYMBOL_PIP_SIZE,
        pip_value_per_lot=SYMBOL_PIP_VALUE_PER_LOT
    )

    # اجرای بک‌تست
    engine.run()
