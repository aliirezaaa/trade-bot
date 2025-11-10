# core/broker.py

class Broker:
    def __init__(self, initial_balance: float, risk_manager, pip_size: float):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.risk_manager = risk_manager
        self.pip_size = pip_size
        self.open_positions = []
        self.trade_history = []
        self.on_position_closed_callback = None

    def register_on_close_callback(self, callback_func):
        self.on_position_closed_callback = callback_func

    def place_market_order(self, order_type: str, sl_price: float, tp_price: float):
        if self.open_positions:
            return

        entry_price = self.current_bar['close']
        lot_size = self.risk_manager.calculate_lot_size(entry_price, sl_price)

        if lot_size < self.risk_manager.min_lot:
            print(f"  ⚠️ Calculated lot size ({lot_size}) is below minimum. Skipping trade.")
            return

        position = {
            'type': order_type, 'volume': lot_size,
            'entry_price': entry_price, 'sl_price': sl_price, 'tp_price': tp_price,
            'entry_time': self.current_bar.name, 'pnl': 0.0,
            'close_price': None, 'close_time': None
        }
        self.open_positions.append(position)
        risk_usd = self.risk_manager.risk_per_trade_usd
        print(f"\n🔵 [{self.current_bar.name}] New Position: {order_type} {lot_size} lot @ {entry_price:.5f}, SL={sl_price:.5f}, TP={tp_price:.5f}. Risking ~${risk_usd:.2f}")

    def check_open_trades(self, current_bar):
        self.current_bar = current_bar
        if not self.open_positions:
            return

        positions_to_close = []
        for pos in self.open_positions:
            closed_by = None
            close_price = None

            if pos['type'] == 'BUY':
                if current_bar['low'] <= pos['sl_price']:
                    closed_by, close_price = 'SL', pos['sl_price']
                elif current_bar['high'] >= pos['tp_price']:
                    closed_by, close_price = 'TP', pos['tp_price']
            elif pos['type'] == 'SELL':
                if current_bar['high'] >= pos['sl_price']:
                    closed_by, close_price = 'SL', pos['sl_price']
                elif current_bar['low'] <= pos['tp_price']:
                    closed_by, close_price = 'TP', pos['tp_price']

            if closed_by:
                pnl = self._calculate_pnl(pos, close_price)
                self.balance += pnl
                pos.update({
                    'pnl': pnl, 'close_price': close_price,
                    'close_time': current_bar.name
                })
                self.trade_history.append(pos)
                positions_to_close.append(pos)

                result_icon = '🔴' if pnl < 0 else '🟢'
                print(f"{result_icon} [{current_bar.name}] Position Closed by {closed_by}: PnL: ${pnl:.2f}. Balance: ${self.balance:.2f}")
                
                if self.on_position_closed_callback:
                    self.on_position_closed_callback(pos)

        if positions_to_close:
            self.open_positions = [p for p in self.open_positions if p not in positions_to_close]
            
    def close_all_open_positions(self, final_bar):
        closed_trades = []
        if not self.open_positions:
            return closed_trades
        
        print(f"\n--- Closing all open positions at the end of backtest at {final_bar.name} ---")
        for pos in self.open_positions:
            close_price = final_bar['close']
            pnl = self._calculate_pnl(pos, close_price)
            self.balance += pnl
            pos.update({
                'pnl': pnl, 'close_price': close_price,
                'close_time': final_bar.name
            })
            closed_trades.append(pos)
            print(f"⚪️ Position Closed (End of Data): PnL: ${pnl:.2f}. Balance: ${self.balance:.2f}")
        
        self.open_positions = []
        return closed_trades
            
    def _calculate_pnl(self, position, close_price):
        pnl_pips = 0
        if position['type'] == 'BUY':
            pnl_pips = (close_price - position['entry_price']) / self.pip_size
        else: # SELL
            pnl_pips = (position['entry_price'] - close_price) / self.pip_size
        
        pnl_usd = pnl_pips * self.risk_manager.pip_value_per_lot * position['volume']
        return pnl_usd
