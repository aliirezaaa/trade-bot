# File: core/portfolio.py

class Portfolio:
    """
    مسئول تحلیل تاریخچه معاملات و تولید گزارش‌های آماری عملکرد است.
    """
    def __init__(self):
        print("✅ Portfolio Manager Initialized.")

    def generate_report(self, trade_history: list, initial_balance: float, final_balance: float):
        """گزارش نهایی بک‌تست را چاپ می‌کند."""
        print("\n" + "="*60)
        print("--- Backtest Finished: Performance Report ---")
        print("="*60)
        
        total_trades = len(trade_history)
        if total_trades == 0:
            print("No trades were executed.")
            print(f"Final Balance:   ${final_balance:,.2f}")
            return

        wins = [t for t in trade_history if t['pnl'] >= 0]
        losses = [t for t in trade_history if t['pnl'] < 0]
        
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
        total_pnl = sum(t['pnl'] for t in trade_history)
        total_win_pnl = sum(t['pnl'] for t in wins)
        total_loss_pnl = abs(sum(t['pnl'] for t in losses))
        profit_factor = total_win_pnl / total_loss_pnl if total_loss_pnl > 0 else float('inf')

        print(f"Initial Balance: ${initial_balance:,.2f}")
        print(f"Final Balance:   ${final_balance:,.2f}")
        print(f"Total Net PnL:   ${total_pnl:,.2f} ({((final_balance/initial_balance)-1)*100:.2f}%)")
        print("-" * 35)
        print(f"Total Trades:    {total_trades}")
        print(f"Winning Trades:  {len(wins)}")
        print(f"Losing Trades:   {len(losses)}")
        print(f"Win Rate:        {win_rate:.2f}%")
        print(f"Profit Factor:   {profit_factor:.2f}")
        print("="*60)
