# START OF FILE: src/main_trader.py

import logging
import time
from pathlib import Path
import pandas as pd
from decimal import Decimal
import schedule
from typing import Optional, Dict, Any, List, Set
import random
from tqdm import tqdm
import sys  # Keep sys import

# --- Add project root ---
import os
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
# --- End ---

# Project Imports
try:
    from config.settings import load_config, get_config_value
    from src.utils.logging_setup import setup_logging
    from src.utils.formatting import to_decimal, apply_filter_rules_to_qty, get_symbol_info_from_exchange_info
    from src.connectors.binance_us import BinanceUSConnector
    from src.data.kline_fetcher import fetch_and_prepare_klines
    from src.analysis.indicators import (
        calculate_atr, calculate_sma, calculate_rsi, calculate_macd, calculate_pivot_points,
        ATR_PERIOD, SMA_SHORT_PERIOD, SMA_LONG_PERIOD, RSI_PERIOD,
        MACD_FAST_PERIOD, MACD_SLOW_PERIOD, MACD_SIGNAL_PERIOD
    )
    from src.strategies.profit_taking import calculate_dynamic_tp_price
    from src.analysis.support_resistance import calculate_dynamic_zones, DEFAULT_PIVOT_WINDOW, DEFAULT_ZONE_PROXIMITY_FACTOR, DEFAULT_MIN_ZONE_TOUCHES
    from src.analysis.confidence import calculate_confidence_v1
    from src.strategies.risk_controls import check_time_stop
    from src.strategies.geometric_grid import plan_buy_grid_v1
    from src.core.order_manager import OrderManager
    from src.core.state_manager import StateManager  # Added Import
except ImportError as e:
    logging.basicConfig(level=logging.ERROR)
    logging.critical(
        f"FATAL ERROR: Module import failed. Error: {e}", exc_info=True)
    sys.exit(1)

logger = logging.getLogger(__name__)


