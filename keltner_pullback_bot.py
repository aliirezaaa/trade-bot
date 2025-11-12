#!/usr/bin/env python3
"""
Live Keltner Pullback Bot - Simplified (CLOSED Candles Only)
- All logic uses CLOSED candles
- No forming candle checks
- Clean 2-state machine: SEARCHING + POSITION_OPEN
"""

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
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

    # Monitoring
    HEARTBEAT_INTERVAL: int = 60
    MAX_NO_DATA_TIME: int = 300
    MIN_PULLBACK_DISTANCE = 1
    UPDATE_INTERVAL=1
# ============================================================================
# BOT STATE (Simplified)
# ============================================================================

class BotState(Enum):
    SEARCHING = "SEARCHING"
    POSITION_OPEN = "POSITION_OPEN"

# ============================================================================
# MAIN BOT
# ============================================================================

class LiveKeltnerBot:
    def __init__(self, config: BotConfig):
        self.config = config
        self.state = BotState.SEARCHING
        self.df = pd.DataFrame()
        self.last_processed_time = None

        # Impulse tracking
        self.impulse_direction = None  # "BUY" or "SELL" or None
        self.impulse_candle_time = None  # ⭐ تغییر از index به timestamp
        # MT5 symbol info
        self.point = 0
        self.pip_value = 0
        self.min_lot = 0
        self.max_lot = 0
        self.lot_step = 0

        # Monitoring
        self.last_data_time = datetime.now()
        self.last_heartbeat = datetime.now()
        self.iteration_count = 0

    # ------------------------------------------------------------------------
    # MONITORING & HEALTH CHECK
    # ------------------------------------------------------------------------
    # ------------------------------------------------------------------------
