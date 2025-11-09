# File: core/risk_manager.py

class RiskManager:
    """
    مسئولیت محاسبه حجم معامله (lot size) را بر اساس قوانین مدیریت ریسک دارد.
    """
    def __init__(self, risk_per_trade_usd: float, pip_size: float, pip_value_per_lot: float):
        self.risk_per_trade_usd = risk_per_trade_usd
        self.pip_size = pip_size
        self.pip_value_per_lot = pip_value_per_lot
        print(f"✅ RiskManager Initialized. Risk per trade: ${self.risk_per_trade_usd:.2f}")

    def calculate_lot_size(self, entry_price: float, sl_price: float) -> float:
        """
        حجم معامله را بر اساس ریسک ثابت دلاری محاسبه می‌کند.
        """
        sl_pips = abs(entry_price - sl_price) / self.pip_size
        
        if sl_pips == 0:
            print("⚠️ WARNING (RiskManager): Stop loss distance is zero. Cannot calculate lot size.")
            return 0.0

        risk_value_per_pip = self.risk_per_trade_usd / sl_pips
        lot_size = risk_value_per_pip / self.pip_value_per_lot

        # گرد کردن به دو رقم اعشار برای لات سایز استاندارد
        final_lot_size = round(lot_size, 2)

        # اطمینان از اینکه حجم کمتر از حداقل (0.01) نباشد
        if final_lot_size < 0.01:
            return 0.01
            
        return final_lot_size
