# strategies/ema_signal_generator.py

import pandas as pd

class EmaSignalGenerator:
    def __init__(self, impulse_atr_multiplier: float):
        self.impulse_atr_multiplier = impulse_atr_multiplier
        self.reset()

    def reset(self):
        self.impulse_confirmed = {'BUY': False, 'SELL': False}

    def check(self, candles: pd.DataFrame):
        last_candle = candles.iloc[-1]

        is_main_uptrend = last_candle['close'] > last_candle['EMA_long']
        is_main_downtrend = last_candle['close'] < last_candle['EMA_long']

        if is_main_uptrend:
            return self._check_buy_setup(candles)
        elif is_main_downtrend:
            return self._check_sell_setup(candles)
        return None

    def _check_buy_setup(self, candles: pd.DataFrame):
        last = candles.iloc[-1]
        prev = candles.iloc[-2]

        if last['close'] < last['EMA_slow']:
            self.reset()
            return None

        if not self.impulse_confirmed['BUY']:
            impulse_distance = self.impulse_atr_multiplier * last['ATR']
            if last['high'] > (last['EMA_fast'] + impulse_distance):
                self.impulse_confirmed['BUY'] = True
                self.impulse_confirmed['SELL'] = False
            return None

        if prev['low'] > prev['EMA_fast'] and last['low'] <= last['EMA_fast']:
            return 'BUY'
        return None

    def _check_sell_setup(self, candles: pd.DataFrame):
        last = candles.iloc[-1]
        prev = candles.iloc[-2]

        if last['close'] > last['EMA_slow']:
            self.reset()
            return None
            
        if not self.impulse_confirmed['SELL']:
            impulse_distance = self.impulse_atr_multiplier * last['ATR']
            if last['low'] < (last['EMA_fast'] - impulse_distance):
                self.impulse_confirmed['SELL'] = True
                self.impulse_confirmed['BUY'] = False
            return None

        if prev['high'] < prev['EMA_fast'] and last['high'] >= last['EMA_fast']:
            return 'SELL'
        return None
