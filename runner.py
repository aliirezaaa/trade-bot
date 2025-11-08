# File: runner.py
# نسخه به‌روز شده برای کار با backtest_engine جدید

import sys
from backtest_engine import BacktestBroker

# --- استراتژی‌های خود را اینجا وارد کنید ---
# هر دو استراتژی را وارد می‌کنیم تا بتوانیم به راحتی بین آنها سوییچ کنیم
from bot_strategy import BotStrategy
from ema_strategy import EmaPullbackStrategy


# ==============================================================================
# --- CONFIGURATION - تمام تنظیمات را اینجا انجام دهید ---
# ==============================================================================

# ۱. انتخاب استراتژی برای اجرا
# 'SMC' یا 'EMA' را انتخاب کنید
STRATEGY_TO_RUN = 'EMA' # <--- اینجا استراتژی مورد نظر را انتخاب کنید

# ۲. مسیر فایل داده‌ها
# توجه: موتور جدید انتظار فرمت خاصی برای CSV دارد (در توضیحات پایین گفته شده)
BACKTEST_DATA_FILE = 'XAUUSD.csv'

# ۳. تنظیمات کلی بک‌تست
INITIAL_BALANCE = 10000.0
COMMISSION = 0.0 # هزینه کمیسیون برای هر معامله (در حال حاضر صفر)

# ۴. پارامترهای مخصوص هر استراتژی
# این پارامترها به صورت خودکار به استراتژی انتخاب شده پاس داده می‌شوند
STRATEGY_PARAMS = {
    'SMC': {
        'risk_to_reward': 2.0,
        # پارامترهای آینده استراتژی SMC را اینجا اضافه کنید
    },
    'EMA': {
        'risk_to_reward': 1.5,
        # پارامترهای آینده استراتژی EMA را اینجا اضافه کنید
    }
}

# ==============================================================================
# --- SCRIPT EXECUTION ---
# ==============================================================================

if __name__ == "__main__":
    
    strategy_map = {
        'SMC': BotStrategy,
        'EMA': EmaPullbackStrategy
    }

    if STRATEGY_TO_RUN not in strategy_map:
        print(f"❌ خطای پیکربندی: استراتژی '{STRATEGY_TO_RUN}' تعریف نشده است.")
        print(f"   گزینه‌های معتبر: {list(strategy_map.keys())}")
        sys.exit()

    print(f"--- شروع بک‌تست برای استراتژی: {STRATEGY_TO_RUN} ---")

    # انتخاب کلاس استراتژی و پارامترهای آن بر اساس تنظیمات
    selected_strategy_class = strategy_map[STRATEGY_TO_RUN]
    selected_strategy_params = STRATEGY_PARAMS[STRATEGY_TO_RUN]

    # ۱. ساخت موتور بک‌تست
    # موتور بک‌تست خودش استراتژی را با پارامترهای لازم می‌سازد
    engine = BacktestBroker(
        data_path=BACKTEST_DATA_FILE,
        strategy_class=selected_strategy_class,
        initial_balance=INITIAL_BALANCE,
        commission_per_trade=COMMISSION,
        **selected_strategy_params  # پاس دادن پارامترهای استراتژی
    )

    # ۲. اجرای بک‌تست
    # متد run() حلقه اصلی را اجرا کرده و در پایان گزارش را چاپ می‌کند
    engine.run()

    print("\n--- بک‌تست به پایان رسید ---")
