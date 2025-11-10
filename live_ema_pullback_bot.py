#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Keltner Channel Pullback Strategy - Live Trading Bot for MetaTrader 5
Author: AI Assistant
Date: 2025-11-10
Strategy: 
- IMPULSE: High/Low touch band (Closed Candle)
- PULLBACK TOUCH: Low/High touch middle (Forming Candle + 5s stability)
- ENTRY: Close beyond middle (Closed Candle)
- Indicators: Calculated with Forming Candle data
"""

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from enum import Enum
import time
import sys

# ============================================================================
# CONFIGURATION SECTION
# ============================================================================

class Config:
    """Centralized configuration for the trading bot"""

    # --- MT5 Connection ---
    MT5_TIMEOUT = 60000  # milliseconds

    # --- Symbol Settings ---
    SYMBOL = "XAUUSD"
    TIMEFRAME = mt5.TIMEFRAME_M1  # 1-minute
    MAGIC_NUMBER = 234567

    # --- Keltner Channel Parameters ---
    KC_EMA_PERIOD = 9
    KC_ATR_PERIOD = 14
    KC_MULTIPLIER = 2.0

    # --- Risk Management ---
    RISK_USD = 50.0  # Fixed dollar risk per trade
    SL_ATR_BUFFER = 0.5  # Additional ATR distance beyond band for SL
    RISK_REWARD_RATIO = 2.0  # TP = SL * RR

    # --- Pullback Stability ---
    PULLBACK_STABILITY_SECONDS = 5  # Seconds to confirm pullback touch

    # --- Filters ---
    USE_EMA200_FILTER = False  # Enable/Disable EMA 200 trend filter
    EMA200_PERIOD = 200

    USE_ADX_FILTER = False  # Enable/Disable ADX volatility filter
    ADX_PERIOD = 14
    ADX_THRESHOLD = 20  # Minimum ADX value to allow trades

    # --- Data Management ---
    INITIAL_CANDLES = 500  # Number of candles to load initially
    UPDATE_INTERVAL = 1.0  # seconds between checks

    # --- Logging ---
    VERBOSE = True  # Print detailed logs

# ============================================================================
# STATE MACHINE
# ============================================================================

class BotState(Enum):
    """Trading bot states"""
    SEARCHING = "SEARCHING"  # Looking for impulse
    IMPULSE_DETECTED_BUY = "IMPULSE_DETECTED_BUY"  # Waiting for pullback touch
    IMPULSE_DETECTED_SELL = "IMPULSE_DETECTED_SELL"
    PULLBACK_TOUCHED_BUY = "PULLBACK_TOUCHED_BUY"  # Pullback touched, waiting stability
    PULLBACK_TOUCHED_SELL = "PULLBACK_TOUCHED_SELL"
    WAITING_ENTRY_BUY = "WAITING_ENTRY_BUY"  # Stability confirmed, waiting for close
    WAITING_ENTRY_SELL = "WAITING_ENTRY_SELL"
    POSITION_OPEN = "POSITION_OPEN"  # Trade is active

# ============================================================================
# KELTNER CHANNEL LIVE BOT
# ============================================================================

class KeltnerChannelBot:
    """Live trading bot using Keltner Channel pullback strategy"""

    def __init__(self, config: Config):
        self.config = config
        self.state = BotState.SEARCHING
        self.df = None
        self.last_processed_time = None
        self.position_ticket = None

        # Pullback tracking
        self.pullback_touch_time = None

        # Symbol info (to be loaded from broker)
        self.symbol_info = None
        self.point = None
        self.min_lot = None
        self.max_lot = None
        self.lot_step = None
        self.pip_value = None

        self.log("Initializing Keltner Channel Bot...")

    def log(self, message: str):
        """Print log messages"""
        if self.config.VERBOSE:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] {message}")

    # ------------------------------------------------------------------------
    # MT5 CONNECTION & INITIALIZATION
    # ------------------------------------------------------------------------

    def connect_mt5(self) -> bool:
        """Connect to MetaTrader 5"""
        if not mt5.initialize():
            self.log(f"❌ ERROR: MT5 initialization failed. Error: {mt5.last_error()}")
            return False

        self.log(f"✅ Connected to MT5. Version: {mt5.version()}")

        # Get account info
        account_info = mt5.account_info()
        if account_info is None:
            self.log("❌ ERROR: Failed to get account info")
            return False

        self.log(f"✅ Account: {account_info.login}, Balance: ${account_info.balance:.2f}")
        return True

    def load_symbol_info(self) -> bool:
        """Load symbol specifications from broker"""
        symbol = self.config.SYMBOL

        # Enable symbol in Market Watch
        if not mt5.symbol_select(symbol, True):
            self.log(f"❌ ERROR: Failed to select symbol {symbol}")
            return False

        self.symbol_info = mt5.symbol_info(symbol)
        if self.symbol_info is None:
            self.log(f"❌ ERROR: Symbol {symbol} not found")
            return False

        self.point = self.symbol_info.point
        self.min_lot = self.symbol_info.volume_min
        self.max_lot = self.symbol_info.volume_max
        self.lot_step = self.symbol_info.volume_step

        # Calculate pip value (for XAUUSD: 1 pip = 0.01, value per lot = $10)
        if "XAU" in symbol or "GOLD" in symbol:
            self.pip_value = 10.0  # Standard for gold
        else:
            # For forex pairs, pip value depends on account currency
            self.pip_value = self.point * self.symbol_info.trade_contract_size

        self.log(f"✅ Symbol Info Loaded: {symbol}")
        self.log(f"   Point: {self.point}, Min Lot: {self.min_lot}, Pip Value: ${self.pip_value:.2f}")

        return True

    # ------------------------------------------------------------------------
    # DATA MANAGEMENT
    # ------------------------------------------------------------------------

    def load_initial_data(self) -> bool:
        """Load initial historical candles"""
        rates = mt5.copy_rates_from_pos(
            self.config.SYMBOL,
            self.config.TIMEFRAME,
            0,
            self.config.INITIAL_CANDLES
        )

        if rates is None or len(rates) == 0:
            self.log(f"❌ ERROR: Failed to load initial data")
            return False

        self.df = pd.DataFrame(rates)
        self.df['time'] = pd.to_datetime(self.df['time'], unit='s')
        self.df.set_index('time', inplace=True)

        # Calculate indicators
        self.calculate_indicators()

        self.last_processed_time = self.df.index[-1]

        self.log(f"✅ Loaded {len(self.df)} candles. Last candle: {self.last_processed_time}")
        return True

    def update_data(self) -> bool:
        """Check for new candles and update dataframe"""
        rates = mt5.copy_rates_from_pos(self.config.SYMBOL, self.config.TIMEFRAME, 0, 1)

        if rates is None or len(rates) == 0:
            return False

        latest_candle = rates[0]
        latest_time = pd.to_datetime(latest_candle['time'], unit='s')

        # Check if this is a new candle
        if latest_time <= self.last_processed_time:
            return False  # No new candle

        # New candle detected
        new_row = pd.DataFrame(rates)
        new_row['time'] = pd.to_datetime(new_row['time'], unit='s')
        new_row.set_index('time', inplace=True)

        # Append to dataframe (sliding window)
        self.df = pd.concat([self.df, new_row])
        self.df = self.df.iloc[-self.config.INITIAL_CANDLES:]

        # Recalculate indicators
        self.calculate_indicators()

        self.last_processed_time = latest_time

        self.log(f"🆕 New candle: {latest_time} | O:{latest_candle['open']:.2f} H:{latest_candle['high']:.2f} L:{latest_candle['low']:.2f} C:{latest_candle['close']:.2f}")

        return True  # New candle processed

    def get_forming_candle(self) -> dict:
        """Get current forming candle data with calculated indicators"""
        # Get current forming candle (position 0 = current unclosed candle)
        rates = mt5.copy_rates_from_pos(self.config.SYMBOL, self.config.TIMEFRAME, 0, 1)
        
        if rates is None or len(rates) == 0:
            return None
        
        forming = rates[0]
        
        # Create temporary dataframe with forming candle appended
        temp_df = self.df.copy()
        forming_row = pd.DataFrame(rates)
        forming_row['time'] = pd.to_datetime(forming_row['time'], unit='s')
        forming_row.set_index('time', inplace=True)
        
        # Replace last row if same time, else append
        if forming_row.index[0] == temp_df.index[-1]:
            temp_df.iloc[-1] = forming_row.iloc[0]
        else:
            temp_df = pd.concat([temp_df, forming_row])
        
        # Recalculate indicators with forming candle
        temp_df['KC_middle'] = ta.ema(temp_df['close'], length=self.config.KC_EMA_PERIOD)
        temp_df['ATR'] = ta.atr(
            temp_df['high'],
            temp_df['low'],
            temp_df['close'],
            length=self.config.KC_ATR_PERIOD
        )
        temp_df['KC_upper'] = temp_df['KC_middle'] + (self.config.KC_MULTIPLIER * temp_df['ATR'])
        temp_df['KC_lower'] = temp_df['KC_middle'] - (self.config.KC_MULTIPLIER * temp_df['ATR'])
        
        # Get last row (forming candle with indicators)
        last_row = temp_df.iloc[-1]
        
        return {
            'time': forming['time'],
            'open': forming['open'],
            'high': forming['high'],
            'low': forming['low'],
            'close': forming['close'],
            'KC_middle': last_row['KC_middle'],
            'KC_upper': last_row['KC_upper'],
            'KC_lower': last_row['KC_lower'],
            'ATR': last_row['ATR']
        }

    def calculate_indicators(self):
        """Calculate all technical indicators"""
        # Keltner Channel
        self.df['KC_middle'] = ta.ema(self.df['close'], length=self.config.KC_EMA_PERIOD)
        self.df['ATR'] = ta.atr(
            self.df['high'],
            self.df['low'],
            self.df['close'],
            length=self.config.KC_ATR_PERIOD
        )
        self.df['KC_upper'] = self.df['KC_middle'] + (self.config.KC_MULTIPLIER * self.df['ATR'])
        self.df['KC_lower'] = self.df['KC_middle'] - (self.config.KC_MULTIPLIER * self.df['ATR'])

        # EMA 200 filter (if enabled)
        if self.config.USE_EMA200_FILTER:
            self.df['EMA_200'] = ta.ema(self.df['close'], length=self.config.EMA200_PERIOD)

        # ADX filter (if enabled)
        if self.config.USE_ADX_FILTER:
            adx_data = ta.adx(
                self.df['high'],
                self.df['low'],
                self.df['close'],
                length=self.config.ADX_PERIOD
            )
            self.df['ADX'] = adx_data[f'ADX_{self.config.ADX_PERIOD}']

        self.df.dropna(inplace=True)

    # ------------------------------------------------------------------------
    # FILTER CHECKS
    # ------------------------------------------------------------------------

    def check_filters(self, direction: str) -> bool:
        """Check if filters allow trading in given direction"""
        last = self.df.iloc[-1]

        # EMA 200 Filter
        if self.config.USE_EMA200_FILTER:
            if 'EMA_200' not in last or pd.isna(last['EMA_200']):
                return False

            if direction == "BUY" and last['close'] < last['EMA_200']:
                self.log(f"   ⛔ EMA200 Filter: Price below EMA200, BUY rejected")
                return False

            if direction == "SELL" and last['close'] > last['EMA_200']:
                self.log(f"   ⛔ EMA200 Filter: Price above EMA200, SELL rejected")
                return False

        # ADX Filter
        if self.config.USE_ADX_FILTER:
            if 'ADX' not in last or pd.isna(last['ADX']):
                return False

            if last['ADX'] < self.config.ADX_THRESHOLD:
                self.log(f"   ⛔ ADX Filter: ADX={last['ADX']:.1f} < {self.config.ADX_THRESHOLD}, trade rejected")
                return False

        return True  # All filters passed

    # ------------------------------------------------------------------------
    # STRATEGY LOGIC
    # ------------------------------------------------------------------------

    def detect_impulse(self) -> str:
        """Detect impulse using CLOSED candle High/Low touch"""
        last = self.df.iloc[-1]

        # Impulse BUY: High touched upper band
        if last['high'] > last['KC_upper']:
            if self.check_filters("BUY"):
                self.log(f"🚀 IMPULSE (BUY): High={last['high']:.2f} > Upper={last['KC_upper']:.2f}")
                return "BUY"

        # Impulse SELL: Low touched lower band
        if last['low'] < last['KC_lower']:
            if self.check_filters("SELL"):
                self.log(f"🚀 IMPULSE (SELL): Low={last['low']:.2f} < Lower={last['KC_lower']:.2f}")
                return "SELL"

        return None

    def check_pullback_touch_forming(self, direction: str) -> bool:
        """Check if FORMING candle touched middle line"""
        forming = self.get_forming_candle()
        if forming is None:
            return False

        middle = forming['KC_middle']

        if direction == "BUY":
            # For BUY: check if LOW touched middle
            if forming['low'] <= middle:
                self.log(f"   ✅ Pullback Touch (BUY - Forming): Low={forming['low']:.2f} <= Middle={middle:.2f}")
                return True

        elif direction == "SELL":
            # For SELL: check if HIGH touched middle
            if forming['high'] >= middle:
                self.log(f"   ✅ Pullback Touch (SELL - Forming): High={forming['high']:.2f} >= Middle={middle:.2f}")
                return True

        return False

    def check_pullback_stability(self, direction: str) -> bool:
        """Check if pullback touch is stable for required time"""
        if self.pullback_touch_time is None:
            return False

        elapsed = time.time() - self.pullback_touch_time
        
        if elapsed >= self.config.PULLBACK_STABILITY_SECONDS:
            self.log(f"   ✅ Pullback Stability Confirmed ({elapsed:.1f}s)")
            return True
        else:
            self.log(f"   ⏳ Pullback Stabilizing... ({elapsed:.1f}s / {self.config.PULLBACK_STABILITY_SECONDS}s)")
            return False

    def check_entry_condition(self, direction: str) -> bool:
        """Check if CLOSED candle confirms entry"""
        last = self.df.iloc[-1]
        middle = last['KC_middle']

        if direction == "BUY":
            if last['close'] > middle:
                self.log(f"   ✅ Entry Confirmed (BUY): Close={last['close']:.2f} > Middle={middle:.2f}")
                return True

        elif direction == "SELL":
            if last['close'] < middle:
                self.log(f"   ✅ Entry Confirmed (SELL): Close={last['close']:.2f} < Middle={middle:.2f}")
                return True

        return False

    # ------------------------------------------------------------------------
    # POSITION MANAGEMENT
    # ------------------------------------------------------------------------

    def calculate_lot_size(self, entry_price: float, sl_price: float) -> float:
        """Calculate lot size based on fixed dollar risk"""
        sl_distance_pips = abs(entry_price - sl_price) / (self.point * 10)

        if sl_distance_pips == 0:
            return 0

        risk_per_pip = self.config.RISK_USD / sl_distance_pips
        lot_size = risk_per_pip / self.pip_value

        # Round to lot step
        lot_size = round(lot_size / self.lot_step) * self.lot_step

        # Clamp to min/max
        lot_size = max(self.min_lot, min(lot_size, self.max_lot))

        return lot_size

    def open_position(self, direction: str):
        """Open a market order"""
        last = self.df.iloc[-1]

        tick = mt5.symbol_info_tick(self.config.SYMBOL)
        if tick is None:
            self.log("❌ ERROR: Failed to get current tick")
            return False

        # Determine entry price and SL
        if direction == "BUY":
            entry_price = tick.ask
            sl_price = last['KC_lower'] - (self.config.SL_ATR_BUFFER * last['ATR'])
            order_type = mt5.ORDER_TYPE_BUY
        else:  # SELL
            entry_price = tick.bid
            sl_price = last['KC_upper'] + (self.config.SL_ATR_BUFFER * last['ATR'])
            order_type = mt5.ORDER_TYPE_SELL

        # Calculate TP
        sl_distance = abs(entry_price - sl_price)
        tp_price = entry_price + (self.config.RISK_REWARD_RATIO * sl_distance) if direction == "BUY" else entry_price - (self.config.RISK_REWARD_RATIO * sl_distance)

        # Calculate lot size
        lot_size = self.calculate_lot_size(entry_price, sl_price)

        if lot_size < self.min_lot:
            self.log(f"❌ ERROR: Lot size {lot_size} below minimum {self.min_lot}")
            return False

        # Prepare order request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.config.SYMBOL,
            "volume": lot_size,
            "type": order_type,
            "price": entry_price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 10,
            "magic": self.config.MAGIC_NUMBER,
            "comment": f"KC_{direction}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Send order
        result = mt5.order_send(request)

        if result is None:
            self.log(f"❌ ERROR: order_send returned None")
            return False

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.log(f"❌ ERROR: Order failed. Retcode: {result.retcode}, Comment: {result.comment}")
            return False

        # Success
        self.position_ticket = result.order
        self.log(f"🟢 POSITION OPENED: {direction} {lot_size} lot @ {entry_price:.5f}, SL={sl_price:.5f}, TP={tp_price:.5f}, Ticket={self.position_ticket}")

        return True

    def check_position_status(self) -> bool:
        """Check if position is still open"""
        if self.position_ticket is None:
            return False

        positions = mt5.positions_get(ticket=self.position_ticket)

        if positions is None or len(positions) == 0:
            self.log(f"✅ Position closed (Ticket: {self.position_ticket})")
            self.position_ticket = None
            return False

        return True

    # ------------------------------------------------------------------------
    # STATE MACHINE
    # ------------------------------------------------------------------------

    def run_iteration(self, new_candle: bool):
        """Execute one iteration of strategy logic"""

        # State: POSITION_OPEN
        if self.state == BotState.POSITION_OPEN:
            if not self.check_position_status():
                self.log("🔄 Position closed. Returning to SEARCHING.")
                self.state = BotState.SEARCHING
                self.pullback_touch_time = None
            return

        # ═══════════════════════════════════════════════════════════
        # STATES THAT PROCESS ON NEW CANDLE
        # ═══════════════════════════════════════════════════════════
        if new_candle:
            
            # State: SEARCHING
            if self.state == BotState.SEARCHING:
                impulse_dir = self.detect_impulse()

                if impulse_dir == "BUY":
                    self.state = BotState.IMPULSE_DETECTED_BUY
                    self.pullback_touch_time = None
                    self.log(f"🔄 State: SEARCHING → IMPULSE_DETECTED_BUY")

                elif impulse_dir == "SELL":
                    self.state = BotState.IMPULSE_DETECTED_SELL
                    self.pullback_touch_time = None
                    self.log(f"🔄 State: SEARCHING → IMPULSE_DETECTED_SELL")

            # State: WAITING_ENTRY_BUY
            elif self.state == BotState.WAITING_ENTRY_BUY:
                last = self.df.iloc[-1]

                # Check for invalidation
                if last['low'] < last['KC_lower']:
                    self.log(f"🔄 Reset: Low touched lower band. Returning to SEARCHING.")
                    self.state = BotState.SEARCHING
                    self.pullback_touch_time = None
                    return

                if last['high'] > last['KC_upper']:
                    self.log(f"🔄 Reset: High touched upper band. Returning to IMPULSE_DETECTED_BUY.")
                    self.state = BotState.IMPULSE_DETECTED_BUY
                    self.pullback_touch_time = None
                    return

                # Check entry condition
                if self.check_entry_condition("BUY"):
                    if self.open_position("BUY"):
                        self.state = BotState.POSITION_OPEN
                        self.pullback_touch_time = None
                        self.log(f"🔄 State: WAITING_ENTRY_BUY → POSITION_OPEN")
                    else:
                        self.log("❌ Failed to open position. Returning to SEARCHING.")
                        self.state = BotState.SEARCHING
                        self.pullback_touch_time = None

            # State: WAITING_ENTRY_SELL
            elif self.state == BotState.WAITING_ENTRY_SELL:
                last = self.df.iloc[-1]

                # Check for invalidation
                if last['high'] > last['KC_upper']:
                    self.log(f"🔄 Reset: High touched upper band. Returning to SEARCHING.")
                    self.state = BotState.SEARCHING
                    self.pullback_touch_time = None
                    return

                if last['low'] < last['KC_lower']:
                    self.log(f"🔄 Reset: Low touched lower band. Returning to IMPULSE_DETECTED_SELL.")
                    self.state = BotState.IMPULSE_DETECTED_SELL
                    self.pullback_touch_time = None
                    return

                # Check entry condition
                if self.check_entry_condition("SELL"):
                    if self.open_position("SELL"):
                        self.state = BotState.POSITION_OPEN
                        self.pullback_touch_time = None
                        self.log(f"🔄 State: WAITING_ENTRY_SELL → POSITION_OPEN")
                    else:
                        self.log("❌ Failed to open position. Returning to SEARCHING.")
                        self.state = BotState.SEARCHING
                        self.pullback_touch_time = None

        # ═══════════════════════════════════════════════════════════
        # STATES THAT PROCESS EVERY ITERATION (Forming Candle)
        # ═══════════════════════════════════════════════════════════

        # State: IMPULSE_DETECTED_BUY
        if self.state == BotState.IMPULSE_DETECTED_BUY:
            # Check pullback touch with forming candle
            if self.check_pullback_touch_forming("BUY"):
                if self.pullback_touch_time is None:
                    self.pullback_touch_time = time.time()
                    self.state = BotState.PULLBACK_TOUCHED_BUY
                    self.log(f"🔄 State: IMPULSE_DETECTED_BUY → PULLBACK_TOUCHED_BUY")

        # State: IMPULSE_DETECTED_SELL
        elif self.state == BotState.IMPULSE_DETECTED_SELL:
            # Check pullback touch with forming candle
            if self.check_pullback_touch_forming("SELL"):
                if self.pullback_touch_time is None:
                    self.pullback_touch_time = time.time()
                    self.state = BotState.PULLBACK_TOUCHED_SELL
                    self.log(f"🔄 State: IMPULSE_DETECTED_SELL → PULLBACK_TOUCHED_SELL")

        # State: PULLBACK_TOUCHED_BUY
        elif self.state == BotState.PULLBACK_TOUCHED_BUY:
            # Check if still touching
            if not self.check_pullback_touch_forming("BUY"):
                self.log(f"⚠️ Pullback lost touch. Returning to IMPULSE_DETECTED_BUY.")
                self.state = BotState.IMPULSE_DETECTED_BUY
                self.pullback_touch_time = None
                return

            # Check stability
            if self.check_pullback_stability("BUY"):
                self.state = BotState.WAITING_ENTRY_BUY
                self.log(f"🔄 State: PULLBACK_TOUCHED_BUY → WAITING_ENTRY_BUY")

        # State: PULLBACK_TOUCHED_SELL
        elif self.state == BotState.PULLBACK_TOUCHED_SELL:
            # Check if still touching
            if not self.check_pullback_touch_forming("SELL"):
                self.log(f"⚠️ Pullback lost touch. Returning to IMPULSE_DETECTED_SELL.")
                self.state = BotState.IMPULSE_DETECTED_SELL
                self.pullback_touch_time = None
                return

            # Check stability
            if self.check_pullback_stability("SELL"):
                self.state = BotState.WAITING_ENTRY_SELL
                self.log(f"🔄 State: PULLBACK_TOUCHED_SELL → WAITING_ENTRY_SELL")

    # ------------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------------

    def run(self):
        """Main execution loop"""
        self.log("="*60)
        self.log("🤖 KELTNER CHANNEL BOT - STARTING")
        self.log("="*60)

        # Step 1: Connect to MT5
        if not self.connect_mt5():
            return

        # Step 2: Load symbol info
        if not self.load_symbol_info():
            mt5.shutdown()
            return

        # Step 3: Load initial data
        if not self.load_initial_data():
            mt5.shutdown()
            return

        self.log("="*60)
        self.log("🟢 BOT IS NOW RUNNING (Press Ctrl+C to stop)")
        self.log("="*60)

        # Main loop
        try:
            while True:
                # Check for new candle
                new_candle = self.update_data()

                # Run strategy iteration
                self.run_iteration(new_candle)

                # Sleep
                time.sleep(self.config.UPDATE_INTERVAL)

        except KeyboardInterrupt:
            self.log("\n🛑 Bot stopped by user.")

        except Exception as e:
            self.log(f"\n❌ FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()

        finally:
            mt5.shutdown()
            self.log("✅ MT5 connection closed. Goodbye!")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    config = Config()
    bot = KeltnerChannelBot(config)
    bot.run()
