# File: backtest_engine.py
# Version: Final with advanced features for the new runner

import pandas as pd
import os
import uuid

class BacktestBroker:
    """
    A simulated broker for backtesting purposes. It loads data, manages trades,
    and calculates performance.
    """
    def __init__(self, csv_filepath, initial_balance=10000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.data = self._load_data(csv_filepath)
        self.total_bars = len(self.data)
        self.current_tick_index = -1

        self.open_positions = []
        self.trade_history = []

        # Assuming EURUSD with 5 decimal places for pip calculation
        self._point_value = 0.00001
        self._pip_value_per_lot = 0.1 # For a standard lot, each pip is ~$10

        if self.total_bars > 0:
            print(f"✅ BacktestBroker Initialized. Loaded {self.total_bars} bars from {os.path.basename(csv_filepath)}.")
        else:
            print(f"⚠️ Warning: Data could not be loaded or the file is empty: {csv_filepath}")

    def _load_data(self, csv_filepath):
        """Loads and formats data from a CSV file."""
        if not os.path.exists(csv_filepath):
            print(f"❌ ERROR: Historical data file not found at: {csv_filepath}")
            return pd.DataFrame()

        try:
            # This logic is designed for MT5's default CSV export format (tab-separated)
            df = pd.read_csv(
                csv_filepath,
                sep='\t',
                header=None,
                names=['date', 'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            )
            df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%Y.%m.%d %H:%M:%S')
            df.set_index('datetime', inplace=True)
            # Keep only the essential columns
            df = df[['open', 'high', 'low', 'close', 'tick_volume']]
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            return df
        except Exception as e:
            # Fallback for standard comma-separated CSV with header
            try:
                print("Attempting to read as standard CSV...")
                df = pd.read_csv(csv_filepath)
                # Try to guess datetime column format
                if 'datetime' in [c.lower() for c in df.columns]:
                     dt_col = [c for c in df.columns if c.lower() == 'datetime'][0]
                     df['datetime'] = pd.to_datetime(df[dt_col])
                elif 'date' in [c.lower() for c in df.columns] and 'time' in [c.lower() for c in df.columns]:
                     date_col = [c for c in df.columns if c.lower() == 'date'][0]
                     time_col = [c for c in df.columns if c.lower() == 'time'][0]
                     df['datetime'] = pd.to_datetime(df[date_col] + ' ' + df[time_col])
                else:
                    raise ValueError("Could not find standard datetime columns (e.g., 'Date', 'Time')")

                df.set_index('datetime', inplace=True)
                
                # Standardize column names (case-insensitive)
                col_map = {col.lower(): col for col in df.columns}
                df = df[[col_map['open'], col_map['high'], col_map['low'], col_map['close'], col_map['volume']]]
                df.columns = ['open', 'high', 'low', 'close', 'volume']
                print("Successfully loaded standard CSV.")
                return df
            except Exception as e_inner:
                print(f"❌ ERROR: Failed to load or parse data file. Tried MT5 format and standard CSV. Error: {e_inner}")
                return pd.DataFrame()


    def advance_time_to(self, index: int):
        """
        Directly sets the current time to a specific bar index and checks positions.
        This is much faster for backtesting.
        """
        if 0 <= index < self.total_bars:
            self.current_tick_index = index
            self._check_positions() # Check SL/TP on the new bar
            return True
        return False

    def get_historical_data(self, window_size: int) -> pd.DataFrame:
        """
        Returns a rolling window of historical data up to the current tick.
        """
        if self.current_tick_index < 0:
            return pd.DataFrame()
        
        end_index = self.current_tick_index + 1
        start_index = max(0, end_index - window_size)
        return self.data.iloc[start_index:end_index]

    def place_market_order(self, symbol, direction, volume, sl, tp):
        """
        Simulates placing a market order. The order is executed at the 'open'
        price of the *next* bar to avoid lookahead bias.
        """
        if self.current_tick_index + 1 >= self.total_bars:
            # print("⚠️ Cannot place order, end of data reached.")
            return

        entry_price = self.data.iloc[self.current_tick_index + 1]['open']
        entry_time = self.data.index[self.current_tick_index + 1]

        position = {
            'id': str(uuid.uuid4()),
            'symbol': symbol,
            'direction': direction,
            'volume': volume,
            'entry_price': entry_price,
            'entry_time': entry_time,
            'sl': sl,
            'tp': tp,
            'status': 'open'
        }
        self.open_positions.append(position)
        # print(f"  -> Market Order Placed: {direction} {volume} lot(s) of {symbol} at {entry_price:.5f}")

    def _check_positions(self):
        """
        On each new bar, check if any open positions have hit their SL or TP.
        """
        if not self.open_positions:
            return

        current_bar = self.data.iloc[self.current_tick_index]
        
        for pos in self.open_positions[:]: # Iterate over a copy
            if pos['direction'] == 'BUY':
                if current_bar['low'] <= pos['sl']:
                    self._close_position(pos, pos['sl'], current_bar.name, 'SL Hit')
                elif current_bar['high'] >= pos['tp']:
                    self._close_position(pos, pos['tp'], current_bar.name, 'TP Hit')

            elif pos['direction'] == 'SELL':
                if current_bar['high'] >= pos['sl']:
                    self._close_position(pos, pos['sl'], current_bar.name, 'SL Hit')
                elif current_bar['low'] <= pos['tp']:
                    self._close_position(pos, pos['tp'], current_bar.name, 'TP Hit')
    
    def _close_position(self, position, exit_price, exit_time, reason):
        """Closes a position, calculates P/L, and moves it to history."""
        
        price_diff = 0
        if position['direction'] == 'BUY':
            price_diff = exit_price - position['entry_price']
        else: # SELL
            price_diff = position['entry_price'] - exit_price
        
        pips = price_diff / self._point_value / 10
        pnl = pips * self._pip_value_per_lot * position['volume']

        self.balance += pnl

        trade_log = {
            **position,
            'exit_price': exit_price,
            'exit_time': exit_time,
            'pnl': pnl,
            'status': 'closed',
            'reason': reason
        }
        
        self.trade_history.append(trade_log)
        self.open_positions.remove(position)
        
        log_message_color = "✅ WIN:" if pnl > 0 else "❌ LOSS:"
        print(f"{log_message_color} Closed {position['direction']} Trade. P/L: ${pnl:,.2f}. Reason: {reason}. Balance: ${self.balance:,.2f}")

    def report_results(self):
        """Prints a final summary of the backtest performance."""
        if not self.trade_history:
            print("\n--- Backtest Report ---")
            print("No trades were executed.")
            print(f"Final Balance:   ${self.balance:,.2f}")
            return

        total_trades = len(self.trade_history)
        wins = [t for t in self.trade_history if t['pnl'] > 0]
        losses = [t for t in self.trade_history if t['pnl'] <= 0]
        
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
        total_pnl = sum(t['pnl'] for t in self.trade_history)
        
        total_win_pnl = sum(t['pnl'] for t in wins)
        total_loss_pnl = sum(t['pnl'] for t in losses)
        
        profit_factor = abs(total_win_pnl / total_loss_pnl) if total_loss_pnl != 0 else float('inf')
        
        print("\n--- Backtest Report ---")
        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Final Balance:   ${self.balance:,.2f}")
        print("-" * 25)
        print(f"Total Net Profit:  ${total_pnl:,.2f} ({(total_pnl/self.initial_balance)*100:.2f}%)")
        print(f"Total Trades:      {total_trades}")
        print(f"Win Rate:          {win_rate:.2f}%")
        print(f"Profit Factor:     {profit_factor:.2f}")
        print(f"Winning Trades:    {len(wins)}")
        print(f"Losing Trades:     {len(losses)}")
        print("-" * 25)