class GeminiTrader:
    SIMULATION_MODE = True
    SIM_PLACEMENT_SUCCESS_RATE = 0.99

    def __init__(self):
        self.config = {}
        self.connector: Optional[BinanceUSConnector] = None
        self.order_manager: Optional[OrderManager] = None
        self.state_manager: Optional[StateManager] = None
        self.state = {
            "klines": pd.DataFrame(), "indicators": {}, "pivot_levels": None,
            "last_data_update_time": None, "last_pivot_calc_time": None,
            "symbol_info": None, "position": None, "sr_zones": [],
            "confidence_score": None, "account_balance": {},
            "active_grid_orders": [], "active_tp_order": None,
            "simulation_data": None, "simulation_index": 0,
            "simulation_end_index": 0, "simulation_start_time": None,
            "simulation_mode": self.SIMULATION_MODE,
            "sim_placement_success_rate": self.SIM_PLACEMENT_SUCCESS_RATE,
            "sim_grid_fills": 0, "sim_tp_fills": 0, "sim_market_sells": 0,
            "sim_grid_place_fail": 0, "sim_tp_place_fail": 0,
            "sim_grid_cancel_fail": 0, "sim_tp_cancel_fail": 0,
            "main_loop_errors": 0, "main_loop_warnings": 0,
            "last_state_save_time": None,
        }
        self.is_running = False
        self._initialize()

    def _initialize(self):
        self.state["simulation_start_time"] = time.monotonic()
        print(
            f"Initializing GeminiTrader... (SIMULATION_MODE: {self.SIMULATION_MODE})")
        self.config = load_config()
        print("Config loaded.")
        if not self.config:
            print("FATAL: Config load failed.")
            sys.exit(1)
        try:
            log_level_str = get_config_value(
                self.config, ('logging', 'level'), 'INFO').upper()
            log_level = getattr(logging, log_level_str, logging.INFO)
            log_file_path = _project_root / \
                get_config_value(
                    self.config, ('logging', 'trader_log_path'), 'data/logs/trader.log')
            console_log_level_str = get_config_value(
                self.config, ('logging', 'console_level'), 'WARNING').upper()
            console_log_level = getattr(
                logging, console_log_level_str, logging.WARNING)
            error_log_path_str = get_config_value(
                self.config, ('logging', 'error_log_path'), 'data/logs/errors.log')
            setup_logging(log_level=log_level, log_file=log_file_path, error_log_file=error_log_path_str, max_bytes=get_config_value(self.config, ('logging', 'max_bytes'),
                          10485760), backup_count=get_config_value(self.config, ('logging', 'backup_count'), 5), console_logging=True, console_log_level=console_log_level)
            logger.info(
                f"Logging setup: File Level={log_level_str}, Console Level={console_log_level_str}, File={log_file_path}, Error File={error_log_path_str}")
        except Exception as e:
            print(f"Logging setup error: {e}. Exiting.")
            sys.exit(1)
        try:
            api_key = get_config_value(self.config, ('binance_us', 'api_key'))
            api_secret = get_config_value(
                self.config, ('binance_us', 'api_secret'))
            if not api_key or not api_secret or 'YOUR_ACTUAL' in str(api_key):
                logger.critical(
                    "FATAL: Binance API Key/Secret missing/invalid.")
                sys.exit(1)
            self.connector = BinanceUSConnector(
                api_key=api_key, api_secret=api_secret, config=self.config)
            if not self.connector.get_client():
                logger.critical("FATAL: Failed Binance client init.")
                sys.exit(1)
            logger.info("BinanceUS Connector initialized.")
            self.connector.get_exchange_info()
            if not self.connector.get_exchange_info_cached():
                logger.warning("Failed init pre-cache exchange info.")
        except Exception as e:
            logger.critical(
                f"FATAL: Connector init failed: {e}.", exc_info=True)
            sys.exit(1)

        state_file_rel_path = get_config_value(
            self.config, ('state_manager', 'filepath'), 'data/state/trader_state.json')
        state_file_abs_path = str(_project_root / state_file_rel_path)
        try:
            self.state_manager = StateManager(filepath=state_file_abs_path)
            logger.info(
                f"StateManager initialized (File: {state_file_abs_path}).")
        except Exception as e:
            logger.critical(
                f"FATAL: StateManager initialization failed: {e}", exc_info=True)
            sys.exit(1)

        loaded_state = self.state_manager.load_state()
        if loaded_state:
            logger.info("Attempting to restore state from file...")
            restorable_keys = ['position', 'active_grid_orders', 'active_tp_order', 'simulation_index', "sim_grid_fills", "sim_tp_fills", "sim_market_sells", "sim_grid_place_fail",
                               "sim_tp_place_fail", "sim_grid_cancel_fail", "sim_tp_cancel_fail", "main_loop_errors", "main_loop_warnings", "account_balance"]  # Added account balance
            keys_restored = 0
            for key in restorable_keys:
                if key in loaded_state:
                    self.state[key] = loaded_state[key]
                    keys_restored += 1
            logger.info(
                f"Restored {keys_restored} state keys from {state_file_abs_path}.")
            logger.debug(f"Restored Position: {self.state.get('position')}")
            logger.debug(
                f"Restored Grid Orders: {len(self.state.get('active_grid_orders', []))} count")
            logger.debug(
                f"Restored TP Order: {'Yes' if self.state.get('active_tp_order') else 'No'}")
            if self.SIMULATION_MODE:
                logger.debug(
                    f"Restored Sim Index: {self.state.get('simulation_index')}")
        else:
            logger.info(
                "No previous state file found or failed to load. Starting with fresh state.")

        try:
            self.order_manager = OrderManager(
                connector=self.connector, state=self.state, config=self.config)
            logger.info("OrderManager initialized.")
        except Exception as e:
            logger.critical(
                f"FATAL: OrderManager initialization failed: {e}", exc_info=True)
            sys.exit(1)

        if self.SIMULATION_MODE:
            sim_file_path_str = get_config_value(
                self.config, ('simulation', 'data_file'))
            if not sim_file_path_str:
                logger.critical(
                    "FATAL: Sim mode enabled but sim.data_file not set.")
                sys.exit(1)
            sim_file_path = _project_root / sim_file_path_str
            req_cols = get_config_value(self.config, ('simulation', 'required_columns'), [
                                        "Timestamp", "Open", "High", "Low", "Close", "Volume"])
            ts_col = get_config_value(
                self.config, ('simulation', 'timestamp_column'), "Timestamp")
            if not sim_file_path.exists():
                logger.critical(
                    f"FATAL: Simulation data file not found: {sim_file_path}")
                sys.exit(1)
            try:
                logger.info(
                    f"SIM MODE: Loading simulation data from: {sim_file_path}")
                df_sim = pd.read_csv(sim_file_path)
                logger.info(f"Loaded {len(df_sim)} rows from simulation file.")
                if not all(col in df_sim.columns for col in req_cols):
                    logger.critical(f"FATAL: Sim data missing columns.")
                    sys.exit(1)
                if ts_col not in df_sim.columns:
                    logger.critical(
                        f"FATAL: Timestamp column '{ts_col}' not found.")
                    sys.exit(1)
                try:
                    df_sim['datetime_utc'] = pd.to_datetime(
                        df_sim[ts_col], unit='ms', utc=True)
                    logger.debug("Converted simulation timestamp column.")
                except Exception as e:
                    logger.critical(
                        f"FATAL: Failed convert timestamp col '{ts_col}': {e}")
                    sys.exit(1)
                for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                    df_sim[col] = df_sim[col].apply(to_decimal)
                df_sim = df_sim.sort_values(
                    by='datetime_utc').reset_index(drop=True)
                self.state['simulation_data'] = df_sim
                min_start_rows = self._get_trading_param('kline_limit', 200)
                if len(df_sim) < min_start_rows:
                    logger.critical(
                        f"FATAL: Not enough data ({len(df_sim)}) for kline limit ({min_start_rows}).")
                    sys.exit(1)
                self.state['simulation_end_index'] = len(df_sim) - 1
                current_sim_index = self.state.get(
                    'simulation_index', 0)  # Get potentially loaded index
                if current_sim_index == 0:
                    self.state['simulation_index'] = min_start_rows - 1
                elif current_sim_index > self.state['simulation_end_index']:
                    logger.warning(
                        f"Loaded sim index ({current_sim_index}) > max ({self.state['simulation_end_index']}). Resetting.")
                    self.state['simulation_index'] = min_start_rows - 1
                logger.info(
                    f"Simulation ready. Current Index: {self.state['simulation_index']}, End Index: {self.state['simulation_end_index']}")
            except Exception as e:
                logger.critical(
                    f"FATAL: Error loading/processing sim data: {e}", exc_info=True)
                sys.exit(1)

        if self.SIMULATION_MODE:
            # Only initialize if not loaded from state
            if not self.state.get('account_balance'):
                initial_cash_str = get_config_value(
                    self.config, ('portfolio', 'initial_cash'), '0')
                initial_cash = to_decimal(
                    initial_cash_str, default=Decimal('0.0'))
                quote_asset = get_config_value(
                    self.config, ('portfolio', 'quote_asset'), 'USDT')
                symbol_str = self._get_trading_param('symbol', 'BTCUSDT')
                base_asset = symbol_str.replace(
                    quote_asset, '') if symbol_str and quote_asset else 'BASE'
                self.state['account_balance'] = {
                    quote_asset: initial_cash, base_asset: Decimal('0.0')}
                logger.info(
                    f"SIM MODE: Initialized balance from config: {quote_asset}={initial_cash:.2f}, {base_asset}=0.0")
            else:
                logger.info(
                    f"SIM MODE: Using account balance loaded from state: {self.state['account_balance']}")
        else:
            self._update_account_balance()
        self._update_symbol_specific_info()
        logger.info("Performing initial data processing & calculations...")
        if self._update_market_data():
            self._calculate_indicators()
            self._calculate_sr_zones()
            self._calculate_confidence()
            self._update_pivot_points()
        else:
            logger.critical("FATAL: Initial market data processing failed.")
            sys.exit(1)

        # --- Initial Order Reconciliation (Placeholder) ---
        # if self.order_manager and not self.SIMULATION_MODE:
        #      logger.info("Performing initial order reconciliation...")
        #      # self.order_manager.reconcile_all_open_orders() # Needs implementation
        # --- End Initial Reconciliation ---

        self._setup_scheduler()
        logger.info("GeminiTrader Initialization Complete.")
        print("-" * 30)

    def _get_trading_param(self, key: str, default=None):
        if key == 'pivot_window':
            default = DEFAULT_PIVOT_WINDOW
        elif key == 'zone_proximity_factor':
            default = DEFAULT_ZONE_PROXIMITY_FACTOR
        elif key == 'min_zone_touches':
            default = DEFAULT_MIN_ZONE_TOUCHES
        elif key == 'entry_confidence_threshold':
            default = 0.5
        elif key == 'entry_rsi_threshold':
            default = 75.0
        return get_config_value(self.config, ('trading', key), default)

    def _update_symbol_specific_info(self) -> bool:
        symbol = self._get_trading_param('symbol', 'BTCUSDT')
        logger.debug(f"Updating symbol info: {symbol}")
        if not self.connector:
            return False
        full_exchange_info = self.connector.get_exchange_info_cached()
        if full_exchange_info:
            try:
                symbol_info = get_symbol_info_from_exchange_info(
                    symbol, full_exchange_info)
                if symbol_info:
                    self.state['symbol_info'] = symbol_info
                    logger.debug(f"Updated symbol info: {symbol}.")
                    return True
                else:
                    logger.error(
                        f"Symbol '{symbol}' not found in exchange info.")
                    self.state['symbol_info'] = None
                    return False
            except Exception as e:
                logger.exception(f"Error extracting symbol info: {e}")
                self.state['symbol_info'] = None
                return False
        else:
            logger.warning("Exchange info cache empty, refreshing...")
            full_exchange_info = self.connector.get_exchange_info(
                force_refresh=True)
            return self._update_symbol_specific_info() if full_exchange_info else False

    def _update_account_balance(self) -> bool:
        logger.debug(
            "Updating REAL account balance (for logging/reference)...")
        if not self.connector:
            return False
        quote_asset = get_config_value(
            self.config, ('portfolio', 'quote_asset'), 'USDT')
        symbol_str = self._get_trading_param('symbol', 'BTCUSDT')
        base_asset = symbol_str.replace(
            quote_asset, '') if symbol_str and quote_asset else None
        if not base_asset:
            logger.error("Could not determine base asset name.")
            return False
        try:
            quote_balance = self.connector.get_asset_balance(quote_asset)
            base_balance = self.connector.get_asset_balance(base_asset)
            if quote_balance is not None and base_balance is not None:
                logger.info(
                    f"REAL Balance Check: {quote_asset}={quote_balance:.2f}, {base_asset}={base_balance:.8f}")
                return True
            else:
                logger.error("Failed fetch REAL account balances.")
                return False
        except Exception as e:
            logger.exception("Error updating REAL account balance.")
            return False

    def _update_market_data(self) -> bool:
        if self.SIMULATION_MODE:
            logger.debug("SIM MODE: Updating market data...")
            if self.state['simulation_data'] is None:
                return False
            sim_idx = self.state['simulation_index']
            sim_end_idx = self.state['simulation_end_index']
            if sim_idx > sim_end_idx:
                logger.info("SIM MODE: End of simulation data.")
                return False
            kline_limit = self._get_trading_param('kline_limit', 200)
            window_start_idx = max(0, sim_idx - kline_limit + 1)
            window_end_idx = sim_idx + 1
            df_window_raw = self.state['simulation_data'].iloc[window_start_idx:window_end_idx].copy(
            )
            ts_col = get_config_value(
                self.config, ('simulation', 'timestamp_column'), "Timestamp")
            if 'datetime_utc' in df_window_raw.columns:
                df_window_raw = df_window_raw.set_index('datetime_utc')
            elif ts_col in df_window_raw.columns:
                try:
                    df_window_raw['datetime_utc'] = pd.to_datetime(
                        df_window_raw[ts_col], unit='ms', utc=True)
                    df_window_raw = df_window_raw.set_index('datetime_utc')
                except Exception as e:
                    logger.error(f"SIM MODE Error: Conv timestamp: {e}")
                    return False
            else:
                logger.error(
                    f"SIM MODE Error: TS column '{ts_col}'/'datetime_utc' missing.")
                return False
            req_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            if not all(c in df_window_raw.columns for c in req_cols):
                logger.error(f"SIM MODE Error: Window missing OHLCV.")
                return False
            df_window = df_window_raw[req_cols]
            self.state["klines"] = df_window
            self.state["last_data_update_time"] = df_window.index[-1]
            logger.debug(
                f"SIM MODE: Updated klines to index {sim_idx}, TS: {self.state['last_data_update_time']}")
            self.state['simulation_index'] += 1
            return True
        else:  # Live Mode
            symbol = self._get_trading_param('symbol', 'BTCUSDT')
            interval = self._get_trading_param('interval', '1h')
            limit = self._get_trading_param('kline_limit', 200)
            logger.debug(
                f"Fetching latest {limit} klines for {symbol} ({interval})...")
            if not self.connector:
                return False
            latest_klines_df = fetch_and_prepare_klines(
                self.connector, symbol, interval, limit=limit)
            if latest_klines_df is not None and not latest_klines_df.empty:
                req_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
                if not all(c in latest_klines_df.columns for c in req_cols):
                    logger.error("Fetched data missing cols.")
                    return False
                if not isinstance(latest_klines_df.index, pd.DatetimeIndex):
                    logger.error("Fetched data index invalid.")
                    return False
                logger.debug(f"Fetched {len(latest_klines_df)} klines.")
                self.state["klines"] = latest_klines_df
                self.state["last_data_update_time"] = pd.Timestamp.utcnow()
                return True
            else:
                logger.warning(f"Failed fetch/empty kline data for {symbol}.")
                return False

    def _calculate_indicators(self):
        if self.state["klines"].empty:
            return
        df = self.state["klines"]
        min_len_needed = max(ATR_PERIOD, SMA_SHORT_PERIOD, SMA_LONG_PERIOD,
                             RSI_PERIOD, MACD_SLOW_PERIOD + MACD_SIGNAL_PERIOD)
        if len(df) < min_len_needed:
            logger.warning(
                f"Not enough data ({len(df)}<{min_len_needed}) for indicators. Skipping.")
            self.state["indicators"] = {}
            return
        logger.debug(f"Calculating indicators on {len(df)} klines...")
        atr_p = get_config_value(
            self.config, ('strategies', 'geometric_grid', 'atr_length'), ATR_PERIOD)
        sma_s, sma_l, rsi_p = SMA_SHORT_PERIOD, SMA_LONG_PERIOD, RSI_PERIOD
        macd_f, macd_s, macd_g = MACD_FAST_PERIOD, MACD_SLOW_PERIOD, MACD_SIGNAL_PERIOD
        calcd_indic = {}
        try:
            def glv(series: Optional[pd.Series], name: str) -> Optional[Decimal]:
                if series is None or series.empty:
                    logger.warning(
                        f"Indicator {name} calc returned None/empty.")
                    return None
                valid_series = series.dropna()
                if valid_series.empty:
                    logger.warning(
                        f"Indicator {name} has no valid values after dropna().")
                    return None
                last_valid_value = valid_series.iloc[-1]
                val = to_decimal(last_valid_value)
                if val is None:
                    logger.warning(
                        f"Indicator {name} last value '{last_valid_value}' couldn't convert to Decimal.")
                return val
            atr = calculate_atr(df, length=atr_p)
            sma10 = calculate_sma(df, period=sma_s)
            sma50 = calculate_sma(df, period=sma_l)
            rsi = calculate_rsi(df, period=rsi_p)
            macd_df = calculate_macd(
                df, fast_period=macd_f, slow_period=macd_s, signal_period=macd_g)
            calcd_indic[f'ATR_{atr_p}'] = glv(atr, f'ATR_{atr_p}')
            calcd_indic[f'SMA_{sma_s}'] = glv(sma10, f'SMA_{sma_s}')
            calcd_indic[f'SMA_{sma_l}'] = glv(sma50, f'SMA_{sma_l}')
            calcd_indic[f'RSI_{rsi_p}'] = glv(rsi, f'RSI_{rsi_p}')
            macd_key_base = f'{MACD_FAST_PERIOD}_{MACD_SLOW_PERIOD}_{MACD_SIGNAL_PERIOD}'
            macd_key = f'MACD_{macd_key_base}'
            signal_key = f'MACDs_{macd_key_base}'
            histo_key = f'MACDh_{macd_key_base}'
            macd_col = None
            signal_col = None
            histo_col = None
            if macd_df is not None and not macd_df.empty:
                macd_col_std = macd_df.get('MACD')
                macd_col = macd_col_std if (
                    macd_col_std is not None and not macd_col_std.empty) else macd_df.get(macd_key)
                signal_col_std = macd_df.get('Signal')
                signal_col = signal_col_std if (
                    signal_col_std is not None and not signal_col_std.empty) else macd_df.get(signal_key)
                histo_col_std = macd_df.get('Histogram')
                histo_col = histo_col_std if (
                    histo_col_std is not None and not histo_col_std.empty) else macd_df.get(histo_key)
                calcd_indic[macd_key] = glv(macd_col, macd_key)
                calcd_indic[signal_key] = glv(signal_col, signal_key)
                calcd_indic[histo_key] = glv(histo_col, histo_key)
            else:
                logger.warning("MACD calculation returned None or empty.")
                calcd_indic[macd_key] = None
                calcd_indic[signal_key] = None
                calcd_indic[histo_key] = None
            self.state["indicators"] = calcd_indic
            log_items = [f"'{k}': {'{:.4f}'.format(v)}" for k, v in calcd_indic.items(
            ) if isinstance(v, Decimal)]
            log_str = "{ "+", ".join(log_items)+" }" if log_items else "{}"
            logger.debug(f"Indicators calculated: {log_str}")
        except Exception as e:
            logger.exception("Error during indicator calculation.")
            self.state["indicators"] = {}

    def _calculate_sr_zones(self):
        if self.state["klines"].empty:
            return
        df_klines = self.state["klines"]
        pivot_window = self._get_trading_param(
            'pivot_window', DEFAULT_PIVOT_WINDOW)
        if len(df_klines) < pivot_window:
            return
        proximity = self._get_trading_param(
            'zone_proximity_factor', DEFAULT_ZONE_PROXIMITY_FACTOR)
        min_touches = self._get_trading_param(
            'min_zone_touches', DEFAULT_MIN_ZONE_TOUCHES)
        try:
            zones = calculate_dynamic_zones(
                df=df_klines, pivot_window=pivot_window, proximity_factor=proximity, min_touches=min_touches)
            self.state["sr_zones"] = zones
            logger.debug(f"Calculated {len(zones)} S/R zones.")
        except Exception as e:
            logger.exception("Error during S/R zone calc.")
            self.state["sr_zones"] = []

    def _calculate_confidence(self):
        if not self.state["indicators"]:
            logger.debug("Indicators NA, cannot calc confidence.")
            self.state['confidence_score'] = 0.5
            return
        try:
            score = calculate_confidence_v1(self.state["indicators"])
            self.state['confidence_score'] = score
            logger.info(f"Confidence Score: {score:.4f}")
        except Exception as e:
            logger.exception("Error during confidence calc.")
            self.state['confidence_score'] = 0.5

    def _update_pivot_points(self):
        pivot_interval = '1d'
        symbol = self._get_trading_param('symbol', 'BTCUSDT')
        logger.debug(f"Updating {pivot_interval} pivots for {symbol}...")
        if not self.connector:
            logger.error("Cannot update pivots: Connector NA.")
            return
        now_utc = pd.Timestamp.utcnow()
        end_y = now_utc.normalize()-pd.Timedelta(seconds=1)
        start_y = end_y.normalize()
        start_ms_str = str(int(start_y.timestamp() * 1000))
        end_ms_str = str(int(end_y.timestamp() * 1000))
        logger.debug(
            f"Fetching prev kline: {start_y} ({start_ms_str}) to {end_y} ({end_ms_str})")
        try:
            prev_df = fetch_and_prepare_klines(
                self.connector, symbol, pivot_interval, start_ms_str, end_ms_str, limit=1)
            if prev_df is not None and not prev_df.empty:
                piv_lvls = calculate_pivot_points(prev_df.iloc[[-1]])
                if piv_lvls is not None:
                    self.state["pivot_levels"] = piv_lvls
                    self.state["last_pivot_calc_time"] = now_utc
                    log_piv = {k: f"{v:.4f}" for k, v in piv_lvls.items()}
                    logger.info(f"Updated {pivot_interval} Pivots: {log_piv}")
                else:
                    logger.warning(
                        "Pivot calculation failed from fetched data.")
            else:
                logger.warning(
                    f"Could not fetch prev {pivot_interval} kline for pivots.")
        except Exception as e:
            logger.exception(f"Error during pivot update.")

    def _setup_scheduler(self):
        logger.info("Setting up scheduler...")
        try:
            schedule.every().day.at("00:01", "UTC").do(self._update_pivot_points)
            schedule.every().day.at("00:05", "UTC").do(self._update_symbol_specific_info)
            if not self.SIMULATION_MODE:
                schedule.every(15).minutes.do(self._update_account_balance)
                logger.info(
                    f"Scheduled daily: Pivots(00:01), SymbolInfo(00:05). Every 15m: Balance.")
            else:
                logger.info(
                    f"Scheduled daily: Pivots(00:01), SymbolInfo(00:05). (Balance check disabled in Sim Mode)")
        except Exception as e:
            logger.error(f"Failed schedule setup: {e}", exc_info=True)

    def _check_and_calculate_tp(self) -> Optional[Decimal]:
        position = self.state.get('position')
        if position is None:
            return None
        if not self.state["indicators"]:
            return None
        full_exchange_info = self.connector.get_exchange_info_cached() if self.connector else None
        if not full_exchange_info:
            return None
        symbol = position['symbol']
        entry_price = position['entry_price']
        atr_key = f'ATR_{get_config_value(self.config, ("strategies", "geometric_grid", "atr_length"), ATR_PERIOD)}'
        current_atr = self.state['indicators'].get(atr_key)
        current_confidence = self.state.get('confidence_score')
        use_conf_scaling = get_config_value(
            self.config, ('feature_flags', 'use_confidence_scaling'), False)
        conf_to_pass = current_confidence if use_conf_scaling and current_confidence is not None else None
        logger.debug(
            f"Calculating TP for {symbol}: Entry={entry_price}, ATR={current_atr}, Conf={conf_to_pass}")
        try:
            tp_price = calculate_dynamic_tp_price(entry_price=entry_price, current_atr=current_atr, config=self.config,
                                                  exchange_info=full_exchange_info, symbol=symbol, confidence_score=conf_to_pass)
            if tp_price:
                logger.info(f"Calculated TP Price target: {tp_price:.4f}")
                return tp_price
            else:
                logger.warning(f"Failed to calculate TP price.")
                return None
        except Exception as e:
            logger.exception(f"Error calculating TP price for {symbol}")
            return None

    def _evaluate_risk_controls(self):
        position = self.state.get('position')
        if position is None:
            return False
        try:
            exit_signal = check_time_stop(
                position=position, current_klines=self.state['klines'], config=self.config, confidence_score=self.state.get('confidence_score'))
            if exit_signal:
                logger.warning(
                    f"*** RISK CONTROL: TIME STOP EXIT SIGNAL for position entered at {position.get('entry_time')} ***")
                self.state['sim_market_sells'] += 1
                return True
        except Exception as e:
            logger.exception("Error during time stop check.")
            self.state['main_loop_warnings'] += 1
        return False

    def _plan_grid_buys(self) -> List[Dict]:
        planned_orders = []
        if self.state['position'] is not None:
            logger.debug("Grid planning skipped: Position exists.")
            return planned_orders
        indicators = self.state.get("indicators")
        confidence = self.state.get('confidence_score')
        klines = self.state.get('klines')
        if not indicators or confidence is None or klines is None or klines.empty:
            logger.warning(
                "Grid planning skipped: Missing indicators/confidence/klines.")
            return planned_orders
        full_exchange_info = self.connector.get_exchange_info_cached() if self.connector else None
        if not full_exchange_info:
            logger.warning("Grid planning skipped: Missing exchange info.")
            return planned_orders
        quote_asset = get_config_value(
            self.config, ('portfolio', 'quote_asset'), 'USDT')
        available_balance = self.state['account_balance'].get(quote_asset)
        if available_balance is None or available_balance <= 0:
            logger.warning(
                f"Grid planning skipped: {quote_asset} balance zero or None ({available_balance}).")
            return planned_orders
        entry_condition_met = False
        conf_threshold = self._get_trading_param(
            'entry_confidence_threshold', 0.5)
        rsi_threshold = self._get_trading_param('entry_rsi_threshold', 75.0)
        rsi_key = f'RSI_{RSI_PERIOD}'
        current_rsi = indicators.get(rsi_key)
        if confidence >= conf_threshold:
            if current_rsi is not None and current_rsi < Decimal(str(rsi_threshold)):
                sma_short_key = f'SMA_{SMA_SHORT_PERIOD}'
                sma_long_key = f'SMA_{SMA_LONG_PERIOD}'
                sma_short = indicators.get(sma_short_key)
                sma_long = indicators.get(sma_long_key)
                if sma_short is not None and sma_long is not None:
                    if sma_short > sma_long:
                        entry_condition_met = True
                        logger.debug(
                            f"Entry conditions met (Conf >= {conf_threshold}, RSI < {rsi_threshold}, Trend OK). Planning grid...")
                    else:
                        logger.info(
                            f"Grid planning skipped: Trend filter failed ({sma_short_key} <= {sma_long_key}).")
                else:
                    logger.warning(
                        f"Grid planning skipped: Could not evaluate trend filter (missing SMAs).")
                    self.state['main_loop_warnings'] += 1
            elif current_rsi is None:
                logger.warning(
                    f"Grid planning skipped: Could not evaluate RSI filter (missing RSI value).")
                self.state['main_loop_warnings'] += 1
            else:
                logger.info(
                    f"Grid planning skipped: RSI filter failed ({current_rsi:.2f} >= {rsi_threshold}).")
        else:
            logger.info(
                f"Grid planning skipped: Confidence ({confidence:.2f}) below threshold ({conf_threshold}).")
        if not entry_condition_met:
            return planned_orders
        symbol = self._get_trading_param('symbol', 'BTCUSDT')
        if 'Close' not in klines.columns or klines['Close'].dropna().empty:
            logger.warning("Grid planning skipped: Close price missing.")
            return planned_orders
        current_price = klines['Close'].iloc[-1]
        atr_key = f'ATR_{get_config_value(self.config, ("strategies", "geometric_grid", "atr_length"), ATR_PERIOD)}'
        current_atr = indicators.get(atr_key)
        if current_price is None or current_atr is None:
            logger.warning("Grid planning skipped: Missing price or ATR.")
            return planned_orders
        try:
            planned_orders = plan_buy_grid_v1(symbol=symbol, current_price=current_price, current_atr=current_atr,
                                              available_quote_balance=available_balance, exchange_info=full_exchange_info, config=self.config, confidence_score=confidence)
            if planned_orders:
                logger.info(
                    f"Planning: Calculated {len(planned_orders)} potential grid buy orders.")
            else:
                logger.debug("Grid planning resulted in no valid orders.")
            return planned_orders
        except Exception as e:
            logger.exception("Error during grid planning calculation.")
            self.state['main_loop_warnings'] += 1
            return []

    def run(self):
        self.is_running = True
        symbol = self._get_trading_param('symbol', 'BTCUSDT')
        interval = self._get_trading_param('interval', '1h')
        loop_sleep = self._get_trading_param(
            'loop_sleep_time', 60) if not self.SIMULATION_MODE else 0
        sim_step_delay = get_config_value(
            self.config, ('simulation', 'step_delay_seconds'), 0.05) if self.SIMULATION_MODE else 0
        kline_limit = self._get_trading_param('kline_limit', 200)
        state_save_interval_seconds = get_config_value(
            self.config, ('state_manager', 'save_interval_seconds'), 300)
        logger.info(
            f"Starting main loop. Symbol:{symbol}, Interval:{interval}, Sleep:{loop_sleep}s (Sim Delay: {sim_step_delay}s)")
        print("-" * 30)
        if self.order_manager is None:
            logger.critical("FATAL: OrderManager not initialized.")
            self.is_running = False
        if self.state_manager is None:
            logger.critical("FATAL: StateManager not initialized.")
            self.is_running = False
        if self.SIMULATION_MODE and self.state.get('simulation_data') is None:
            logger.critical("FATAL: Sim mode active but no sim data loaded.")
            self.is_running = False
        total_sim_steps = (self.state['simulation_end_index'] - self.state['simulation_index'] +
                           1) if self.SIMULATION_MODE and 'simulation_end_index' in self.state and 'simulation_index' in self.state else 0
        pbar = None
        # --- Correct initial value for tqdm ---
        initial_step = 0
        if self.SIMULATION_MODE and 'simulation_index' in self.state and 'simulation_end_index' in self.state:
            # Calculate already completed steps
            initial_step = max(
                0, self.state['simulation_index'] - (kline_limit - 1))
        if self.SIMULATION_MODE and total_sim_steps > 0:
            pbar = tqdm(total=total_sim_steps, initial=initial_step, desc="Simulating", unit="step", leave=True,
                        dynamic_ncols=True, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]')
        last_state_save_time = time.monotonic()

        while self.is_running:
            loop_start = time.monotonic()
            try:
                if self.SIMULATION_MODE and pbar and self.state['simulation_index'] > self.state['simulation_end_index']:
                    logger.info(
                        "SIM MODE: End of simulation data reached. Final Save & Stop.")
                    if not pbar.disable and pbar.n < pbar.total:
                        pbar.update(pbar.total - pbar.n)  # Update to 100%
                    self._save_current_state()
                    sim_duration = time.monotonic(
                    ) - self.state['simulation_start_time']
                    total_steps = pbar.n if pbar else 0
                    logger.info(
                        f"Simulation Summary: Ran {total_steps} steps in {sim_duration:.2f} seconds.")
                    final_counts = {k: v for k, v in self.state.items() if k.startswith(
                        'sim_') or k in ['main_loop_errors', 'main_loop_warnings']}
                    logger.info(f"Final Sim Counts: {final_counts}")
                    self.is_running = False
                    continue
                if not self.SIMULATION_MODE:
                    schedule.run_pending()
                data_updated = self._update_market_data()
                if not data_updated:
                    logger.warning(
                        "Market data update failed or sim ended. Skipping cycle.")
                    time.sleep(loop_sleep if not self.SIMULATION_MODE else 0.1)
                    continue
                self._calculate_indicators()
                self._calculate_sr_zones()
                self._calculate_confidence()
                if self.order_manager and self.state["indicators"] and self.state.get('confidence_score') is not None:
                    self.order_manager.check_orders()
                    if self.state['position']:
                        tp_target_price = self._check_and_calculate_tp()
                        exit_signal = self._evaluate_risk_controls()
                        if exit_signal:
                            self.order_manager.execute_market_sell(
                                reason="Risk Control Trigger")
                        elif tp_target_price:
                            self.order_manager.place_or_update_tp_order(
                                tp_target_price)
                    if not self.state['position']:
                        planned_buy_orders = self._plan_grid_buys()
                        if planned_buy_orders:
                            self.order_manager.reconcile_and_place_grid(
                                planned_buy_orders)
                else:
                    logger.warning(
                        "Skipping trading logic: OrderMgr/Indicators/Confidence NA.")
                    self.state['main_loop_warnings'] += 1
                current_time = time.monotonic()
                if current_time - last_state_save_time >= state_save_interval_seconds:
                    self._save_current_state()
                    last_state_save_time = current_time
                elapsed = time.monotonic() - loop_start
                if self.SIMULATION_MODE and pbar:
                    if sim_step_delay > 0:
                        time.sleep(sim_step_delay)
                    pbar.update(1)
                    ts = self.state['last_data_update_time']
                    ts_str = ts.strftime(
                        '%y%m%d-%H%M') if pd.notna(ts) else "N/A"
                    pos_qty = self.state['position']['quantity'] if self.state['position'] else Decimal(
                        '0.0')
                    pos_entry = self.state['position']['entry_price'] if self.state['position'] else Decimal(
                        '0.0')
                    grid_count = len(self.state['active_grid_orders'])
                    tp_id_short = str(self.state['active_tp_order']['orderId'])[
                        -4:] if self.state['active_tp_order'] else "--"
                    conf = self.state['confidence_score'] if self.state['confidence_score'] is not None else 0.5
                    total_errors = self.state.get('main_loop_errors', 0) + self.state.get('sim_grid_place_fail', 0) + self.state.get(
                        'sim_tp_place_fail', 0) + self.state.get('sim_grid_cancel_fail', 0) + self.state.get('sim_tp_cancel_fail', 0)
                    postfix_data = {"T": ts_str, "Pos": f"{pos_qty:.5f}@{pos_entry:.1f}", "Gr": grid_count, "TP": tp_id_short, "Cf": f"{conf:.2f}", "GF": self.state.get('sim_grid_fills', 0), "TF": self.state.get(
                        'sim_tp_fills', 0), "MS": self.state.get('sim_market_sells', 0), "W": self.state.get('main_loop_warnings', 0), "E": total_errors, "L": f"{elapsed:.3f}s"}
                    pbar.set_postfix(postfix_data, refresh=False)
                    sim_idx = self.state['simulation_index'] - 1
                    if sim_idx > 0 and sim_idx % 100 == 0:
                        logger.info(
                            f"Sim Progress: Step {sim_idx}/{self.state['simulation_end_index']+1}, Last Sim Time: {ts}")
                else:
                    sleep = max(0, loop_sleep - elapsed)
                    time.sleep(sleep)
                    if elapsed > loop_sleep * 1.1:
                        logger.warning(
                            f"Loop time ({elapsed:.2f}s) > target ({loop_sleep}s).")
            except KeyboardInterrupt:
                logger.warning("KeyboardInterrupt received. Stopping...")
                self.is_running = False
            except Exception as e:
                logger.exception("CRITICAL Error in main loop.")
                self.state['main_loop_errors'] += 1
                if pbar:
                    tqdm.write(f"!! CRITICAL ERROR in loop: {e} !!")
                time.sleep(loop_sleep * 5 if not self.SIMULATION_MODE else 0.5)
        if pbar:
            pbar.close()
        logger.info("Run loop finished.")

    def _save_current_state(self):
        if not self.state_manager:
            logger.error("Cannot save state: StateManager not initialized.")
            return
        try:
            state_to_save = {
                'position': self.state.get('position'), 'active_grid_orders': self.state.get('active_grid_orders', []),
                'active_tp_order': self.state.get('active_tp_order'), 'simulation_index': self.state.get('simulation_index', 0),
                "sim_grid_fills": self.state.get('sim_grid_fills', 0), "sim_tp_fills": self.state.get('sim_tp_fills', 0),
                "sim_market_sells": self.state.get('sim_market_sells', 0), "sim_grid_place_fail": self.state.get('sim_grid_place_fail', 0),
                "sim_tp_place_fail": self.state.get('sim_tp_place_fail', 0), "sim_grid_cancel_fail": self.state.get('sim_grid_cancel_fail', 0),
                "sim_tp_cancel_fail": self.state.get('sim_tp_cancel_fail', 0), "main_loop_errors": self.state.get('main_loop_errors', 0),
                "main_loop_warnings": self.state.get('main_loop_warnings', 0), "last_state_save_time": pd.Timestamp.utcnow(),
                "account_balance": self.state.get('account_balance', {})
            }
            self.state_manager.save_state(state_to_save)
            self.state['last_state_save_time'] = state_to_save['last_state_save_time']
        except Exception as e:
            logger.exception("Failed to prepare or save state.")

    def stop(self): logger.info(
        "Stop signal received."); self.is_running = False


if __name__ == '__main__':
    trader = None
    try:
        trader = GeminiTrader()
        trader.run()
    except SystemExit:
        print("Exiting: SystemExit called, likely during initialization.")
        sys.exit(1)
    except Exception as e:
        logging.critical(
            f"Unhandled exception at main entry point: {e}", exc_info=True)
        print(f"FATAL Unhandled Exception: {e}")
        sys.exit(1)
    finally:
        if trader and trader.state_manager:
            logger.info("Performing final state save on exit.")
            trader._save_current_state()
        logger.info("GeminiTrader process finished.")
        print("\nProcess finished.")
        # --- ADDED Explicit Exit ---
        sys.exit(0)

# END OF FILE: src/main_trader.py
