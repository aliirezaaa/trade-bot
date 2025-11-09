# File: runner.py

import sys

# --- وارد کردن تمام اجزای مورد نیاز ---
from core.data_handler import DataHandler
from core.risk_manager import RiskManager
from core.broker import BacktestBroker
from core.portfolio import Portfolio
from backtest_engine import BacktestEngine

# --- وارد کردن استراتژی‌ها ---
from strategies.ema_strategy import EmaPullbackStrategy
# from strategies.bot_strategy import BotStrategy # <--- استراتژی‌های دیگر را اینجا اضافه کنید

# ==============================================================================
# --- CONFIGURATION - تمام تنظیمات را اینجا انجام دهید ---
# ==============================================================================

# ۱. انتخاب استراتژی برای اجرا
STRATEGY_TO_RUN = 'EMA'  # <--- نام استراتژی مورد نظر (کلید دیکشنری strategy_map)

# ۲. مسیر فایل داده‌ها
BACKTEST_DATA_FILE = 'XAUUSD.csv'  # <--- نام فایل دیتای خود را اینجا قرار دهید

# ۳. تنظیمات مالی و بروکر
INITIAL_BALANCE = 10000.0
RISK_PER_TRADE_USD = 100.0  # <--- مبلغ ریسک ثابت به دلار برای هر معامله
PIP_SIZE = 0.00001           # برای جفت‌ارزهای 5 رقمی (مثل EURUSD)
PIP_VALUE_PER_LOT = 10.0   # ارزش هر پیپ به ازای یک لات استاندارد (برای EURUSD)

# ۴. پارامترهای مخصوص هر استراتژی
STRATEGY_PARAMS = {
    'SMC': {
        'risk_to_reward': 2.0,
    },
    'EMA': {
        'risk_to_reward': 2.0,
        'atr_period': 14,
        'ema_slow': 50,
        'ema_fast': 20,
        'impulse_atr_multiplier': 0.8,
        'sl_atr_multiplier': 0.5
    }
}

# ==============================================================================
# --- SCRIPT EXECUTION - از اینجا به بعد کد را تغییر ندهید ---
# ==============================================================================

if __name__ == "__main__":

    # نقشه برای انتخاب کلاس استراتژی بر اساس نام
    strategy_map = {
        'EMA': EmaPullbackStrategy,
        # 'SMC': BotStrategy
    }

    if STRATEGY_TO_RUN not in strategy_map:
        print(f"❌ خطای پیکربندی: استراتژی '{STRATEGY_TO_RUN}' تعریف نشده است.")
        sys.exit(1)

    print("="*30)
    print(f"🚀 Initializing Backtest for Strategy: {STRATEGY_TO_RUN}")
    print("="*30)

    # --- مرحله ۱: ساخت و مونتاژ اجزا ---
    print("\n--- Step 1: Assembling Components ---")
    try:
        # ۱.۱: ساختن مسئول داده
        data_handler = DataHandler(data_path=BACKTEST_DATA_FILE)

        # ۱.۲: ساختن مدیر ریسک
        risk_manager = RiskManager(
            risk_per_trade_usd=RISK_PER_TRADE_USD,
            pip_size=PIP_SIZE,
            pip_value_per_lot=PIP_VALUE_PER_LOT
        )
        
        # ۱.۳: ساختن تحلیلگر پورتفولیو
        portfolio = Portfolio()

        # ۱.۴: ساختن شبیه‌ساز بروکر
        broker = BacktestBroker(
            initial_balance=INITIAL_BALANCE,
            risk_manager=risk_manager
        )

        # ۱.۵: ساختن استراتژی و اتصال آن به بروکر
        selected_strategy_class = strategy_map[STRATEGY_TO_RUN]
        selected_strategy_params = STRATEGY_PARAMS[STRATEGY_TO_RUN]
        
        strategy = selected_strategy_class(
            broker=broker,  # <--- بروکر به استراتژی پاس داده می‌شود
            **selected_strategy_params
        )

        # ۱.۶: اتصال متد بازگشتی (callback) از استراتژی به بروکر
        # این کار به بروکر اجازه می‌دهد تا پس از بستن معامله، به استراتژی اطلاع دهد
        broker.set_strategy_callbacks(
            position_closed=strategy.signal_position_closed
        )

        # ۱.۷: ساختن موتور اصلی بک‌تست با تمام اجزای آماده
        engine = BacktestEngine(
            data_handler=data_handler,
            broker=broker,
            strategy=strategy,
            portfolio=portfolio
        )

    except Exception as e:
        print(f"\n❌ An error occurred during initialization: {e}")
        sys.exit(1)

    # --- مرحله ۲: اجرای بک‌تست ---
    engine.run()

    print("\n--- Backtest Finished ---")
