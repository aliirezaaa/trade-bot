# File: backtest_engine.py

from tqdm import tqdm

class BacktestEngine:
    """
    موتور اصلی بک‌تست که اجزای مختلف (داده، بروکر، استراتژی) را هماهنگ می‌کند.
    """
    def __init__(self, data_handler, broker, strategy, portfolio):
        self.data_handler = data_handler
        self.broker = broker
        self.strategy = strategy
        self.portfolio = portfolio
        print("✅ BacktestEngine (Orchestrator) Initialized.")

    def run(self):
        """
        حلقه اصلی بک‌تست را اجرا می‌کند.
        """
        print("\n🚀 Starting backtest simulation...")
        # استفاده از tqdm برای نمایش نوار پیشرفت
        for i in tqdm(range(self.data_handler.total_bars), desc="Simulating"):
            current_bar = self.data_handler.get_bar(i)
            
            # ۱. بروکر پوزیشن‌های باز را با کندل جدید چک کند
            self.broker.check_open_trades(current_bar)

            # ۲. اگر کندل کافی برای تحلیل وجود دارد، به استراتژی خبر بده
            if i >= self.strategy.N_BARS_FOR_ENTRY:
                # داده‌های تاریخی مورد نیاز استراتژی را آماده کن
                historical_data = self.data_handler.get_historical_data(i, self.strategy.N_BARS_FOR_ENTRY)
                
                # به استراتژی اجازه بده تحلیل و اقدام کند
                # استراتژی مستقیماً با بروکر صحبت می‌کند
                self.strategy.on_bar(historical_data)
        
        print("🏁 Simulation finished.")
        
        # ۳. در پایان، از پورتفولیو بخواه گزارش را تولید کند
        self.portfolio.generate_report(
            self.broker.trade_history,
            self.broker.initial_balance,
            self.broker.balance
        )
