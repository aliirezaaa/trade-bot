# strategies/ema_strategy.py

import pandas as pd
import pandas_ta as ta
from .ema_signal_generator import EmaSignalGenerator
from .ema_order_calculator import EmaOrderCalculator

class EmaPullbackStrategy:
    def __init__(self, risk_to_reward, atr_period, ema_slow, ema_fast, ema_long, impulse_atr_multiplier, sl_atr_multiplier):
        self.broker = None # بروکر توسط موتور بک‌تست تزریق خواهد شد
        self.position_open = False
        
        self.ema_long_period = ema_long
        self.N_BARS_FOR_ENTRY = self.ema_long_period + 5 

        self.signal_generator = EmaSignalGenerator(impulse_atr_multiplier=impulse_atr_multiplier)
        self.order_calculator = EmaOrderCalculator(risk_to_reward=risk_to_reward, sl_atr_multiplier=sl_atr_multiplier)
        
        self.atr_period = atr_period
        self.ema_slow_period = ema_slow
        self.ema_fast_period = ema_fast

        print("✅ EmaPullbackStrategy Initialized with Long-Term Trend Filter.")

    def on_bar(self, candles: pd.DataFrame):
        if self.position_open:
            return

        self._calculate_indicators(candles)

        signal_type = self.signal_generator.check(candles)

        if signal_type:
            order_details = self.order_calculator.calculate(candles, signal_type)
            
            if order_details:
                self.broker.place_market_order(
                    order_type=signal_type,
                    sl_price=order_details['sl'],
                    tp_price=order_details['tp']
                )
                self.position_open = True
    
    def on_position_closed(self, trade_info: dict):
        self.position_open = False
        self.signal_generator.reset()
        # print(f"INFO [{trade_info['close_time']}]: Position closed. Strategy reset.")

    def _calculate_indicators(self, candles: pd.DataFrame):
        candles['ATR'] = ta.atr(candles['high'], candles['low'], candles['close'], length=self.atr_period)
        candles['EMA_slow'] = ta.ema(candles['close'], length=self.ema_slow_period)
        candles['EMA_fast'] = ta.ema(candles['close'], length=self.ema_fast_period)
        candles['EMA_long'] = ta.ema(candles['close'], length=self.ema_long_period)
        candles.dropna(inplace=True)
