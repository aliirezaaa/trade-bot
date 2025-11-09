# File: strategies/ema_strategy.py (نسخه نهایی)

import pandas as pd
import pandas_ta as ta
from .ema_signal_generator import EmaSignalGenerator
from .ema_order_calculator import EmaOrderCalculator

class EmaPullbackStrategy:
    def __init__(self, broker, risk_to_reward: float, atr_period: int,
                 ema_slow: int, ema_fast: int,
                 impulse_atr_multiplier: float, sl_atr_multiplier: float):
        
        self.broker = broker
        self.signal_generator = EmaSignalGenerator(impulse_atr_multiplier)
        self.order_calculator = EmaOrderCalculator(risk_to_reward, sl_atr_multiplier)
        
        # پارامترهای اندیکاتور
        self.atr_period = atr_period
        self.ema_slow_period = ema_slow
        self.ema_fast_period = ema_fast

        self.position_open = False
        # موتور بک‌تست باید حداقل به این تعداد کندل برای استراتژی فراهم کند
        self.N_BARS_FOR_ENTRY = self.ema_slow_period + 5 

        print("✅ EmaPullbackStrategy Initialized.")

    def on_bar(self, candles: pd.DataFrame):
        if self.position_open:
            return

        self._calculate_indicators(candles)
        signal_type = self.signal_generator.check(candles)

        if signal_type:
            last_candle = candles.iloc[-1]
            order_details = None

            if signal_type == 'BUY':
                order_details = self.order_calculator.calculate_buy_order(last_candle)
            elif signal_type == 'SELL':
                order_details = self.order_calculator.calculate_sell_order(last_candle)

            if order_details:
                # <<< تغییر اصلی: ارسال last_candle به بروکر >>>
                self.broker.place_market_order(
                    direction=signal_type,
                    sl=order_details['sl'],
                    tp=order_details['tp'],
                    current_bar=last_candle # بروکر به این کندل برای قیمت ورود نیاز دارد
                )
                self.position_open = True

    def signal_position_closed(self):
        self.position_open = False
        self.signal_generator.reset()
        # print("INFO (Strategy): Acknowledged position closed. Ready for new signals.")

    def _calculate_indicators(self, candles: pd.DataFrame):
        candles['ATR'] = ta.atr(candles['high'], candles['low'], candles['close'], length=self.atr_period)
        candles['EMA_slow'] = ta.ema(candles['close'], length=self.ema_slow_period)
        candles['EMA_fast'] = ta.ema(candles['close'], length=self.ema_fast_period)
        candles.dropna(inplace=True)
