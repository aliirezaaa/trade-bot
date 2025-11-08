# File: backtest_engine.py (نسخه نهایی با ریسک ثابت دلاری - بر اساس فایل شما)

import pandas as pd
import os
from tqdm import tqdm

class BacktestEngine:
    # <<< تغییر ۱: پارامتر ورودی از risk_per_trade_percent به risk_per_trade_usd تغییر کرد >>>
    def __init__(self, csv_filepath, strategy_class, initial_balance=10000.0, risk_per_trade_usd=50.0, pip_size=0.0001, pip_value_per_lot=10.0):
        self.data_path = csv_filepath
        self.initial_balance = initial_balance
        self.balance = initial_balance
        
        # <<< تغییر ۲: ذخیره کردن ریسک ثابت دلاری >>>
        self.risk_per_trade_usd = risk_per_trade_usd
        
        self.df = self._load_data(csv_filepath)
        if self.df is None or self.df.empty:
            raise ValueError("Data could not be loaded. Aborting.")

        # شما می‌توانید پارامترهای استراتژی را از runner.py به اینجا پاس دهید
        self.strategy = strategy_class(broker=self, risk_to_reward=2.0) 

        self.current_tick_index = 0
        self.open_positions = []
        self.trade_history = []
        
        # --- مشخصات نماد (اکنون از ورودی دریافت می‌شود) ---
        self.min_lot = 0.01
        self.pip_size = pip_size
        self.pip_value_per_lot = pip_value_per_lot

    def _load_data(self, csv_filepath):
        if not os.path.exists(csv_filepath):
            print(f"❌ ERROR: Historical data file not found at: {csv_filepath}")
            return None
        try:
            # این بخش برای خواندن فایل‌های استاندارد CSV با هدر است
            try:
                df = pd.read_csv(csv_filepath, parse_dates=['datetime'], index_col='datetime')
                print(f"✅ Data loaded successfully from standard CSV. {len(df)} bars.")
                return df
            except (ValueError, KeyError):
                 # اگر فرمت بالا ناموفق بود، فرمت تب-جداشده متاتریدر را امتحان می‌کند
                print("Standard CSV failed, trying MT5 tab-separated format...")
                df = pd.read_csv(
                    csv_filepath,
                    sep='\t',
                    header=None,
                    names=['date', 'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
                )
                df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%Y.%m.%d %H:%M:%S')
                df.set_index('datetime', inplace=True)
                df.drop(['date', 'time', 'spread', 'real_volume'], axis=1, inplace=True)
                print(f"✅ Data loaded successfully from MT5 format. {len(df)} bars.")
                return df
        except Exception as e:
            print(f"❌ ERROR: Failed to load or parse data file. Error: {e}")
            return None

    def get_current_bar(self):
        return self.df.iloc[self.current_tick_index]

    def get_historical_data(self, n_bars: int):
        if self.current_tick_index < n_bars:
            return pd.DataFrame()
        start_index = self.current_tick_index - n_bars
        return self.df.iloc[start_index:self.current_tick_index].copy()

    def run(self):
        print("\n--- Starting backtest... ---")
        print(f"Risk model: Fixed Amount (${self.risk_per_trade_usd:.2f} per trade)")
        for i in tqdm(range(len(self.df)), desc="Backtesting Progress"):
            self.current_tick_index = i
            
            self._check_open_trades()
            
            current_bar = self.get_current_bar()
            self.strategy.on_bar(current_bar)
            
        self._generate_report()

    def _check_open_trades(self):
        if not self.open_positions:
            return
        
        positions_to_close = []
        current_bar = self.get_current_bar()
        
        for pos in self.open_positions:
            pnl = 0
            closed_by = None
            
            if pos['direction'] == 'BUY':
                if current_bar['low'] <= pos['sl']:
                    closed_by, close_price = 'SL', pos['sl']
                elif current_bar['high'] >= pos['tp']:
                    closed_by, close_price = 'TP', pos['tp']
            elif pos['direction'] == 'SELL':
                if current_bar['high'] >= pos['sl']:
                    closed_by, close_price = 'SL', pos['sl']
                elif current_bar['low'] <= pos['tp']:
                    closed_by, close_price = 'TP', pos['tp']

            if closed_by:
                pnl_pips = (close_price - pos['entry_price']) / self.pip_size if pos['direction'] == 'BUY' else (pos['entry_price'] - close_price) / self.pip_size
                pnl = pnl_pips * self.pip_value_per_lot * pos['volume']
                
                self.balance += pnl
                pos['pnl'] = pnl
                pos['close_price'] = close_price
                pos['close_time'] = current_bar.name
                self.trade_history.append(pos)
                positions_to_close.append(pos)
                
                result_icon = '🔴' if pnl < 0 else '🟢'
                print(f"\n{result_icon} Position Closed by {closed_by}: {pos['direction']} {pos['volume']} lot. PnL: ${pnl:.2f}. Balance: ${self.balance:.2f}")

        if positions_to_close:
            self.open_positions = [p for p in self.open_positions if p not in positions_to_close]
            if hasattr(self.strategy, 'signal_position_closed'):
                for closed_pos in positions_to_close:
                    self.strategy.signal_position_closed(closed_pos)


    def _calculate_lot_size(self, risk_amount_usd, sl_pips):
        if sl_pips <= 0: return 0
        value_per_pip = risk_amount_usd / sl_pips
        lot_size = value_per_pip / self.pip_value_per_lot
        # گرد کردن به نزدیک‌ترین 0.01 (گام استاندارد لات)
        lot_size_rounded = round(lot_size / self.min_lot) * self.min_lot
        return max(self.min_lot, lot_size_rounded)

    def place_market_order(self, direction, sl, tp):
        if self.open_positions:
            return

        # <<< تغییر ۳: استفاده مستقیم از مبلغ ریسک ثابت به جای محاسبه درصدی >>>
        risk_amount_usd = self.risk_per_trade_usd
        
        current_bar = self.get_current_bar()
        entry_price = current_bar['close']

        sl_pips = abs(entry_price - sl) / self.pip_size
        
        if sl_pips == 0:
            print("  ⚠️ SL distance is zero. Skipping trade.")
            return

        lot_size = self._calculate_lot_size(risk_amount_usd, sl_pips)

        if lot_size < self.min_lot:
            print(f"  ⚠️ Calculated lot size ({lot_size}) is below minimum. Skipping trade.")
            return

        position = {
            'direction': direction,
            'volume': lot_size,
            'entry_price': entry_price,
            'sl': sl,
            'tp': tp,
            'entry_time': current_bar.name
        }
        self.open_positions.append(position)
        print(f"\n🔵 New Position Opened: {direction} {lot_size} lot @ {entry_price:.5f}, SL={sl:.5f}, TP={tp:.5f}. Risking ~${risk_amount_usd:.2f}")

    def _generate_report(self):
        print("\n" + "="*50)
        print("--- Backtest Finished: Results ---")
        print("="*50)
        
        total_trades = len(self.trade_history)
        if total_trades == 0:
            print("No trades were executed.")
            print(f"Final Balance:   ${self.balance:,.2f}")
            return

        pnl = self.balance - self.initial_balance
        pnl_percent = (pnl / self.initial_balance) * 100

        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Final Balance:   ${self.balance:,.2f}")
        print(f"Net Profit/Loss: ${pnl:,.2f} ({pnl_percent:.2f}%)")
        print("-" * 50)
        print(f"Total Trades:    {total_trades}")
        
        wins = [t for t in self.trade_history if t['pnl'] >= 0]
        losses = [t for t in self.trade_history if t['pnl'] < 0]
        
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
        
        total_win_pnl = sum(t['pnl'] for t in wins)
        total_loss_pnl = abs(sum(t['pnl'] for t in losses))
        
        avg_win = total_win_pnl / len(wins) if wins else 0
        avg_loss = total_loss_pnl / len(losses) if losses else 0
        
        profit_factor = total_win_pnl / total_loss_pnl if total_loss_pnl > 0 else float('inf')
        
        print(f"Win Rate:        {win_rate:.2f}% ({len(wins)} wins / {len(losses)} losses)")
        print(f"Average Win:     ${avg_win:,.2f}")
        print(f"Average Loss:    ${avg_loss:,.2f}")
        print(f"Profit Factor:   {profit_factor:.2f}")
        print("="*50)
