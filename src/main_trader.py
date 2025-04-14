# START OF FILE: src/main_trader.py

import logging
import time
from pathlib import Path
import pandas as pd
from decimal import Decimal
import schedule  # Added for scheduling tasks like pivot recalc
from typing import Optional, Dict, Any  # Added Optional, Dict, Any

# --- Add project root to sys.path ---
import os
import sys
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
# --- End sys.path modification ---

# Project Imports
try:
    from config.settings import load_config, get_config_value  # Added get_config_value
    from src.utils.logging_setup import setup_logging
    from src.utils.formatting import to_decimal  # Import for potential use later
    from src.connectors.binance_us import BinanceUSConnector
    from src.data.kline_fetcher import fetch_and_prepare_klines
    # Import the indicator calculation functions
    from src.analysis.indicators import (
        calculate_atr,
        calculate_sma,
        calculate_rsi,
        calculate_macd,
        calculate_pivot_points,
        # Import default periods for reference or fallback
        ATR_PERIOD,
        SMA_SHORT_PERIOD,
        SMA_LONG_PERIOD,
        RSI_PERIOD,
        MACD_FAST_PERIOD,
        MACD_SLOW_PERIOD,
        MACD_SIGNAL_PERIOD
    )
    # Import the profit taking function (will be used later)
    from src.strategies.profit_taking import calculate_dynamic_tp_price
except ImportError as e:
    # Use basic logging if setup hasn't happened yet
    logging.basicConfig(level=logging.ERROR)
    logging.critical(
        f"FATAL ERROR: Could not import necessary modules. Check PYTHONPATH and module paths. Error: {e}")
    sys.exit(1)

# --- Global Logger ---
logger = logging.getLogger(__name__)  # Will be configured by setup_logging

# --- Main Application Class ---


