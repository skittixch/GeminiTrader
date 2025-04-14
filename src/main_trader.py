# START OF FILE: src/main_trader.py

import logging
import time
from pathlib import Path
import pandas as pd
from decimal import Decimal
import schedule
from typing import Optional, Dict, Any, List

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
    from src.utils.formatting import to_decimal
    from src.connectors.binance_us import BinanceUSConnector
    from src.data.kline_fetcher import fetch_and_prepare_klines
    from src.analysis.indicators import (
        calculate_atr, calculate_sma, calculate_rsi, calculate_macd, calculate_pivot_points,
        ATR_PERIOD, SMA_SHORT_PERIOD, SMA_LONG_PERIOD, RSI_PERIOD,
        MACD_FAST_PERIOD, MACD_SLOW_PERIOD, MACD_SIGNAL_PERIOD
    )
    from src.strategies.profit_taking import calculate_dynamic_tp_price
    from src.analysis.support_resistance import calculate_dynamic_zones, DEFAULT_PIVOT_WINDOW, DEFAULT_ZONE_PROXIMITY_FACTOR, DEFAULT_MIN_ZONE_TOUCHES
except ImportError as e:
    logging.basicConfig(level=logging.ERROR)
    logging.critical(
        # Add exc_info
        f"FATAL ERROR: Module import failed. Error: {e}", exc_info=True)
    sys.exit(1)

# --- Global Logger ---
logger = logging.getLogger(__name__)

# --- Main Application Class ---


