# START OF FILE: src/main_trader.py (Updated based on recommendations)

import logging
import logging.config
import time
import sys
import signal
import csv
from datetime import datetime, timezone
from decimal import Decimal, getcontext, InvalidOperation
from typing import Dict, Any, Optional, List
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
from src.utils.formatting import to_decimal

# Set Decimal precision
getcontext().prec = 18

# Setup Logging early
setup_logging()
logger = logging.getLogger(__name__)
project_root = Path(__file__).parent.parent

# --- Define CSV Report Fieldnames ---
REPORT_FIELDNAMES = [
    "TimestampUTC", "EventType", "Symbol", "Quantity", "Price",
    "CostOrProceeds", "PnL", "QuoteBalanceAfter", "PositionSizeAfter", "Notes"
]


class GeminiTrader:
    """Main autonomous trading bot class."""

    # START OF METHOD: src/main_trader.py -> __init__ (Updated OM instantiation)
    def __init__(self):
        logger.info("Initializing GeminiTrader...")
        self.report_writer: Optional[csv.DictWriter] = None
        self.report_file_handle: Optional[Any] = None
        self.report_filepath: Optional[Path] = None
        try:
            # --- Configuration Loading ---
            self.config: Dict[str, Any] = load_config()
            if not self.config:
                raise ValueError("Config dictionary is empty.")
            api_key = get_config_value(self.config, ('binance_us', 'api_key'))
            api_secret = get_config_value(
                self.config, ('binance_us', 'api_secret'))
            tld = get_config_value(self.config, ('binance_us', 'tld'), 'us')
            if not api_key or not api_secret:
                raise ValueError("API Key/Secret not found.")

            # --- Connector Initialization ---
            self.connector = BinanceUSConnector(
                api_key=api_key, api_secret=api_secret, config=self.config, tld=tld)

            # --- State Manager Initialization ---
            state_file_rel = get_config_value(
                self.config, ('state_manager', 'filepath'), 'data/state/trader_state.json')
            state_file_abs = project_root / state_file_rel
            self.state_manager = StateManager(filepath=str(state_file_abs))

            # --- State Loading and Initialization ---
            logger.info(f"Attempting to load state from {state_file_abs}...")
            loaded_state = self.state_manager.load_state()
            # Optionally force a clean state for testing
            FORCE_CLEAN_STATE = False

            if not loaded_state or FORCE_CLEAN_STATE:
                if FORCE_CLEAN_STATE:
                    logger.warning(
                        "FORCE_CLEAN_STATE=True: Initializing fresh state.")
                else:
                    logger.info(
                        "State file not found or empty. Initializing fresh state.")

                initial_sim_balance_str = get_config_value(
                    self.config, ('simulation', 'initial_balance'), '1000.0')
                initial_sim_balance_dec = to_decimal(initial_sim_balance_str)
                if initial_sim_balance_dec is None:
                    logger.error(
                        f"Invalid initial_balance '{initial_sim_balance_str}' in config. Defaulting to 1000.0")
                    initial_sim_balance_dec = Decimal('1000.0')

                self.state: Dict[str, Any] = {
                    'position_size': Decimal('0'),
                    'position_entry_price': Decimal('0'),
                    'position_entry_timestamp': None,
                    'balance_quote': initial_sim_balance_dec,
                    'balance_base': Decimal('0'),
                    'active_grid_orders': [],
                    'active_tp_order': None,
                    'historical_klines': None,
                    'current_kline': None,
                    'last_processed_timestamp': None,
                    'indicators': None,
                    'sr_zones': None,
                    'confidence_score': None,
                    'planned_grid': [],
                    'planned_tp_price': None
                }
                logger.info(
                    f"Initialized fresh state. Quote Balance: {self.state['balance_quote']:.4f}")
            else:
                logger.info("Successfully loaded existing state from file.")
                self.state = loaded_state
                # State manager's _post_load_process ensures types are correct

                # Debug logging for loaded balance
                balance_value = self.state.get('balance_quote')
                if isinstance(balance_value, Decimal):
                    balance_str = f"{balance_value:.4f}"
                else:
                    balance_str = str(balance_value)
                logger.info(
                    f"Loaded existing state. Quote Balance: {balance_str}")

                # Consistency check
                if self.state.get('position_size', Decimal('0')) <= Decimal('0'):
                    if self.state.get('position_entry_timestamp') is not None:
                        logger.warning(
                            "Correcting loaded state: Position size is zero but entry timestamp was set. Clearing timestamp.")
                        self.state['position_entry_timestamp'] = None

            # --- Initialize Report Writer (Only in Simulation Mode) ---
            self.simulation_mode = get_config_value(
                self.config, ('trading', 'simulation_mode'), False)
            if self.simulation_mode:
                self._initialize_report_writer()
                # Save initial state *after* report is initialized (and initial balance written)
                logger.info("Saving initial state...")
                self.state_manager.save_state(self.state)

            # --- Order Manager Initialization ---
            # Pass config and connector, but NOT state_manager
            self.order_manager = OrderManager(
                config_dict=self.config,
                connector=self.connector
            )

            # --- Final Setup ---
            logger.info(
                f"Initialization complete. SIMULATION_MODE: {self.simulation_mode}")
            self.running = True
            self.is_shutting_down = False
            self.sim_data = None
            self.sim_data_iterator = None
            self.sim_current_row = None

        except Exception as e:
            logger.critical(f"FATAL: Init failed: {e}", exc_info=True)
            self._close_report_file()  # Attempt to close report file on init failure
            # Attempt to save state only if state_manager and state attribute exist
            if hasattr(self, 'state_manager') and self.state_manager and hasattr(self, 'state'):
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
            self.running = False
            print(f"Exiting due to initialization error: {e}")
            sys.exit(1)
    # END OF METHOD: src/main_trader.py -> __init__

    # START OF METHOD: src/main_trader.py -> _initialize_report_writer (Unchanged)
    def _initialize_report_writer(self):
        """Sets up the CSV writer for simulation reports."""
        if not self.simulation_mode:
            return

        try:
            # Generate filename
            report_dir = project_root / "data" / "sim_reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            timestamp_utc = datetime.now(timezone.utc)
            timestamp_str = timestamp_utc.strftime("%Y%m%d_%H%M%S")
            report_symbol = get_config_value(
                self.config, ('trading', 'symbol'), 'UNKNOWN')
            report_interval = get_config_value(
                self.config, ('trading', 'interval'), 'UNK')
            filename = f"SimReport_{report_symbol}_{report_interval}_{timestamp_str}.csv"
            self.report_filepath = report_dir / filename

            # Open file and writer
            self.report_file_handle = open(
                self.report_filepath, 'w', newline='', encoding='utf-8')
            self.report_writer = csv.DictWriter(
                self.report_file_handle, fieldnames=REPORT_FIELDNAMES)
            self.report_writer.writeheader()
            logger.info(
                f"Initialized simulation report CSV: {self.report_filepath}")

            # Write initial balance row
            initial_balance_value = self.state.get(
                'balance_quote', Decimal('0'))
            self._write_report_row(
                event_type="INITIAL_BALANCE",
                notes=f"Starting Balance: {initial_balance_value:.8f}"
            )

        except Exception as e:
            logger.error(
                f"Failed to initialize simulation report writer: {e}", exc_info=True)
            self.report_writer = None
            if self.report_file_handle:
                try:
                    self.report_file_handle.close()
                except Exception:
                    pass
                self.report_file_handle = None
            self.report_filepath = None
    # END OF METHOD: src/main_trader.py -> _initialize_report_writer

    # START OF METHOD: src/main_trader.py -> _write_report_row (Unchanged)
    def _write_report_row(self, event_type: str, quantity: Optional[Decimal] = None, price: Optional[Decimal] = None, cost_or_proceeds: Optional[Decimal] = None, pnl: Optional[Decimal] = None, notes: str = ""):
        """Helper function to write a row to the simulation report CSV."""
        if not self.simulation_mode or self.report_writer is None or self.report_file_handle is None:
            return

        try:
            # Use timestamp from state if available (more accurate for sim), else use now
            timestamp_state = self.state.get('last_processed_timestamp')
            if isinstance(timestamp_state, pd.Timestamp):
                timestamp_to_use = timestamp_state.to_pydatetime()
                if timestamp_to_use.tzinfo is None:
                    timestamp_to_use = timestamp_to_use.replace(
                        tzinfo=timezone.utc)
            else:
                timestamp_to_use = datetime.now(timezone.utc)  # Fallback

            timestamp_str = timestamp_to_use.strftime(
                '%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

            symbol = getattr(self, 'symbol', 'N/A')
            balance_quote = to_decimal(self.state.get('balance_quote', '0'))
            pos_size = to_decimal(self.state.get('position_size', '0'))

            row_data = {
                "TimestampUTC": timestamp_str,
                "EventType": event_type,
                "Symbol": symbol,
                "Quantity": f"{quantity:.8f}" if quantity is not None else None,
                "Price": f"{price:.8f}" if price is not None else None,
                "CostOrProceeds": f"{cost_or_proceeds:.8f}" if cost_or_proceeds is not None else None,
                "PnL": f"{pnl:.8f}" if pnl is not None else None,
                "QuoteBalanceAfter": f"{balance_quote:.8f}" if balance_quote is not None else '0.00000000',
                "PositionSizeAfter": f"{pos_size:.8f}" if pos_size is not None else '0.00000000',
                "Notes": notes
            }
            self.report_writer.writerow(row_data)
            self.report_file_handle.flush()
        except Exception as e:
            logger.error(
                f"Failed to write row to simulation report: {e}", exc_info=True)
    # END OF METHOD: src/main_trader.py -> _write_report_row

    # START OF METHOD: src/main_trader.py -> _close_report_file (Unchanged)
    def _close_report_file(self):
        """Closes the simulation report file if it's open."""
        if self.report_file_handle:
            try:
                logger.info(
                    f"Closing simulation report file: {self.report_filepath}")
                self.report_file_handle.close()
            except Exception as e:
                logger.error(
                    f"Error closing report file {self.report_filepath}: {e}")
            finally:
                self.report_file_handle = None
                self.report_writer = None
                self.report_filepath = None
    # END OF METHOD: src/main_trader.py -> _close_report_file

    # START OF METHOD: src/main_trader.py -> _initialize (Unchanged - retains fast-forward)
    def _initialize(self):
        logger.info("Starting Initialization Sequence...")
        self.symbol = get_config_value(
            self.config, ('trading', 'symbol'), 'BTCUSDT')
        self.quote_asset = get_config_value(
            self.config, ('portfolio', 'quote_asset'), 'USDT')
        # Base asset inference logic
        if self.symbol.endswith(self.quote_asset):
            self.base_asset = self.symbol[:-len(self.quote_asset)]
        else:
            common_bases = ['BTC', 'ETH']
            inferred = False
            for base in common_bases:
                if self.symbol.startswith(base):
                    self.base_asset = base
                    inferred = True
                    logger.info(f"Inferred base asset: {self.base_asset}")
                    break
            if not inferred:
                self.base_asset = 'UNKNOWN_BASE'
                logger.error(
                    f"Could not infer base asset for symbol '{self.symbol}' and quote '{self.quote_asset}'. Defaulting to {self.base_asset}.")
        self.kline_interval = get_config_value(
            self.config, ('trading', 'interval'), '1h')

        if not self.simulation_mode:
            # Live mode logic
            logger.info("Verifying exchange connection...")
            server_time = self.connector.get_server_time()
            if server_time is None:
                raise ConnectionError("Exchange connection failed.")
            logger.info(f"Exchange connection OK. Server time: {server_time}")
            self._update_balances()
        else:  # Sim setup
            logger.info(
                "Simulation mode: Skipping live connection check & balance fetch.")
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
                self.sim_data = pd.read_csv(sim_file, dtype={
                                            'Open': str, 'High': str, 'Low': str, 'Close': str, 'Volume': str})
                if ts_col_name not in self.sim_data.columns:
                    raise ValueError(
                        f"Timestamp column '{ts_col_name}' not found in CSV.")
                self.sim_data[ts_col_name] = pd.to_datetime(
                    self.sim_data[ts_col_name], unit='ms', errors='coerce', utc=True)
                self.sim_data = self.sim_data.set_index(ts_col_name)

                # Convert OHLCV columns to Decimal
                for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    if col in self.sim_data.columns:
                        self.sim_data[col] = self.sim_data[col].apply(
                            lambda x: to_decimal(x) if pd.notna(x) else None)
                ohlc_cols_present = [c for c in [
                    'Open', 'High', 'Low', 'Close'] if c in self.sim_data.columns]
                if not ohlc_cols_present:
                    raise ValueError("Sim data missing essential OHLC.")
                initial_rows = len(self.sim_data)
                self.sim_data.dropna(subset=ohlc_cols_present, inplace=True)
                if len(self.sim_data) < initial_rows:
                    logger.info(
                        f"Dropped {initial_rows - len(self.sim_data)} rows missing OHLC.")
                if self.sim_data.empty:
                    raise ValueError("Sim data empty after NaN OHLC drop.")

                # Index Handling
                if not isinstance(self.sim_data.index, pd.DatetimeIndex):
                    logger.error(
                        "Index is not DatetimeIndex after loading! Check CSV parsing.")
                    try:
                        self.sim_data.index = pd.to_datetime(
                            self.sim_data.index, errors='coerce', utc=True)
                        if not isinstance(self.sim_data.index, pd.DatetimeIndex):
                            raise TypeError("Index conversion failed.")
                    except Exception as idx_err:
                        raise TypeError(
                            f"Critical error processing simulation data index: {idx_err}")
                initial_rows_idx = len(self.sim_data)
                self.sim_data = self.sim_data[self.sim_data.index.notna()]
                if len(self.sim_data) < initial_rows_idx:
                    logger.info(
                        f"Dropped {initial_rows_idx - len(self.sim_data)} rows with invalid index timestamps.")
                if self.sim_data.empty:
                    raise ValueError("Sim data empty after NaT drop.")

                self.sim_data_iterator = self.sim_data.iterrows()
                logger.info(
                    f"Loaded {len(self.sim_data)} valid sim rows from {sim_file}.")

                # --- Fast-forward Simulation Start (Optional - Keep or Remove) ---
                TARGET_LOGIC_START_TIME_STR = "2024-02-15 16:00:00"  # Example
                try:
                    TARGET_LOGIC_START_TIME = pd.Timestamp(
                        TARGET_LOGIC_START_TIME_STR, tz='UTC')
                    warmup_candles = max(
                        get_config_value(
                            self.config, ('strategies', 'geometric_grid', 'sma_slow_period'), 200),
                        get_config_value(
                            self.config, ('analysis', 'min_candles_for_analysis'), 100)
                    ) + 5
                    target_loc = self.sim_data.index.get_indexer(
                        [TARGET_LOGIC_START_TIME], method='nearest')[0]
                    iterator_start_loc = max(0, target_loc - warmup_candles)
                    if iterator_start_loc > 0:
                        start_ts = self.sim_data.index[iterator_start_loc]
                        logger.warning(
                            f"--- TEMP DEBUG: Fast-forwarding simulation iterator ---")
                        logger.warning(
                            f"Target Logic Start: {TARGET_LOGIC_START_TIME}, Warmup: ~{warmup_candles}")
                        logger.warning(
                            f"Starting iterator at index {iterator_start_loc} (Timestamp: {start_ts})")
                        self.sim_data_iterator = self.sim_data.iloc[iterator_start_loc:].iterrows(
                        )
                    else:
                        logger.info(
                            "Target start time too early, starting sim from beginning.")
                except Exception as ff_err:
                    logger.error(
                        f"Error during sim fast-forward: {ff_err}. Starting from beginning.", exc_info=True)
                # --- End Fast-forward ---

                # Resume Logic (Currently disabled)
                logger.info("Resume logic disabled for targeted test.")
                self.state['last_processed_timestamp'] = None

            except Exception as e:
                logger.critical(
                    f"FATAL: Sim data load/process error: {e}", exc_info=True)
                raise

        # Exchange Info Fetch (common)
        cache_mins = get_config_value(
            self.config, ('trading', 'exchange_info_cache_minutes'), 1440)
        logger.info(
            f"Fetching/loading exchange info (cache: {cache_mins}m)...")
        exchange_info_loaded = self.connector.get_exchange_info(
            force_refresh=False)
        if not exchange_info_loaded:
            logger.warning(
                "Cached exchange info expired/missing. Fetching fresh.")
            exchange_info_loaded = self.connector.get_exchange_info(
                force_refresh=True)
        if not exchange_info_loaded:
            raise ConnectionError("Failed to get exchange info.")
        logger.info("Exchange info loaded successfully.")

        logger.info("Initialization Sequence Complete.")
    # END OF METHOD: src/main_trader.py -> _initialize

    # START OF METHOD: src/main_trader.py -> _update_market_data (Unchanged)
    def _update_market_data(self):
        if self.simulation_mode:
            if self.sim_data_iterator is None:
                logger.error("Sim iterator unavailable.")
                self.running = False
                return False
            try:
                timestamp, row = next(self.sim_data_iterator)
                current_kline = {'timestamp': timestamp, 'open': to_decimal(row.get('Open')), 'high': to_decimal(row.get(
                    'High')), 'low': to_decimal(row.get('Low')), 'close': to_decimal(row.get('Close')), 'volume': to_decimal(row.get('Volume'))}
                if any(v is None for k, v in current_kline.items() if k not in ['timestamp', 'volume']):
                    logger.error(
                        f"Missing OHLC at sim TS {timestamp}. Row: {row.to_dict()}. Stopping.")
                    self.running = False
                    return False
                self.state['current_kline'] = current_kline
                self.state['last_processed_timestamp'] = timestamp
                hist_klines = self.state.get('historical_klines')
                new_row_df = pd.DataFrame(
                    [current_kline]).set_index('timestamp')
                if hist_klines is None or not isinstance(hist_klines, pd.DataFrame):
                    self.state['historical_klines'] = new_row_df
                else:
                    # Timezone Alignment
                    hist_tz = getattr(hist_klines.index, 'tz', None)
                    new_tz = getattr(new_row_df.index, 'tz', None)
                    if hist_tz != new_tz:
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
                                f"TZ align fail: {tz_align_err}. Resetting hist.")
                            self.state['historical_klines'] = new_row_df
                    # Concatenation
                    try:
                        self.state['historical_klines'] = pd.concat(
                            [hist_klines, new_row_df])
                    except Exception as concat_err:
                        logger.error(
                            f"Kline concat error: {concat_err}. Resetting hist.", exc_info=False)
                        self.state['historical_klines'] = new_row_df
                # Trimming
                max_hist = get_config_value(
                    self.config, ('analysis', 'max_historical_candles'), 500)
                if len(self.state['historical_klines']) > max_hist:
                    self.state['historical_klines'] = self.state['historical_klines'].iloc[-max_hist:]
                return True
            except StopIteration:
                logger.info("End of sim data.")
                self.running = False
                return False
            except Exception as e:
                logger.error(f"Sim step error: {e}", exc_info=True)
                self.running = False
                return False
        else:  # Live Mode
            logger.debug("Fetching live klines...")
            try:
                limit = get_config_value(
                    self.config, ('trading', 'kline_limit'), 200)
                df = self.connector.fetch_prepared_klines(
                    self.symbol, self.kline_interval, limit=limit)
            except Exception as e:
                logger.error(f"Live kline fetch error: {e}", exc_info=True)
                return False
            if df is None or df.empty:
                logger.warning("Live kline fetch empty.")
                return False
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            if any(col not in df.columns for col in required_cols):
                logger.error(f"Live data missing cols.")
                return False
            self.state['historical_klines'] = df
            self.state['current_kline'] = df.iloc[-1].to_dict()
            self.state['last_processed_timestamp'] = df.index[-1]
            logger.debug(
                f"Fetched {len(df)} live klines. Latest: {self.state['last_processed_timestamp']}")
            return True
    # END OF METHOD: src/main_trader.py -> _update_market_data

    # START OF METHOD: src/main_trader.py -> _calculate_analysis (Unchanged)
    def _calculate_analysis(self):
        if 'historical_klines' not in self.state or not isinstance(self.state['historical_klines'], pd.DataFrame) or self.state['historical_klines'].empty:
            return False
        klines_df = self.state['historical_klines']
        min_candles = get_config_value(
            self.config, ('analysis', 'min_candles_for_analysis'), 100)
        if len(klines_df) < min_candles:
            logger.warning(
                f"Insufficient hist data ({len(klines_df)}<{min_candles}).")
            return False
        logger.debug(f"Calculating analysis on {len(klines_df)} klines...")
        try:
            klines_df_analysis = klines_df.copy()
            if not isinstance(klines_df_analysis.index, pd.DatetimeIndex):
                klines_df_analysis.index = pd.to_datetime(
                    klines_df_analysis.index)
            rename_map = {c: c.capitalize() for c in klines_df_analysis.columns if c in [
                'open', 'high', 'low', 'close', 'volume']}
            if rename_map:
                klines_df_analysis.rename(columns=rename_map, inplace=True)
            self.state['indicators'] = calculate_indicators(
                klines_df_analysis, self.config)
            if self.state['indicators'] is None or not isinstance(self.state['indicators'], pd.DataFrame) or self.state['indicators'].empty:
                raise ValueError("Indicator calc failed.")
            logger.debug(
                f"Indicators calculated: {list(self.state['indicators'].columns)}")
            self.state['sr_zones'] = calculate_dynamic_zones(
                klines_df_analysis, self.config)
            logger.debug(
                f"S/R zones calculated: {len(self.state.get('sr_zones', []))} zones.")
            indicators_data = self.state.get('indicators', pd.DataFrame())
            sr_zones_data = self.state.get('sr_zones', [])
            self.state['confidence_score'] = calculate_confidence_v1(
                indicators_data, sr_zones_data, self.config)
            if not isinstance(self.state['confidence_score'], (float, Decimal)):
                logger.warning(
                    f"Confidence non-numeric: {self.state['confidence_score']}")
                self.state['confidence_score'] = Decimal('0.5')
            logger.debug(
                f"Confidence score: {self.state.get('confidence_score', Decimal('0.5')):.4f}")
            return True
        except Exception as e:
            logger.error(f"Analysis error: {e}", exc_info=True)
            self.state['indicators'] = None
            self.state['sr_zones'] = None
            self.state['confidence_score'] = None
            return False
    # END OF METHOD: src/main_trader.py -> _calculate_analysis

    # START OF METHOD: src/main_trader.py -> _update_balances (Unchanged)
    def _update_balances(self):
        if self.simulation_mode:
            base_bal = to_decimal(self.state.get('balance_base', '0'))
            quote_bal = to_decimal(self.state.get('balance_quote', '0'))
            logger.debug(
                f"Sim Balances: Base={base_bal:.8f} {self.base_asset}, Quote={quote_bal:.2f} {self.quote_asset}")
            return True
        else:
            logger.debug(f"Fetching live balances...")
            try:
                balances = self.connector.get_balances()
                if balances is None:
                    logger.error("Failed fetch live balances.")
                    return False
                self.state['balance_base'] = to_decimal(
                    balances.get(self.base_asset, '0'))
                self.state['balance_quote'] = to_decimal(
                    balances.get(self.quote_asset, '0'))
                logger.info(
                    f"Live Balances: Base={self.state['balance_base']:.8f}, Quote={self.state['balance_quote']:.2f}")
                return True
            except Exception as e:
                logger.error(f"Live balance fetch error: {e}", exc_info=True)
                return False
    # END OF METHOD: src/main_trader.py -> _update_balances

    # START OF METHOD: src/main_trader.py -> _process_fills (Unchanged - state updated directly)
    def _process_fills(self, fills: Dict):
        grid_fills = fills.get('grid_fills', [])
        tp_fill = fills.get('tp_fill', None)
        if not grid_fills and not tp_fill:
            return
        logger.info(
            f"Processing Fills - Grid: {len(grid_fills)}, TP: {'Yes' if tp_fill else 'No'}")
        pos_size = to_decimal(self.state.get('position_size', '0'))
        entry_px = to_decimal(self.state.get('position_entry_price', '0'))
        initial_entry_px = entry_px  # Store entry before modification for TP P/L
        for fill in grid_fills:
            try:
                qty_str = fill.get('executedQty') or fill.get('origQty')
                qty = to_decimal(qty_str)
                cumm_quote_str = fill.get('cummulativeQuoteQty')
                price_str = fill.get('price')
                if cumm_quote_str is not None and qty is not None and qty > 0:
                    px = to_decimal(cumm_quote_str) / qty
                elif price_str is not None:
                    px = to_decimal(price_str)
                else:
                    continue
                if qty is None or px is None or qty <= 0 or px <= 0:
                    continue
                cost = px * qty
                logger.info(
                    f"Grid Fill: +{qty:.8f} {self.base_asset} @ {px:.4f} (Cost: {cost:.4f})")
                current_value = pos_size * entry_px
                new_total_value = current_value + cost
                new_total_size = pos_size + qty
                new_entry_px = new_total_value / \
                    new_total_size if new_total_size > Decimal(
                        '0') else Decimal('0')
                pos_size = new_total_size
                entry_px = new_entry_px
                self.state['balance_quote'] = to_decimal(
                    self.state.get('balance_quote', '0')) - cost
                self.state['balance_base'] = to_decimal(
                    self.state.get('balance_base', '0')) + qty
                # --- Update main state directly ---
                self.state['position_size'] = pos_size
                self.state['position_entry_price'] = entry_px
                # ---------------------------------
                self._write_report_row(event_type="GRID_ENTRY", quantity=qty, price=px,
                                       cost_or_proceeds=-cost, notes=f"Grid Fill (Order {fill.get('orderId', 'N/A')})")
            except Exception as e:
                order_id = fill.get('orderId', 'N/A')
                logger.error(
                    f"Error processing grid fill {order_id}: {e}. Data: {fill}", exc_info=True)
        if tp_fill:
            try:
                qty_str = tp_fill.get('executedQty') or tp_fill.get('origQty')
                qty = to_decimal(qty_str)
                cumm_quote_str = tp_fill.get('cummulativeQuoteQty')
                price_str = tp_fill.get('price')
                if cumm_quote_str is not None and qty is not None and qty > 0:
                    px = to_decimal(cumm_quote_str) / qty
                elif price_str is not None:
                    px = to_decimal(price_str)
                else:
                    px = None
                if qty is not None and px is not None and qty > 0 and px > 0:
                    proceeds = px * qty
                    logger.info(
                        f"TP Fill: -{qty:.8f} {self.base_asset} @ {px:.4f} (Proceeds: {proceeds:.4f})")
                    realized_pnl = None
                    # Use the entry price *before* it might have been reset by grid fills in the same batch
                    if initial_entry_px > 0:
                        realized_pnl = (px - initial_entry_px) * qty
                        logger.info(
                            f"Realized P/L from TP: {realized_pnl:.4f}")
                    else:
                        logger.warning("Could not calc P/L for TP fill.")
                    pos_size = Decimal('0')
                    entry_px = Decimal('0')
                    self.state['balance_quote'] = to_decimal(
                        self.state.get('balance_quote', '0')) + proceeds
                    self.state['balance_base'] = max(Decimal('0'), to_decimal(
                        self.state.get('balance_base', '0')) - qty)
                    # --- Update main state directly ---
                    self.state['position_size'] = pos_size
                    self.state['position_entry_price'] = entry_px
                    # ---------------------------------
                    self._write_report_row(event_type="TP_EXIT", quantity=-qty, price=px, cost_or_proceeds=proceeds,
                                           pnl=realized_pnl, notes=f"TP Fill (Order {tp_fill.get('orderId', 'N/A')})")
                else:
                    logger.warning(
                        f"Skipping invalid TP fill: Qty={qty}, Px={px}.")
            except Exception as e:
                order_id = tp_fill.get('orderId', 'N/A')
                logger.error(
                    f"Error processing TP fill {order_id}: {e}. Data: {tp_fill}", exc_info=True)
        logger.info(
            f"State after fills batch: Pos={self.state['position_size']:.8f}, Entry={self.state['position_entry_price']:.4f}, BalQ={self.state['balance_quote']:.4f}, BalB={self.state['balance_base']:.8f}")
    # END OF METHOD: src/main_trader.py -> _process_fills

    # START OF METHOD: src/main_trader.py -> _plan_trades (Unchanged)
    def _plan_trades(self):
        logger.debug("Planning trades for the next cycle...")
        current_kline_data = self.state.get('current_kline', {})
        curr_px = current_kline_data.get('close')
        conf = self.state.get('confidence_score')
        pos_size = to_decimal(self.state.get('position_size', '0'))
        entry_px = to_decimal(self.state.get('position_entry_price', '0'))
        available_quote_balance = to_decimal(
            self.state.get('balance_quote', '0'))
        indicators_df = self.state.get('indicators')
        sr_zones = self.state.get('sr_zones', [])
        self.state['planned_grid'] = []
        self.state['planned_tp_price'] = None
        if curr_px is None or conf is None:
            logger.warning("Skipping plan: Missing price/confidence.")
            return

        # Grid Planning (Entry Conditions)
        entry_conf = to_decimal(get_config_value(
            self.config, ('trading', 'entry_confidence_threshold'), 0.6))
        entry_rsi_thresh = to_decimal(get_config_value(
            self.config, ('trading', 'entry_rsi_threshold'), 75.0))
        use_trend_filter = get_config_value(
            self.config, ('trading', 'use_trend_filter'), True)
        use_rsi_filter = get_config_value(
            self.config, ('trading', 'use_rsi_filter'), True)
        sma_f_p = get_config_value(
            self.config, ('strategies', 'geometric_grid', 'sma_fast_period'), 50)
        sma_s_p = get_config_value(
            self.config, ('strategies', 'geometric_grid', 'sma_slow_period'), 200)
        rsi_p = get_config_value(
            self.config, ('strategies', 'geometric_grid', 'rsi_period'), 14)
        latest_indicators = indicators_df.iloc[-1] if isinstance(
            indicators_df, pd.DataFrame) and not indicators_df.empty else None
        should_plan_grid = False
        reason_skip = ""
        log_prefix = "Entry Check:"
        conf_ok = conf >= entry_conf
        logger.debug(
            f"{log_prefix} Conf={conf:.2f}, Threshold={entry_conf:.2f}, OK={conf_ok}")
        trend_ok = True
        if use_trend_filter:
            if latest_indicators is not None:
                sma_fast_val = latest_indicators.get(f'SMA_{sma_f_p}')
                sma_slow_val = latest_indicators.get(f'SMA_{sma_s_p}')
                if sma_fast_val is not None and sma_slow_val is not None:
                    trend_ok = to_decimal(
                        sma_fast_val) > to_decimal(sma_slow_val)
                    logger.debug(
                        f"{log_prefix} Trend Filter (SMA_{sma_f_p}={sma_fast_val:.2f}, SMA_{sma_s_p}={sma_slow_val:.2f}), OK={trend_ok}")
                else:
                    trend_ok = False
                    reason_skip += "[Trend Vals Missing]"
                    logger.debug(
                        f"{log_prefix} Trend Filter enabled but SMA missing. Trend OK=False")
            else:
                trend_ok = False
                reason_skip += "[Indicators Missing]"
                logger.debug(
                    f"{log_prefix} Trend Filter enabled but indicators missing. Trend OK=False")
        else:
            logger.debug(f"{log_prefix} Trend Filter disabled.")
        rsi_ok = True
        if use_rsi_filter:
            if latest_indicators is not None:
                rsi_val = latest_indicators.get(f'RSI_{rsi_p}')
                if rsi_val is not None:
                    rsi_ok = to_decimal(rsi_val) < entry_rsi_thresh
                    logger.debug(
                        f"{log_prefix} RSI Filter (RSI_{rsi_p}={rsi_val:.2f}, Threshold={entry_rsi_thresh:.2f}), OK={rsi_ok}")
                else:
                    rsi_ok = False
                    reason_skip += "[RSI Val Missing]"
                    logger.debug(
                        f"{log_prefix} RSI Filter enabled but RSI missing. RSI OK=False")
            else:
                rsi_ok = False
                if "[Indicators Missing]" not in reason_skip:
                    reason_skip += "[Indicators Missing]"
                    logger.debug(
                        f"{log_prefix} RSI Filter enabled but indicators missing. RSI OK=False")
        else:
            logger.debug(f"{log_prefix} RSI Filter disabled.")
        if conf_ok and trend_ok and rsi_ok:
            should_plan_grid = True
            logger.info(f"*** ENTRY CONDITIONS MET *** -> Planning Grid")
        else:
            if not conf_ok:
                reason_skip += f"[Conf Fail ({conf:.2f}<{entry_conf:.2f})]"
            if not trend_ok and "[Trend" not in reason_skip and "[Indicators Missing]" not in reason_skip:
                reason_skip += "[Trend Fail]"
            if not rsi_ok and "[RSI" not in reason_skip and "[Indicators Missing]" not in reason_skip:
                reason_skip += "[RSI Fail]"
            logger.debug(
                f"--- Entry Conditions NOT MET --- Reason(s): {reason_skip} -> Skipping Grid Plan")

        # Call Grid Planning Function
        if should_plan_grid:
            try:
                current_atr = None
                if latest_indicators is not None:
                    atr_period = get_config_value(
                        self.config, ('strategies', 'geometric_grid', 'atr_period'), 14)
                    atr_col_name = f'ATR_{atr_period}'
                    current_atr = latest_indicators.get(atr_col_name)
                    current_atr = to_decimal(current_atr)
                exchange_info = self.connector.get_exchange_info_cached()
                if not exchange_info:
                    raise ValueError(
                        "Exchange info not available for grid plan.")
                logger.info(
                    f"Calling plan_buy_grid_v1. Avail Quote: {available_quote_balance:.4f}")
                # Planned grid is stored in self.state directly now
                self.state['planned_grid'] = plan_buy_grid_v1(symbol=self.symbol, current_price=curr_px, current_atr=current_atr,
                                                              available_quote_balance=available_quote_balance, exchange_info=exchange_info, config_dict=self.config, confidence_score=conf)
                if self.state['planned_grid']:
                    logger.info(
                        f"Planned Grid: {len(self.state['planned_grid'])} levels")
            except Exception as e:
                logger.error(f"Error during grid plan: {e}", exc_info=True)
                self.state['planned_grid'] = []  # Ensure cleared on error

        # Take Profit Planning
        if pos_size > Decimal('0'):
            logger.debug("Planning Take Profit...")
            try:
                current_atr_for_tp = None
                if latest_indicators is not None:
                    tp_atr_period = get_config_value(
                        self.config, ('strategies', 'profit_taking', 'atr_period'), 14)
                    atr_col_name = f'ATR_{tp_atr_period}'
                    current_atr_for_tp = latest_indicators.get(atr_col_name)
                    current_atr_for_tp = to_decimal(current_atr_for_tp)
                exchange_info_for_tp = self.connector.get_exchange_info_cached()
                if not exchange_info_for_tp:
                    logger.error("Cannot plan TP: Exchange info missing.")
                    self.state['planned_tp_price'] = None
                else:
                    # Planned TP is stored in self.state directly now
                    self.state['planned_tp_price'] = calculate_dynamic_tp_price(
                        entry_price=entry_px, current_atr=current_atr_for_tp, config=self.config, exchange_info=exchange_info_for_tp, symbol=self.symbol, confidence_score=conf)
                    if self.state['planned_tp_price'] is not None:
                        logger.info(
                            f"Planned TP Price: {self.state['planned_tp_price']:.4f}")
                    else:
                        logger.info("TP calc resulted in no TP level.")
            except Exception as e:
                logger.error(f"Error during TP plan: {e}", exc_info=True)
                # Ensure cleared on error
                self.state['planned_tp_price'] = None
        else:
            logger.debug("No active position, skipping TP plan.")
    # END OF METHOD: src/main_trader.py -> _plan_trades

    # START OF METHOD: src/main_trader.py -> _execute_trades (Updated OM calls)
    def _execute_trades(self):
        logger.debug("Executing planned trades...")
        planned_grid = self.state.get('planned_grid', [])
        planned_tp = self.state.get('planned_tp_price')
        current_pos_size = to_decimal(self.state.get('position_size', '0'))

        # --- Execute Grid Orders ---
        try:
            # Pass self.state to the OrderManager method
            reconciliation_result = self.order_manager.reconcile_and_place_grid(
                self.state, planned_grid)
            # OrderManager modifies self.state['active_grid_orders'] directly

            placed = len(reconciliation_result.get('placed', []))
            cancelled = len(reconciliation_result.get('cancelled', []))
            failed = len(reconciliation_result.get('failed', []))
            unchanged = len(reconciliation_result.get('unchanged', []))
            if placed > 0 or cancelled > 0 or failed > 0:
                logger.info(
                    f"Grid Reconcile: Placed={placed}, Cancelled={cancelled}, Failed={failed}, Unchanged={unchanged}")
            else:
                logger.debug("Grid Reconcile: No changes.")
        except Exception as e:
            logger.error(
                f"Error during grid reconcile/place: {e}", exc_info=True)

        # --- Execute Take Profit Order ---
        try:
            if current_pos_size > Decimal('0'):
                if planned_tp is not None:
                    logger.debug(
                        f"Attempt place/update TP @ {planned_tp:.4f} for size {current_pos_size:.8f}")
                    # Pass self.state to the OrderManager method
                    tp_result = self.order_manager.place_or_update_tp_order(
                        self.state, planned_tp, current_pos_size)
                    # OrderManager modifies self.state['active_tp_order'] directly
                else:
                    logger.info("No TP planned. Ensuring existing cancelled.")
                    # Pass self.state to the OrderManager method
                    self.order_manager.place_or_update_tp_order(
                        self.state, None, Decimal('0'))
            else:
                logger.debug(
                    "No active position. Ensuring existing TP cancelled.")
                # Pass self.state to the OrderManager method
                self.order_manager.place_or_update_tp_order(
                    self.state, None, Decimal('0'))
        except Exception as e:
            logger.error(f"Error during TP place/update: {e}", exc_info=True)
    # END OF METHOD: src/main_trader.py -> _execute_trades

    # START OF METHOD: src/main_trader.py -> _apply_risk_controls (Updated OM call)
    def _apply_risk_controls(self):
        logger.debug("Applying risk controls...")
        pos_size = to_decimal(self.state.get('position_size', '0'))
        ts_entry = self.state.get('position_entry_timestamp')
        px_entry = to_decimal(self.state.get('position_entry_price', '0'))
        klines_hist = self.state.get('historical_klines')
        conf = self.state.get('confidence_score')
        if pos_size <= Decimal('0'):
            return
        if not ts_entry or px_entry <= Decimal('0') or klines_hist is None or klines_hist.empty:
            return
        try:
            ts_entry_ts = None
            if isinstance(ts_entry, str):
                try:
                    ts_entry_ts = pd.Timestamp(ts_entry)
                    ts_entry_ts = ts_entry_ts.tz_localize(
                        'UTC') if ts_entry_ts.tzinfo is None else ts_entry_ts
                except ValueError:
                    return
            elif isinstance(ts_entry, pd.Timestamp):
                ts_entry_ts = ts_entry
                ts_entry_ts = ts_entry_ts.tz_localize(
                    'UTC') if ts_entry_ts.tzinfo is None else ts_entry_ts
            else:
                return

            # Time Stop Check
            position_dict_for_ts = {
                'entry_time': ts_entry_ts, 'entry_price': px_entry}
            time_stop_triggered = check_time_stop(position=position_dict_for_ts, current_klines=klines_hist,
                                                  config=self.config, confidence_score=conf if isinstance(conf, (float, Decimal)) else None)

            if time_stop_triggered:
                logger.info(
                    f"Executing market sell {pos_size:.8f} due to time stop...")
                entry_price_for_pnl = px_entry  # Store before state might be modified
                # Pass self.state to the OrderManager method
                sell_result = self.order_manager.execute_market_sell(
                    self.state, pos_size, reason="time_stop")
                # OrderManager modifies self.state balance, position, orders directly

                if sell_result:
                    logger.info(
                        f"Time stop market sell successful. Response: {sell_result}")
                    # --- Reporting ---
                    if self.simulation_mode:
                        sell_qty = to_decimal(sell_result.get('executedQty'))
                        cumm_quote = to_decimal(
                            sell_result.get('cummulativeQuoteQty'))
                        if cumm_quote is not None and sell_qty is not None and sell_qty > 0:
                            effective_sell_price = cumm_quote / sell_qty
                        else:
                            # Fallback if fill info incomplete (less likely with market sell)
                            kline_close = to_decimal(self.state.get(
                                'current_kline', {}).get('close'))
                            effective_sell_price = kline_close if kline_close else Decimal(
                                '0')

                        # Get cost/proceeds directly from fill if possible
                        sell_proceeds = cumm_quote if cumm_quote is not None else effective_sell_price * sell_qty
                        realized_pnl = None
                        if entry_price_for_pnl > 0 and effective_sell_price > 0 and sell_qty is not None:
                            realized_pnl = (
                                effective_sell_price - entry_price_for_pnl) * sell_qty
                        else:
                            logger.warning(
                                "Could not calc P/L for TS Exit report.")

                        self._write_report_row(
                            event_type="TS_EXIT",
                            quantity=-sell_qty if sell_qty else None,
                            price=effective_sell_price,
                            cost_or_proceeds=sell_proceeds if sell_proceeds else None,
                            pnl=realized_pnl,
                            notes=f"Time Stop Triggered (Order {sell_result.get('orderId', 'N/A')})"
                        )
                    # --- End Reporting ---
                    # Position state (size, entry price, timestamp) already updated by execute_market_sell
                    # Balance state already updated by execute_market_sell
                    # Active orders already updated by execute_market_sell (cancels TP)

                    # No need for separate state updates here
                    logger.info(
                        "Position and balance state updated by market sell execution.")
                    # Save state immediately after critical risk action (handled in run loop)
                else:
                    logger.error("Time stop market sell FAILED.")
        except Exception as e:
            logger.error(f"Error during risk control: {e}", exc_info=True)
    # END OF METHOD: src/main_trader.py -> _apply_risk_controls

    # START OF METHOD: src/main_trader.py -> _check_orders_and_update_state (Updated OM call)
    def _check_orders_and_update_state(self):
        logger.debug("Checking status of active orders...")
        current_kline_data = self.state.get('current_kline', {})
        px_curr = current_kline_data.get('close')
        price_for_check = px_curr if self.simulation_mode else None
        if self.simulation_mode and price_for_check is None:
            logger.warning("Cannot check sim orders: Current price missing.")
            return
        try:
            # Pass self.state to the OrderManager method
            fill_results = self.order_manager.check_orders(
                self.state, price_for_check)
            # OrderManager modifies self.state['active_grid_orders'] / ['active_tp_order'] directly

            if fill_results.get('grid_fills') or fill_results.get('tp_fill'):
                logger.info("Fills detected, processing state updates...")
                # _process_fills updates position size, entry price, balances directly in self.state
                # It also handles writing the GRID_ENTRY and TP_EXIT report rows
                self._process_fills(fill_results)

                # --- Update Entry Timestamp (logic remains the same) ---
                pos_size_after_fill = to_decimal(
                    self.state.get('position_size', '0'))
                ts_entry_after_fill = self.state.get(
                    'position_entry_timestamp')
                ts_last_kline = self.state.get('last_processed_timestamp')

                if fill_results.get('grid_fills') and pos_size_after_fill > Decimal('0') and ts_entry_after_fill is None:
                    if ts_last_kline:
                        self.state['position_entry_timestamp'] = ts_last_kline
                        logger.info(
                            f"Position opened. Entry TS set: {ts_last_kline}")
                    else:
                        logger.error(
                            "Cannot set entry TS: Last kline TS missing!")
                elif fill_results.get('tp_fill') and pos_size_after_fill == Decimal('0'):
                    if ts_entry_after_fill is not None:
                        self.state['position_entry_timestamp'] = None
                        logger.info("Position closed by TP. Entry TS cleared.")
                # --- End Timestamp Logic ---

                if not self.simulation_mode:
                    self._update_balances()  # Re-fetch live balance after fills

                # Saving state is handled in the run loop after this method returns
                logger.debug("State updated after processing fills.")
            # else: logger.debug("No new fills detected.") # Can be verbose
        except Exception as e:
            logger.error(
                f"Error during order check/fill process: {e}", exc_info=True)
    # END OF METHOD: src/main_trader.py -> _check_orders_and_update_state

    # START OF METHOD: src/main_trader.py -> _shutdown (Updated OM call)
    def _shutdown(self, signum=None, frame=None):
        if self.is_shutting_down:
            logger.info("Shutdown already in progress.")
            return
        self.is_shutting_down = True
        self.running = False
        signal_name = signal.Signals(signum).name if signum is not None and isinstance(
            signum, int) else 'programmatic'
        logger.warning(f"Initiating shutdown (Trigger: {signal_name})...")
        cancel_on_exit = get_config_value(
            self.config, ('trading', 'cancel_orders_on_exit'), False)
        if cancel_on_exit:
            if hasattr(self, 'order_manager') and self.order_manager:
                logger.info("Attempting cancel open orders...")
                try:
                    current_state = self.state  # Use current state dictionary
                    active_grid = current_state.get('active_grid_orders', [])
                    active_tp = current_state.get('active_tp_order')
                    if not isinstance(active_grid, list):
                        active_grid = []
                    orders_to_cancel = list(active_grid)
                    if active_tp is not None:
                        if isinstance(active_tp, dict):
                            orders_to_cancel.append(active_tp)
                        else:
                            logger.warning(
                                f"State TP order not dict: {type(active_tp)}. Skip cancel.")
                    logger.info(
                        f"Found {len(orders_to_cancel)} potential orders to cancel.")
                    cancelled_count, failed_count = 0, 0
                    for order in orders_to_cancel:
                        if not isinstance(order, dict):
                            logger.warning(
                                f"Non-dict item in cancel list: {order}. Skip.")
                            failed_count += 1
                            continue
                        client_order_id = order.get('clientOrderId')
                        order_id = order.get('orderId')
                        side = order.get('side')
                        label = "TP" if side == 'SELL' else "Grid"
                        if order_id or client_order_id:
                            logger.debug(
                                f"Requesting cancel for {label}: ID={order_id}, ClientID={client_order_id}")
                            try:
                                # Pass self.state to the OrderManager method
                                success = self.order_manager.cancel_order(
                                    self.state, client_order_id, order_id, f"{label} (Shutdown)")
                                # OrderManager modifies self.state['active_grid_orders'] / ['active_tp_order'] directly
                                if success:
                                    cancelled_count += 1
                                else:
                                    failed_count += 1
                            except Exception as cancel_err:
                                logger.error(
                                    f"Error cancelling order {order_id or client_order_id}: {cancel_err}", exc_info=False)
                                failed_count += 1
                        else:
                            logger.warning(
                                f"Cannot cancel, missing IDs: {order}")
                            failed_count += 1
                    logger.info(
                        f"Order cancel requests: Attempt={len(orders_to_cancel)}, Success={cancelled_count}, Fail/Skip={failed_count}")
                except Exception as e:
                    logger.error(
                        f"Error during order cancel process: {e}", exc_info=True)
            else:
                logger.warning(
                    "Order manager unavailable, cannot cancel orders.")
        else:
            logger.info("Skipping order cancellation (disabled).")

        # --- Save Final State ---
        if hasattr(self, 'state_manager') and self.state_manager and hasattr(self, 'state'):
            final_state = getattr(self, 'state', None)
            if isinstance(final_state, dict):
                logger.info("Saving final application state...")
                try:
                    # Save the final state dictionary
                    self.state_manager.save_state(final_state)
                    logger.info("Final state saved.")
                except Exception as e:
                    logger.error(
                        f"Failed save final state: {e}", exc_info=True)
            else:
                logger.warning(
                    "Cannot save final state: state attr missing/not dict.")
        else:
            logger.warning(
                "State manager/state unavailable, cannot save final state.")

        # --- Reporting ---
        if self.simulation_mode:
            logger.info("Writing final balance to sim report...")
            self._write_report_row(
                event_type="FINAL_BALANCE",
                notes=f"Final Balance: {self.state.get('balance_quote', 'N/A')}"
            )
            self._close_report_file()  # Close report file

        logger.warning("Shutdown sequence complete. Exiting.")
        print("\nGeminiTrader stopped.")
        sys.exit(0)
    # END OF METHOD: src/main_trader.py -> _shutdown

    # START OF METHOD: src/main_trader.py -> run (Updated state saving)
    def run(self):
        logger.info("Starting main trading loop...")
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
        try:
            self._initialize()
            if not self.running:
                logger.error("Exiting run: Initialization failed.")
                return
            loop_interval_seconds = get_config_value(
                self.config, ('trading', 'loop_sleep_time'), 60)
            sim_steps = len(
                self.sim_data) if self.simulation_mode and self.sim_data is not None else 0
            pbar = tqdm(total=sim_steps, desc="Simulating", unit=" steps",
                        disable=not self.simulation_mode, leave=True)
            if self.simulation_mode:
                logger.info(
                    f"Running SIMULATION mode. Processing {sim_steps} data points.")
            else:
                logger.info(
                    f"Running LIVE mode. Loop interval: {loop_interval_seconds}s.")

            # Main Trading Loop
            while self.running:
                cycle_start_time = time.monotonic()
                logger.debug(
                    f"------ New Cycle: {pd.Timestamp.now(tz='UTC')} ------")

                # 1. Update Market Data
                market_data_ok = self._update_market_data()
                if not market_data_ok:
                    if not self.running:
                        break  # Sim ended or critical error
                    logger.warning(
                        "Failed update market data. Skipping cycle.")
                    if not self.simulation_mode:
                        time.sleep(loop_interval_seconds)
                    continue

                # 2. Update Sim Progress Bar
                if self.simulation_mode:
                    pbar.update(1)
                    conf_score = self.state.get('confidence_score')
                    conf_str = f"{conf_score:.2f}" if isinstance(
                        conf_score, (float, Decimal)) else "N/A"
                    pos_size_state = to_decimal(
                        self.state.get('position_size', '0'))
                    pos_str = f"{pos_size_state:.4f}" if pos_size_state is not None else "N/A"
                    grid_list = self.state.get('active_grid_orders', [])
                    grid_count = len(grid_list) if isinstance(
                        grid_list, list) else "N/A"
                    tp_order = self.state.get('active_tp_order')
                    tp_str = "Y" if isinstance(tp_order, dict) else "N"
                    bal_q_str = f"{to_decimal(self.state.get('balance_quote', '0')):.2f}"
                    pfix = {"Conf": conf_str, "Pos": pos_str,
                            "Grid": grid_count, "TP": tp_str, "Bal": bal_q_str}
                    pbar.set_postfix(pfix, refresh=False)

                # 3. Calculate Analysis
                analysis_ok = self._calculate_analysis()

                # 4. Check Orders & Process Fills
                # Modifies self.state via _process_fills if fills occur
                self._check_orders_and_update_state()
                # Save state after potential updates from fills
                if self.running and self.state_manager:
                    try:
                        self.state_manager.save_state(self.state)
                    except Exception as save_err:
                        logger.error(
                            f"Save Error (after check_orders): {save_err}", exc_info=False)
                if not self.running:
                    break

                # 5. Apply Risk Controls
                # Modifies self.state via OM.execute_market_sell if stop triggered
                self._apply_risk_controls()
                # Save state after potential updates from risk controls
                if self.running and self.state_manager:
                    try:
                        self.state_manager.save_state(self.state)
                    except Exception as save_err:
                        logger.error(
                            f"Save Error (after risk_controls): {save_err}", exc_info=False)
                if not self.running:
                    break

                # 6. Plan Trades
                if analysis_ok:
                    self._plan_trades()  # Stores plans in self.state
                else:
                    self.state['planned_grid'] = []
                    self.state['planned_tp_price'] = None
                if not self.running:
                    break

                # 7. Execute Trades
                # Modifies self.state's active orders via OM methods
                self._execute_trades()
                # Save state after potential order placement/cancellation
                if self.running and self.state_manager:
                    try:
                        self.state_manager.save_state(self.state)
                    except Exception as save_err:
                        logger.error(
                            f"Save Error (after execute_trades): {save_err}", exc_info=False)
                if not self.running:
                    break

                # --- Cycle End ---
                cycle_end_time = time.monotonic()
                cycle_duration = cycle_end_time - cycle_start_time
                logger.debug(
                    f"Trading cycle completed in {cycle_duration:.2f} seconds.")

                sleep_time = max(0, loop_interval_seconds - cycle_duration)
                if self.running and sleep_time > 0 and not self.simulation_mode:
                    time.sleep(sleep_time)
                # elif ... # Cycle overrun log

            # --- Loop End ---
            if self.simulation_mode:
                pbar.close()
                logger.info("Simulation finished.")
            else:
                logger.info("Live trading loop terminated.")

        except KeyboardInterrupt:
            logger.warning("KeyboardInterrupt. Shutdown...")
            self._shutdown(signal.SIGINT)
        except ConnectionError as ce:
            logger.critical(
                f"CRITICAL Connection Error: {ce}. Shutdown.", exc_info=True)
            self._shutdown(signal.SIGABRT)
        except Exception as e:
            logger.critical(f"CRITICAL UNHANDLED ERROR: {e}", exc_info=True)
            self._shutdown(signal.SIGABRT)
        finally:
            if not self.is_shutting_down:
                logger.warning("Main loop exited unexpectedly. Shutdown.")
                self._shutdown()
    # END OF METHOD: src/main_trader.py -> run


if __name__ == "__main__":
    logger.info("Starting GeminiTrader application...")
    bot = GeminiTrader()
    if bot.running:
        logger.info("Initialization successful. Starting run loop.")
        bot.run()
    else:
        logger.error("Initialization failed. App did not run.")
        print("Exiting: Init failed.")

# END OF FILE: src/main_trader.py