class GeminiTrader:
    """
    Main class orchestrating the GeminiTrader bot operations.
    Handles initialization, data fetching, indicator calculation,
    state management, and the main trading loop.
    """

    def __init__(self):
        self.config = {}
        self.connector: Optional[BinanceUSConnector] = None  # Type hint
        # State dictionary to hold dynamic data
        self.state = {
            "klines": pd.DataFrame(),       # Stores the historical klines (OHLCV)
            # Stores latest calculated indicator values (SMA_10, RSI_14, etc.)
            "indicators": {},
            # Stores the current period's pivot levels (pd.Series or None)
            "pivot_levels": None,
            "last_data_update_time": None,  # Timestamp of last successful kline fetch
            "last_pivot_calc_time": None,  # Timestamp of last pivot calculation
            "symbol_info": None,            # Cache for exchange info for the trading symbol
            # --- Future state additions ---
            # "open_orders": [],            # List of currently open orders
            # "positions": {},              # Dictionary tracking current asset positions {symbol: {'qty': Decimal, 'entry_price': Decimal, ...}}
            # "confidence_score": None,     # Latest calculated confidence score
            # "account_balance": {},        # Cache of relevant account balances
        }
        self.is_running = False
        self._initialize()

    def _initialize(self):
        """Load configuration, set up logging, and initialize connectors."""
        print("Initializing GeminiTrader...")  # Print early before logging is set

        # 1. Load Configuration
        self.config = load_config()
        if not self.config:
            logging.critical(
                "FATAL ERROR: Configuration could not be loaded. Exiting.")
            sys.exit(1)
        print("Configuration loaded.")

        # 2. Setup Logging
        try:
            log_level_str = get_config_value(
                self.config, ('logging', 'level'), 'INFO').upper()
            log_level = getattr(logging, log_level_str, logging.INFO)
            log_file_path_str = get_config_value(
                self.config, ('logging', 'trader_log_path'), 'data/logs/trader.log')
            log_file_path = _project_root / log_file_path_str

            setup_logging(
                log_level=log_level,
                log_file=log_file_path,
                max_bytes=get_config_value(
                    self.config, ('logging', 'max_bytes'), 10*1024*1024),
                backup_count=get_config_value(
                    self.config, ('logging', 'backup_count'), 5),
                console_logging=True  # Keep console logging for interactive feedback
            )
            logger.info(
                f"Logging setup complete. Level: {log_level_str}, File: {log_file_path}")
        except Exception as e:
            logging.exception(
                f"Error setting up logging from config: {e}. Using basic config.", exc_info=True)

        # 3. Initialize Binance Connector
        try:
            api_key = get_config_value(self.config, ('binance_us', 'api_key'))
            api_secret = get_config_value(
                self.config, ('binance_us', 'api_secret'))

            if not api_key or not api_secret or 'YOUR_ACTUAL' in str(api_key):
                logger.critical(
                    "FATAL ERROR: Binance API Key/Secret missing or invalid in config/environment. Exiting.")
                sys.exit(1)

            self.connector = BinanceUSConnector(
                api_key=api_key,
                api_secret=api_secret,
                config=self.config
            )
            if not self.connector.get_client():
                logger.critical(
                    "FATAL ERROR: Failed to initialize Binance client within the connector. Exiting.")
                sys.exit(1)
            logger.info("BinanceUS Connector initialized successfully.")

        except Exception as e:
            logger.critical(
                f"FATAL ERROR: Connector initialization failed: {e}. Exiting.", exc_info=True)
            sys.exit(1)

        # 4. Fetch Initial Symbol Info (needed for filters)
        self._update_symbol_info()

        # 5. Load Initial Data
        logger.info("Performing initial market data fetch...")
        if not self._update_market_data():
            logger.warning(
                "Initial market data fetch failed. Will retry in loop.")
        else:
            self._calculate_indicators()
            self._update_pivot_points()

        # 6. Setup Scheduler
        self._setup_scheduler()

        logger.info("GeminiTrader Initialization Complete.")

    def _get_trading_param(self, key: str, default=None):
        """Helper to get parameters from the [trading] config section."""
        return get_config_value(self.config, ('trading', key), default)

    def _update_symbol_info(self) -> bool:
        """Fetches and caches exchange information for the trading symbol."""
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        logger.info(f"Fetching exchange info for symbol: {symbol}")
        if not self.connector:
            return False

        try:
            info = self.connector.get_symbol_info(symbol)
            if info:
                self.state['symbol_info'] = info
                logger.debug(f"Successfully cached symbol info for {symbol}.")
                # Potential: Save to cache file defined in config['data']['exchange_info_cache']
                return True
            else:
                logger.error(
                    f"Failed to retrieve symbol info for {symbol} from exchange.")
                self.state['symbol_info'] = None
                return False
        except Exception as e:
            logger.exception(f"Error fetching symbol info for {symbol}: {e}")
            self.state['symbol_info'] = None
            return False

    def _update_market_data(self) -> bool:
        """Fetches the latest kline data required for indicator calculations."""
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        interval = self._get_trading_param('interval', '1h')
        # Use updated default/config value
        limit = self._get_trading_param('kline_limit', 200)

        logger.info(
            f"Fetching latest {limit} klines for {symbol} ({interval})...")
        if not self.connector:
            logger.error("Connector not available.")
            return False

        latest_klines_df = fetch_and_prepare_klines(
            connector=self.connector,
            symbol=symbol,
            interval=interval,
            limit=limit
        )

        if latest_klines_df is not None and not latest_klines_df.empty:
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in latest_klines_df.columns for col in required_cols):
                logger.error(
                    f"Fetched kline data missing required columns. Found: {list(latest_klines_df.columns)}")
                return False
            if not isinstance(latest_klines_df.index, pd.DatetimeIndex):
                logger.error(
                    "Fetched kline data index is not a DatetimeIndex.")
                return False
            # Basic type check
            try:
                if not isinstance(to_decimal(latest_klines_df['Close'].iloc[-1]), Decimal):
                    logger.warning(
                        "Fetched 'Close' column may not contain Decimals.")
            except Exception:
                logger.warning(
                    "Could not verify Decimal type in fetched klines.")

            logger.debug(
                f"Successfully fetched {len(latest_klines_df)} klines. Updating state.")
            self.state["klines"] = latest_klines_df
            self.state["last_data_update_time"] = pd.Timestamp.utcnow()
            return True
        else:
            logger.warning(
                f"Failed to fetch or received empty kline data for {symbol}.")
            return False

    def _calculate_indicators(self):
        """Calculates all required indicators based on the current kline data."""
        if self.state["klines"].empty:
            logger.warning(
                "Kline data is empty, skipping indicator calculation.")
            self.state["indicators"] = {}
            return

        df = self.state["klines"]
        logger.info(f"Calculating indicators on {len(df)} klines...")

        # Get periods from config or use defaults
        atr_p = get_config_value(
            self.config, ('strategies', 'geometric_grid', 'atr_length'), ATR_PERIOD)
        sma_s = SMA_SHORT_PERIOD
        sma_l = SMA_LONG_PERIOD
        rsi_p = RSI_PERIOD
        macd_f = MACD_FAST_PERIOD
        macd_s = MACD_SLOW_PERIOD
        macd_g = MACD_SIGNAL_PERIOD

        calculated_indicators = {}
        try:
            atr = calculate_atr(df, length=atr_p)
            sma10 = calculate_sma(df, period=sma_s, price_col='Close')
            sma50 = calculate_sma(df, period=sma_l, price_col='Close')
            rsi = calculate_rsi(df, period=rsi_p, price_col='Close')
            macd_df = calculate_macd(
                df, fast_period=macd_f, slow_period=macd_s, signal_period=macd_g, price_col='Close')

            def get_last_valid(series: Optional[pd.Series]) -> Optional[Decimal]:
                if series is not None and not series.empty:
                    last_valid = series.dropna(
                    ).iloc[-1] if not series.dropna().empty else None
                    return to_decimal(last_valid) if last_valid is not None else None
                return None

            calculated_indicators[f'ATR_{atr_p}'] = get_last_valid(atr)
            calculated_indicators[f'SMA_{sma_s}'] = get_last_valid(sma10)
            calculated_indicators[f'SMA_{sma_l}'] = get_last_valid(sma50)
            calculated_indicators[f'RSI_{rsi_p}'] = get_last_valid(rsi)

            if macd_df is not None and not macd_df.empty:
                calculated_indicators['MACD'] = get_last_valid(
                    macd_df.get('MACD'))
                calculated_indicators['Signal'] = get_last_valid(
                    macd_df.get('Signal'))
                calculated_indicators['Histogram'] = get_last_valid(
                    macd_df.get('Histogram'))
            else:
                calculated_indicators['MACD'], calculated_indicators['Signal'], calculated_indicators['Histogram'] = None, None, None

            # --- State Update ---
            self.state["indicators"] = calculated_indicators

            # Build the log string manually (Corrected f-string handling)
            indicator_log_items = []
            for k, v in calculated_indicators.items():
                value_str = f"'{v:.4f}'" if isinstance(v, Decimal) else repr(v)
                indicator_log_items.append(f"'{k}': {value_str}")
            indicator_log_str = "{ " + ", ".join(indicator_log_items) + " }"
            logger.info(f"Latest Indicators calculated: {indicator_log_str}")

        except Exception as e:
            logger.exception("Error occurred during indicator calculation.")

    def _update_pivot_points(self):
        """Fetches previous period data and calculates pivot points."""
        pivot_interval = '1d'  # Example: Daily pivots
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        logger.info(
            f"Attempting to update {pivot_interval} pivot points for {symbol}...")
        if not self.connector:
            return

        now_utc = pd.Timestamp.utcnow()
        end_of_yesterday = now_utc.normalize() - pd.Timedelta(seconds=1)
        start_of_yesterday = end_of_yesterday.normalize()
        start_ts_ms = int(start_of_yesterday.timestamp() * 1000)
        end_ts_ms = int(end_of_yesterday.timestamp() * 1000)
        logger.debug(
            f"Fetching previous period kline: {start_of_yesterday} to {end_of_yesterday}")

        try:
            prev_klines_df = fetch_and_prepare_klines(
                connector=self.connector, symbol=symbol, interval=pivot_interval,
                start_str=str(start_ts_ms), end_str=str(end_ts_ms), limit=1
            )
            if prev_klines_df is not None and not prev_klines_df.empty:
                prev_period_data = prev_klines_df.iloc[[-1]]
                pivot_levels = calculate_pivot_points(prev_period_data)
                if pivot_levels is not None:
                    self.state["pivot_levels"] = pivot_levels
                    self.state["last_pivot_calc_time"] = now_utc
                    pivots_log = {k: f"{v:.4f}" for k,
                                  v in pivot_levels.items()}
                    logger.info(
                        f"Successfully updated {pivot_interval} Pivot Points: {pivots_log}")
                else:
                    logger.warning(
                        "Calculation of pivot points failed from fetched previous period data.")
            else:
                logger.warning(
                    f"Could not fetch previous {pivot_interval} kline data for pivot point calc.")
        except Exception as e:
            logger.exception(f"Error occurred during pivot point update.")

    def _setup_scheduler(self):
        """Sets up scheduled tasks."""
        logger.info("Setting up scheduler...")
        try:
            # Example: Update pivots daily
            schedule.every().day.at("00:01", "UTC").do(self._update_pivot_points)
            # Example: Update symbol info daily (filters might change)
            schedule.every().day.at("00:05", "UTC").do(self._update_symbol_info)
            logger.info(
                "Scheduled daily tasks: Pivot Points update (00:01 UTC), Symbol Info update (00:05 UTC).")
        except Exception as e:
            logger.error(f"Failed to set up schedule: {e}", exc_info=True)

    def _calculate_tp_example(self):
        """Placeholder showing how to potentially call calculate_dynamic_tp_price."""
        # --- THIS IS JUST AN EXAMPLE - NEEDS REAL POSITION DATA ---
        if not self.state["indicators"] or not self.state['symbol_info']:
            return  # Need indicators (for ATR) and symbol info (for filters)

        mock_position = {
            'symbol': self._get_trading_param('symbol', 'BTCUSD'),
            'entry_price': Decimal('84000.00'),  # Example entry
            'quantity': Decimal('0.01'),
        }
        current_atr = self.state['indicators'].get(
            f'ATR_{ATR_PERIOD}')  # Get calculated ATR
        # Confidence score would come from Phase 3.5
        mock_confidence = 0.75

        if mock_position and current_atr:
            logger.debug(
                f"Example TP Calc: Entry={mock_position['entry_price']}, ATR={current_atr}, Conf={mock_confidence}")
            tp_price = calculate_dynamic_tp_price(
                entry_price=mock_position['entry_price'],
                current_atr=current_atr,
                config=self.config,
                # Pass cached symbol info
                symbol_info=self.state['symbol_info'],
                confidence_score=mock_confidence
            )
            if tp_price:
                logger.info(f"[EXAMPLE] Calculated TP Price: {tp_price:.4f}")
                # In reality: Place a limit sell order at tp_price for position quantity
            else:
                logger.warning("[EXAMPLE] Failed to calculate TP price.")
        # --- END EXAMPLE ---

    def run(self):
        """Starts the main trading loop."""
        if not self.connector or not self.connector.get_client():
            logger.critical("Trader not initialized properly. Cannot run.")
            return

        self.is_running = True
        # *** FIX: Get params BEFORE logging start message ***
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        interval = self._get_trading_param('interval', '1h')
        loop_sleep_time = self._get_trading_param('loop_sleep_time', 60)

        logger.info(
            f"Starting main trading loop. Symbol: {symbol}, Interval: {interval}")

        while self.is_running:
            loop_start_time = time.monotonic()
            try:
                logger.debug(
                    f"--- Loop Start (State Update Time: {self.state['last_data_update_time']}) ---")

                # 1. Run Pending Scheduled Tasks
                schedule.run_pending()

                # 2. Update Market Data (Klines)
                data_updated = self._update_market_data()

                # 3. Calculate Indicators
                if data_updated or not self.state["indicators"]:
                    self._calculate_indicators()

                # --- TRADING LOGIC (Placeholder Section) ---
                if self.state["indicators"] and self.state["symbol_info"]:
                    # 4. Check Open Orders/Positions (Phase 3+)
                    # self._check_orders_and_positions()

                    # 5. Evaluate Risk Controls (Phase 3+)
                    # self._evaluate_risk_controls()

                    # 6. Calculate Confidence Score (Phase 3+)
                    # confidence = self._calculate_confidence()
                    # self.state['confidence_score'] = confidence # Store it

                    # 7. Plan New Trades / Update Existing (Phase 1 MVP+, Phase 3+)
                    # a. Check for new entry signals (e.g., based on indicators, confidence)
                    #    -> If signal: plan grid buy orders using geometric_grid module
                    # b. Check existing positions
                    #    -> If position exists: calculate/update TP using profit_taking module
                    #       (This is where calculate_dynamic_tp_price is called with real data)
                    # self._calculate_tp_example() # Run example for now

                    # 8. Execute Trades (Phase 1 MVP+, Phase 3+)
                    # self._execute_trades(planned_buy_orders, planned_tp_orders, planned_cancellations)
                    pass  # Placeholder for actual trading decisions
                else:
                    if not self.state["indicators"]:
                        logger.warning(
                            "Skipping trading logic: Indicators not available.")
                    if not self.state["symbol_info"]:
                        logger.warning(
                            "Skipping trading logic: Symbol info not available.")

                # --- End Trading Logic ---

                logger.debug("--- Loop End ---")

                loop_end_time = time.monotonic()
                elapsed_time = loop_end_time - loop_start_time
                sleep_duration = max(0, loop_sleep_time - elapsed_time)
                if elapsed_time > loop_sleep_time:
                    logger.warning(
                        f"Loop execution time ({elapsed_time:.2f}s) exceeded target ({loop_sleep_time}s).")
                time.sleep(sleep_duration)

            except KeyboardInterrupt:
                logger.warning(
                    "KeyboardInterrupt received. Stopping trader...")
                self.is_running = False
            except Exception as e:
                logger.exception(
                    "An critical error occurred in the main loop.")
                time.sleep(loop_sleep_time * 5)

        logger.info("GeminiTrader run loop finished.")

    def stop(self):
        """Signals the main loop to stop gracefully."""
        logger.info(
            "Stop signal received. Trader will halt after current loop iteration.")
        self.is_running = False


# --- Script Entry Point ---
if __name__ == '__main__':
    try:
        trader = GeminiTrader()  # Instantiation handles initialization checks
        trader.run()
    except SystemExit:
        print("Exiting due to initialization failure.")
        sys.exit(1)
    except Exception as e:
        logging.critical(
            f"Unhandled exception during trader run: {e}", exc_info=True)
        print(f"FATAL: Unhandled exception: {e}")
        sys.exit(1)
    finally:
        logger.info("GeminiTrader finished.")
        print("GeminiTrader process finished.")
        sys.exit(0)

# END OF FILE: src/main_trader.py