class GeminiTrader:
    """ Main class orchestrating the GeminiTrader bot operations. """

    def __init__(self):
        self.config = {}
        self.connector: Optional[BinanceUSConnector] = None
        self.state = {
            "klines": pd.DataFrame(),
            "indicators": {},
            "pivot_levels": None,
            "last_data_update_time": None,
            "last_pivot_calc_time": None,
            "symbol_info": None,  # Specific symbol info cache
            "position": None,
            "sr_zones": [],
        }
        self.is_running = False
        self._initialize()

    def _initialize(self):
        """Load config, logging, connectors, initial data."""
        print("Initializing GeminiTrader...")
        self.config = load_config()
        print("Config loaded.")
        if not self.config:
            logging.critical("FATAL: Config load failed.")
            sys.exit(1)
        try:  # Setup Logging
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
        try:  # Setup Connector
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
            # --- Pre-cache exchange info after successful connection ---
            self.connector.get_exchange_info()  # Fetch and cache immediately
            if not self.connector.get_exchange_info_cached():
                logger.warning(
                    "Failed to pre-cache exchange info during initialization.")
            # --- End pre-cache ---
        except Exception as e:
            logger.critical(
                f"FATAL: Connector init failed: {e}.", exc_info=True)
            sys.exit(1)

        # Use the cached full info to get specific symbol info
        self._update_symbol_specific_info()
        logger.info("Performing initial data fetch & calculations...")
        if self._update_market_data():
            self._calculate_indicators()
            self._calculate_sr_zones()
            self._update_pivot_points()
        else:
            logger.warning("Initial market data fetch failed.")

        self._simulate_position_entry()
        self._setup_scheduler()
        logger.info("GeminiTrader Initialization Complete.")

    def _simulate_position_entry(self):
        """ Sets a mock position in the state for testing purposes. """
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        if not self.state['klines'].empty:
            mock_entry_price = self.state['klines']['Close'].iloc[-1] * \
                Decimal('0.998')
            mock_quantity = Decimal('0.001')
            self.state['position'] = {'symbol': symbol, 'entry_price': mock_entry_price.quantize(Decimal(
                '0.01')), 'quantity': mock_quantity, 'entry_time': pd.Timestamp.utcnow() - pd.Timedelta(hours=1)}
            logger.warning(
                f"*** SIMULATING POSITION ENTRY for {symbol} at ~{self.state['position']['entry_price']} Qty: {mock_quantity} ***")
        else:
            logger.warning("Cannot simulate position entry: No kline data.")

    def _get_trading_param(self, key: str, default=None):
        """Helper to get parameters from the [trading] config section."""
        if key == 'pivot_window':
            default = DEFAULT_PIVOT_WINDOW
        elif key == 'zone_proximity_factor':
            default = DEFAULT_ZONE_PROXIMITY_FACTOR
        elif key == 'min_zone_touches':
            default = DEFAULT_MIN_ZONE_TOUCHES
        return get_config_value(self.config, ('trading', key), default)

    # --- UPDATED: Renamed and uses cached full info ---
    def _update_symbol_specific_info(self) -> bool:
        """Extracts and caches info for the specific trading symbol from the full exchange info cache."""
        symbol = self._get_trading_param('symbol', 'BTCUSD')
        logger.info(f"Extracting/Updating specific info for symbol: {symbol}")
        if not self.connector:
            logger.error("Connector not available.")
            return False

        full_exchange_info = self.connector.get_exchange_info_cached()  # Get from cache

        if full_exchange_info:
            try:
                # Import helper locally if needed (or ensure it's available globally)
                from src.utils.formatting import get_symbol_info_from_exchange_info
                symbol_info = get_symbol_info_from_exchange_info(
                    symbol, full_exchange_info)

                if symbol_info:
                    self.state['symbol_info'] = symbol_info  # Update state
                    logger.debug(
                        f"Successfully updated specific symbol info for {symbol}.")
                    return True
                else:
                    logger.error(
                        f"Symbol '{symbol}' not found within cached exchange info.")
                    self.state['symbol_info'] = None
                    return False
            except ImportError:
                logger.error(
                    "Failed to import 'get_symbol_info_from_exchange_info'. Cannot update symbol info.")
                return False
            except Exception as e:
                logger.exception(
                    f"Error extracting symbol info for {symbol}: {e}")
                self.state['symbol_info'] = None
                return False
        else:
            logger.error(
                f"Failed to retrieve full exchange info from cache. Cannot update symbol info.")
            # Attempt to fetch fresh? Maybe rely on scheduler for now.
            self.state['symbol_info'] = None
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
        """Calculates all required indicators based on the current kline data."""
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

            def glv(s: Optional[pd.Series]) -> Optional[Decimal]:  # get_last_valid
                if s is not None and not s.empty:
                    lst = s.dropna().iloc[-1] if not s.dropna().empty else None
                    return to_decimal(lst) if lst is not None else None
                return None
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
            self.state["sr_zones"] = zones  # Store list of zone dicts
            # Logging is handled inside calculate_dynamic_zones
        except Exception as e:
            logger.exception("Error during S/R zone calc.")
            self.state["sr_zones"] = []

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
            schedule.every().day.at("00:05", "UTC").do(
                self._update_symbol_specific_info)  # Changed from _update_symbol_info
            logger.info(
                "Scheduled daily tasks: Pivots (00:01 UTC), Symbol Info (00:05 UTC).")
        except Exception as e:
            logger.error(f"Failed schedule setup: {e}", exc_info=True)

    def _check_and_calculate_tp(self):
        """ Checks if a position exists and calculates its TP price using filters. """
        if self.state['position'] is None:
            return
        if not self.state["indicators"]:
            logger.warning("Skip TP calc: Indicators NA.")
            return

        # --- Use Connector Cache for Exchange Info ---
        full_exchange_info = self.connector.get_exchange_info_cached() if self.connector else None
        if not full_exchange_info:
            logger.error("Skip TP calc: Exchange info not available in cache.")
            # Optionally trigger a fetch?
            # self._update_symbol_specific_info() # This fetches full info if cache is empty/stale
            # full_exchange_info = self.connector.get_exchange_info_cached()
            # if not full_exchange_info: return # Give up if still not available
            return  # Give up if not cached

        pos = self.state['position']
        symbol = pos['symbol']
        entry_price = pos['entry_price']
        atr_key = f'ATR_{get_config_value(self.config, ("strategies", "geometric_grid", "atr_length"), ATR_PERIOD)}'
        current_atr = self.state['indicators'].get(atr_key)
        use_conf = get_config_value(
            self.config, ('feature_flags', 'use_confidence_scaling'), False)
        mock_conf = 0.75 if use_conf else None
        logger.debug(
            f"Calculating TP for {symbol}: Entry={entry_price}, ATR={current_atr}, Conf={mock_conf}")

        # --- CORRECTED Call ---
        tp_price = calculate_dynamic_tp_price(
            entry_price=entry_price,
            current_atr=current_atr,
            config=self.config,
            exchange_info=full_exchange_info,  # Pass FULL exchange info
            symbol=symbol,                     # Pass SYMBOL
            confidence_score=mock_conf
        )

        if tp_price:
            logger.info(
                f"Calculated TP Price for {symbol} position: {tp_price:.4f}")
            # TODO: Store TP in state / Place or update TP order
        else:
            logger.warning(
                f"Failed to calculate TP price for {symbol} position.")

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
                # 2. Market Data
                data_updated = self._update_market_data()
                # 3. Calculations (Indicators & S/R Zones)
                if data_updated or not self.state["indicators"]:
                    self._calculate_indicators()
                    self._calculate_sr_zones()  # Calculate S/R zones

                # --- TRADING LOGIC ---
                # Check if essential data is present before proceeding
                # symbol_info is now checked indirectly via exchange_info check in TP calc
                if self.state["indicators"]:
                    # 4. Position Management / TP Calc
                    self._check_and_calculate_tp()
                    # 5. Check Orders
                    # self._check_orders()
                    # 6. Risk Controls
                    # self._evaluate_risk_controls()
                    # 7. Confidence Score (Phase 3.5)
                    # confidence = self._calculate_confidence()
                    # 8. Plan Trades / Exits
                    # current_zones = self.state['sr_zones'] # Access zones here
                    # self._plan_trades(confidence, current_zones)
                    # 9. Execute Orders
                    # self._execute_trades(planned_orders)
                    pass  # Placeholder
                else:
                    logger.warning("Skipping logic: Indicators NA.")
                # --- End Logic ---

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
                time.sleep(loop_sleep * 5)
        logger.info("Run loop finished.")

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
