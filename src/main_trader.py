# START OF FILE: src/main_trader.py

import logging
import time
from pathlib import Path
import pandas as pd
from decimal import Decimal
import schedule
from typing import Optional, Dict, Any, List
import random  # For order simulation

# --- Add project root ---
import os
import sys
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
# --- End ---

# Project Imports
try:
    from config.settings import load_config, get_config_value
    from src.utils.logging_setup import setup_logging
    # --- Corrected Import ---
    from src.utils.formatting import to_decimal, apply_filter_rules_to_qty
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
except ImportError as e:
    logging.basicConfig(level=logging.ERROR)
    logging.critical(
        f"FATAL ERROR: Module import failed. Error: {e}", exc_info=True)
    sys.exit(1)

# --- Global Logger ---
logger = logging.getLogger(__name__)

# --- Main Application Class ---


class GeminiTrader:
    """ Main class orchestrating the GeminiTrader bot operations. """
    # --- Simulation Control Flag ---
    # Set to True to run with simulated orders, False for live API calls (when uncommented)
    SIMULATION_MODE = True
    # --- End Simulation Control ---

    def __init__(self):
        self.config = {}
        self.connector: Optional[BinanceUSConnector] = None
        # --- State Management ---
        self.state = {
            "klines": pd.DataFrame(), "indicators": {}, "pivot_levels": None,
            "last_data_update_time": None, "last_pivot_calc_time": None,
            "symbol_info": None, "position": None, "sr_zones": [],
            "confidence_score": None, "account_balance": {},
            "active_grid_orders": [],  # List to store dicts of active limit orders from grid
            # Store details of the active TP order (if any)
            "active_tp_order": None,
        }
        self.is_running = False
        self._initialize()

    def _initialize(self):
        """Load config, logging, connectors, initial data."""
        print(
            f"Initializing GeminiTrader... (SIMULATION_MODE: {self.SIMULATION_MODE})")
        self.config = load_config()
        print("Config loaded.")
        if not self.config:
            logging.critical("FATAL: Config load failed.")
            sys.exit(1)
        try:  # Logging
            log_level_str = get_config_value(
                self.config, ('logging', 'level'), 'INFO').upper()
            log_level = getattr(logging, log_level_str, logging.INFO)
            log_file_path = _project_root / \
                get_config_value(
                    self.config, ('logging', 'trader_log_path'), 'data/logs/trader.log')
            setup_logging(log_level=log_level, log_file=log_file_path, max_bytes=get_config_value(self.config, ('logging', 'max_bytes'),
                          10485760), backup_count=get_config_value(self.config, ('logging', 'backup_count'), 5), console_logging=True)
            logger.info(
                f"Logging setup: Level={log_level_str}, File={log_file_path}")
        except Exception as e:
            logging.exception(f"Logging setup error: {e}.")
        try:  # Connector
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
            self.connector.get_exchange_info()  # Pre-cache
            if not self.connector.get_exchange_info_cached():
                logger.warning("Failed init pre-cache exchange info.")
        except Exception as e:
            logger.critical(
                f"FATAL: Connector init failed: {e}.", exc_info=True)
            sys.exit(1)

        self._update_symbol_specific_info()
        self._update_account_balance()
        # TODO: Load state from file
        logger.info("Performing initial data fetch & calculations...")
        if self._update_market_data():
            self._calculate_indicators()
            self._calculate_sr_zones()
            self._calculate_confidence()
            self._update_pivot_points()
        else:
            logger.warning("Initial market data fetch failed.")
        # TODO: Reconcile open orders
        self._setup_scheduler()
        logger.info("GeminiTrader Initialization Complete.")

    def _get_trading_param(self, key: str, default=None):
        """Helper to get parameters from the [trading] config section."""
        if key == 'pivot_window':
            default = DEFAULT_PIVOT_WINDOW
        elif key == 'zone_proximity_factor':
            default = DEFAULT_ZONE_PROXIMITY_FACTOR
        elif key == 'min_zone_touches':
            default = DEFAULT_MIN_ZONE_TOUCHES
        return get_config_value(self.config, ('trading', key), default)

    def _update_symbol_specific_info(self) -> bool:
        """Extracts/caches info for trading symbol from full exchange info cache."""
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        logger.info(f"Updating specific info for symbol: {symbol}")
        if not self.connector:
            logger.error("Connector not available.")
            return False
        full_exchange_info = self.connector.get_exchange_info_cached()
        if full_exchange_info:
            try:
                from src.utils.formatting import get_symbol_info_from_exchange_info
                symbol_info = get_symbol_info_from_exchange_info(
                    symbol, full_exchange_info)
                if symbol_info:
                    self.state['symbol_info'] = symbol_info
                    logger.debug(f"Updated specific symbol info for {symbol}.")
                    return True
                else:
                    logger.error(
                        f"Symbol '{symbol}' not found in cached exchange info.")
                    self.state['symbol_info'] = None
                    return False
            except Exception as e:
                logger.exception(f"Error extracting symbol info: {e}")
                self.state['symbol_info'] = None
                return False
        else:
            logger.warning(
                "Exchange info cache empty, attempting fresh fetch...")
            full_exchange_info = self.connector.get_exchange_info(
                force_refresh=True)
            return self._update_symbol_specific_info() if full_exchange_info else False

    def _update_account_balance(self) -> bool:
        """ Fetches and caches the current account balance for relevant assets. """
        logger.info("Updating account balance...")
        if not self.connector:
            logger.error("Connector not available.")
            return False
        quote_asset = get_config_value(
            self.config, ('portfolio', 'quote_asset'), 'USD')
        symbol_str = self._get_trading_param('symbol', 'BTCUSD')
        base_asset = symbol_str.replace(
            quote_asset, '') if symbol_str and quote_asset else None
        if not base_asset:
            logger.error("Could not determine base asset name.")
            return False
        try:
            quote_balance = self.connector.get_asset_balance(quote_asset)
            base_balance = self.connector.get_asset_balance(base_asset)
            if quote_balance is not None and base_balance is not None:
                self.state['account_balance'] = {
                    quote_asset: quote_balance, base_asset: base_balance}
                logger.info(
                    f"Account balance updated: {quote_asset}={quote_balance:.2f}, {base_asset}={base_balance:.8f}")
                return True
            else:
                logger.error(
                    "Failed to fetch one or both required asset balances.")
                return False
        except Exception as e:
            logger.exception("Error updating account balance.")
            return False

    def _update_market_data(self) -> bool:
        """Fetches the latest kline data."""
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        interval = self._get_trading_param('interval', '1h')
        limit = self._get_trading_param('kline_limit', 200)
        logger.info(
            f"Fetching latest {limit} klines for {symbol} ({interval})...")
        if not self.connector:
            logger.error("Connector NA.")
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
            logger.debug(
                f"Fetched {len(latest_klines_df)} klines. Updating state.")
            self.state["klines"] = latest_klines_df
            self.state["last_data_update_time"] = pd.Timestamp.utcnow()
            return True
        else:
            logger.warning(f"Failed fetch/empty kline data for {symbol}.")
            return False

    def _calculate_indicators(self):
        """Calculates all required indicators."""
        if self.state["klines"].empty:
            logger.warning("Kline empty, skip indicators.")
            self.state["indicators"] = {}
            return
        df = self.state["klines"]
        logger.info(f"Calculating indicators on {len(df)} klines...")
        atr_p = get_config_value(
            self.config, ('strategies', 'geometric_grid', 'atr_length'), ATR_PERIOD)
        sma_s, sma_l, rsi_p = SMA_SHORT_PERIOD, SMA_LONG_PERIOD, RSI_PERIOD
        macd_f, macd_s, macd_g = MACD_FAST_PERIOD, MACD_SLOW_PERIOD, MACD_SIGNAL_PERIOD
        calcd_indic = {}
        try:
            atr = calculate_atr(df, length=atr_p)
            sma10 = calculate_sma(df, period=sma_s)
            sma50 = calculate_sma(df, period=sma_l)
            rsi = calculate_rsi(df, period=rsi_p)
            macd_df = calculate_macd(
                df, fast_period=macd_f, slow_period=macd_s, signal_period=macd_g)
            def glv(s: Optional[pd.Series]) -> Optional[Decimal]: return to_decimal(s.dropna(
            ).iloc[-1]) if s is not None and not s.empty and not s.dropna().empty else None
            calcd_indic[f'ATR_{atr_p}'] = glv(atr)
            calcd_indic[f'SMA_{sma_s}'] = glv(sma10)
            calcd_indic[f'SMA_{sma_l}'] = glv(sma50)
            calcd_indic[f'RSI_{rsi_p}'] = glv(rsi)
            if macd_df is not None and not macd_df.empty:
                calcd_indic['MACD'], calcd_indic['Signal'], calcd_indic['Histogram'] = glv(
                    macd_df.get('MACD')), glv(macd_df.get('Signal')), glv(macd_df.get('Histogram'))
            else:
                calcd_indic['MACD'], calcd_indic['Signal'], calcd_indic['Histogram'] = None, None, None
            self.state["indicators"] = calcd_indic
            log_items = [
                f"'{k}': {'{:.4f}'.format(v) if isinstance(v, Decimal) else repr(v)}" for k, v in calcd_indic.items()]
            log_str = "{ "+", ".join(log_items)+" }"
            logger.info(f"Latest Indicators calculated: {log_str}")
        except Exception as e:
            logger.exception("Error during indicator calc.")

    def _calculate_sr_zones(self):
        """ Calculates rolling S/R zones based on pivot clustering. """
        if self.state["klines"].empty:
            logger.warning("Kline empty, skip S/R zone calc.")
            self.state["sr_zones"] = []
            return
        df_klines = self.state["klines"]
        pivot_window = self._get_trading_param(
            'pivot_window', DEFAULT_PIVOT_WINDOW)
        proximity = self._get_trading_param(
            'zone_proximity_factor', DEFAULT_ZONE_PROXIMITY_FACTOR)
        min_touches = self._get_trading_param(
            'min_zone_touches', DEFAULT_MIN_ZONE_TOUCHES)
        try:
            zones = calculate_dynamic_zones(
                df=df_klines, pivot_window=pivot_window, proximity_factor=proximity, min_touches=min_touches)
            self.state["sr_zones"] = zones
        except Exception as e:
            logger.exception("Error during S/R zone calc.")
            self.state["sr_zones"] = []

    def _calculate_confidence(self):
        """ Calculates the confidence score based on current indicators. """
        if not self.state["indicators"]:
            logger.warning("Indicators NA, cannot calc confidence.")
            self.state['confidence_score'] = 0.5
            return
        try:
            score = calculate_confidence_v1(self.state["indicators"])
            self.state['confidence_score'] = score
        except Exception as e:
            logger.exception("Error during confidence calc.")
            self.state['confidence_score'] = 0.5

    def _update_pivot_points(self):
        """Fetches previous period data and calculates daily pivot points."""
        pivot_interval = '1d'
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        logger.info(f"Updating {pivot_interval} pivots for {symbol}...")
        if not self.connector:
            return
        now_utc = pd.Timestamp.utcnow()
        end_y = now_utc.normalize()-pd.Timedelta(seconds=1)
        start_y = end_y.normalize()
        start_ms, end_ms = int(start_y.timestamp() *
                               1000), int(end_y.timestamp()*1000)
        logger.debug(f"Fetching prev kline: {start_y} to {end_y}")
        try:
            prev_df = fetch_and_prepare_klines(
                self.connector, symbol, pivot_interval, str(start_ms), str(end_ms), 1)
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
        """Sets up scheduled tasks."""
        logger.info("Setting up scheduler...")
        try:
            schedule.every().day.at("00:01", "UTC").do(self._update_pivot_points)
            schedule.every().day.at("00:05", "UTC").do(self._update_symbol_specific_info)
            schedule.every(15).minutes.do(self._update_account_balance)
            logger.info(
                "Scheduled daily: Pivots(00:01), SymbolInfo(00:05). Every 15m: Balance.")
        except Exception as e:
            logger.error(f"Failed schedule setup: {e}", exc_info=True)

    def _check_and_calculate_tp(self) -> Optional[Decimal]:
        """ Checks position, calculates TP price. Returns price or None. """
        position = self.state.get('position')
        if position is None:
            return None
        if not self.state["indicators"]:
            logger.warning("Skip TP calc: Indicators NA.")
            return None
        full_exchange_info = self.connector.get_exchange_info_cached() if self.connector else None
        if not full_exchange_info:
            logger.error("Skip TP calc: Exchange info NA.")
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
        tp_price = calculate_dynamic_tp_price(entry_price=entry_price, current_atr=current_atr, config=self.config,
                                              exchange_info=full_exchange_info, symbol=symbol, confidence_score=conf_to_pass)
        if tp_price:
            logger.info(
                f"Calculated TP Price target for {symbol} position: {tp_price:.4f}")
            return tp_price
        else:
            logger.warning(
                f"Failed to calculate TP price for {symbol} position.")
            return None

    def _evaluate_risk_controls(self):
        """ Evaluates risk controls. Returns True if position should be closed. """
        position = self.state.get('position')
        if position is None:
            return False
        try:  # Time Stop Check
            exit_signal = check_time_stop(
                position=position, current_klines=self.state['klines'], config=self.config, confidence_score=self.state.get('confidence_score'))
            if exit_signal:
                logger.warning(
                    f"TIME STOP EXIT SIGNAL for position entered at {position.get('entry_time')}")
                return True
        except Exception as e:
            logger.exception("Error during time stop check.")
        return False

    def _plan_grid_buys(self) -> List[Dict]:
        """ Plans geometric grid buy orders. Returns list of potential orders. """
        planned_orders = []
        if self.state['position'] is not None:
            return planned_orders
        if not self.state["indicators"] or self.state.get('confidence_score') is None or self.state['klines'].empty:
            logger.warning("Grid planning skipped: Missing data.")
            return planned_orders
        full_exchange_info = self.connector.get_exchange_info_cached() if self.connector else None
        if not full_exchange_info:
            logger.warning("Grid planning skipped: Missing exchange info.")
            return planned_orders
        quote_asset = get_config_value(
            self.config, ('portfolio', 'quote_asset'), 'USD')
        available_balance = self.state['account_balance'].get(quote_asset)

        # --- START TEMPORARY SIMULATION HACK ---
        # Inject a fake balance if the real one is zero/low, ONLY for simulation testing
        # REMOVE THIS BLOCK FOR LIVE TRADING
        if self.SIMULATION_MODE and (available_balance is None or available_balance < Decimal('100')):
            logger.warning(
                f"SIMULATION HACK: Injecting FAKE ${get_config_value(self.config, ('portfolio', 'initial_cash'), '1000')} balance for testing!")
            available_balance = to_decimal(get_config_value(
                self.config, ('portfolio', 'initial_cash'), '1000'))
        # --- END TEMPORARY SIMULATION HACK ---

        if available_balance is None or available_balance <= 0:
            logger.warning(
                "Grid planning skipped: Quote balance unavailable or zero.")
            return planned_orders
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        if 'Close' not in self.state['klines'].columns or self.state['klines']['Close'].dropna().empty:
            logger.warning("Grid planning skipped: 'Close' unavailable.")
            return planned_orders
        current_price = self.state['klines']['Close'].iloc[-1]
        atr_key = f'ATR_{get_config_value(self.config, ("strategies", "geometric_grid", "atr_length"), ATR_PERIOD)}'
        current_atr = self.state['indicators'].get(atr_key)
        confidence = self.state['confidence_score']
        if current_price is None or current_atr is None:
            logger.warning("Grid planning skipped: Missing price or ATR.")
            return planned_orders

        # --- TEMPORARY Entry Condition ---
        # REMOVE/REPLACE with real logic later
        entry_condition_met = True
        conf_threshold = 0.5  # Temporarily lowered for testing
        if confidence < conf_threshold:
            entry_condition_met = False
            logger.info(
                f"Grid planning skipped: Confidence ({confidence:.2f}) < {conf_threshold}.")
        # --- END TEMPORARY Entry Condition ---

        if not entry_condition_met:
            return planned_orders

        logger.info(
            f"Entry conditions met. Planning grid buy orders for {symbol}...")
        planned_orders = plan_buy_grid_v1(symbol=symbol, current_price=current_price, current_atr=current_atr,
                                          available_quote_balance=available_balance, exchange_info=full_exchange_info, config=self.config, confidence_score=confidence)
        if planned_orders:
            logger.info(
                f"Successfully planned {len(planned_orders)} grid buy orders.")
        else:
            logger.info("Grid planning resulted in no valid orders.")
        return planned_orders

    def _check_orders(self):
        """ Checks status of orders via API (or SIMULATES), updates state. """
        if not self.connector:
            logger.error("Cannot check orders: Connector NA.")
            return
        symbol = self._get_trading_param('symbol')
        log_prefix = "(SIM)" if self.SIMULATION_MODE else ""
        logger.info(f"Checking status of active orders {log_prefix}...")
        made_state_changes = False

        # Check Grid Orders
        orders_to_remove_indices = []
        grid_orders_copy = list(self.state['active_grid_orders'])
        for i, order_data in enumerate(grid_orders_copy):
            if not isinstance(order_data, dict):
                logger.warning(f"Invalid item idx {i}. Removing.")
                orders_to_remove_indices.append(i)
                continue
            order_id = order_data.get('orderId')
            if not order_id:
                logger.warning(f"Grid order data missing orderId. Removing.")
                orders_to_remove_indices.append(i)
                continue
            logger.debug(f"Checking grid order ID: {order_id}...")
            status_info = None
            if self.SIMULATION_MODE:
                sim_status = 'NEW'
                if random.random() < 0.05:
                    sim_status = 'FILLED'  # 5% fill chance
                elif random.random() < 0.01:
                    sim_status = random.choice(
                        ['CANCELED', 'REJECTED', 'UNKNOWN'])  # 1% fail chance
                if sim_status != 'NEW':
                    status_info = {'symbol': symbol, 'orderId': order_id, 'status': sim_status, 'price': str(order_data.get('price', '0')), 'origQty': str(order_data.get(
                        'origQty', '0')), 'executedQty': str(order_data.get('origQty', '0')) if sim_status == 'FILLED' else '0', 'updateTime': int(time.time()*1000)}
            else:
                # status_info = self.connector.get_order_status(symbol, str(order_id)) # REAL CALL
                pass
            if status_info:
                status = status_info.get('status')
                if status == 'FILLED':
                    logger.info(
                        f"{log_prefix} GRID BUY FILLED: {order_id}, Qty:{status_info.get('executedQty')}, Px:{status_info.get('price')}")
                    entry_price = to_decimal(status_info.get('price'))
                    filled_qty = to_decimal(status_info.get('executedQty'))
                    if entry_price and filled_qty and self.state['position'] is None:
                        self.state['position'] = {'symbol': symbol, 'entry_price': entry_price, 'quantity': filled_qty, 'entry_time': pd.Timestamp(
                            status_info.get('updateTime'), unit='ms', tz='UTC')}
                        logger.info(
                            f"Position CREATED {log_prefix}: Entry={entry_price:.4f}, Qty={filled_qty}")
                        logger.warning(
                            f"{log_prefix}: Cancelling remaining grid orders...")
                        orders_to_remove_indices.extend(
                            j for j in range(len(grid_orders_copy)) if j != i)
                        if not self.SIMULATION_MODE:
                            pass  # Add real cancel loop
                        made_state_changes = True
                        break
                    elif self.state['position'] is not None:
                        logger.warning(
                            f"{log_prefix} fill {order_id}, but pos exists. Ignoring.")
                        orders_to_remove_indices.append(i)
                    else:
                        logger.error(
                            f"Could not parse fill {order_id}. Info: {status_info}")
                        orders_to_remove_indices.append(i)
                elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'UNKNOWN']:
                    logger.warning(
                        f"Grid order {order_id} inactive (Status: {status}). Removing.")
                    orders_to_remove_indices.append(i)
                    made_state_changes = True
            else:
                logger.debug(f"Grid order {order_id} status: NEW.") if sim_status == 'NEW' else logger.error(
                    f"Failed get status {order_id}. Removing.")
                orders_to_remove_indices.append(i)
            time.sleep(0.05 if self.SIMULATION_MODE else 0.1)
        unique_indices_to_remove = sorted(
            list(set(orders_to_remove_indices)), reverse=True)
        if unique_indices_to_remove:
            logger.debug(
                f"Removing indices {unique_indices_to_remove} from active_grid_orders")
            original_length = len(self.state['active_grid_orders'])
            temp_list = []
            removed_count = 0
            indices_set = set(unique_indices_to_remove)
            for i, item in enumerate(self.state['active_grid_orders']):
                if i not in indices_set:
                    temp_list.append(item)
                else:
                    removed_count += 1
            self.state['active_grid_orders'] = temp_list
            logger.debug(
                f"Removed {removed_count} orders (Orig:{original_length}, New:{len(self.state['active_grid_orders'])}).")

        # Check TP Order
        tp_order = self.state.get('active_tp_order')
        if tp_order and isinstance(tp_order, dict) and tp_order.get('orderId'):
            order_id = tp_order['orderId']
            logger.debug(f"Checking TP order ID: {order_id}...")
            status_info_tp = None
            if self.SIMULATION_MODE:
                sim_status_tp = 'NEW'
                if self.state['position'] and random.random() < 0.02:
                    sim_status_tp = 'FILLED'  # 2% chance if pos exists
                elif random.random() < 0.01:
                    sim_status_tp = random.choice(
                        ['CANCELED', 'REJECTED', 'UNKNOWN'])
                if sim_status_tp != 'NEW':
                    status_info_tp = {'symbol': symbol, 'orderId': order_id, 'status': sim_status_tp, 'price': str(tp_order.get('price', '0')), 'executedQty': str(
                        self.state['position'].get('quantity', '0')) if sim_status_tp == 'FILLED' and self.state['position'] else '0', 'updateTime': int(time.time()*1000)}
            else:
                # status_info_tp = self.connector.get_order_status(symbol, str(order_id)) # REAL CALL
                pass
            if status_info_tp:
                status = status_info_tp.get('status')
                if status == 'FILLED':
                    logger.info(
                        f"{log_prefix} TAKE PROFIT FILLED: {order_id}, Qty:{status_info_tp.get('executedQty')}, Px:{status_info_tp.get('price')}")
                    self.state['position'] = None
                    self.state['active_tp_order'] = None
                    logger.info(f"Position CLEARED {log_prefix}.")
                    made_state_changes = True
                elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'UNKNOWN']:
                    logger.warning(
                        f"TP order {order_id} inactive (Status: {status}). Clearing.")
                    self.state['active_tp_order'] = None
                    made_state_changes = True
            else:
                logger.debug(f"TP order {order_id} status: NEW.") if sim_status_tp == 'NEW' else logger.error(
                    f"Failed get status TP {order_id}. Clearing.")
                self.state['active_tp_order'] = None
        if not made_state_changes:
            logger.info("Order check complete: No relevant state changes.")

    # --- UPDATED: Order Execution Placeholders with Simulation Control ---

    def _reconcile_and_place_grid(self, planned_orders: List[Dict]):
        """Compares planned orders to active orders, places new, cancels old (SIMULATED or LIVE)."""
        if not self.connector:
            logger.error("Cannot place orders: Connector NA.")
            return
        symbol = self._get_trading_param('symbol')
        log_prefix = "(SIMULATED)" if self.SIMULATION_MODE else "(LIVE)"
        logger.info(f"Starting Grid Reconciliation {log_prefix}...")
        active_orders_in_state = list(self.state['active_grid_orders'])
        cancelled_ids = []
        placed_orders_state = []
        # Cancel existing orders
        for order_data in active_orders_in_state:
            order_id = order_data.get('orderId')
            if order_id:
                logger.info(
                    f"{log_prefix} Cancelling previous grid order {order_id}...")
                cancel_result = None
                if self.SIMULATION_MODE:
                    cancel_result = {
                        'orderId': order_id, 'status': 'CANCELED'} if random.random() > 0.05 else None
                else:
                    # cancel_result = self.connector.cancel_order(symbol, order_id=str(order_id)) # LIVE
                    pass
                if cancel_result and (cancel_result.get('status') == 'CANCELED' or cancel_result.get('status') == 'UNKNOWN'):
                    cancelled_ids.append(order_id)
                else:
                    logger.error(
                        f"{log_prefix} Cancel FAILED for {order_id}. Result: {cancel_result}")
                time.sleep(0.05 if self.SIMULATION_MODE else 0.2)
        # Place new orders
        for order_to_place in planned_orders:
            logger.info(
                f"{log_prefix} Placing new grid order: {order_to_place['quantity']}@{order_to_place['price']}")
            result = None
            if self.SIMULATION_MODE:
                if random.random() > 0.1:  # 90% success sim
                    sim_order_id = random.randint(10000000, 99999999)
                    result = {'symbol': symbol, 'orderId': sim_order_id, 'clientOrderId': f"sim_{sim_order_id}", 'transactTime': int(time.time() * 1000), 'price': str(order_to_place['price']), 'origQty': str(
                        order_to_place['quantity']), 'executedQty': '0.0', 'cummulativeQuoteQty': '0.0', 'status': 'NEW', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'BUY'}
            else:
                # result = self.connector.create_limit_buy(symbol=symbol, quantity=order_to_place['quantity'], price=order_to_place['price']) # LIVE
                pass
            if result and result.get('orderId'):
                placed_orders_state.append(result)
                logger.info(
                    f"{log_prefix} Placement successful. Order ID: {result.get('orderId')}")
            else:
                logger.error(
                    f"{log_prefix} Placement FAILED for grid order at {order_to_place['price']}.")
            time.sleep(0.1 if self.SIMULATION_MODE else 0.3)
        self.state['active_grid_orders'] = placed_orders_state
        logger.info(
            f"Grid Reconciliation Complete {log_prefix}. Active Grid Orders: {len(self.state['active_grid_orders'])}")

    def _place_or_update_tp_order(self, tp_price: Decimal):
        """Places or updates the take profit order (SIMULATED or LIVE)."""
        if not self.connector or self.state['position'] is None:
            return
        log_prefix = "(SIM)" if self.SIMULATION_MODE else "(LIVE)"
        symbol = self.state['position']['symbol']
        quantity = self.state['position']['quantity']
        active_tp_order = self.state.get('active_tp_order')
        exchange_info = self.connector.get_exchange_info_cached()
        if not exchange_info:
            logger.error("Cannot place TP: Exchange info missing.")
            return
        # --- Use imported function ---
        sell_qty = apply_filter_rules_to_qty(
            symbol, quantity, exchange_info, operation='floor')
        if sell_qty is None or sell_qty <= 0:
            logger.error(
                f"Cannot place TP: Invalid sell qty {quantity} after filter.")
            return
        # TODO: Add MIN_NOTIONAL check

        needs_action = False
        order_to_cancel = None
        if active_tp_order and isinstance(active_tp_order, dict) and active_tp_order.get('orderId'):
            sim_current_tp_price = to_decimal(active_tp_order.get('price'))
            # Update if differs by >= 0.1%
            if not sim_current_tp_price or abs(tp_price - sim_current_tp_price) / sim_current_tp_price >= Decimal('0.001'):
                needs_action = True
                order_to_cancel = active_tp_order['orderId']
                logger.info(
                    f"TP target {tp_price:.4f} differs from active {order_to_cancel} @ {sim_current_tp_price:.4f}. Update needed.")
            else:
                logger.debug(
                    f"TP price {tp_price:.4f} close enough to existing {active_tp_order['orderId']} @ {sim_current_tp_price:.4f}. No action.")
        else:
            needs_action = True  # Need initial placement

        if needs_action:
            if order_to_cancel:  # Cancel existing order first
                logger.info(
                    f"{log_prefix} Cancelling existing TP order {order_to_cancel} to update...")
                cancel_success = False
                if self.SIMULATION_MODE:
                    cancel_success = random.random() > 0.05
                else:
                    # cancel_result = self.connector.cancel_order(symbol, order_id=str(order_to_cancel)); cancel_success = cancel_result is not None;
                    pass
                if not cancel_success:
                    logger.error(
                        f"{log_prefix} Cancel FAILED for TP {order_to_cancel}. Update aborted.")
                    return
                self.state['active_tp_order'] = None
                time.sleep(0.05 if self.SIMULATION_MODE else 0.2)
            # Place new/updated TP order
            logger.info(
                f"{log_prefix} Placing TP order: Sell {sell_qty}@{tp_price}")
            result = None
            if self.SIMULATION_MODE:
                if random.random() > 0.1:
                    sim_order_id = random.randint(10000000, 99999999)
                    result = {'symbol': symbol, 'orderId': sim_order_id, 'status': 'NEW', 'price': str(
                        tp_price), 'origQty': str(sell_qty)}
            else:
                # result = self.connector.create_limit_sell(symbol, sell_qty, tp_price) # LIVE
                pass
            if result:
                self.state['active_tp_order'] = result
                logger.info(f"{log_prefix} TP placed: {result.get('orderId')}")
            else:
                logger.error(f"{log_prefix} Placement FAILED for TP order.")
                self.state['active_tp_order'] = None

    def _execute_market_sell(self, reason: str):
        """ Executes a market sell for the current position quantity (SIMULATED or LIVE). """
        if not self.connector or self.state['position'] is None:
            return False
        log_prefix = "(SIM)" if self.SIMULATION_MODE else "(LIVE)"
        symbol = self.state['position']['symbol']
        quantity = self.state['position']['quantity']
        logger.warning(
            f"{log_prefix} Executing Market SELL for {quantity} {symbol} due to: {reason}")
        result = None
        if self.SIMULATION_MODE:
            sim_order_id = random.randint(10000000, 99999999)
            result = {'symbol': symbol, 'orderId': sim_order_id,
                      # Simulate success
                      'status': 'FILLED', 'executedQty': str(quantity)}
        else:
            # result = self.connector.create_market_sell(symbol, quantity) # LIVE
            pass
        if result and result.get('status') == 'FILLED':
            logger.info(
                f"{log_prefix} Market SELL successful. Order ID: {result.get('orderId')}")
            self.state['position'] = None
            active_tp_order = self.state.get('active_tp_order')
            if active_tp_order and isinstance(active_tp_order, dict) and active_tp_order.get('orderId'):
                tp_order_id = active_tp_order['orderId']
                logger.info(
                    f"{log_prefix} Cancelling associated TP order {tp_order_id}...")
                if self.SIMULATION_MODE:
                    pass
                else:
                    # self.connector.cancel_order(symbol, str(tp_order_id))
                    pass
                self.state['active_tp_order'] = None
            return True
        else:
            logger.error(f"{log_prefix} Market SELL FAILED! Result: {result}.")
            return False

    # --- Main Loop ---
    def run(self):
        """Starts the main trading loop."""
        self.is_running = True
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        interval = self._get_trading_param('interval', '1h')
        loop_sleep = self._get_trading_param('loop_sleep_time', 60)
        logger.info(
            f"Starting main loop. Symbol:{symbol}, Interval:{interval}, Sleep:{loop_sleep}s")

        while self.is_running:
            loop_start = time.monotonic()
            try:
                # 1. Scheduled Tasks
                schedule.run_pending()
                # 2. Market Data & Balance
                data_updated = self._update_market_data()
                # 3. Calculations
                if data_updated or not self.state["indicators"]:
                    self._calculate_indicators()
                    self._calculate_sr_zones()
                    self._calculate_confidence()

                # --- TRADING LOGIC ---
                if self.state["indicators"] and self.state.get('confidence_score') is not None:

                    # 4. Check Active Orders & Update State <<< Moved Up
                    # Updates self.state['position'] if fills occur
                    self._check_orders()

                    # 5. Position / TP / Risk Management (If Position Exists)
                    if self.state['position']:
                        tp_target_price = self._check_and_calculate_tp()  # Calculate potential TP price
                        # Check time stops etc.
                        exit_signal = self._evaluate_risk_controls()

                        if exit_signal:
                            self._execute_market_sell(
                                reason="Risk Control Trigger")  # Attempt market sell
                            # Position state is cleared inside _execute_market_sell if successful
                        elif tp_target_price:
                            self._place_or_update_tp_order(
                                tp_target_price)  # Place/Update TP order

                    # 6. Strategy Execution (If NO Position Exists)
                    if not self.state['position']:
                        planned_buy_orders = self._plan_grid_buys()
                        if planned_buy_orders:
                            self._reconcile_and_place_grid(
                                planned_buy_orders)  # Place/Cancel Grid orders

                else:
                    logger.warning(
                        "Skipping logic: Indicators or Confidence Score NA.")
                # --- End Logic ---

                # --- Save State Periodically (Phase 7) ---
                # self._save_state()

                elapsed = time.monotonic() - loop_start
                sleep = max(0, loop_sleep - elapsed)
                if elapsed > loop_sleep * 1.1:
                    logger.warning(
                        f"Loop time ({elapsed:.2f}s) > target ({loop_sleep}s).")
                time.sleep(sleep)

            except KeyboardInterrupt:
                logger.warning("KeyboardInterrupt. Stopping...")
                self.is_running = False
            except Exception as e:
                logger.exception("CRITICAL Error in main loop.")
                time.sleep(loop_sleep * 5)  # Longer sleep on error
        logger.info("Run loop finished.")
        # --- Save State on Exit ---
        # self._save_state()

    def stop(self):
        """Signals the main loop to stop gracefully."""
        logger.info("Stop signal received.")
        self.is_running = False


# --- Entry Point ---
if __name__ == '__main__':
    try:
        trader = GeminiTrader()
        trader.run()
    except SystemExit:
        print("Exiting: Init failure.")
        sys.exit(1)
    except Exception as e:
        logging.critical(f"Unhandled exception: {e}", exc_info=True)
        print(f"FATAL: {e}")
        sys.exit(1)
    finally:
        logger.info("GeminiTrader finished.")
        print("Process finished.")
        sys.exit(0)

# END OF FILE: src/main_trader.py
