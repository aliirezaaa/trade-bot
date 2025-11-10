# runner.py

from core.backtest_engine import BacktestEngine
from strategies.ema_strategy import EmaPullbackStrategy

# --- پارامترهای اصلی بک‌تست ---
INITIAL_BALANCE = 10000.0
RISK_PER_TRADE_USD = 100.0  # ریسک ثابت به دلار برای هر معامله
CSV_FILEPATH = 'data/XAUUSD.csv'

# --- مشخصات نماد (Symbol Specification) ---
PIP_SIZE = 0.0001
PIP_VALUE_PER_LOT = 10.0  # به ازای هر 1 لات استاندارد

# --- پارامترهای استراتژی ---
STRATEGY_PARAMS = {
    'risk_to_reward': 2.0,
    'atr_period': 14,
    'ema_slow': 50,
    'ema_fast': 20,
    'ema_long': 200,  # فیلتر روند بلندمدت
    'impulse_atr_multiplier': 1.5,
    'sl_atr_multiplier': 1.5
}

def main():
    print("🚀 Starting Backtest Runner with a fully refactored engine...")

    # ۱. ساخت استراتژی با پارامترهای مشخص شده
    # بروکر بعدا توسط موتور بک‌تست به استراتژی "تزریق" (inject) می‌شود.
    strategy_instance = EmaPullbackStrategy(**STRATEGY_PARAMS)

    # ۲. ساخت موتور بک‌تست با تمام اجزای جدید
    engine = BacktestEngine(
        csv_filepath=CSV_FILEPATH,
        strategy_instance=strategy_instance,
        initial_balance=INITIAL_BALANCE,
        risk_per_trade_usd=RISK_PER_TRADE_USD,
        pip_size=PIP_SIZE,
        pip_value_per_lot=PIP_VALUE_PER_LOT
    )

    # ۳. اجرای بک‌تست
    engine.run()

if __name__ == "__main__":
    main()
