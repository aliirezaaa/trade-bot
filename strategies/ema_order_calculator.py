# strategies/ema_order_calculator.py

import pandas as pd

class EmaOrderCalculator:
    def __init__(self, risk_to_reward: float, sl_atr_multiplier: float):
        self.risk_to_reward = risk_to_reward
        self.sl_atr_multiplier = sl_atr_multiplier

    def calculate(self, candles: pd.DataFrame, signal_type: str):
        if signal_type == 'BUY':
            return self._calculate_buy_order(candles)
        elif signal_type == 'SELL':
            return self._calculate_sell_order(candles)
        return None

    def _calculate_buy_order(self, candles: pd.DataFrame):
        last = candles.iloc[-1]
        entry_price = last['close'] 
        sl_distance = self.sl_atr_multiplier * last['ATR']
        sl_price = last['EMA_slow'] - sl_distance
        
        if entry_price <= sl_price:
            return None
            
        risk_per_share = entry_price - sl_price
        tp_price = entry_price + (risk_per_share * self.risk_to_reward)
        return {'sl': sl_price, 'tp': tp_price}

    def _calculate_sell_order(self, candles: pd.DataFrame):
        last = candles.iloc[-1]
        entry_price = last['close']
        sl_distance = self.sl_atr_multiplier * last['ATR']
        sl_price = last['EMA_slow'] + sl_distance
        
        if entry_price >= sl_price:
            return None
        
        risk_per_share = sl_price - entry_price
        tp_price = entry_price - (risk_per_share * self.risk_to_reward)
        return {'sl': sl_price, 'tp': tp_price}
