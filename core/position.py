# core/position.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Position:
    """کلاس مدل پوزیشن"""
    direction: str  # 'BUY' or 'SELL'
    volume: float
    entry_price: float
    sl: float
    tp: float
    entry_time: datetime
    
    # اختیاری - برای بعد از بسته شدن
    close_price: Optional[float] = None
    close_time: Optional[datetime] = None
    pnl: Optional[float] = None
    closed_by: Optional[str] = None  # 'SL', 'TP', 'MANUAL'
    
    def is_open(self) -> bool:
        """آیا پوزیشن باز است؟"""
        return self.close_price is None
    
    def to_dict(self) -> dict:
        """تبدیل به دیکشنری"""
        return {
            'direction': self.direction,
            'volume': self.volume,
            'entry_price': self.entry_price,
            'sl': self.sl,
            'tp': self.tp,
            'entry_time': self.entry_time,
            'close_price': self.close_price,
            'close_time': self.close_time,
            'pnl': self.pnl,
            'closed_by': self.closed_by
        }
