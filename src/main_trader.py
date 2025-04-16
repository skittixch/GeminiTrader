# START OF FILE: src/main_trader.py

import logging
import logging.config
import time
import sys
import signal
from decimal import Decimal, getcontext, InvalidOperation  # Added InvalidOperation
from typing import Dict, Any
from pathlib import Path

import pandas as pd
from tqdm import tqdm  # type: ignore

# Project Modules
from config.settings import load_config, get_config_value
from src.connectors.binance_us import BinanceUSConnector
from src.core.state_manager import StateManager
from src.core.order_manager import OrderManager
from src.analysis.indicators import calculate_indicators
from src.analysis.support_resistance import calculate_dynamic_zones
from src.analysis.confidence import calculate_confidence_v1
from src.strategies.geometric_grid import plan_buy_grid_v1
from src.strategies.profit_taking import calculate_dynamic_tp_price
from src.strategies.risk_controls import check_time_stop
from src.utils.logging_setup import setup_logging
from src.utils.formatting import to_decimal  # Ensure imported

# Set Decimal precision
getcontext().prec = 18

# Setup Logging early
setup_logging()
logger = logging.getLogger(__name__)
project_root = Path(__file__).parent.parent


class GeminiTrader:
    """Main autonomous trading bot class."""

    def __init__(self):
        logger.info("Initializing GeminiTrader...")
        try:
            self.config: Dict[str, Any] = load_config()
            if not self.config:
                raise ValueError("Config dictionary is empty.")
            api_key = get_config_value(self.config, ('binance_us', 'api_key'))
            api_secret = get_config_value(
                self.config, ('binance_us', 'api_secret'))
            tld = get_config_value(self.config, ('binance_us', 'tld'), 'us')
            if not api_key or not api_secret:
                raise ValueError("API Key/Secret not found.")
            self.connector = BinanceUSConnector(
                api_key=api_key, api_secret=api_secret, config=self.config, tld=tld)
            state_file_rel = get_config_value(
                self.config, ('state_manager', 'filepath'), 'data/state/trader_state.json')
            state_file_abs = project_root / state_file_rel
            self.state_manager = StateManager(filepath=str(state_file_abs))
            # Initialize state attribute early for potential use in error handling
            self.state = self.state_manager.load_state()
            self.state = self.state if self.state else {}
            # Ensure crucial numeric state values are Decimal after loading
            self.state['position_size'] = to_decimal(
                self.state.get('position_size', '0'))
            self.state['position_entry_price'] = to_decimal(
                self.state.get('position_entry_price', '0'))
            self.state['balance_quote'] = to_decimal(
                self.state.get('balance_quote', '0'))
            self.state['balance_base'] = to_decimal(
                self.state.get('balance_base', '0'))

            self.order_manager = OrderManager(
                config_dict=self.config, connector=self.connector, state_manager=self.state_manager)
            # Reload state after OrderManager is initialized, in case OM modifies it (though unlikely here)
            # Re-ensure types after potential reload/modification by OM init
            loaded_state_after_om = self.state_manager.load_state()
            # Use new state if loaded, else keep current
            self.state = loaded_state_after_om if loaded_state_after_om else self.state
            self.state['position_size'] = to_decimal(
                self.state.get('position_size', '0'))
            self.state['position_entry_price'] = to_decimal(
                self.state.get('position_entry_price', '0'))
            self.state['balance_quote'] = to_decimal(
                self.state.get('balance_quote', '0'))
            self.state['balance_base'] = to_decimal(
                self.state.get('balance_base', '0'))

            self.simulation_mode = get_config_value(
                self.config, ('trading', 'simulation_mode'), False)
            logger.info(
                f"Initialization complete. SIMULATION_MODE: {self.simulation_mode}")
            self.running = True
            self.is_shutting_down = False
            self.sim_data = None
            self.sim_data_iterator = None
            self.sim_current_row = None
        except Exception as e:
            # === START REPLACEMENT BLOCK: __init__ except Exception ===
            logger.critical(f"FATAL: Init failed: {e}", exc_info=True)
            # Attempt to save state even if init failed partially
            if hasattr(self, 'state_manager') and self.state_manager and hasattr(self, 'state'):
                # Ensure state exists and is a dict before attempting save
                current_state_on_fail = getattr(self, 'state', None)
                if isinstance(current_state_on_fail, dict):
                    logger.warning(
                        "Attempting to save state after initialization failure...")
                    try:
                        self.state_manager.save_state(current_state_on_fail)
                        logger.info(
                            "State saved successfully after init failure.")
                    except Exception as save_err:
                        logger.error(
                            f"Could not save state after init failure: {save_err}", exc_info=False)
                else:
                    logger.warning(
                        "Cannot save state after init failure: state attribute missing or not a dict.")

            self.running = False  # Ensure running is False
            print(f"Exiting due to initialization error: {e}")
            sys.exit(1)
            # === END REPLACEMENT BLOCK: __init__ except Exception ===

    # !!! CORRECTED INDENTATION LEVEL FOR THE ENTIRE METHOD !!!
    def _initialize(self):
        logger.info("Starting Initialization Sequence...")
        # Ensure state exists before logging it
        # Use to_decimal here as well for safety, though __init__ should have handled it
        pos_size_state = to_decimal(self.state.get('position_size', '0'))
        pos_size_log = f"{pos_size_state:.8f}" if pos_size_state is not None else 'N/A'
        grid_orders_log = len(self.state.get('active_grid_orders', [])) if isinstance(
            self.state.get('active_grid_orders'), list) else 'N/A'
        tp_order_log = 'Yes' if self.state.get('active_tp_order') else 'No'
        logger.info(
            f"Initial State: Pos:{pos_size_log}, Grid:{grid_orders_log}, TP:{tp_order_log}")

        self.symbol = get_config_value(
            self.config, ('trading', 'symbol'), 'BTCUSDT')
        self.quote_asset = get_config_value(
            self.config, ('portfolio', 'quote_asset'), 'USDT')
        if self.symbol.endswith(self.quote_asset):
            self.base_asset = self.symbol[:-len(self.quote_asset)]
        else:
            # Attempt to infer common base assets if quote asset doesn't match end
            common_bases = ['BTC', 'ETH']  # Extend as needed
            inferred = False
            for base in common_bases:
                if self.symbol.startswith(base):
                    self.base_asset = base
                    inferred = True
                    logger.info(f"Inferred base asset: {self.base_asset}")
                    break
            if not inferred:
                self.base_asset = 'UNKNOWN_BASE'  # Fallback
                logger.error(
                    f"Could not infer base asset for symbol '{self.symbol}' and quote '{self.quote_asset}'. Defaulting to {self.base_asset}. Please check configuration.")
        self.kline_interval = get_config_value(
            self.config, ('trading', 'interval'), '1h')

        if not self.simulation_mode:
            logger.info("Verifying exchange connection...")
            server_time = self.connector.get_server_time()
            if server_time is None:
                raise ConnectionError("Exchange connection failed.")
            logger.info(f"Exchange connection OK. Server time: {server_time}")
            self._update_balances()  # Fetch live balances
        else:  # Sim setup
            logger.info("Simulation mode: Skipping live connection check.")
            # Ensure balances are Decimal (already done in __init__, but good practice)
            if 'balance_quote' not in self.state or self.state['balance_quote'] is None:
                init_bal = get_config_value(
                    self.config, ('simulation', 'initial_balance'), 1000.0)
                self.state['balance_quote'] = Decimal(str(init_bal))
                logger.info(
                    f"Set initial sim balance: {self.state['balance_quote']} {self.quote_asset}")
            else:
                # Ensure Decimal on load (redundant if __init__ worked, but safe)
                self.state['balance_quote'] = to_decimal(
                    self.state['balance_quote'])

            if 'balance_base' not in self.state or self.state['balance_base'] is None:
                self.state['balance_base'] = Decimal('0')
            else:
                # Ensure Decimal on load (redundant if __init__ worked, but safe)
                self.state['balance_base'] = to_decimal(
                    self.state['balance_base'])

            # Save potentially corrected balances (if they were missing)
            self.state_manager.save_state(self.state)
            logger.info("Loading simulation data...")
            sim_file_path = get_config_value(
                self.config, ('simulation', 'data_file'))
            ts_col_name = get_config_value(
                self.config, ('simulation', 'timestamp_column'), 'Timestamp')
            if not sim_file_path:
                raise ValueError("Missing simulation data_file config")
            try:
                sim_file = Path(sim_file_path)
                if not sim_file.is_absolute():
                    sim_file = project_root / sim_file
                logger.info(
                    f"Attempting load simulation data from: {sim_file}")
                # Load CSV, setting index and parsing dates
                # Add 'date_format' if known to suppress UserWarning and improve performance
                # Example: date_format='%Y-%m-%d %H:%M:%S' or '%Y-%m-%d %H:%M:%S%z' if timezone included
                self.sim_data = pd.read_csv(
                    sim_file,
                    parse_dates=[ts_col_name],
                    index_col=ts_col_name,
                    dtype={'Open': str, 'High': str,
                           'Low': str, 'Close': str, 'Volume': str}
                    # date_format=... # Optional: Add format string here if known
                )

                # Convert OHLCV columns to Decimal
                for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    if col in self.sim_data.columns:
                        self.sim_data[col] = self.sim_data[col].apply(
                            lambda x: to_decimal(x) if pd.notna(x) else None)
                    else:
                        logger.warning(
                            f"Sim data missing expected column: {col}")

                # Identify required OHLC columns actually present
                ohlc_cols_present = [c for c in [
                    'Open', 'High', 'Low', 'Close'] if c in self.sim_data.columns]
                if not ohlc_cols_present:
                    raise ValueError(
                        "Simulation data missing essential OHLC columns.")

                # Drop rows where any of the essential OHLC columns are missing
                logger.debug(
                    f"Checking NaNs in present OHLC columns: {ohlc_cols_present}")
                initial_rows = len(self.sim_data)
                self.sim_data.dropna(subset=ohlc_cols_present, inplace=True)
                rows_dropped_ohlc = initial_rows - len(self.sim_data)
                if rows_dropped_ohlc > 0:
                    logger.info(
                        f"Dropped {rows_dropped_ohlc} rows due to missing OHLC data.")

                if self.sim_data.empty:
                    raise ValueError(
                        "Simulation data is empty after removing rows with missing OHLC values.")

                # --- Corrected Index Handling ---
                # Verify if index is already DatetimeIndex
                if not isinstance(self.sim_data.index, pd.DatetimeIndex):
                    logger.warning(
                        "Simulation data index is not a DatetimeIndex after loading. Attempting conversion.")
                    original_index = self.sim_data.index
                    try:
                        # Attempt conversion, coercing errors to NaT (Not a Time)
                        self.sim_data.index = pd.to_datetime(
                            original_index, errors='coerce')
                        logger.info(
                            "Successfully converted simulation data index to DatetimeIndex format.")
                    except Exception as idx_err:
                        # Catch unexpected errors during conversion itself
                        logger.error(
                            f"Error during index conversion to DatetimeIndex: {idx_err}", exc_info=True)
                        raise TypeError(
                            "Critical error converting simulation data index.")
                else:
                    logger.debug(
                        "Simulation data index is already DatetimeIndex.")

                # Drop rows where index conversion resulted in NaT
                initial_rows_idx = len(self.sim_data)
                # Use index.notna() to keep only valid timestamps
                self.sim_data = self.sim_data[self.sim_data.index.notna()]
                rows_dropped_nat = initial_rows_idx - len(self.sim_data)
                if rows_dropped_nat > 0:
                    logger.info(
                        f"Dropped {rows_dropped_nat} rows due to invalid index timestamps (NaT).")

                # Final check if DataFrame became empty after NaT drop
                if self.sim_data.empty:
                    raise ValueError(
                        "Simulation data is empty after removing rows with invalid timestamps.")

                # Final verification that index is usable
                if not isinstance(self.sim_data.index, pd.DatetimeIndex):
                    raise TypeError(
                        "Index is not a DatetimeIndex after processing and NaT removal.")
                # --- End Corrected Index Handling ---

                self.sim_data_iterator = self.sim_data.iterrows()
                logger.info(
                    f"Loaded {len(self.sim_data)} valid simulation data rows from {sim_file}.")

                # --- Resume Logic (Remains the same as before) ---
                last_ts = self.state.get('last_processed_timestamp')
                if last_ts:
                    try:
                        if isinstance(last_ts, str):
                            last_ts = pd.Timestamp(last_ts)
                        sim_tz = self.sim_data.index.tz
                        last_tz_info = getattr(last_ts, 'tzinfo', None)
                        if sim_tz != last_tz_info:
                            logger.warning(
                                f"Timezone mismatch: Sim data ({sim_tz}) vs Last state ({last_tz_info}). Attempting conversion.")
                            try:
                                if sim_tz is None:
                                    # If sim data is naive, make last_ts naive
                                    last_ts = last_ts.tz_convert(None)
                                elif last_tz_info is None:
                                    # If last_ts is naive, localize it to sim data's timezone
                                    last_ts = last_ts.tz_localize(sim_tz)
                                else:
                                    # Both are timezone-aware, convert last_ts to match sim data
                                    last_ts = last_ts.tz_convert(sim_tz)
                                logger.info(
                                    f"Successfully aligned timestamp for comparison: {last_ts}")
                            except Exception as tz_err:
                                logger.error(
                                    f"Timezone conversion error during resume: {tz_err}. Restarting simulation from beginning.", exc_info=False)
                                last_ts = None  # Prevent resume attempt
                        if last_ts:
                            logger.info(
                                f"Attempting to resume simulation from state timestamp: {last_ts}")
                        else:
                            logger.info(
                                "Starting simulation from beginning (timestamp alignment issue).")

                        resumed = False
                        if last_ts:
                            # Find the index location strictly after the last processed timestamp
                            # Use searchsorted for efficiency
                            resume_index_loc = self.sim_data.index.searchsorted(
                                last_ts, side='right')

                            if resume_index_loc < len(self.sim_data.index):
                                resume_ts = self.sim_data.index[resume_index_loc]
                                # Fast-forward the main iterator by recreating it from the resume point
                                self.sim_data_iterator = self.sim_data.iloc[resume_index_loc:].iterrows(
                                )
                                skipped_count = resume_index_loc
                                logger.info(
                                    f"Resuming simulation from timestamp: {resume_ts} (Skipped {skipped_count} rows based on state timestamp {last_ts})")
                                resumed = True
                            else:
                                # Last processed timestamp was the last one in the data or later
                                logger.warning(
                                    f"Last processed timestamp {last_ts} is at or after the end of simulation data. Restarting from beginning.")
                                # Iterator already reset if alignment failed or no last_ts
                                self.sim_data_iterator = self.sim_data.iterrows()
                                # Clear state ts
                                self.state['last_processed_timestamp'] = None

                        # Only log if we tried and failed to resume, but didn't hit the end-of-data case above
                        if not resumed and last_ts is not None:
                            logger.warning(
                                "Could not find timestamp immediately after last processed. Restarting from beginning.")
                            self.sim_data_iterator = self.sim_data.iterrows()  # Reset iterator
                            self.state['last_processed_timestamp'] = None
                        elif not last_ts:
                            # Already reset if alignment failed or no last_ts initially
                            logger.info("Starting simulation from beginning.")
                            self.sim_data_iterator = self.sim_data.iterrows()  # Ensure iterator is reset
                            # Ensure state is clear
                            self.state['last_processed_timestamp'] = None

                    except Exception as resume_err:
                        logger.error(
                            f"Error during simulation resume logic: {resume_err}. Restarting from beginning.", exc_info=True)
                        self.sim_data_iterator = self.sim_data.iterrows()  # Reset iterator on error
                        # Clear timestamp in state
                        self.state['last_processed_timestamp'] = None
                else:
                    logger.info(
                        "Starting simulation from beginning (no previous timestamp found in state).")
                    # Ensure it's clear
                    self.state['last_processed_timestamp'] = None
                # --- End Resume Logic ---

            except ValueError as ve:
                logger.critical(f"FATAL: CSV Value Error: {ve}", exc_info=True)
                raise
            except FileNotFoundError:
                logger.critical(
                    f"FATAL: Simulation data file not found: {sim_file}")
                raise
            except Exception as e:
                logger.critical(
                    f"FATAL: Failed to load or process simulation data: {e}", exc_info=True)
                raise

        # Fetch/Load Exchange Info (common to both modes)
        cache_mins = get_config_value(
            self.config, ('trading', 'exchange_info_cache_minutes'), 1440)
        logger.info(
            f"Fetching/loading exchange info (cache duration: {cache_mins}m)...")
        exchange_info_loaded = self.connector.get_exchange_info(
            force_refresh=False)
        if not exchange_info_loaded:
            logger.warning(
                "Cached exchange info not found or expired. Fetching fresh data...")
            exchange_info_loaded = self.connector.get_exchange_info(
                force_refresh=True)
        if not exchange_info_loaded:
            raise ConnectionError(
                "Failed to get exchange info after forced refresh.")
        logger.info("Exchange info loaded successfully.")
        logger.info("Initialization Sequence Complete.")

    def _update_market_data(self):
        if self.simulation_mode:
            if self.sim_data_iterator is None:
                logger.error(
                    "Simulation iterator is not available. Stopping simulation.")
                self.running = False
                return False
            try:
                # Use the pre-advanced row if resuming, otherwise get next
                if self.sim_current_row:
                    timestamp, row = self.sim_current_row
                    self.sim_current_row = None  # Consume the stored row
                else:
                    timestamp, row = next(self.sim_data_iterator)

                # Construct kline dict using .get() for safety, ensure Decimal
                current_kline = {
                    'timestamp': timestamp,
                    'open': to_decimal(row.get('Open')),
                    'high': to_decimal(row.get('High')),
                    'low': to_decimal(row.get('Low')),
                    'close': to_decimal(row.get('Close')),
                    'volume': to_decimal(row.get('Volume'))
                }

                # Validate essential data points
                # Allow volume to be None
                if any(v is None for k, v in current_kline.items() if k != 'timestamp' and k != 'volume'):
                    logger.error(
                        f"Missing essential OHLC data at simulation timestamp {timestamp}. Row data: {row.to_dict()}. Stopping simulation.")
                    self.running = False
                    return False

                self.state['current_kline'] = current_kline
                # Store the actual timestamp object
                self.state['last_processed_timestamp'] = timestamp

                # Update historical klines DataFrame
                hist_klines = self.state.get('historical_klines')
                new_row_df = pd.DataFrame(
                    [current_kline]).set_index('timestamp')

                if hist_klines is None or not isinstance(hist_klines, pd.DataFrame):
                    self.state['historical_klines'] = new_row_df
                else:
                    # Ensure timezone consistency before concatenating
                    hist_tz = getattr(hist_klines.index, 'tz', None)
                    new_tz = getattr(new_row_df.index, 'tz', None)

                    if hist_tz != new_tz:
                        logger.debug(
                            f"Aligning timezone for DataFrame concat: Hist ({hist_tz}), New ({new_tz})")
                        try:
                            if hist_tz is None:
                                new_row_df.index = new_row_df.index.tz_convert(
                                    None)
                            elif new_tz is None:
                                new_row_df.index = new_row_df.index.tz_localize(
                                    hist_tz)
                            else:
                                new_row_df.index = new_row_df.index.tz_convert(
                                    hist_tz)
                        except Exception as tz_align_err:
                            logger.warning(
                                f"Could not align timezones for concat: {tz_align_err}. Resetting history might occur.")
                            # Potentially reset history or handle differently if alignment fails
                            # Example reset
                            self.state['historical_klines'] = new_row_df

                    try:
                        # Use concat instead of append for modern pandas
                        self.state['historical_klines'] = pd.concat(
                            [hist_klines, new_row_df])
                    except Exception as concat_err:
                        logger.error(
                            f"Error concatenating historical klines: {concat_err}. Resetting history.", exc_info=False)
                        # Reset history on failure
                        self.state['historical_klines'] = new_row_df

                # Trim historical data to max length
                max_hist = get_config_value(
                    self.config, ('analysis', 'max_historical_candles'), 500)
                current_hist_len = len(self.state['historical_klines'])
                if current_hist_len > max_hist:
                    self.state['historical_klines'] = self.state['historical_klines'].iloc[-max_hist:]
                    # logger.debug(f"Trimmed historical klines from {current_hist_len} to {max_hist}")

                return True  # Success

            except StopIteration:
                logger.info("End of simulation data reached.")
                self.running = False
                return False  # End of data
            except Exception as e:
                logger.error(
                    f"Unhandled error processing simulation step: {e}", exc_info=True)
                self.running = False
                return False  # Error
        else:  # Live Mode
            logger.debug("Fetching latest klines for live mode...")
            try:
                limit = get_config_value(
                    self.config, ('trading', 'kline_limit'), 200)
                # Use the connector's prepared kline fetcher
                df = self.connector.fetch_prepared_klines(
                    self.symbol, self.kline_interval, limit=limit)  # Pass limit
            except Exception as e:
                logger.error(f"Error fetching live klines: {e}", exc_info=True)
                return False  # Indicate failure

            if df is None or df.empty:
                logger.warning("Fetching live klines returned no data.")
                return False  # Indicate failure or lack of data

            # Ensure required columns exist and are Decimal
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in required_cols:
                if col not in df.columns:
                    logger.error(
                        f"Live kline data missing required column: {col}")
                    return False
                # Assuming fetch_prepared_klines already returns Decimals

            self.state['historical_klines'] = df
            # Store the latest kline data
            self.state['current_kline'] = df.iloc[-1].to_dict()
            # Store the timestamp of the latest kline
            self.state['last_processed_timestamp'] = df.index[-1]
            logger.debug(
                f"Successfully fetched {len(df)} live klines. Latest timestamp: {self.state['last_processed_timestamp']}")
            return True  # Success

    def _calculate_analysis(self):
        if 'historical_klines' not in self.state or not isinstance(self.state['historical_klines'], pd.DataFrame) or self.state['historical_klines'].empty:
            logger.warning(
                "Skipping analysis: Historical klines data is missing or invalid.")
            return False

        klines_df = self.state['historical_klines']
        min_candles = get_config_value(
            self.config, ('analysis', 'min_candles_for_analysis'), 100)

        if len(klines_df) < min_candles:
            logger.warning(
                f"Skipping analysis: Insufficient historical data ({len(klines_df)} candles available, {min_candles} required).")
            return False

        logger.debug(
            f"Calculating analysis based on {len(klines_df)} klines...")
        try:
            # Work on a copy to avoid modifying the state DataFrame directly
            klines_df_analysis = klines_df.copy()

            # Ensure index is DatetimeIndex (should be guaranteed by _update_market_data, but check again)
            if not isinstance(klines_df_analysis.index, pd.DatetimeIndex):
                klines_df_analysis.index = pd.to_datetime(
                    klines_df_analysis.index)
                logger.debug(
                    "Converted analysis DataFrame index to DatetimeIndex.")

            # Ensure column names are capitalized ('Open', 'High', 'Low', 'Close', 'Volume') for indicator functions
            rename_map = {c: c.capitalize() for c in klines_df_analysis.columns if c in [
                'open', 'high', 'low', 'close', 'volume']}
            if rename_map:
                klines_df_analysis.rename(columns=rename_map, inplace=True)
                # logger.debug(f"Renamed columns for analysis: {rename_map}") # DEBUG

            # Calculate Technical Indicators
            self.state['indicators'] = calculate_indicators(
                klines_df_analysis, self.config)
            if self.state['indicators'] is None or not isinstance(self.state['indicators'], pd.DataFrame) or self.state['indicators'].empty:
                # Raise specific error instead of generic one
                raise ValueError(
                    "Indicator calculation returned invalid data.")
            logger.debug(
                f"Indicators calculated successfully. Columns: {list(self.state['indicators'].columns)}")

            # Calculate Support/Resistance Zones
            # Assuming calculate_dynamic_zones expects capitalized columns too
            self.state['sr_zones'] = calculate_dynamic_zones(
                klines_df_analysis, self.config)
            # Check type if necessary, depends on expected return format
            logger.debug(
                f"Support/Resistance zones calculated: {len(self.state.get('sr_zones', []))} zones found.")

            # Calculate Confidence Score
            # Pass the calculated indicators and S/R zones
            # Ensure indicators is a DataFrame and sr_zones is a list/dict as expected by confidence func
            indicators_data = self.state.get(
                'indicators', pd.DataFrame())  # Default to empty DF
            sr_zones_data = self.state.get(
                'sr_zones', [])  # Default to empty list

            self.state['confidence_score'] = calculate_confidence_v1(
                indicators_data, sr_zones_data, self.config)

            # Validate confidence score if needed (e.g., check if it's a number)
            if not isinstance(self.state['confidence_score'], (float, Decimal)):
                logger.warning(
                    f"Confidence score calculation resulted in non-numeric value: {self.state['confidence_score']}")
                # Fallback to a neutral score
                self.state['confidence_score'] = Decimal('0.5')

            logger.debug(
                # Use .get for safety and ensure formatting works even if fallback occurred
                f"Confidence score calculated: {self.state.get('confidence_score', Decimal('0.5')):.4f}")

            return True  # Analysis successful

        except Exception as e:
            logger.error(
                f"Error occurred during market analysis: {e}", exc_info=True)
            # Reset analysis results in state on error to avoid using stale/invalid data
            self.state['indicators'] = None
            self.state['sr_zones'] = None
            self.state['confidence_score'] = None
            return False  # Analysis failed

    def _update_balances(self):
        if self.simulation_mode:
            # In simulation, balances are updated internally during fill processing
            # Log current simulated balances for debugging
            # Use to_decimal for safety, though __init__ and _process_fills should handle it
            base_bal = to_decimal(self.state.get('balance_base', '0'))
            quote_bal = to_decimal(self.state.get('balance_quote', '0'))
            logger.debug(
                f"Simulated Balances: Base={base_bal:.8f} {self.base_asset}, Quote={quote_bal:.2f} {self.quote_asset}")
            return True  # Always succeeds in simulation
        else:
            # Live Mode: Fetch actual balances from the exchange
            logger.debug(
                f"Fetching live balances for {self.base_asset} and {self.quote_asset}...")
            try:
                balances = self.connector.get_balances()
                if balances is None:
                    logger.error("Failed to fetch live balances.")
                    return False  # Indicate failure

                # Update state with fetched balances, ensuring they are Decimal
                self.state['balance_base'] = to_decimal(
                    balances.get(self.base_asset, '0'))
                self.state['balance_quote'] = to_decimal(
                    balances.get(self.quote_asset, '0'))

                logger.info(
                    f"Live Balances Updated: Base={self.state['balance_base']:.8f} {self.base_asset}, Quote={self.state['balance_quote']:.2f} {self.quote_asset}")
                return True  # Success
            except Exception as e:
                logger.error(
                    f"Error fetching or processing live balances: {e}", exc_info=True)
                return False  # Indicate failure

    def _process_fills(self, fills: Dict):
        """Processes filled orders (grid buys, TP sells) and updates position state and balances."""
        grid_fills = fills.get('grid_fills', [])
        tp_fill = fills.get('tp_fill', None)

        if not grid_fills and not tp_fill:
            logger.debug("No fills to process.")
            return  # Nothing to do

        logger.info(
            f"Processing Fills - Grid Orders Filled: {len(grid_fills)}, TP Order Filled: {'Yes' if tp_fill else 'No'}")

        # Load current state for modification, ensuring types are Decimal
        pos_size = to_decimal(self.state.get('position_size', '0'))
        entry_px = to_decimal(self.state.get('position_entry_price', '0'))
        bal_q = to_decimal(self.state.get('balance_quote', '0'))
        bal_b = to_decimal(self.state.get('balance_base', '0'))

        # Process Grid Buy Fills
        for fill in grid_fills:
            try:
                # Extract quantity and price safely, handling potential None or string values
                # Prefer executedQty, fallback to origQty only if necessary (and log if so)
                qty_str = fill.get('executedQty')
                if qty_str is None:
                    qty_str = fill.get('origQty')
                    logger.warning(
                        f"Grid fill {fill.get('orderId')} missing 'executedQty', using 'origQty'. This might be inaccurate for partial fills.")
                qty = to_decimal(qty_str)

                cumm_quote_str = fill.get('cummulativeQuoteQty')
                # Price on the order (may differ slightly from effective price)
                price_str = fill.get('price')

                # Calculate effective price: cummulativeQuoteQty / executedQty is most accurate
                if cumm_quote_str is not None and qty is not None and qty > 0:
                    px = to_decimal(cumm_quote_str) / qty
                elif price_str is not None:
                    px = to_decimal(price_str)
                    logger.warning(
                        f"Grid fill {fill.get('orderId')} missing 'cummulativeQuoteQty', using order price '{price_str}'. Effective price might differ.")
                else:
                    logger.error(
                        f"Grid fill {fill.get('orderId')} missing price information. Cannot process.")
                    continue  # Skip this fill

                if qty is None or px is None or qty <= 0 or px <= 0:
                    logger.warning(
                        f"Skipping invalid grid fill data: Qty={qty}, Price={px}. Fill Details: {fill}")
                    continue  # Skip invalid fill

                cost = px * qty  # Calculate cost based on effective price

                logger.info(
                    f"Processing Grid Fill: Bought +{qty:.8f} {self.base_asset} @ {px:.4f} {self.quote_asset} (Cost: {cost:.4f})")

                # Update position: Calculate new average entry price
                # Ensure all inputs are Decimal before calculation
                current_value = pos_size * entry_px
                new_total_value = current_value + cost
                new_total_size = pos_size + qty
                new_entry_px = new_total_value / \
                    new_total_size if new_total_size > 0 else Decimal('0')

                # Update state variables (local copies first)
                pos_size = new_total_size
                entry_px = new_entry_px
                bal_q -= cost
                bal_b += qty

            except (InvalidOperation, TypeError, KeyError, ZeroDivisionError, ValueError) as e:
                order_id = fill.get('orderId', 'N/A')
                logger.error(
                    f"Error processing grid fill for order {order_id}: {e}. Fill Data: {fill}", exc_info=False)
            # No 'continue' here, proceed to next fill if error occurs

        # Process Take Profit Sell Fill
        if tp_fill:
            try:
                # Extract quantity and price safely
                qty_str = tp_fill.get('executedQty')
                if qty_str is None:
                    qty_str = tp_fill.get('origQty')
                    logger.warning(
                        f"TP fill {tp_fill.get('orderId')} missing 'executedQty', using 'origQty'.")
                qty = to_decimal(qty_str)

                cumm_quote_str = tp_fill.get('cummulativeQuoteQty')
                price_str = tp_fill.get('price')

                # Calculate effective price
                if cumm_quote_str is not None and qty is not None and qty > 0:
                    px = to_decimal(cumm_quote_str) / qty
                elif price_str is not None:
                    px = to_decimal(price_str)
                    logger.warning(
                        f"TP fill {tp_fill.get('orderId')} missing 'cummulativeQuoteQty', using order price '{price_str}'.")
                else:
                    logger.error(
                        f"TP fill {tp_fill.get('orderId')} missing price information. Cannot process.")
                    # Don't reset position if price is missing, just log error
                    px = None  # Mark price as unknown

                if qty is not None and px is not None and qty > 0 and px > 0:
                    proceeds = px * qty
                    logger.info(
                        f"Processing TP Fill: Sold -{qty:.8f} {self.base_asset} @ {px:.4f} {self.quote_asset} (Proceeds: {proceeds:.4f})")

                    # Calculate realized profit/loss for this fill
                    if entry_px > 0:  # Avoid division by zero if entry price wasn't set
                        profit = (px - entry_px) * qty
                        logger.info(
                            f"Approximate Realized P/L from TP: {profit:.4f} {self.quote_asset}")
                    else:
                        logger.warning(
                            "Could not calculate P/L for TP fill as entry price was zero.")

                    # Reset position state as TP implies closing the entire position
                    pos_size = Decimal('0')
                    entry_px = Decimal('0')

                    # Update balances (local copies)
                    bal_q += proceeds
                    # Ensure base balance doesn't go negative due to rounding
                    bal_b = max(Decimal('0'), bal_b - qty)

                else:
                    logger.warning(
                        f"Skipping invalid TP fill data: Qty={qty}, Price={px}. Fill Details: {tp_fill}")

            except (InvalidOperation, TypeError, KeyError, ZeroDivisionError, ValueError) as e:
                order_id = tp_fill.get('orderId', 'N/A')
                logger.error(
                    f"Error processing TP fill for order {order_id}: {e}. Fill Data: {tp_fill}", exc_info=False)

        # Update the global state with the final Decimal values after processing all fills
        self.state['position_size'] = pos_size
        self.state['position_entry_price'] = entry_px
        self.state['balance_quote'] = bal_q
        self.state['balance_base'] = bal_b

        logger.info(
            f"State after processing fills: Position Size={pos_size:.8f} {self.base_asset}, Avg Entry Price={entry_px:.4f} {self.quote_asset}, "
            f"Balance Quote={self.state['balance_quote']:.4f} {self.quote_asset}, Balance Base={self.state['balance_base']:.8f} {self.base_asset}")

    def _plan_trades(self):
        logger.debug("Planning trades for the next cycle...")

        # Get necessary data from state, ensuring types are Decimal where needed
        current_kline_data = self.state.get('current_kline', {})
        # Already Decimal if _update_market_data is correct
        curr_px = current_kline_data.get('close')
        # Already Decimal if _calculate_analysis is correct
        conf = self.state.get('confidence_score')
        # === FIX: Ensure pos_size is Decimal for comparison ===
        pos_size = to_decimal(self.state.get('position_size', '0'))
        entry_px = to_decimal(self.state.get('position_entry_price', '0'))
        available_quote_balance = to_decimal(
            self.state.get('balance_quote', '0'))
        # ======================================================
        indicators_df = self.state.get('indicators')
        sr_zones = self.state.get('sr_zones', [])

        # Reset planned trades for this cycle
        self.state['planned_grid'] = []
        self.state['planned_tp_price'] = None

        # --- Grid Planning ---
        if curr_px is None or conf is None:
            logger.warning(
                "Skipping trade planning: Missing current price or confidence score.")
            return  # Cannot plan without essential data

        # Entry conditions from config
        entry_conf = to_decimal(get_config_value(
            self.config, ('trading', 'entry_confidence_threshold'), 0.6))
        entry_rsi = to_decimal(get_config_value(
            # Upper bound for RSI
            self.config, ('trading', 'entry_rsi_threshold'), 75.0))
        use_trend_filter = get_config_value(
            self.config, ('trading', 'use_trend_filter'), True)
        use_rsi_filter = get_config_value(
            self.config, ('trading', 'use_rsi_filter'), True)

        # Indicator periods needed for filters
        sma_f_p = get_config_value(
            self.config, ('strategies', 'geometric_grid', 'sma_fast_period'), 50)
        sma_s_p = get_config_value(
            self.config, ('strategies', 'geometric_grid', 'sma_slow_period'), 200)
        rsi_p = get_config_value(
            self.config, ('strategies', 'geometric_grid', 'rsi_period'), 14)

        # Extract latest indicator values safely
        latest_indicators = None
        if isinstance(indicators_df, pd.DataFrame) and not indicators_df.empty:
            latest_indicators = indicators_df.iloc[-1]

        # Determine if conditions are met to plan grid buys
        should_plan_grid = False
        if conf >= entry_conf:
            trend_ok = True  # Assume trend is OK if filter disabled or indicators unavailable
            rsi_ok = True  # Assume RSI is OK if filter disabled or indicators unavailable

            if latest_indicators is not None:
                # Check Trend Filter (SMA Crossover)
                if use_trend_filter:
                    sma_fast = latest_indicators.get(f'SMA_{sma_f_p}')
                    sma_slow = latest_indicators.get(f'SMA_{sma_s_p}')
                    if sma_fast is not None and sma_slow is not None:
                        # Ensure comparison is between Decimals (indicators should return Decimal)
                        trend_ok = to_decimal(sma_fast) > to_decimal(sma_slow)
                    else:
                        logger.warning(
                            "Grid planning: Trend filter enabled but SMA values missing.")
                        trend_ok = False  # Cannot confirm trend

                # Check RSI Filter (Not Overbought)
                if use_rsi_filter:
                    rsi_value = latest_indicators.get(f'RSI_{rsi_p}')
                    if rsi_value is not None:
                        # Ensure comparison is between Decimals
                        rsi_ok = to_decimal(rsi_value) < entry_rsi
                    else:
                        logger.warning(
                            "Grid planning: RSI filter enabled but RSI value missing.")
                        rsi_ok = False  # Cannot confirm RSI

                # Combine conditions
                if trend_ok and rsi_ok:
                    should_plan_grid = True
                    logger.debug(
                        f"Grid planning conditions met: Conf ({conf:.2f}>={entry_conf}), Trend ({trend_ok}), RSI ({rsi_ok})")
                else:
                    # Log specific reasons for not planning
                    reasons = []
                    if not trend_ok:
                        reasons.append(
                            f"Trend Filter (SMA {sma_f_p}/{sma_s_p})")
                    if not rsi_ok:
                        rsi_val_str = f"{to_decimal(latest_indicators.get(f'RSI_{rsi_p}')):.1f}" if latest_indicators.get(
                            f'RSI_{rsi_p}') is not None else 'N/A'
                        reasons.append(
                            f"RSI Filter ({rsi_val_str} >= {entry_rsi})")
                    if reasons:  # Only log if there's a reason
                        logger.debug(
                            f"Grid planning skipped due to unmet conditions: {', '.join(reasons)}")

            else:  # Indicators not available
                if use_trend_filter or use_rsi_filter:
                    logger.warning(
                        "Grid planning skipped: Filters enabled but indicator data is unavailable.")
                    should_plan_grid = False
                else:  # No filters enabled, confidence is enough
                    should_plan_grid = True
                    logger.debug(
                        "Grid planning conditions met: Conf ({conf:.2f}>={entry_conf}) (Filters disabled/unavailable)")

        else:  # Confidence too low
            logger.debug(
                f"Grid planning skipped: Confidence ({conf:.2f}) below threshold ({entry_conf})")

        # If conditions met, call the grid planning function
        if should_plan_grid:
            try:
                # Get current ATR for volatility adjustment in grid planning
                current_atr = None
                if latest_indicators is not None:
                    atr_period = get_config_value(
                        self.config, ('strategies', 'geometric_grid', 'atr_period'), 14)
                    atr_col_name = f'ATR_{atr_period}'
                    current_atr = latest_indicators.get(atr_col_name)
                    current_atr = to_decimal(current_atr)  # Ensure Decimal

                # Fetch cached exchange info for order validation within planning
                exchange_info = self.connector.get_exchange_info_cached()
                if not exchange_info:
                    raise ValueError(
                        "Exchange info not available for grid planning.")

                self.state['planned_grid'] = plan_buy_grid_v1(
                    symbol=self.symbol,
                    current_price=curr_px,  # Already Decimal
                    current_atr=current_atr,  # Already Decimal (or None)
                    available_quote_balance=available_quote_balance,  # Already Decimal
                    exchange_info=exchange_info,
                    config_dict=self.config,  # Pass full config
                    confidence_score=conf  # Already Decimal
                )
                if self.state['planned_grid']:  # Only log if grid was planned
                    logger.info(
                        f"Planned Grid Buy Orders: {len(self.state['planned_grid'])} levels")
            except Exception as e:
                logger.error(f"Error during grid planning: {e}", exc_info=True)
                self.state['planned_grid'] = []  # Ensure it's reset on error
        # else: # Already logged reasons for skipping above

        # --- Take Profit Planning ---
        # === Use the pos_size variable already converted to Decimal ===
        if pos_size > Decimal('0'):
            logger.debug("Planning Take Profit level for existing position...")
            try:
                self.state['planned_tp_price'] = calculate_dynamic_tp_price(
                    entry_price=entry_px,       # Already Decimal
                    position_size=pos_size,     # Already Decimal
                    current_price=curr_px,      # Already Decimal
                    confidence_score=conf,      # Already Decimal
                    indicators=indicators_df if isinstance(
                        # Pass DataFrame
                        indicators_df, pd.DataFrame) else pd.DataFrame(),
                    sr_zones=sr_zones if isinstance(
                        sr_zones, (list, dict)) else [],  # Pass list/dict
                    config_dict=self.config,  # Pass full config
                    connector=self.connector,  # Pass connector for filters
                    symbol=self.symbol
                )
                if self.state['planned_tp_price'] is not None:
                    logger.info(
                        f"Planned Take Profit Price: {self.state['planned_tp_price']:.4f} {self.quote_asset}")
                else:
                    # This can happen if TP logic decides not to set a TP (e.g., price too close to entry)
                    logger.info(
                        "Take Profit calculation resulted in no TP level being set for this cycle.")
            except Exception as e:
                logger.error(
                    f"Error during Take Profit planning: {e}", exc_info=True)
                self.state['planned_tp_price'] = None  # Reset on error
        else:
            logger.debug("No active position, skipping Take Profit planning.")

    def _execute_trades(self):
        logger.debug("Executing planned trades...")
        planned_grid = self.state.get('planned_grid', [])
        planned_tp = self.state.get(
            'planned_tp_price')  # Can be None or Decimal
        # === FIX: Ensure current_pos_size is Decimal for comparison/use ===
        current_pos_size = to_decimal(self.state.get('position_size', '0'))
        # ================================================================

        # --- Execute Grid Orders ---
        # reconcile_and_place_grid handles placing new orders and cancelling outdated ones
        try:
            reconciliation_result = self.order_manager.reconcile_and_place_grid(
                planned_grid)
            placed = len(reconciliation_result.get('placed', []))
            cancelled = len(reconciliation_result.get('cancelled', []))
            failed = len(reconciliation_result.get('failed', []))
            unchanged = len(reconciliation_result.get('unchanged', []))
            # Log only if there were changes
            if placed > 0 or cancelled > 0 or failed > 0:
                logger.info(
                    f"Grid Order Reconciliation: Placed={placed}, Cancelled={cancelled}, Failed={failed}, Unchanged={unchanged}")
            else:
                logger.debug("Grid Order Reconciliation: No changes.")
        except Exception as e:
            logger.error(
                f"Error during grid order reconciliation and placement: {e}", exc_info=True)

        # --- Execute Take Profit Order ---
        # place_or_update_tp_order handles placing a new TP or modifying/cancelling the existing one
        try:
            # === Use the current_pos_size variable already converted to Decimal ===
            if current_pos_size > Decimal('0'):
                # If we have a position, try to place/update TP based on plan
                if planned_tp is not None:
                    logger.debug(
                        f"Attempting to place/update TP order at {planned_tp:.4f} for size {current_pos_size:.8f}")
                    tp_result = self.order_manager.place_or_update_tp_order(
                        planned_tp, current_pos_size)
                    # Logging is handled within place_or_update_tp_order now
                    # if tp_result: log success... else: log warning...
                else:
                    # This case means _plan_trades decided not to set a TP for this cycle
                    # We might want to cancel any existing TP if the plan is None
                    logger.info(
                        "No Take Profit price planned this cycle. Ensuring any existing TP is cancelled.")
                    # Call with zero/None signals cancellation intent to OrderManager
                    self.order_manager.place_or_update_tp_order(
                        None, Decimal('0'))

            else:  # No position exists
                logger.debug(
                    "No active position. Ensuring any existing Take Profit order is cancelled.")
                # Call with zero/None signals cancellation intent
                self.order_manager.place_or_update_tp_order(None, Decimal('0'))

        except Exception as e:
            logger.error(
                f"Error during Take Profit order placement/update: {e}", exc_info=True)

    def _apply_risk_controls(self):
        logger.debug("Applying risk controls...")

        # Get necessary state variables, ensuring Decimal type
        # === FIX: Ensure pos_size is Decimal for comparison ===
        pos_size = to_decimal(self.state.get('position_size', '0'))
        # ======================================================
        ts_entry = self.state.get('position_entry_timestamp')
        px_entry = to_decimal(self.state.get('position_entry_price', '0'))
        current_kline_data = self.state.get('current_kline', {})
        px_curr = current_kline_data.get('close')  # Already Decimal
        ts_curr = self.state.get(
            'last_processed_timestamp')  # Already Timestamp

        # Check if risk controls should be applied (requires an active position and current data)
        # === Use the pos_size variable already converted to Decimal ===
        if pos_size <= Decimal('0'):
            # logger.debug("Skipping risk controls: No active position.") # Can be verbose
            return
        if not ts_entry or px_entry <= Decimal('0') or not px_curr or not ts_curr:
            logger.warning(
                f"Skipping risk controls: Missing data. "
                f"Pos={pos_size}, EntryTs={ts_entry}, EntryPx={px_entry}, CurrPx={px_curr}, CurrTs={ts_curr}")
            return

        try:
            # Ensure entry timestamp is a Timestamp object
            ts_entry_ts = None
            if isinstance(ts_entry, str):
                try:
                    ts_entry_ts = pd.Timestamp(ts_entry)
                except ValueError:
                    logger.error(
                        f"Invalid position entry timestamp format found in state: {ts_entry}")
                    return  # Cannot proceed without valid timestamp
            elif isinstance(ts_entry, pd.Timestamp):
                ts_entry_ts = ts_entry  # Use directly
            else:
                logger.error(
                    f"Unexpected type for position entry timestamp: {type(ts_entry)}")
                return  # Cannot proceed

            # --- Time Stop Check ---
            # check_time_stop function encapsulates the logic
            time_stop_triggered = check_time_stop(
                entry_timestamp=ts_entry_ts,  # Pass Timestamp object
                entry_price=px_entry,        # Pass Decimal
                position_size=pos_size,      # Pass Decimal
                current_price=px_curr,       # Pass Decimal
                current_timestamp=ts_curr,   # Pass Timestamp object
                config_dict=self.config      # Pass the full config
            )

            if time_stop_triggered:
                # Warning log is inside check_time_stop
                logger.info(
                    f"Executing market sell for {pos_size:.8f} {self.base_asset} due to time stop trigger...")
                sell_result = self.order_manager.execute_market_sell(
                    pos_size, reason="time_stop")

                if sell_result:
                    # If sell succeeds, OrderManager should update internal state (active orders).
                    # We need to update the main state here reflecting the closed position.
                    logger.info(
                        # Log full response if needed
                        f"Time stop market sell successful. Response: {sell_result}")
                    # Manually update position state immediately after successful market sell
                    # (as _check_orders might run later or miss the fill in the same cycle)
                    self.state['position_size'] = Decimal('0')
                    self.state['position_entry_price'] = Decimal('0')
                    self.state['position_entry_timestamp'] = None
                    # Balances will be updated more accurately when the fill is processed,
                    # but we can log the state change now.
                    logger.info(
                        "Position state reset after time stop market sell execution.")
                    # Save state immediately after critical risk action
                    self.state_manager.save_state(self.state)
                else:
                    logger.error(
                        "Time stop market sell execution FAILED. Position remains open.")
                    # Potentially add retry logic or alerting here

            # --- Add other risk controls here (e.g., conditional stops) ---
            # Example:
            # conditional_stop_triggered = check_conditional_stop(...)
            # if conditional_stop_triggered:
            #     logger.warning("RISK CONTROL: Conditional stop triggered!")
            #     # ... execute market sell ...

        except Exception as e:
            logger.error(
                f"Error occurred during risk control application: {e}", exc_info=True)

    def _check_orders_and_update_state(self):
        logger.debug("Checking status of active orders...")

        current_kline_data = self.state.get('current_kline', {})
        px_curr = current_kline_data.get('close')  # Already Decimal

        # Price needed only for simulation checks
        price_for_check = px_curr if self.simulation_mode else None
        if self.simulation_mode and price_for_check is None:
            logger.warning(
                "Cannot check simulated order status: Current price is unavailable.")
            return

        try:
            # Delegate order checking to OrderManager
            # It handles both live API checks and simulated checks based on current price
            fill_results = self.order_manager.check_orders(price_for_check)

            # Check if any fills occurred (grid or TP)
            if fill_results.get('grid_fills') or fill_results.get('tp_fill'):
                logger.info("Fills detected, processing state updates...")

                # Process the fills to update position size, entry price, and balances
                # This modifies self.state directly, ensuring Decimal types internally
                self._process_fills(fill_results)

                # Update position entry timestamp if a position was opened or closed
                # Check state *after* _process_fills potentially modified it
                pos_size_after_fill = to_decimal(
                    self.state.get('position_size', '0'))
                ts_entry_after_fill = self.state.get(
                    'position_entry_timestamp')  # Get current value
                ts_last_kline = self.state.get(
                    'last_processed_timestamp')  # Already Timestamp

                # If position opened (size > 0 and no previous entry timestamp)
                # Check ts_entry_after_fill is None to avoid overwriting existing one
                if fill_results.get('grid_fills') and pos_size_after_fill > Decimal('0') and ts_entry_after_fill is None:
                    self.state['position_entry_timestamp'] = ts_last_kline
                    logger.info(
                        f"Position opened by grid fill. Entry timestamp set to: {ts_last_kline}")

                # If position closed (size is 0 and TP fill occurred)
                # _process_fills should have already set pos_size to 0
                elif fill_results.get('tp_fill') and pos_size_after_fill == Decimal('0'):
                    # Clearing timestamp should happen *after* P/L calc if needed
                    # Or be handled consistently within _process_fills
                    if ts_entry_after_fill is not None:  # Check if it needs clearing
                        self.state['position_entry_timestamp'] = None
                        logger.info(
                            "Position closed by Take Profit fill. Entry timestamp cleared.")

                # In live mode, balances should reflect the exchange state after fills. Re-fetch.
                if not self.simulation_mode:
                    logger.debug(
                        "Re-fetching live balances after processing fills...")
                    self._update_balances()  # Ensures state balances are updated to Decimal

                # Save the updated state after processing fills
                logger.debug("Saving state after processing fills...")
                self.state_manager.save_state(self.state)
            else:
                logger.debug("No new fills detected in this cycle.")

        except Exception as e:
            logger.error(
                f"Error during order checking or fill processing: {e}", exc_info=True)

    def _shutdown(self, signum=None, frame=None):
        if self.is_shutting_down:
            logger.info("Shutdown already in progress.")
            return  # Prevent redundant shutdown calls

        self.is_shutting_down = True
        self.running = False  # Signal loops to stop

        signal_name = signal.Signals(signum).name if signum is not None and isinstance(
            signum, int) else 'programmatic'
        logger.warning(
            f"Initiating shutdown sequence (Trigger: {signal_name})...")

        # --- Cancel Open Orders (Optional) ---
        cancel_on_exit = get_config_value(
            self.config, ('trading', 'cancel_orders_on_exit'), False)

        if cancel_on_exit:
            if hasattr(self, 'order_manager') and self.order_manager:
                logger.info(
                    "Attempting to cancel all open orders as configured...")
                try:
                    # === START REPLACEMENT BLOCK: _shutdown if cancel_on_exit try ===
                    # Load the most recent state to get active orders
                    # Use self.state as it should be up-to-date from the loop
                    current_state = self.state  # Assumes self.state is the source of truth
                    active_grid = current_state.get('active_grid_orders', [])
                    active_tp = current_state.get(
                        'active_tp_order')  # Can be None or dict

                    # Ensure active_grid is a list
                    if not isinstance(active_grid, list):
                        logger.warning(
                            f"State 'active_grid_orders' is not a list: {type(active_grid)}. Skipping grid cancellation.")
                        active_grid = []

                    orders_to_cancel = list(active_grid)  # Make a mutable copy

                    # Ensure active_tp is a dict if not None
                    if active_tp is not None:
                        if isinstance(active_tp, dict):
                            orders_to_cancel.append(active_tp)
                        else:
                            logger.warning(
                                f"State 'active_tp_order' is not a dict: {type(active_tp)}. Skipping TP cancellation.")

                    logger.info(
                        f"Found {len(orders_to_cancel)} potential orders in state to cancel.")
                    cancelled_count = 0
                    failed_count = 0
                    for order in orders_to_cancel:
                        # Ensure order is a dictionary before accessing keys
                        if not isinstance(order, dict):
                            logger.warning(
                                f"Found non-dict item in orders_to_cancel list: {order}. Skipping.")
                            failed_count += 1
                            continue

                        # Extract necessary IDs safely
                        client_order_id = order.get('clientOrderId')
                        order_id = order.get('orderId')
                        side = order.get('side')
                        label = "TP" if side == 'SELL' else "Grid"

                        if order_id or client_order_id:  # Need at least one ID
                            logger.debug(
                                f"Requesting cancellation for {label} order: ID={order_id}, ClientID={client_order_id}")
                            try:
                                # OrderManager handles simulation vs live cancellation
                                success = self.order_manager.cancel_order(
                                    client_order_id, order_id, f"{label} (Shutdown)")
                                if success:
                                    cancelled_count += 1
                                else:
                                    # cancel_order returning False likely means OM handled failure
                                    failed_count += 1
                            except Exception as cancel_err:
                                logger.error(
                                    f"Error during cancellation request for order {order_id or client_order_id}: {cancel_err}", exc_info=False)
                                failed_count += 1
                        else:
                            logger.warning(
                                f"Cannot cancel order, missing required IDs: {order}")
                            failed_count += 1

                    logger.info(
                        f"Order cancellation requests summary: Attempted={len(orders_to_cancel)}, Successful={cancelled_count}, Failed/Skipped={failed_count}")
                    # === END REPLACEMENT BLOCK: _shutdown if cancel_on_exit try ===
                except Exception as e:
                    logger.error(
                        f"Error occurred during order cancellation process on shutdown: {e}", exc_info=True)
            else:
                logger.warning(
                    "Order manager not available, cannot cancel orders on exit.")
        else:
            logger.info(
                "Skipping order cancellation on exit (disabled in config).")

        # --- Save Final State ---
        if hasattr(self, 'state_manager') and self.state_manager and hasattr(self, 'state'):
            # Ensure state is a dictionary before saving
            final_state = getattr(self, 'state', None)
            if isinstance(final_state, dict):
                logger.info("Saving final application state...")
                try:
                    # Ensure numeric types are correctly serialized by StateManager if needed
                    self.state_manager.save_state(final_state)
                    logger.info("Final state saved successfully.")
                except Exception as e:
                    logger.error(
                        f"Failed to save final state during shutdown: {e}", exc_info=True)
            else:
                logger.warning(
                    "Cannot save final state: state attribute missing or not a dict.")
        else:
            logger.warning(
                "State manager or state not available, cannot save final state.")

        logger.warning("Shutdown sequence complete. Exiting application.")
        print("\nGeminiTrader stopped.")
        sys.exit(0)  # Ensure clean exit

    def run(self):
        logger.info("Starting main trading loop...")
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)  # Handle Ctrl+C
        # Handle termination signals
        signal.signal(signal.SIGTERM, self._shutdown)

        try:
            # Perform initial setup (_initialize now ensures Decimals in state)
            self._initialize()
            # Check if initialization succeeded (self.running might be set to False in __init__ on error)
            if not self.running:
                logger.error("Exiting run loop: Initialization failed.")
                # _shutdown is not called here as sys.exit was likely called in __init__
                return  # Exit run method

            # Get loop interval from config
            loop_interval_seconds = get_config_value(
                self.config, ('trading', 'loop_sleep_time'), 60)

            # Setup progress bar for simulation mode
            sim_steps = len(
                self.sim_data) if self.simulation_mode and self.sim_data is not None else 0
            pbar = tqdm(total=sim_steps, desc="Simulating", unit=" steps",
                        disable=not self.simulation_mode, leave=True)

            if self.simulation_mode:
                logger.info(
                    f"Running in SIMULATION mode. Processing {sim_steps} data points.")
            else:
                logger.info(
                    f"Running in LIVE mode. Main loop interval: {loop_interval_seconds} seconds.")

            # Main Trading Loop
            while self.running:
                cycle_start_time = time.monotonic()
                logger.debug(
                    # Added UTC for clarity
                    f"------ New Cycle Started: {pd.Timestamp.now(tz='UTC')} ------")

                # 1. Update Market Data (Fetch Klines)
                market_data_ok = self._update_market_data()
                if not market_data_ok:
                    if not self.running:
                        break  # Exit if simulation ended or critical error occurred
                    logger.warning(
                        "Failed to update market data this cycle. Skipping other actions.")
                    # Consider a shorter sleep/retry or specific error handling here if needed
                    time.sleep(loop_interval_seconds)
                    continue  # Skip to next cycle

                # Update simulation progress bar (after potentially long data step)
                if self.simulation_mode:
                    pbar.update(1)
                    # Format postfix string safely using .get() and ensuring Decimal
                    conf_score = self.state.get('confidence_score')
                    conf_str = f"{conf_score:.2f}" if isinstance(
                        conf_score, (float, Decimal)) else "N/A"
                    # === FIX: Ensure pos_size is Decimal for display ===
                    pos_size_state = to_decimal(
                        self.state.get('position_size', '0'))
                    pos_str = f"{pos_size_state:.4f}" if pos_size_state is not None else "N/A"
                    # ===================================================
                    grid_list = self.state.get('active_grid_orders', [])
                    grid_count = len(grid_list) if isinstance(
                        grid_list, list) else "N/A"
                    tp_order = self.state.get('active_tp_order')
                    tp_str = "Y" if isinstance(tp_order, dict) else "N"
                    pfix = {"Conf": conf_str, "Pos": pos_str,
                            "Grid": grid_count, "TP": tp_str}
                    pbar.set_postfix(pfix, refresh=False)  # Refresh less often

                # 2. Calculate Analysis (Indicators, S/R, Confidence)
                analysis_ok = self._calculate_analysis()
                # If analysis failed, dependent steps might use stale data or fail.
                # Decide if continuing is safe based on strategy needs.
                # For now, we proceed but log the failure.

                # 3. Check Orders & Update State from Fills
                # This step now ensures state numerics are Decimal
                self._check_orders_and_update_state()
                if not self.running:
                    break  # check_orders might stop run on error

                # 4. Apply Risk Controls (e.g., Time Stops)
                # This step now ensures state numerics are Decimal before checks
                self._apply_risk_controls()
                if not self.running:
                    break  # Risk controls might trigger shutdown

                # 5. Plan Trades (Grid Buys, Take Profit)
                # This step now ensures state numerics are Decimal before planning
                if analysis_ok:  # Only plan if analysis succeeded
                    self._plan_trades()
                else:
                    logger.warning(
                        "Skipping trade planning due to previous analysis failure.")
                    self.state['planned_grid'] = []  # Ensure plans are cleared
                    self.state['planned_tp_price'] = None
                if not self.running:
                    break

                # 6. Execute Trades (Place/Cancel Orders)
                # This step now ensures state numerics are Decimal before execution
                self._execute_trades()
                if not self.running:
                    break

                # --- Cycle End ---
                # Save state at end of each cycle for resilience
                try:
                    # Only save if running to avoid saving during shutdown sequence again
                    if self.running:
                        self.state_manager.save_state(self.state)
                        logger.debug("State saved at end of cycle.")
                except Exception as save_err:
                    logger.error(
                        f"Error saving state at end of cycle: {save_err}", exc_info=False)

                cycle_end_time = time.monotonic()
                cycle_duration = cycle_end_time - cycle_start_time
                logger.debug(
                    f"Trading cycle completed in {cycle_duration:.2f} seconds.")

                # Calculate sleep time, ensuring it's not negative
                sleep_time = max(0, loop_interval_seconds - cycle_duration)
                if self.running and sleep_time > 0 and not self.simulation_mode:  # Don't sleep in sim mode
                    logger.debug(f"Sleeping for {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                elif self.running and not self.simulation_mode:
                    logger.warning(
                        f"Cycle duration ({cycle_duration:.2f}s) exceeded loop interval ({loop_interval_seconds}s). Running next cycle immediately.")
                # No sleep needed in simulation mode, run next step immediately

            # --- Loop End ---
            if self.simulation_mode:
                pbar.close()
                logger.info("Simulation processing finished.")
            else:
                logger.info("Live trading loop terminated.")

        except KeyboardInterrupt:
            logger.warning(
                "KeyboardInterrupt detected in main loop. Initiating shutdown...")
            self._shutdown(signal.SIGINT)
        except ConnectionError as ce:
            logger.critical(
                f"CRITICAL Connection Error in main loop: {ce}. Initiating shutdown...", exc_info=True)
            self._shutdown(signal.SIGABRT)  # Use SIGABRT for critical errors
        except Exception as e:
            logger.critical(
                f"CRITICAL UNHANDLED ERROR in main loop: {e}", exc_info=True)
            # Attempt graceful shutdown even on unknown errors
            self._shutdown(signal.SIGABRT)
        finally:
            # Ensure shutdown is called if the loop exits unexpectedly without is_shutting_down being set
            if not self.is_shutting_down:
                logger.warning(
                    "Main loop exited unexpectedly without explicit shutdown signal. Initiating shutdown now.")
                self._shutdown()  # Call shutdown without signal


if __name__ == "__main__":
    logger.info("Starting GeminiTrader application...")
    bot = GeminiTrader()

    # Check if initialization was successful (bot.running should be True)
    if bot.running:
        logger.info("Initialization successful. Starting main run loop.")
        bot.run()  # Start the main trading loop
    else:
        # Initialization failed, error logged in __init__, sys.exit already called
        logger.error(
            "GeminiTrader initialization failed. Application will not run (exit already initiated).")
        # No need for sys.exit(1) here as __init__ handles it on failure.
        # Keep the print message for user feedback.
        print("Exiting: GeminiTrader initialization failed. Check logs for details.")


# EOF: src/main_trader.py
