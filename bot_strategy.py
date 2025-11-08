# File: bot_strategy.py
# Version: Entry at FVG Edge (High for Buy, Low for Sell)

import pandas as pd
from typing import Literal

class BotStrategy:
    """
    This class contains the trading logic for the SMC (Smart Money Concepts) bot.
    It identifies trading setups based on market structure (CHoCH, BOS) and Fair Value Gaps (FVG).
    """

    def __init__(self, risk_to_reward: float):
        """
        Initializes the strategy with necessary parameters.
        :param risk_to_reward: The desired risk-to-reward ratio for trades (e.g., 3 for 1:3).
        """
        self.pending_setup = None
        self.risk_to_reward = risk_to_reward
        if self.risk_to_reward <= 0:
            raise ValueError("Risk to Reward ratio must be greater than 0.")

    def on_bar(self, candles: pd.DataFrame, broker):
        """
        This is the main entry point for the strategy on each new candle.
        It manages the state and decides which logic to execute.
        """
        # --- 1. Manage any pending setup first ---
        if self.pending_setup:
            self._manage_pending_setup(candles, broker)
            return # If we have a pending setup, we don't look for a new one

        # --- 2. If no pending setup, search for a new one ---
        # You can choose which setup to prioritize or run both.
        # For now, let's check for CHoCH first. If found, we stop.
        # If not, we check for BOS.
        self._check_for_choch_setup(candles)
        if not self.pending_setup:
            self._check_for_bos_setup(candles)

    def _manage_pending_setup(self, candles: pd.DataFrame, broker):
        """
        Handles the logic when a setup has been identified but not yet triggered.
        It checks for entry triggers or invalidation.
        """
        current_bar = candles.iloc[-1]
        setup = self.pending_setup
        
        # --- Check for Invalidation ---
        # If the price hits our SL *before* our entry, the setup is invalid.
        is_invalidated = False
        if setup['direction'] == 'BUY' and current_bar['low'] <= setup['sl']:
            is_invalidated = True
        elif setup['direction'] == 'SELL' and current_bar['high'] >= setup['sl']:
            is_invalidated = True

        if is_invalidated:
            print(f"🔴 SETUP INVALIDATED: Price hit SL @ {setup['sl']:.5f} before entry. Setup cancelled.")
            self.pending_setup = None
            return

        # --- Check for Entry Trigger ---
        # The price must touch our entry price to trigger the trade.
        entry_triggered = False
        if setup['direction'] == 'BUY' and current_bar['low'] <= setup['entry_price']:
            entry_triggered = True
        elif setup['direction'] == 'SELL' and current_bar['high'] >= setup['entry_price']:
            entry_triggered = True

        if entry_triggered:
            print(f"✅✅✅ TRADE EXECUTED: {setup['direction']} at {setup['entry_price']:.5f} | SL: {setup['sl']:.5f} | TP: {setup['tp']:.5f}")
            broker.place_market_order(
                symbol='EURUSD',
                direction=setup['direction'],
                volume=0.1,  # Example volume
                sl=setup['sl'],
                tp=setup['tp']
            )
            self.pending_setup = None # Clear the setup once executed

    def _calculate_swings(self, candles: pd.DataFrame, lookback: int = 10):
        """
        Identifies Swing Highs and Swing Lows based on the LuxAlgo SMC logic.
        A swing high is a high with `lookback` lower highs on both sides.
        A swing low is a low with `lookback` higher lows on both sides.
        """
        swings = []
        for i in range(lookback, len(candles) - lookback):
            # Check for Swing High
            is_swing_high = True
            for j in range(1, lookback + 1):
                if candles['high'].iloc[i] <= candles['high'].iloc[i-j] or \
                   candles['high'].iloc[i] <= candles['high'].iloc[i+j]:
                    is_swing_high = False
                    break
            if is_swing_high:
                # Avoid adding consecutive swings of the same type
                if not swings or swings[-1]['type'] != 'high':
                    swings.append({'time': candles.index[i], 'price': candles['high'].iloc[i], 'type': 'high'})
                continue # Move to the next candle

            # Check for Swing Low
            is_swing_low = True
            for j in range(1, lookback + 1):
                if candles['low'].iloc[i] >= candles['low'].iloc[i-j] or \
                   candles['low'].iloc[i] >= candles['low'].iloc[i+j]:
                    is_swing_low = False
                    break
            if is_swing_low:
                 # Avoid adding consecutive swings of the same type
                if not swings or swings[-1]['type'] != 'low':
                    swings.append({'time': candles.index[i], 'price': candles['low'].iloc[i], 'type': 'low'})

        return swings

    def _find_fvg(self, candles: pd.DataFrame, start_index, end_index, direction: Literal['buy', 'sell']):
        """
        Finds the first valid Fair Value Gap (FVG) within a specific range of candles.
        :param candles: The full DataFrame of candles.
        :param start_index: The timestamp to start searching from.
        :param end_index: The timestamp to end the search at.
        :param direction: 'buy' for Bullish FVG, 'sell' for Bearish FVG.
        :return: A dictionary with FVG details or None if not found.
        """
        leg_candles = candles.loc[start_index:end_index]

        # Iterate backwards from the second to last candle in the leg
        for i in range(len(leg_candles) - 2, 0, -1):
            c1 = leg_candles.iloc[i-1] # First candle
            c2 = leg_candles.iloc[i]   # Middle candle (ignored)
            c3 = leg_candles.iloc[i+1] # Third candle

            # Bullish FVG (Imbalance): C1 High is lower than C3 Low
            if direction == 'buy' and c1['high'] < c3['low']:
                fvg = {
                    'high': c3['low'],
                    'low': c1['high'],
                    'midpoint': (c1['high'] + c3['low']) / 2,
                    'time': c2.name
                }
                # print(f"DEBUG: Bullish FVG found at {c2.name} between {fvg['high']:.5f} and {fvg['low']:.5f}")
                return fvg
            
            # Bearish FVG (Imbalance): C1 Low is higher than C3 High
            if direction == 'sell' and c1['low'] > c3['high']:
                fvg = {
                    'high': c1['low'],
                    'low': c3['high'],
                    'midpoint': (c1['low'] + c3['high']) / 2,
                    'time': c2.name
                }
                # print(f"DEBUG: Bearish FVG found at {c2.name} between {fvg['high']:.5f} and {fvg['low']:.5f}")
                return fvg
        
        return None

    def _check_for_choch_setup(self, candles: pd.DataFrame):
        """
        Looks for a Change of Character (CHoCH) setup for trend reversals.
        Then, it finds an FVG in the breakout leg to place a limit order.
        """
        swing_points = self._calculate_swings(candles)
        if len(swing_points) < 3:
            return

        p3, p2, p1 = swing_points[-3:] # p1 is the most recent swing
        last_candle = candles.iloc[-1]
        current_price = last_candle['close']

        # --- Check for Bullish CHoCH (Reversal from Downtrend to Uptrend) ---
        # Structure: High (p3) -> Low (p2) -> New High breaks p3
        is_bullish_choch = p3['type'] == 'high' and p2['type'] == 'low' and p1['type'] == 'high' and \
                           p1['price'] > p3['price']

        if is_bullish_choch:
            # We look for a Bullish FVG in the leg that caused the break (p2 to p1).
            fvg = self._find_fvg(candles, p2['time'], p1['time'], direction='buy')
            if fvg:
                sl = p2['price'] # The absolute low before the reversal
                
                # *** MODIFIED LOGIC: Entry at FVG High ***
                entry_price = fvg['high']
                risk_amount = entry_price - sl
                if risk_amount <= 0: return

                tp = entry_price + (risk_amount * self.risk_to_reward)
                setup = {
                    'type': 'Bullish CHoCH', 'direction': 'BUY',
                    'entry_price': entry_price,
                    'sl': sl, 'tp': tp,
                    'fvg_zone': (fvg['high'], fvg['low']),
                    'break_point': p3['price'], 'invalidation_point': p2['price']
                }
                print(f"✅✅✅ [CHoCH] Bullish Setup Found! Break of {p3['price']:.5f}. Entry at FVG edge {entry_price:.5f}, SL {sl:.5f}")
                self.pending_setup = setup
                return

        # --- Check for Bearish CHoCH (Reversal from Uptrend to Downtrend) ---
        # Structure: Low (p3) -> High (p2) -> New Low breaks p3
        is_bearish_choch = p3['type'] == 'low' and p2['type'] == 'high' and p1['type'] == 'low' and \
                           p1['price'] < p3['price']
        
        if is_bearish_choch:
            # We look for a Bearish FVG in the leg that caused the break (p2 to p1).
            fvg = self._find_fvg(candles, p2['time'], p1['time'], direction='sell')
            if fvg:
                sl = p2['price'] # The absolute high before the reversal
                
                # *** MODIFIED LOGIC: Entry at FVG Low ***
                entry_price = fvg['low']
                risk_amount = sl - entry_price
                if risk_amount <= 0: return

                tp = entry_price - (risk_amount * self.risk_to_reward)
                setup = {
                    'type': 'Bearish CHoCH', 'direction': 'SELL',
                    'entry_price': entry_price,
                    'sl': sl, 'tp': tp,
                    'fvg_zone': (fvg['high'], fvg['low']),
                    'break_point': p3['price'], 'invalidation_point': p2['price']
                }
                print(f"✅✅✅ [CHoCH] Bearish Setup Found! Break of {p3['price']:.5f}. Entry at FVG edge {entry_price:.5f}, SL {sl:.5f}")
                self.pending_setup = setup
                return

    def _check_for_bos_setup(self, candles):
        """
        Looks for a Break of Structure (BOS) setup to trade WITH the trend.
        Then, it finds an FVG in the breakout leg to place a limit order.
        """
        swing_points = self._calculate_swings(candles)
        if len(swing_points) < 3:
            return

        p3, p2, p1 = swing_points[-3:]  # p1 is the most recent swing
        last_candle = candles.iloc[-1]
        current_price = last_candle['close']

        # --- Check for Bullish BOS (Continuation of Uptrend) ---
        # Structure must be: Low (p3) -> High (p2) -> Higher Low (p1)
        is_uptrend_structure = p3['type'] == 'low' and p2['type'] == 'high' and p1['type'] == 'low' and \
                               p1['price'] > p3['price']

        if is_uptrend_structure and current_price > p2['price']:
            # BOS confirmed: The high at p2 is broken.
            # We look for an FVG in the leg from the last low (p1) to the current candle.
            breakout_leg_start_index = p1['time']
            breakout_leg_end_index = last_candle.name
            fvg = self._find_fvg(candles, breakout_leg_start_index, breakout_leg_end_index, direction='buy')

            if fvg:
                sl = p1['price']  # Invalidation point is the last confirmed Higher Low
                
                # *** MODIFIED LOGIC: Entry at FVG High ***
                entry_price = fvg['high']
                risk_amount = entry_price - sl
                if risk_amount <= 0: return

                tp = entry_price + (risk_amount * self.risk_to_reward)
                setup = {
                    'type': 'Bullish BOS', 'direction': 'BUY',
                    'entry_price': entry_price,
                    'sl': sl, 'tp': tp,
                    'fvg_zone': (fvg['high'], fvg['low']),
                    'break_point': p2['price'], 'invalidation_point': p1['price']
                }
                print(f"✅✅✅ [BOS] Bullish Setup Found! Break of {p2['price']:.5f}. Entry at FVG edge {entry_price:.5f}, SL {sl:.5f}")
                self.pending_setup = setup
                return

        # --- Check for Bearish BOS (Continuation of Downtrend) ---
        # Structure must be: High (p3) -> Low (p2) -> Lower High (p1)
        is_downtrend_structure = p3['type'] == 'high' and p2['type'] == 'low' and p1['type'] == 'high' and \
                                 p1['price'] < p3['price']

        if is_downtrend_structure and current_price < p2['price']:
            # BOS confirmed: The low at p2 is broken.
            # We look for an FVG in the leg from the last high (p1) to the current candle.
            breakout_leg_start_index = p1['time']
            breakout_leg_end_index = last_candle.name
            fvg = self._find_fvg(candles, breakout_leg_start_index, breakout_leg_end_index, direction='sell')

            if fvg:
                sl = p1['price']  # Invalidation point is the last confirmed Lower High

                # *** MODIFIED LOGIC: Entry at FVG Low ***
                entry_price = fvg['low']
                risk_amount = sl - entry_price
                if risk_amount <= 0: return

                tp = entry_price - (risk_amount * self.risk_to_reward)
                setup = {
                    'type': 'Bearish BOS', 'direction': 'SELL',
                    'entry_price': entry_price,
                    'sl': sl, 'tp': tp,
                    'fvg_zone': (fvg['high'], fvg['low']),
                    'break_point': p2['price'], 'invalidation_point': p1['price']
                }
                print(f"✅✅✅ [BOS] Bearish Setup Found! Break of {p2['price']:.5f}. Entry at FVG edge {entry_price:.5f}, SL {sl:.5f}")
                self.pending_setup = setup
                return