# HEALTH MONITORING & RECOVERY
# ------------------------------------------------------------------------
    def connect_mt5(self) -> bool:
        """Initialize MT5 connection"""
        try:
            if not mt5.initialize():
                self.log(f"❌ MT5 initialize failed: {mt5.last_error()}")
                return False

            self.log("✅ MT5 initialized successfully")
            return True

        except Exception as e:
            self.log(f"❌ MT5 initialization error: {e}")
            return False

    def load_symbol_info(self) -> bool:
        """Load symbol information and trading parameters"""
        try:
            symbol_info = mt5.symbol_info(self.config.SYMBOL)

            if symbol_info is None:
                self.log(f"❌ Symbol {self.config.SYMBOL} not found")
                return False

            # Make symbol visible if needed
            if not symbol_info.visible:
                if not mt5.symbol_select(self.config.SYMBOL, True):
                    self.log(f"❌ Failed to select {self.config.SYMBOL}")
                    return False

            # Store symbol parameters
            self.point = symbol_info.point
            self.pip_value = 10 if self.config.SYMBOL in ["XAUUSD", "XAGUSD"] else 1
            self.min_lot = symbol_info.volume_min
            self.max_lot = symbol_info.volume_max
            self.lot_step = symbol_info.volume_step

            self.log(f"✅ Symbol info loaded: {self.config.SYMBOL}")
            self.log(f"   Point: {self.point}, Pip Value: {self.pip_value}")
            self.log(f"   Lot Range: {self.min_lot} - {self.max_lot} (Step: {self.lot_step})")

            return True

        except Exception as e:
            self.log(f"❌ Error loading symbol info: {e}")
            return False
    
    def check_mt5_connection(self) -> bool:
        """Check if MT5 is still connected"""
        try:
            terminal_info = mt5.terminal_info()
            if terminal_info is None:
                self.log("   ⚠️ MT5 terminal_info returned None")
                return False

            # Check if terminal is connected to trade server
            if not terminal_info.connected:
                self.log("   ⚠️ MT5 not connected to trade server")
                return False

            return True
        except Exception as e:
            self.log(f"   ⚠️ Error checking MT5 connection: {e}")
            return False

    def is_market_open(self) -> bool:
        """Check if market is open for trading"""
        try:
            # Get current symbol info
            symbol_info = mt5.symbol_info(self.config.SYMBOL)
            if symbol_info is None:
                return False

            # Check if trading is allowed
            if not symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
                return False

            # Get latest tick
            tick = mt5.symbol_info_tick(self.config.SYMBOL)
            if tick is None:
                return False

            # Check if last tick is recent (< 60 seconds old)
            current_time = datetime.now().timestamp()
            tick_time = tick.time

            if (current_time - tick_time) > 60:
                self.log(f"   📴 Market appears closed. Last tick: {datetime.fromtimestamp(tick_time)}")
                return False

            return True

        except Exception as e:
            self.log(f"   ⚠️ Error checking market status: {e}")
            return False

    def recover_data(self) -> bool:
        """Try to recover from data freeze by reloading data"""
        try:
            self.log("   🔧 Attempting data recovery...")

            # Check MT5 connection first
            if not self.check_mt5_connection():
                self.log("   ❌ MT5 not connected. Attempting reconnect...")
                mt5.shutdown()
                time.sleep(2)
                if not self.connect_mt5():
                    self.log("   ❌ Reconnection failed")
                    return False

                if not self.load_symbol_info():
                    self.log("   ❌ Failed to reload symbol info")
                    return False

            # Check if market is open
            if not self.is_market_open():
                self.log("   📴 Market is closed. Recovery not needed.")
                return True

            # ⭐ Reset ALL state BEFORE loading data
            old_impulse = self.impulse_direction
            old_state = self.state

            # Reset impulse tracking
            self.impulse_direction = None
            self.impulse_candle_time = None  # ⭐ تغییر از index به time

            # Ensure state is correct
            if self.state != BotState.POSITION_OPEN:
                self.state = BotState.SEARCHING

            # Try to reload data
            if self.load_initial_data():
                self.log("   ✅ Data recovered successfully")
                self.last_data_time = datetime.now()

                if old_impulse:
                    self.log(f"   ⚠️ Previous {old_impulse} impulse cleared (was in {old_state.value})")
                    self.log(f"   ℹ️ Bot reset to SEARCHING state - looking for new setup")

                return True
            else:
                self.log("   ❌ Data reload failed")
                return False

        except Exception as e:
            self.log(f"   ❌ Recovery error: {e}")
            import traceback
            traceback.print_exc()
            return False


    def heartbeat(self):
        """Periodic health check"""
        now = datetime.now()
    
        if (now - self.last_heartbeat).seconds >= self.config.HEARTBEAT_INTERVAL:
            self.log("=" * 60)
            self.log("💓 HEARTBEAT CHECK")
            self.log(f"   State: {self.state.value}")
            
            # ⭐ نمایش وضعیت impulse با timestamp
            if self.impulse_direction:
                if self.impulse_candle_time:
                    try:
                        impulse_index = self.df.index.get_loc(self.impulse_candle_time)
                        current_index = len(self.df) - 1
                        distance = current_index - impulse_index
                        self.log(f"   Impulse: {self.impulse_direction} (Active) - {distance} candles ago")
                    except KeyError:
                        self.log(f"   Impulse: {self.impulse_direction} (EXPIRED - not in window)")
                else:
                    self.log(f"   Impulse: {self.impulse_direction} (No timestamp recorded!)")
            else:
                self.log(f"   Impulse: None (Searching)")
                
            self.log(f"   Iteration Count: {self.iteration_count}")
            self.log(f"   Last Data: {(now - self.last_data_time).seconds}s ago")
            self.log(f"   Last Candle: {self.last_processed_time}")
        # ⭐ به‌روز کردن timestamp همون اول (قبل از return)
            self.last_heartbeat = now

            # Check MT5 connection
            if not self.check_mt5_connection():
                self.log("   ⚠️ MT5 Connection Issue!")
                self.log("=" * 60)
                return False

            # Check market status
            if not self.is_market_open():
                self.log("   📴 Market is CLOSED (This is normal)")
                self.log("=" * 60)
                return True  # Market closed is not an error

            # Check data freshness
            data_age = (now - self.last_data_time).seconds
            if data_age > self.config.MAX_NO_DATA_TIME:
                self.log(f"   ❌ DATA FREEZE DETECTED! No new data for {data_age}s")

                # ⭐ Try recovery immediately
                if self.recover_data():
                    self.log("   ✅ Recovery successful!")
                    self.log("=" * 60)
                    return True
                else:
                    self.log("   ❌ Recovery failed. Will retry next heartbeat (60s)...")
                    self.log("=" * 60)
                    return False

            self.log("   ✅ All systems operational")
            self.log("=" * 60)

        return True  # ⭐ اگر هنوز وقت heartbeat نیست، بدون چک True برگردون

    # ------------------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------------------

    

    # ------------------------------------------------------------------------
    # INITIALIZATION
    # ------------------------------------------------------------------------
    def load_initial_data(self) -> bool:
        """Load initial historical data and calculate indicators"""
        try:
            # Fetch historical candles
            rates = mt5.copy_rates_from_pos(
                self.config.SYMBOL,
                self.config.TIMEFRAME,
                0,
                self.config.INITIAL_CANDLES
            )

            if rates is None or len(rates) == 0:
                self.log("❌ Failed to load initial data from MT5")
                return False

            # Convert to DataFrame
            self.df = pd.DataFrame(rates)
            self.df['time'] = pd.to_datetime(self.df['time'], unit='s')
            self.df.set_index('time', inplace=True)

            # Calculate indicators
            self.calculate_indicators()

            # Check if we have valid data after indicator calculation
            if len(self.df) == 0:
                self.log("❌ DataFrame empty after calculating indicators")
                return False

            # Set last processed time
            self.last_processed_time = self.df.index[-1]
            self.last_data_time = datetime.now()

            # Log success
            self.log(f"✅ Loaded {len(self.df)} candles")
            self.log(f"   First candle: {self.df.index[0].strftime('%Y-%m-%d %H:%M:%S')}")
            self.log(f"   Last candle:  {self.last_processed_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Show last candle values
            last = self.df.iloc[-1]
            if 'KC_upper' in last and not pd.isna(last['KC_upper']):
                self.log(f"   Last Close: {last['close']:.2f}")
                self.log(f"   KC Upper:   {last['KC_upper']:.2f}")
                self.log(f"   KC Middle:  {last['KC_middle']:.2f}")
                self.log(f"   KC Lower:   {last['KC_lower']:.2f}")
                self.log(f"   ATR:        {last['ATR']:.2f}")

            return True

        except Exception as e:
            self.log(f"❌ Error loading initial data: {e}")
            import traceback
            traceback.print_exc()
            return False

    def initialize(self) -> bool:
        """Complete initialization process"""
        # Connect to MT5
        if not self.connect_mt5():
            return False

        # Load symbol info
        if not self.load_symbol_info():
            return False

        # Load initial data
        if not self.load_initial_data():
            return False

        return True

    # ------------------------------------------------------------------------
    # DATA UPDATE
    # ------------------------------------------------------------------------

    def update_data(self) -> bool:
        """Update with new closed candle"""
        try:
            rates = mt5.copy_rates_from_pos(self.config.SYMBOL, self.config.TIMEFRAME, 0, 2)

            if rates is None or len(rates) < 2:
                if (datetime.now() - self.last_data_time).seconds > 120:
                    self.log(f"⚠️ No data received for 2+ minutes")
                return False

            temp_df = pd.DataFrame(rates)
            temp_df['time'] = pd.to_datetime(temp_df['time'], unit='s')
            temp_df.set_index('time', inplace=True)

            # Only closed candle matters
            previous_time = temp_df.index[-2]
            previous_candle = temp_df.iloc[-2]

            if previous_time > self.last_processed_time:
                new_row = temp_df.iloc[-2:-1]

                self.df = pd.concat([self.df, new_row])
                self.df = self.df.iloc[-self.config.INITIAL_CANDLES:]

                self.calculate_indicators()

                if len(self.df) == 0:
                    return False

                self.last_processed_time = previous_time
                self.last_data_time = datetime.now()

                # Log candle
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


        """Check if market is open"""
        symbol_info = mt5.symbol_info(self.config.SYMBOL)

        if symbol_info is None:
            self.log(f"⚠️ Symbol {self.config.SYMBOL} not found")
            return False

        if symbol_info.trade_mode != mt5.SYMBOL_TRADE_MODE_FULL:
            return False

        spread = symbol_info.spread
        if spread > 100:
            self.log(f"⚠️ Abnormal spread: {spread} (Market might be closed)")
            return False

        return True

    def calculate_indicators(self):
        """Calculate all indicators"""
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

    # ------------------------------------------------------------------------
    # FILTERS
    # ------------------------------------------------------------------------

    def check_filters(self, direction: str) -> bool:
        """Check if filters allow trading"""
        last = self.df.iloc[-1]

        if self.config.USE_EMA200_FILTER:
            if 'EMA_200' not in last or pd.isna(last['EMA_200']):
                return False

            if direction == "BUY" and last['close'] < last['EMA_200']:
                self.log(f"   ⛔ EMA200 Filter: BUY rejected")
                return False

            if direction == "SELL" and last['close'] > last['EMA_200']:
                self.log(f"   ⛔ EMA200 Filter: SELL rejected")
                return False

        if self.config.USE_ADX_FILTER:
            if 'ADX' not in last or pd.isna(last['ADX']):
                return False

            if last['ADX'] < self.config.ADX_THRESHOLD:
                self.log(f"   ⛔ ADX Filter: ADX={last['ADX']:.1f} < {self.config.ADX_THRESHOLD}")
                return False

        return True

    # ------------------------------------------------------------------------
    # STRATEGY LOGIC (Closed Candles Only)
    # ------------------------------------------------------------------------

    def detect_impulse_closed(self) -> str:
       """Detect impulse from CLOSED candle using High/Low"""
       last = self.df.iloc[-1]

       # BUY Impulse: High touched/crossed upper band
       if last['high'] >= last['KC_upper']:
           if self.check_filters("BUY"):
               self.impulse_candle_time = last.name  # ⭐ ذخیره timestamp
               self.log(f"🚀 IMPULSE (BUY): High={last['high']:.2f} >= Upper={last['KC_upper']:.2f} [Time: {self.impulse_candle_time}]")
               return "BUY"

       # SELL Impulse: Low touched/crossed lower band
       if last['low'] <= last['KC_lower']:
           if self.check_filters("SELL"):
               self.impulse_candle_time = last.name  # ⭐ ذخیره timestamp
               self.log(f"🚀 IMPULSE (SELL): Low={last['low']:.2f} <= Lower={last['KC_lower']:.2f} [Time: {self.impulse_candle_time}]")
               return "SELL"

       return None



    def check_pullback_and_entry_closed(self, direction: str) -> bool:
        """
        Check if CLOSED candle shows valid pullback entry
        WITH minimum distance requirement from impulse candle
        """

        # ⭐ چک فاصله با استفاده از timestamp
        if self.impulse_candle_time is not None:
            try:
                # پیدا کردن index شمعه impulse در DataFrame فعلی
                impulse_index = self.df.index.get_loc(self.impulse_candle_time)
                current_index = len(self.df) - 1
                candle_distance = current_index - impulse_index

                if candle_distance < self.config.MIN_PULLBACK_DISTANCE:
                    self.log(f"   ⏳ Distance: {candle_distance}/{self.config.MIN_PULLBACK_DISTANCE} candles (waiting...)")
                    return False

                self.log(f"   ✅ Distance OK: {candle_distance} candles from impulse")

            except KeyError:
                # شمعه impulse دیگر در DataFrame نیست (خیلی قدیمیه)
                self.log(f"   ⚠️ Impulse candle expired (not in window). Clearing impulse...")
                self.impulse_direction = None
                self.impulse_candle_time = None
                return False

        # منطق پولبک (بدون تغییر)
        last = self.df.iloc[-1]
        middle = last['KC_middle']

        if direction == "BUY":
            touched = last['low'] <= middle
            closed_correctly = last['close'] > middle

            if touched and closed_correctly:
                self.log(f"✅ Pullback Entry (BUY): Low={last['low']:.2f} <= Middle={middle:.2f}, Close={last['close']:.2f} > Middle")
                return True
            else:
                if not touched:
                    self.log(f"   ⏳ Waiting: Low={last['low']:.2f} hasn't touched Middle={middle:.2f} yet")
                elif not closed_correctly:
                    self.log(f"   ⏳ Waiting: Close={last['close']:.2f} not above Middle={middle:.2f}")

        elif direction == "SELL":
            touched = last['high'] >= middle
            closed_correctly = last['close'] < middle

            if touched and closed_correctly:
                self.log(f"✅ Pullback Entry (SELL): High={last['high']:.2f} >= Middle={middle:.2f}, Close={last['close']:.2f} < Middle")
                return True
            else:
                if not touched:
                    self.log(f"   ⏳ Waiting: High={last['high']:.2f} hasn't touched Middle={middle:.2f} yet")
                elif not closed_correctly:
                    self.log(f"   ⏳ Waiting: Close={last['close']:.2f} not below Middle={middle:.2f}")

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

        lot_size = round(lot_size / self.lot_step) * self.lot_step
        lot_size = max(self.min_lot, min(lot_size, self.max_lot))

        return lot_size

    def open_position(self, direction: str) -> bool:
        """Open market order"""
        last = self.df.iloc[-1]

        tick = mt5.symbol_info_tick(self.config.SYMBOL)
        if tick is None:
            self.log("❌ Failed to get tick")
            return False

        if direction == "BUY":
            entry_price = tick.ask
            sl_price = last['KC_lower'] - (self.config.SL_ATR_BUFFER * last['ATR'])
            order_type = mt5.ORDER_TYPE_BUY
        else:
            entry_price = tick.bid
            sl_price = last['KC_upper'] + (self.config.SL_ATR_BUFFER * last['ATR'])
            order_type = mt5.ORDER_TYPE_SELL

        sl_distance = abs(entry_price - sl_price)
        tp_price = entry_price + (self.config.TP_RATIO * sl_distance) if direction == "BUY" else entry_price - (self.config.TP_RATIO * sl_distance)

        lot_size = self.calculate_lot_size(entry_price, sl_price)

        if lot_size < self.min_lot:
            self.log(f"❌ Lot size {lot_size} below minimum")
            return False

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

        result = mt5.order_send(request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            self.log(f"❌ Order failed: {result.comment if result else 'None'}")
            return False

        self.log(f"🟢 POSITION OPENED: {direction} {lot_size} lot @ {entry_price:.5f}, SL={sl_price:.5f}, TP={tp_price:.5f}")
        return True

    def check_position_status(self) -> bool:
        """Check if any position is open"""
        positions = mt5.positions_get(symbol=self.config.SYMBOL, magic=self.config.MAGIC_NUMBER)

        if positions is None or len(positions) == 0:
            return False

        return True

    # ------------------------------------------------------------------------
    # STATE MACHINE (Simplified)
    # ------------------------------------------------------------------------

    def process_strategy(self, new_candle: bool):
        """Main strategy logic"""

        # ======== State: POSITION_OPEN ========
        if self.state == BotState.POSITION_OPEN:
            if not self.check_position_status():
                self.log("✅ Position closed. → SEARCHING")
                self.state = BotState.SEARCHING
                self.impulse_direction = None
                self.impulse_candle_time = None  # ⭐
            return

        if not new_candle:
            return

        # ======== State: SEARCHING ========
        last = self.df.iloc[-1]

        # 1. Check for opposite impulse (reset)
        if self.impulse_direction == "BUY":
            if last['low'] <= last['KC_lower']:
                self.log(f"🔄 Opposite impulse (SELL). Resetting.")
                self.impulse_direction = "SELL"
                self.impulse_candle_time = None  # ⭐

        elif self.impulse_direction == "SELL":
            if last['high'] >= last['KC_upper']:
                self.log(f"🔄 Opposite impulse (BUY). Resetting.")
                self.impulse_direction = "BUY"
                self.impulse_candle_time = None  # ⭐

        # 2. If no impulse yet, detect one
        if self.impulse_direction is None:
            impulse = self.detect_impulse_closed()
            if impulse:
                self.impulse_direction = impulse
                self.log(f"🎯 Impulse detected: {impulse}. Waiting {self.config.MIN_PULLBACK_DISTANCE}+ candles for pullback...")
                return

        # 3. If impulse exists, check for pullback entry
        if self.impulse_direction:
            if self.check_pullback_and_entry_closed(self.impulse_direction):
                if self.open_position(self.impulse_direction):
                    self.state = BotState.POSITION_OPEN
                    self.log(f"🔄 State: SEARCHING → POSITION_OPEN")
                    self.impulse_direction = None
                    self.impulse_candle_time = None  # ⭐
                else:
                    self.log("❌ Failed to open position. Resetting impulse.")
                    self.impulse_direction = None
                    self.impulse_candle_time = None  # ⭐

    def log(self, message: str):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

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
                self.log("❌ Failed to connect to MT5. Exiting...")
                return

            # Step 2: Load symbol info
            if not self.load_symbol_info():
                self.log("❌ Failed to load symbol info. Exiting...")
                mt5.shutdown()
                return

            # Step 3: Load initial data
            if not self.load_initial_data():
                self.log("❌ Failed to load initial data. Exiting...")
                mt5.shutdown()
                return

            self.log("="*60)
            self.log("🟢 BOT IS NOW RUNNING (Press Ctrl+C to stop)")
            self.log("="*60)

            # Main loop
            try:
                while True:
                    # ⭐ Heartbeat check (هر 60 ثانیه یکبار)
                    if not self.heartbeat():
                        # Heartbeat failed - wait and retry
                        time.sleep(10)
                        continue

                    # ⭐ Check for new candle
                    new_candle = self.update_data()

                    # ⭐ Process strategy
                    self.process_strategy(new_candle)

                    # ⭐ Increment iteration counter
                    self.iteration_count += 1

                    # ⭐ Sleep before next check
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
# MAIN
# ============================================================================

if __name__ == "__main__":
    config = BotConfig()
    bot = LiveKeltnerBot(config)

    if bot.initialize():
        bot.run()
