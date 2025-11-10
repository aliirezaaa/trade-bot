# core/portfolio.py

class Portfolio:
    def __init__(self, initial_balance: float):
        self.initial_balance = initial_balance
        self.trade_history = []

    def add_trades(self, trades: list):
        self.trade_history.extend(trades)

    def generate_report(self, final_balance: float):
        print("\n" + "="*50)
        print("--- Backtest Finished: Results ---")
        print("="*50)

        total_trades = len(self.trade_history)
        if total_trades == 0:
            print("No trades were executed.")
            print(f"Final Balance:   ${final_balance:,.2f}")
            return

        pnl = final_balance - self.initial_balance
        pnl_percent = (pnl / self.initial_balance) * 100

        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Final Balance:   ${final_balance:,.2f}")
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
