# core/risk_manager.py

class RiskManager:
    def __init__(self, risk_per_trade_usd: float, pip_size: float, pip_value_per_lot: float, min_lot: float = 0.01):
        self.risk_per_trade_usd = risk_per_trade_usd
        self.pip_size = pip_size
        self.pip_value_per_lot = pip_value_per_lot
        self.min_lot = min_lot

    def calculate_lot_size(self, entry_price: float, sl_price: float):
        sl_pips = abs(entry_price - sl_price) / self.pip_size
        if sl_pips <= 0:
            return 0.0

        value_per_pip = self.risk_per_trade_usd / sl_pips
        lot_size = value_per_pip / self.pip_value_per_lot
        
        lot_size_rounded = round(lot_size / self.min_lot) * self.min_lot
        
        return max(self.min_lot, lot_size_rounded)
