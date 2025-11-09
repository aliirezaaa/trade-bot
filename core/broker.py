# File: core/broker.py (نسخه نهایی)

class BacktestBroker:
    """
    یک بروکر را برای اهداف بک‌تست شبیه‌سازی می‌کند.
    """
    def __init__(self, initial_balance: float, risk_manager):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.risk_manager = risk_manager
        
        self.open_positions = []
        self.trade_history = []
        
        # این متغیر برای نگهداری متد callback استراتژی است
        self.on_position_closed_callback = None
        
        print(f"✅ Broker Initialized. Initial Balance: ${self.initial_balance:,.2f}")

    def set_strategy_callbacks(self, position_closed):
        """
        متدهای بازگشتی (callbacks) را از استراتژی دریافت و ذخیره می‌کند.
        این متد باید از runner.py فراخوانی شود.
        """
        self.on_position_closed_callback = position_closed
        print("🔗 Broker is now linked with strategy callbacks.")

    def place_market_order(self, direction: str, sl: float, tp: float, current_bar):
        # ... (بقیه کد این متد بدون تغییر باقی می‌ماند)
        entry_price = current_bar['close']
        
        lot_size = self.risk_manager.calculate_lot_size(entry_price, sl)
        
        if lot_size < 0.01:
            print("❌ ORDER FAILED (Broker): Lot size is too small after calculation. Skipping trade.")
            return

        position = {
            'direction': direction,
            'lot_size': lot_size,
            'entry_price': entry_price,
            'sl': sl,
            'tp': tp,
            'entry_time': current_bar.name,
            'pnl': 0.0,
            'close_price': None,
            'close_time': None
        }
        self.open_positions.append(position)
        print(f"  -> 🔵 ORDER PLACED: {direction} {lot_size} lots @ {entry_price:.5f} | SL={sl:.5f} TP={tp:.5f}")


    def check_open_trades(self, current_bar):
        # ... (منطق بررسی SL/TP بدون تغییر باقی می‌ماند)
        positions_to_close = []
        for pos in self.open_positions:
            # ... (کد بررسی SL/TP)
            closed_by = None
            close_price = None

            if pos['direction'] == 'BUY':
                if current_bar['low'] <= pos['sl']: closed_by, close_price = 'SL', pos['sl']
                elif current_bar['high'] >= pos['tp']: closed_by, close_price = 'TP', pos['tp']
            elif pos['direction'] == 'SELL':
                if current_bar['high'] >= pos['sl']: closed_by, close_price = 'SL', pos['sl']
                elif current_bar['low'] <= pos['tp']: closed_by, close_price = 'TP', pos['tp']

            if closed_by:
                # ... (کد محاسبه PnL)
                pnl_pips = (close_price - pos['entry_price']) if pos['direction'] == 'BUY' else (pos['entry_price'] - close_price)
                pnl_pips /= self.risk_manager.pip_size
                pnl_usd = pnl_pips * pos['lot_size'] * self.risk_manager.pip_value_per_lot
                self.balance += pnl_usd
                
                pos.update({'pnl': pnl_usd, 'close_price': close_price, 'close_time': current_bar.name})
                self.trade_history.append(pos)
                positions_to_close.append(pos)
                
                status = "WIN" if pnl_usd >= 0 else "LOSS"
                print(f"  -> 🔴 POSITION CLOSED by {closed_by} ({status}): PnL=${pnl_usd:,.2f}, Balance=${self.balance:,.2f}")

                # <<< تغییر اصلی: فراخوانی callback ذخیره شده >>>
                if self.on_position_closed_callback:
                    self.on_position_closed_callback()

        self.open_positions = [p for p in self.open_positions if p not in positions_to_close]
