# core/backtest_engine.py

from tqdm import tqdm
from .data_handler import DataHandler
from .risk_manager import RiskManager
from .broker import Broker
from .portfolio import Portfolio

class BacktestEngine:
    def __init__(self, csv_filepath, strategy_instance, initial_balance, risk_per_trade_usd, pip_size, pip_value_per_lot):
        self.strategy = strategy_instance
        
        self.data_handler = DataHandler(csv_filepath)
        self.risk_manager = RiskManager(risk_per_trade_usd, pip_size, pip_value_per_lot)
        
        self.broker = Broker(
            initial_balance=initial_balance, 
            risk_manager=self.risk_manager,
            pip_size=pip_size
        )
        
        self.portfolio = Portfolio(initial_balance)

        # تزریق بروکر به استراتژی و ثبت callback
        self.strategy.broker = self.broker
        self.broker.register_on_close_callback(self.strategy.on_position_closed)
        
        print("✅ Backtest Engine Initialized.")

    def run(self):
        print(f"\n--- Starting backtest... ---")
        print(f"Risk model: Fixed Amount (${self.risk_manager.risk_per_trade_usd:.2f} per trade)")

        historical_data_needed = self.strategy.N_BARS_FOR_ENTRY
        
        for current_bar in tqdm(self.data_handler.stream_bars(), desc="Backtesting Progress", total=len(self.data_handler.df)):
            self.broker.check_open_trades(current_bar)
            
            # تهیه داده‌های تاریخی برای استراتژی
            historical_data = self.data_handler.get_historical_data(historical_data_needed)
            if historical_data.empty or len(historical_data) < historical_data_needed:
                continue

            self.strategy.on_bar(historical_data)

        # بستن تمام معاملات باز در انتهای بک‌تست و افزودن به تاریخچه
        final_bar = self.data_handler.get_last_bar()
        closed_trades = self.broker.close_all_open_positions(final_bar)
        self.portfolio.add_trades(closed_trades)

        # افزودن تاریخچه معاملات از بروکر به پورتفولیو
        self.portfolio.add_trades(self.broker.trade_history)
        
        # تولید گزارش نهایی
        self.portfolio.generate_report(self.broker.balance)
