#!/usr/bin/env python3
"""
Live EMA Pullback Bot - Corrected Logic:
- Impulse Detection: FORMING candle (for speed)
- Entry Confirmation: CLOSED candle (for accuracy)
"""

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import time


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class BotConfig:
    """Bot configuration parameters"""
    SYMBOL: str = "XAUUSD"
    TIMEFRAME: int = mt5.TIMEFRAME_M1
    MAGIC_NUMBER: int = 234000

    # Keltner Channel
    KC_EMA_PERIOD: int = 9
    KC_ATR_PERIOD: int = 14
    KC_MULTIPLIER: float = 1.5

    # Risk Management
    RISK_USD: float = 10.0
    SL_ATR_BUFFER: float = 0.5
    TP_RATIO: float = 2.0

    # Filters
    USE_EMA200_FILTER: bool = False
    EMA200_PERIOD: int = 200

    USE_ADX_FILTER: bool = False
    ADX_PERIOD: int = 14
    ADX_THRESHOLD: float = 25.0

    # Data
    INITIAL_CANDLES: int = 300


# ============================================================================
# BOT STATE
# ============================================================================

class BotState(Enum):
    SEARCHING = "SEARCHING"
    IMPULSE_DETECTED_BUY = "IMPULSE_DETECTED_BUY"
    IMPULSE_DETECTED_SELL = "IMPULSE_DETECTED_SELL"
    PULLBACK_TOUCHED_BUY = "PULLBACK_TOUCHED_BUY"
    PULLBACK_TOUCHED_SELL = "PULLBACK_TOUCHED_SELL"
    POSITION_OPEN = "POSITION_OPEN"


# ============================================================================
# MAIN BOT
# ============================================================================

class LiveKeltnerkBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.state = BotState.SEARCHING
        self.df = pd.DataFrame()
        self.last_processed_time = None
        self.impulse_direction = None  # "BUY" or "SELL" or None
        

        # MT5 symbol info
        self.point = 0
        self.pip_value = 0
        self.min_lot = 0
        self.max_lot = 0
        self.lot_step = 0

    # ------------------------------------------------------------------------
    # INITIALIZATION
    # ------------------------------------------------------------------------

    def initialize(self) -> bool:
        """Initialize MT5 connection and load initial data"""
        if not mt5.initialize():
            self.log(f"❌ MT5 initialize failed: {mt5.last_error()}")
            return False

        symbol_info = mt5.symbol_info(self.config.SYMBOL)
        if symbol_info is None:
            self.log(f"❌ Symbol {self.config.SYMBOL} not found")
            return False

        if not symbol_info.visible:
            if not mt5.symbol_select(self.config.SYMBOL, True):
                self.log(f"❌ Failed to select {self.config.SYMBOL}")
                return False

        self.point = symbol_info.point
        self.pip_value = 10 if self.config.SYMBOL in ["XAUUSD", "XAGUSD"] else 1
        self.min_lot = symbol_info.volume_min
        self.max_lot = symbol_info.volume_max
        self.lot_step = symbol_info.volume_step

        self.log(f"✅ Connected to {self.config.SYMBOL}")
        self.log(f"   Point: {self.point}, Pip Value: {self.pip_value}")
        self.log(f"   Lot Range: {self.min_lot} - {self.max_lot} (Step: {self.lot_step})")

        return self.load_initial_data()

    def load_initial_data(self) -> bool:
        """Load initial historical data"""
        rates = mt5.copy_rates_from_pos(
            self.config.SYMBOL,
            self.config.TIMEFRAME,
            0,
            self.config.INITIAL_CANDLES
        )

        if rates is None or len(rates) == 0:
            self.log("❌ ERROR: Failed to load initial data")
            return False

        self.df = pd.DataFrame(rates)
        self.df['time'] = pd.to_datetime(self.df['time'], unit='s')
        self.df.set_index('time', inplace=True)

        self.calculate_indicators()

        if len(self.df) == 0:
            self.log("❌ ERROR: DataFrame empty after indicators")
            return False

        self.last_processed_time = self.df.index[-1]
        self.log(f"✅ Loaded {len(self.df)} candles. Last candle: {self.last_processed_time}")
        return True

    def update_data(self) -> bool:
        """
        ⭐ CORRECTED LOGIC:
        When new candle starts, read the PREVIOUS (closed) candle
        """
        try:
            rates = mt5.copy_rates_from_pos(self.config.SYMBOL, self.config.TIMEFRAME, 0, 2)

            if rates is None or len(rates) < 2:
                return False

            # تبدیل کل آرایه به DataFrame یکجا
            temp_df = pd.DataFrame(rates)
            temp_df['time'] = pd.to_datetime(temp_df['time'], unit='s')
            temp_df.set_index('time', inplace=True)

            # آخرین کندل (در حال شکل‌گیری)
            current_time = temp_df.index[-1]

            # کندل قبلی (بسته شده)
            previous_time = temp_df.index[-2]
            previous_candle = temp_df.iloc[-2]

            # ⭐ FIX: چک کن که کندل بسته شده جدیده یا نه
            if previous_time > self.last_processed_time:
                # کندل بسته شده (قبلی) رو به عنوان DataFrame اضافه کن
                new_row = temp_df.iloc[-2:-1]  # این یک DataFrame تک‌رکوردی می‌سازه

                self.df = pd.concat([self.df, new_row])
                self.df = self.df.iloc[-self.config.INITIAL_CANDLES:]

                self.calculate_indicators()

                if len(self.df) == 0:
                    return False

                # ⭐ FIX: ذخیره زمان کندل بسته شده (نه کندل در حال شکل‌گیری!)
                self.last_processed_time = previous_time

                # لاگ کندل بسته شده با مقادیر باندها
                last_closed = self.df.iloc[-1]
                o = float(previous_candle['open'])
                h = float(previous_candle['high'])
                l = float(previous_candle['low'])
                c = float(previous_candle['close'])

                if 'KC_upper' in last_closed and not pd.isna(last_closed['KC_upper']):
                    upper = float(last_closed['KC_upper'])
                    middle = float(last_closed['KC_middle'])
                    lower = float(last_closed['KC_lower'])

                    self.log(f"🆕 New candle: {previous_time.strftime('%H:%M:%S')} | O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}")
                    self.log(f"   📊 Bands: Upper={upper:.2f}, Middle={middle:.2f}, Lower={lower:.2f}")
                else:
                    self.log(f"🆕 New candle: {previous_time.strftime('%H:%M:%S')} | O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}")

                return True

        except Exception as e:
            self.log(f"⚠️ update_data error: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

        return False

    def check_mt5_connection(self) -> bool:
        """Check and restore MT5 connection if needed"""
        terminal_info = mt5.terminal_info()

        if terminal_info is None:
            self.log("⚠️  MT5 connection lost. Reconnecting...")
            mt5.shutdown()
            if mt5.initialize():
                self.log("✅ MT5 reconnected")
                return True
            else:
                self.log("❌ Failed to reconnect MT5")
                return False

        if not terminal_info.connected:
            self.log("⚠️  MT5 not connected to broker")
            return False

        return True

    def is_market_open(self) -> bool:
        """Check if market is open"""
        symbol_info = mt5.symbol_info(self.config.SYMBOL)

        if symbol_info is None:
            self.log(f"⚠️  Symbol {self.config.SYMBOL} not found")
            return False

        # Check trading status
        if symbol_info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
            self.log(f"⚠️  Market closed for {self.config.SYMBOL}")
            return False

        # Check spread (if too high, market might be closed)
        spread = symbol_info.spread
        if spread > 100:  # برای XAUUSD معمولاً spread کمتر از 50 هست
            self.log(f"⚠️  Abnormal spread: {spread} (Market might be closed)")
            return False

        return True

    def calculate_indicators(self):
        self.df['KC_middle'] = ta.ema(self.df['close'], length=self.config.KC_EMA_PERIOD)
        self.df['ATR'] = ta.atr(
            self.df['high'],
            self.df['low'],
            self.df['close'],
            length=self.config.KC_ATR_PERIOD
        )
        self.df['KC_upper'] = self.df['KC_middle'] + (self.config.KC_MULTIPLIER * self.df['ATR'])
        self.df['KC_lower'] = self.df['KC_middle'] - (self.config.KC_MULTIPLIER * self.df['ATR'])

        if self.config.USE_EMA200_FILTER:
            self.df['EMA_200'] = ta.ema(self.df['close'], length=self.config.EMA200_PERIOD)

        if self.config.USE_ADX_FILTER:
            adx_data = ta.adx(
                self.df['high'],
                self.df['low'],
                self.df['close'],
                length=self.config.ADX_PERIOD
            )
            self.df['ADX'] = adx_data[f'ADX_{self.config.ADX_PERIOD}']

        self.df.dropna(inplace=True)

    def get_forming_candle(self):
        """Get FORMING candle with updated indicators"""
        rates = mt5.copy_rates_from_pos(self.config.SYMBOL, self.config.TIMEFRAME, 0, 1)

        if rates is None or len(rates) < 1:
            return None

        forming_df = pd.DataFrame(rates)
        forming_df['time'] = pd.to_datetime(forming_df['time'], unit='s')
        forming_df.set_index('time', inplace=True)

        forming_row = forming_df.iloc[-1:].copy()

        # Combine historical closed candles + forming
        temp_df = pd.concat([self.df, forming_row])

        # Calculate indicators including forming candle
        temp_df['KC_middle'] = ta.ema(temp_df['close'], length=self.config.KC_EMA_PERIOD)
        temp_df['ATR'] = ta.atr(
            temp_df['high'],
            temp_df['low'],
            temp_df['close'],
            length=self.config.KC_ATR_PERIOD
        )
        temp_df['KC_upper'] = temp_df['KC_middle'] + (self.config.KC_MULTIPLIER * temp_df['ATR'])
        temp_df['KC_lower'] = temp_df['KC_middle'] - (self.config.KC_MULTIPLIER * temp_df['ATR'])

        if self.config.USE_EMA200_FILTER:
            temp_df['EMA_200'] = ta.ema(temp_df['close'], length=self.config.EMA200_PERIOD)

        if self.config.USE_ADX_FILTER:
            adx_data = ta.adx(
                temp_df['high'],
                temp_df['low'],
                temp_df['close'],
                length=self.config.ADX_PERIOD
            )
            temp_df['ADX'] = adx_data[f'ADX_{self.config.ADX_PERIOD}']

        temp_df.dropna(inplace=True)

        if len(temp_df) == 0:
            return None

        return temp_df.iloc[-1]

    # ------------------------------------------------------------------------
    # FILTERS
    # ------------------------------------------------------------------------

    def check_filters(self, direction: str, candle_data) -> bool:
        if self.config.USE_EMA200_FILTER:
            if 'EMA_200' not in candle_data or pd.isna(candle_data['EMA_200']):
                return False

            if direction == "BUY" and candle_data['close'] < candle_data['EMA_200']:
                self.log(f"   ⛔ EMA200 Filter: BUY rejected")
                return False

            if direction == "SELL" and candle_data['close'] > candle_data['EMA_200']:
                self.log(f"   ⛔ EMA200 Filter: SELL rejected")
                return False

        if self.config.USE_ADX_FILTER:
            if 'ADX' not in candle_data or pd.isna(candle_data['ADX']):
                return False

            if candle_data['ADX'] < self.config.ADX_THRESHOLD:
                self.log(f"   ⛔ ADX Filter: ADX={candle_data['ADX']:.1f} < {self.config.ADX_THRESHOLD}")
                return False

        return True

    # ------------------------------------------------------------------------
    # STRATEGY LOGIC
    # ------------------------------------------------------------------------

    def detect_impulse_forming(self) -> str:
        """Detect impulse using FORMING candle H/L touching bands"""
        forming = self.get_forming_candle()

        if forming is None:
            return None

        if pd.isna(forming['KC_upper']) or pd.isna(forming['KC_lower']):
            return None

        # BUY: High touched upper band
        if forming['high'] >= forming['KC_upper']:
            if self.check_filters("BUY", forming):
               
                self.log(f"🚀 IMPULSE (BUY): High={forming['high']:.2f} >= Upper={forming['KC_upper']:.2f}")
                return "BUY"

        # SELL: Low touched lower band
        if forming['low'] <= forming['KC_lower']:
            if self.check_filters("SELL", forming):
                
                self.log(f"🚀 IMPULSE (SELL): Low={forming['low']:.2f} <= Lower={forming['KC_lower']:.2f}")
                return "SELL"

        return None

    def check_pullback_touch_forming(self, direction: str) -> bool:
        """Check if FORMING candle touched middle line (BUT NOT THE IMPULSE CANDLE)"""
        forming = self.get_forming_candle()

        if forming is None:
            return False

      

        middle = forming['KC_middle']

        if direction == "BUY":
            if forming['low'] <= middle:
                self.log(f"👀 Pullback Touch (BUY): Low={forming['low']:.2f} <= Middle={middle:.2f}")
                return True

        elif direction == "SELL":
            if forming['high'] >= middle:
                self.log(f"👀 Pullback Touch (SELL): High={forming['high']:.2f} >= Middle={middle:.2f}")
                return True

        return False
    
    def check_entry_confirmed_closed(self, direction: str) -> bool:
        """
        Check if CLOSED candle confirms entry
        Returns: True if entry confirmed
        """
        if len(self.df) == 0:
            return False

        last = self.df.iloc[-1]
        middle = last['KC_middle']

        if direction == "BUY":
            if last['close'] > middle:
                self.log(f"   ✅ Entry Confirmed (BUY): Close={last['close']:.2f} > Middle={middle:.2f}")
                return True
            else:
                self.log(f"   ❌ Entry NOT Confirmed (BUY): Close={last['close']:.2f} <= Middle={middle:.2f}")

        elif direction == "SELL":
            if last['close'] < middle:
                self.log(f"   ✅ Entry Confirmed (SELL): Close={last['close']:.2f} < Middle={middle:.2f}")
                return True
            else:
                self.log(f"   ❌ Entry NOT Confirmed (SELL): Close={last['close']:.2f} >= Middle={middle:.2f}")

        return False

    def check_pullback_entry_closed(self, direction: str) -> bool:
        """
        ⭐ CORRECTED: Check if CLOSED candle shows pullback and closed in trade direction
        """
        if len(self.df) == 0:
            return False

        last = self.df.iloc[-1]
        middle = last['KC_middle']

        if direction == "BUY":
            # Must touch middle AND close above it
            if last['low'] <= middle and last['close'] > middle:
                self.log(f"✅ Pullback Entry (BUY): Low={last['low']:.2f} <= Middle={middle:.2f}, Close={last['close']:.2f} > Middle")
                return True

        elif direction == "SELL":
            # Must touch middle AND close below it
            if last['high'] >= middle and last['close'] < middle:
                self.log(f"✅ Pullback Entry (SELL): High={last['high']:.2f} >= Middle={middle:.2f}, Close={last['close']:.2f} < Middle")
                return True

        return False

    # ------------------------------------------------------------------------
    # POSITION MANAGEMENT
    # ------------------------------------------------------------------------

    def calculate_lot_size(self, entry_price: float, sl_price: float) -> float:
        sl_distance_pips = abs(entry_price - sl_price) / (self.point * 10)

        if sl_distance_pips == 0:
            return 0

        risk_per_pip = self.config.RISK_USD / sl_distance_pips
        lot_size = risk_per_pip / self.pip_value
        lot_size = round(lot_size / self.lot_step) * self.lot_step
        lot_size = max(self.min_lot, min(lot_size, self.max_lot))

        return lot_size

    def open_position(self, direction: str) -> bool:
        """Open a new position"""
        if len(self.df) == 0:
            return False

        last = self.df.iloc[-1]

        tick = mt5.symbol_info_tick(self.config.SYMBOL)
        if tick is None:
            self.log("❌ ERROR: Failed to get current tick")
            return False

        if direction == "BUY":
            entry_price = tick.ask
            sl_price = last['KC_lower'] - (self.config.SL_ATR_BUFFER * last['ATR'])
            order_type = mt5.ORDER_TYPE_BUY
        else:
            entry_price = tick.bid
            sl_price = last['KC_upper'] + (self.config.SL_ATR_BUFFER * last['ATR'])
            order_type = mt5.ORDER_TYPE_SELL

        tp_price = entry_price + (self.config.TP_RATIO * abs(entry_price - sl_price)) if direction == "BUY" else entry_price - (self.config.TP_RATIO * abs(entry_price - sl_price))

        lot_size = self.calculate_lot_size(entry_price, sl_price)

        if lot_size == 0:
            self.log("❌ ERROR: Lot size = 0")
            return False

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.config.SYMBOL,
            "volume": lot_size,
            "type": order_type,
            "price": entry_price,
            "sl": sl_price,
            "tp": tp_price,
            "magic": self.config.MAGIC_NUMBER,
            "comment": f"EMA_Pullback_{direction}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.log(f"❌ Order failed: {result.retcode} - {result.comment}")
            return False

        self.log(f"✅ {direction} Position Opened")
        self.log(f"   Entry: {entry_price:.2f}, SL: {sl_price:.2f}, TP: {tp_price:.2f}, Lot: {lot_size}")

        return True

    def check_position_status(self) -> bool:
        """Check if position is still open (using MAGIC_NUMBER)"""
        positions = mt5.positions_get(
            symbol=self.config.SYMBOL, 
            magic=self.config.MAGIC_NUMBER
        )

        if positions is None or len(positions) == 0:
            return False  # No position open

        return True  # Position still open

            
    def check_pullback_and_entry_closed(self, direction: str) -> bool:
        """
        Check if CLOSED candle:
        1. Touched middle line
        2. Closed in trade direction

        Returns: True if both conditions met
        """
        if len(self.df) == 0:
            return False

        last = self.df.iloc[-1]
        middle = last['KC_middle']

        if direction == "BUY":
            # Must touch middle AND close ABOVE it
            touched_middle = last['low'] <= middle
            closed_correctly = last['close'] > middle

            if touched_middle and closed_correctly:
                self.log(f"   ✅ Pullback+Entry (BUY): Low={last['low']:.2f} <= Middle={middle:.2f}, Close={last['close']:.2f} > Middle")
                return True
            else:
                if not touched_middle:
                    self.log(f"   ⏳ Middle not touched yet (BUY): Low={last['low']:.2f} > Middle={middle:.2f}")
                elif not closed_correctly:
                    self.log(f"   ⏳ Not closed above middle (BUY): Close={last['close']:.2f} <= Middle={middle:.2f}")

        elif direction == "SELL":
            # Must touch middle AND close BELOW it
            touched_middle = last['high'] >= middle
            closed_correctly = last['close'] < middle

            if touched_middle and closed_correctly:
                self.log(f"   ✅ Pullback+Entry (SELL): High={last['high']:.2f} >= Middle={middle:.2f}, Close={last['close']:.2f} < Middle")
                return True
            else:
                if not touched_middle:
                    self.log(f"   ⏳ Middle not touched yet (SELL): High={last['high']:.2f} < Middle={middle:.2f}")
                elif not closed_correctly:
                    self.log(f"   ⏳ Not closed below middle (SELL): Close={last['close']:.2f} >= Middle={middle:.2f}")

        return False

    # ------------------------------------------------------------------------
    # STATE MACHINE
    # ------------------------------------------------------------------------

    def process_strategy(self, new_candle: bool):
         """Main strategy orchestrator - delegates to state handlers"""

         # Check position status if open
         if self.state == BotState.POSITION_OPEN:
             self.check_position_status()
             # If closed, state changed to SEARCHING - continue execution
         # Delegate to appropriate state handler
         if self.state == BotState.SEARCHING:
             self._handle_searching()
         elif self.state == BotState.IMPULSE_DETECTED_BUY:
             self._handle_impulse_buy()
         elif self.state == BotState.IMPULSE_DETECTED_SELL:
             self._handle_impulse_sell()
         elif self.state == BotState.PULLBACK_TOUCHED_BUY:
             self._handle_pullback_buy(new_candle)
         elif self.state == BotState.PULLBACK_TOUCHED_SELL:
             self._handle_pullback_sell(new_candle)


        # ============================================================
        # STATE HANDLERS (Clean & Modular)
        # ============================================================

    def _handle_searching(self):
        """Handle SEARCHING state - detect impulse"""
        self.log("🔍 SEARCHING: Checking for impulse...")

        impulse = self.detect_impulse_forming()

        if impulse == "BUY":
            self._transition_to(BotState.IMPULSE_DETECTED_BUY, "SEARCHING → IMPULSE_DETECTED_BUY")

        elif impulse == "SELL":
            self._transition_to(BotState.IMPULSE_DETECTED_SELL, "SEARCHING → IMPULSE_DETECTED_SELL")


    def _handle_impulse_buy(self):
        """Handle IMPULSE_DETECTED_BUY state"""
        forming = self.get_forming_candle()

        if forming is None:
            return

        # Check for opposite impulse (reset)
        if forming['low'] <= forming['KC_lower']:
            self.log("🔄 Reset: Low touched lower band.")
            self._transition_to(BotState.SEARCHING, "IMPULSE_DETECTED_BUY → SEARCHING (Reset)")
            return

        # Check pullback touch
        if self.check_pullback_touch_forming("BUY"):
            self._transition_to(BotState.PULLBACK_TOUCHED_BUY, "IMPULSE_DETECTED_BUY → PULLBACK_TOUCHED_BUY")


    def _handle_impulse_sell(self):
        """Handle IMPULSE_DETECTED_SELL state"""
        forming = self.get_forming_candle()

        if forming is None:
            return

        # Check for opposite impulse (reset)
        if forming['high'] >= forming['KC_upper']:
            self.log("🔄 Reset: High touched upper band.")
            self._transition_to(BotState.SEARCHING, "IMPULSE_DETECTED_SELL → SEARCHING (Reset)")
            return

        # Check pullback touch
        if self.check_pullback_touch_forming("SELL"):
            self._transition_to(BotState.PULLBACK_TOUCHED_SELL, "IMPULSE_DETECTED_SELL → PULLBACK_TOUCHED_SELL")


    def _handle_pullback_buy(self, new_candle: bool):
        """Handle PULLBACK_TOUCHED_BUY state"""
        # Wait for closed candle
        if not new_candle:
            return

        # Check entry confirmation
        if self.check_pullback_entry_closed("BUY"):
            if self.open_position("BUY"):
                self._transition_to(BotState.POSITION_OPEN, "PULLBACK_TOUCHED_BUY → POSITION_OPEN")
            else:
                self.log("❌ Failed to open position.")
                self._transition_to(BotState.SEARCHING, "PULLBACK_TOUCHED_BUY → SEARCHING (Order Failed)")
        else:
            self.log("⏳ Closed candle did not confirm entry.")
            self._transition_to(BotState.SEARCHING, "PULLBACK_TOUCHED_BUY → SEARCHING (No Confirmation)")


    def _handle_pullback_sell(self, new_candle: bool):
        """Handle PULLBACK_TOUCHED_SELL state"""
        # Wait for closed candle
        if not new_candle:
            return

        # Check entry confirmation
        if self.check_pullback_entry_closed("SELL"):
            if self.open_position("SELL"):
                self._transition_to(BotState.POSITION_OPEN, "PULLBACK_TOUCHED_SELL → POSITION_OPEN")
            else:
                self.log("❌ Failed to open position.")
                self._transition_to(BotState.SEARCHING, "PULLBACK_TOUCHED_SELL → SEARCHING (Order Failed)")
        else:
            self.log("⏳ Closed candle did not confirm entry.")
            self._transition_to(BotState.SEARCHING, "PULLBACK_TOUCHED_SELL → SEARCHING (No Confirmation)")


    # ============================================================
    # HELPER: Clean State Transition
    # ============================================================

    def _transition_to(self, new_state: BotState, log_message: str):
        """Centralized state transition with logging"""
        self.state = new_state
        self.log(f"🔄 State: {log_message}")


    


    # ------------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------------

    def run(self):
        """Main bot loop"""
        self.log("=" * 60)
        self.log("🤖 Live EMA Pullback Bot Started (CORRECTED LOGIC)")
        self.log("=" * 60)

        while True:
            try:
                if not self.check_mt5_connection():
                    self.log("⏸️  Waiting for MT5 connection...")
                    time.sleep(10)
                    continue
        
                if not self.is_market_open():
                    time.sleep(60)
                    continue
                
                new_candle = self.update_data()
                self.process_strategy(new_candle)
                time.sleep(1)

            except KeyboardInterrupt:
                self.log("\n🛑 Bot stopped by user")
                break
            except Exception as e:
                self.log(f"❌ ERROR: {e}")
                time.sleep(5)

        mt5.shutdown()
        self.log("👋 MT5 connection closed")

    def log(self, message: str):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    config = BotConfig()
    bot = LiveEMAPullbackBot(config)

    if bot.initialize():
        bot.run()
