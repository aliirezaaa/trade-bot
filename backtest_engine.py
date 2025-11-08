# File: backtest_engine.py (نسخه نهایی و صحیح)

import pandas as pd
from tqdm import tqdm
import sys

class BacktestBroker:
    """
    موتور بک‌تست که مسئولیت مدیریت داده‌ها، اجرای استراتژی و گزارش‌گیری را بر عهده دارد.
    """
    def __init__(self, data_path, strategy_class, initial_balance=10000.0, commission_per_trade=0.0, **strategy_params):
        """
        سازنده موتور بک‌تست.
        
        Args:
            data_path (str): مسیر فایل CSV داده‌ها.
            strategy_class: کلاس استراتژی که باید اجرا شود (مثلا BotStrategy).
            initial_balance (float): موجودی اولیه حساب.
            commission_per_trade (float): هزینه کمیسیون برای هر معامله.
            **strategy_params: پارامترهای اضافی که مستقیما به استراتژی پاس داده می‌شوند.
        """
        self.data_path = data_path
        self.df = self._load_data()
        if self.df is None:
            sys.exit("برنامه به دلیل عدم بارگذاری داده متوقف شد.")

        # --- مدیریت مالی و معاملات ---
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.commission = commission_per_trade
        self.open_trade = None
        self.trade_history = []
        
        # --- ساخت استراتژی ---
        # موتور بک‌تست (self) به عنوان بروکر به استراتژی معرفی می‌شود
        self.strategy = strategy_class(broker=self, **strategy_params)
        
        self.current_tick_index = 0
        print(f"✅ BacktestBroker Initialized. Initial Balance: ${self.initial_balance:,.2f}")
        print(f"   - Strategy: {strategy_class.__name__}")
        print(f"   - Data loaded successfully. Shape: {self.df.shape}")


    def _load_data(self):
        """
        داده‌ها را از فایل CSV/TXT با فرمت جدید بارگذاری می‌کند.
        فرمت مورد انتظار: 9 ستون تب-جداشده، بدون هدر
        (date, time, open, high, low, close, tick_volume, spread, real_volume)
        """
        try:
            # تعریف نام ستون‌ها به ترتیب موجود در فایل
            column_names = [
                'date', 'time', 'open', 'high', 'low', 'close', 
                'tick_volume', 'spread', 'real_volume'
            ]

            df = pd.read_csv(
                self.data_path,
                sep='\t',  # ۱. مشخص کردن جداکننده تب
                header=None, # ۲. اعلام اینکه فایل هدر ندارد
                names=column_names, # ۳. اختصاص دادن نام به ستون‌ها
                # ۴. ترکیب دو ستون اول (date, time) برای ساخت یک ستون datetime
                parse_dates={'datetime': ['date', 'time']},
                # ۵. قرار دادن ستون datetime به عنوان ایندکس دیتافریم
                index_col='datetime' 
            )

            # تغییر نام ستون حجم برای هماهنگی با استانداردهای رایج
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            
            # اطمینان از اینکه ستون‌های مورد نیاز وجود دارند
            required_cols = ['open', 'high', 'low', 'close']
            if not all(col in df.columns for col in required_cols):
                print(f"❌ خطا: فایل داده پس از پردازش، شامل ستون‌های {required_cols} نیست.")
                return None
                
            # انتخاب فقط ستون‌های ضروری برای جلوگیری از مصرف حافظه اضافی
            # این کار اختیاری است اما کد را تمیزتر می‌کند
            df = df[['open', 'high', 'low', 'close', 'volume']]
            
            print("✅ داده‌ها با فرمت جدید (تب-جداشده) با موفقیت بارگذاری شد.")
            return df
            
        except FileNotFoundError:
            print(f"❌ خطا: فایل داده در مسیر '{self.data_path}' یافت نشد.")
            return None
        except Exception as e:
            print(f"❌ خطا در هنگام بارگذاری یا پردازش فایل داده: {e}")
            return None

    def get_historical_data(self, n_bars: int):
        """
        داده‌های تاریخی تا کندل فعلی را به استراتژی می‌دهد.
        """
        if self.current_tick_index < n_bars:
            return pd.DataFrame() # دیتای کافی وجود ندارد
        
        start_index = self.current_tick_index - n_bars
        # از iloc برای انتخاب بر اساس موقعیت عددی استفاده می‌کنیم
        return self.df.iloc[start_index:self.current_tick_index].copy()

    def advance_time(self):
        """زمان را یک کندل به جلو می‌برد."""
        if self.current_tick_index >= len(self.df):
            return False # پایان داده‌ها
        
        self.current_tick_index += 1
        return True

    def run(self):
        """حلقه اصلی بک‌تست را اجرا می‌کند."""
        print("\n--- Starting backtest... ---")
        
        # اطمینان از وجود N_BARS_FOR_ENTRY در استراتژی
        if not hasattr(self.strategy, 'N_BARS_FOR_ENTRY'):
             print("❌ خطای استراتژی: متغیر 'N_BARS_FOR_ENTRY' در کلاس استراتژی تعریف نشده است.")
             return

        # حلقه اصلی بک‌تست
        for i in tqdm(range(len(self.df)), desc="Backtesting Progress"):
            self.current_tick_index = i + 1
            
            # 1. مدیریت معامله باز (چک کردن SL/TP)
            if self.open_trade:
                self._check_open_trades()

            # 2. دریافت داده‌های تاریخی و ارسال به استراتژی
            # فقط در صورتی که دیتای کافی برای تحلیل وجود داشته باشد
            if i >= self.strategy.N_BARS_FOR_ENTRY:
                historical_candles = self.get_historical_data(self.strategy.N_BARS_FOR_ENTRY)
                
                # فراخوانی متد اصلی استراتژی
                trade_signal = self.strategy.on_bar(historical_candles)
                
                if trade_signal:
                    self._execute_trade(trade_signal)

        print("\n--- Backtest finished. ---")
        self._generate_report()

    def _execute_trade(self, trade_signal: dict):
        """یک سیگنال معاملاتی را اجرا می‌کند."""
        if self.open_trade is not None:
            # print("INFO: Trade signal received but a position is already open. Signal ignored.")
            return

        current_time = self.df.index[self.current_tick_index - 1]
        
        self.open_trade = {
            'type': trade_signal['type'],
            'entry_price': trade_signal['entry_price'],
            'sl': trade_signal['sl'],
            'tp': trade_signal['tp'],
            'entry_time': current_time,
            'status': 'open'
        }
        # print(f"\n✅ TRADE OPENED at {current_time}: {trade_signal}")

    def _check_open_trades(self):
        """وضعیت معامله باز را در هر کندل بررسی می‌کند."""
        if self.open_trade is None:
            return None

        current_bar = self.df.iloc[self.current_tick_index - 1]
        trade = self.open_trade
        
        hit = None
        pnl = 0

        if trade['type'] == 'BUY':
            if current_bar['low'] <= trade['sl']:
                hit = 'SL'
            elif current_bar['high'] >= trade['tp']:
                hit = 'TP'
        elif trade['type'] == 'SELL':
            if current_bar['high'] >= trade['sl']:
                hit = 'SL'
            elif current_bar['low'] <= trade['tp']:
                hit = 'TP'
        
        if hit:
            exit_price = trade[hit.lower()]
            pnl = (exit_price - trade['entry_price']) if trade['type'] == 'BUY' else (trade['entry_price'] - exit_price)
            
            # بستن معامله
            trade['status'] = 'closed'
            trade['exit_time'] = current_bar.name
            trade['exit_price'] = exit_price
            trade['pnl'] = pnl
            trade['result'] = 'Win' if hit == 'TP' else 'Loss'
            
            self.trade_history.append(trade)
            self.balance += pnl # ساده‌سازی: محاسبه PnL بدون در نظر گرفتن حجم
            self.open_trade = None
            
            # اطلاع به استراتژی که معامله بسته شده است
            if hasattr(self.strategy, 'signal_position_closed'):
                self.strategy.signal_position_closed()
            
            return trade
        return None


    def _generate_report(self):
        """یک گزارش نهایی از نتایج بک‌تست تولید و چاپ می‌کند."""
        print("\n--- Backtest Report ---")
        
        # بخش ۱: خلاصه وضعیت مالی
        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Final Balance:   ${self.balance:,.2f}")
        
        total_pnl = self.balance - self.initial_balance
        # جلوگیری از خطای تقسیم بر صفر اگر بالانس اولیه صفر باشد
        pnl_percentage = (total_pnl / self.initial_balance) * 100 if self.initial_balance != 0 else 0.0
        
        print(f"Total Net PnL:   ${total_pnl:,.2f} ({pnl_percentage:.2f}%)")
        print("-" * 25)

        if not self.trade_history:
            print("No trades were executed.")
            return

        # بخش ۲: آمار معاملات
        total_trades = len(self.trade_history)
        wins = len([t for t in self.trade_history if t['result'] == 'Win'])
        losses = total_trades - wins
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # محاسبه Profit Factor (مجموع سودها تقسیم بر مجموع ضررها)
        total_win_pnl = sum(t['pnl'] for t in self.trade_history if t['result'] == 'Win')
        total_loss_pnl = abs(sum(t['pnl'] for t in self.trade_history if t['result'] == 'Loss'))
        # جلوگیری از خطای تقسیم بر صفر اگر هیچ معامله ضرردهی وجود نداشته باشد
        profit_factor = total_win_pnl / total_loss_pnl if total_loss_pnl > 0 else float('inf')

        print(f"Total Trades:    {total_trades}")
        print(f"Winning Trades:  {wins}")
        print(f"Losing Trades:   {losses}")
        print(f"Win Rate:        {win_rate:.2f}%")
        print(f"Profit Factor:   {profit_factor:.2f}")

