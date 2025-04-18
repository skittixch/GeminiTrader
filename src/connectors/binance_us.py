# START OF FILE: src/connectors/binance_us.py (Corrected get_ticker, Removed get_order_book_ticker)

import logging
import time
import hashlib
import hmac
import requests
import json
from decimal import Decimal
from typing import Dict, List, Optional, Any
from pathlib import Path
import pandas as pd

# --- Fix Imports for Standalone Execution ---
if __name__ == '__main__':
    import sys
    # Adjust if directory structure changes
    _project_root = Path(__file__).resolve().parent.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))
        print(f"Temporarily added project root to sys.path: {_project_root}")
# --- End Fix ---

# Import base class if you have one, otherwise remove
# from src.connectors.base_connector import BaseConnector

# Import utilities carefully, handle potential ImportErrors during startup
try:
    from config.settings import get_config_value  # Removed get_env_variable import
    from src.utils.formatting import to_decimal, get_symbol_filter, get_symbol_info_from_exchange_info
except ImportError as e:
    logging.critical(
        f"Failed to import necessary modules (settings/formatting) in binance_us.py: {e}", exc_info=True)
    raise ImportError(f"Could not import core modules: {e}") from e


# Use standard python-binance client
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException, BinanceRequestException
except ImportError as e:
    logging.critical(
        f"Failed to import 'python-binance' library. Please install it: pip install python-binance. Error: {e}")
    raise ImportError("python-binance library not found.") from e


logger = logging.getLogger(__name__)

# Define Kline columns here if using the fetch_prepared_klines method from the user's file
KLINE_COLUMN_NAMES = [
    'open_time', 'open', 'high', 'low', 'close', 'volume',
    'close_time', 'quote_asset_volume', 'number_of_trades',
    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
]
KLINE_DECIMAL_CONVERSION_COLUMNS = [
    'open', 'high', 'low', 'close', 'volume', 'quote_asset_volume',
    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume'
]


# Assuming BaseConnector exists or remove inheritance
# class BinanceUSConnector(BaseConnector):
class BinanceUSConnector:
    """Handles connection and API calls to Binance.US."""

    _exchange_info_cache: Optional[Dict] = None
    _exchange_info_last_update: float = 0.0

    def __init__(self, api_key: str, api_secret: str, config: Dict, tld: str = 'us'):
        self.api_key = api_key
        self.api_secret = api_secret
        self.config = config
        self.tld = tld

        try:
            self.client = Client(api_key, api_secret, tld=self.tld)
            logger.info(f"Binance Client initialized for tld='{self.tld}'.")
            self.get_server_time()
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.critical(
                f"Failed to initialize Binance Client (API/Request Error): {e}", exc_info=False)
            self.client = None
            raise ConnectionError(
                f"Failed to connect to Binance.{self.tld}: {e}") from e
        except Exception as e:
            logger.critical(
                f"Failed to initialize Binance Client (Unexpected Error): {e}", exc_info=True)
            self.client = None
            raise ConnectionError(
                f"Unexpected error connecting to Binance.{self.tld}: {e}") from e

        project_root_for_paths = Path(__file__).resolve().parent.parent.parent
        cache_file_rel = get_config_value(
            config, ('data', 'exchange_info_cache'), 'data/cache/exchange_info.json')
        self.exchange_info_cache_path = project_root_for_paths / cache_file_rel

        self.exchange_info_cache_minutes = get_config_value(
            config, ('trading', 'exchange_info_cache_minutes'), 1440)
        self.max_retries = get_config_value(config, ('api', 'max_retries'), 3)
        self.retry_delay = get_config_value(
            config, ('api', 'retry_delay_seconds'), 5)

        self.exchange_info_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.get_exchange_info(force_refresh=False)
        if not self._exchange_info_cache:
            logger.warning(
                "Failed to load exchange info during initialization.")

    def _handle_api_error(self, e: Exception, context: str = "API call") -> None:
        if isinstance(e, BinanceAPIException):
            logger.error(
                f"Binance API Error ({context}): Status={e.status_code}, Code={e.code}, Message='{e.message}'")
        elif isinstance(e, BinanceRequestException):
            logger.error(
                f"Binance Request Error ({context}): Message='{e.message}'")
        else:
            logger.error(f"Unexpected Error ({context}): {e}", exc_info=True)

    # --- Core Methods ---

    def get_server_time(self) -> Optional[int]:
        if not self.client:
            logger.error(
                "Cannot get server time: Binance client not initialized.")
            return None
        try:
            server_time = self.client.get_server_time()
            logger.debug("Successfully retrieved server time.")
            return server_time['serverTime']
        except (BinanceAPIException, BinanceRequestException) as e:
            self._handle_api_error(e, "get_server_time")
            return None
        except Exception as e:
            self._handle_api_error(e, "get_server_time")
            return None

    def get_exchange_info(self, force_refresh: bool = False) -> Optional[Dict]:
        cache_duration_seconds = self.exchange_info_cache_minutes * 60
        now = time.time()
        if not force_refresh and BinanceUSConnector._exchange_info_cache and \
           (now - BinanceUSConnector._exchange_info_last_update < cache_duration_seconds):
            logger.debug("Returning cached exchange info (memory).")
            return BinanceUSConnector._exchange_info_cache
        if not force_refresh and self.exchange_info_cache_path.exists():
            try:
                file_mod_time = self.exchange_info_cache_path.stat().st_mtime
                if now - file_mod_time < cache_duration_seconds:
                    with open(self.exchange_info_cache_path, 'r') as f:
                        BinanceUSConnector._exchange_info_cache = json.load(f)
                        BinanceUSConnector._exchange_info_last_update = file_mod_time
                        logger.info(
                            f"Loaded exchange info from file cache: {self.exchange_info_cache_path}")
                        return BinanceUSConnector._exchange_info_cache
                else:
                    logger.info("Exchange info file cache expired.")
            except Exception as e:
                logger.error(
                    f"Error loading exchange info from file cache {self.exchange_info_cache_path}: {e}")
        if not self.client:
            logger.error(
                "Cannot fetch exchange info: Binance client not initialized.")
            return BinanceUSConnector._exchange_info_cache
        logger.info("Fetching fresh exchange info from API...")
        try:
            exchange_info = self.client.get_exchange_info()
            BinanceUSConnector._exchange_info_cache = exchange_info
            BinanceUSConnector._exchange_info_last_update = now
            logger.info("Successfully fetched fresh exchange info.")
            try:
                with open(self.exchange_info_cache_path, 'w') as f:
                    json.dump(exchange_info, f, indent=4)
                logger.info(
                    f"Saved fresh exchange info to file cache: {self.exchange_info_cache_path}")
            except Exception as e:
                logger.error(
                    f"Error saving exchange info to file cache {self.exchange_info_cache_path}: {e}")
            return exchange_info
        except (BinanceAPIException, BinanceRequestException) as e:
            self._handle_api_error(e, "get_exchange_info")
            return BinanceUSConnector._exchange_info_cache
        except Exception as e:
            self._handle_api_error(e, "get_exchange_info")
            return BinanceUSConnector._exchange_info_cache

    def get_exchange_info_cached(self) -> Optional[Dict]:
        if BinanceUSConnector._exchange_info_cache:
            cache_age = time.time() - BinanceUSConnector._exchange_info_last_update
            max_age_seconds = self.exchange_info_cache_minutes * 60 * 1.1
            if cache_age > max_age_seconds:
                logger.warning(
                    f"Cached exchange info is older than configured max age ({cache_age/60:.1f}m > {self.exchange_info_cache_minutes*1.1:.1f}m). May be stale.")
            return BinanceUSConnector._exchange_info_cache
        else:
            logger.info(
                "Memory cache empty, attempting to load from file cache...")
            return self.get_exchange_info(force_refresh=False)

    def get_klines(self, symbol: str, interval: str, limit: int = 500, startTime: Optional[int] = None, endTime: Optional[int] = None) -> Optional[List[List[Any]]]:
        if not self.client:
            logger.error("Cannot get klines: Binance client not initialized.")
            return None
        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        if startTime:
            params['startTime'] = startTime
        if endTime:
            params['endTime'] = endTime
        retries = 0
        while retries < self.max_retries:
            try:
                if startTime:
                    klines = self.client.get_historical_klines(symbol, interval, str(
                        startTime), end_str=str(endTime) if endTime else None, limit=limit)
                else:
                    klines = self.client.get_klines(**params)
                return klines
            except (BinanceAPIException, BinanceRequestException) as e:
                self._handle_api_error(e, f"get_klines ({symbol}, {interval})")
                retries += 1
                if retries < self.max_retries:
                    logger.warning(
                        f"Retrying get_klines ({symbol}) in {self.retry_delay}s... ({retries}/{self.max_retries})")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"Max retries reached for get_klines ({symbol}).")
                    return None
            except Exception as e:
                self._handle_api_error(e, f"get_klines ({symbol}, {interval})")
                return None
        return None

    def fetch_prepared_klines(self, symbol: str, interval: str, limit: int = 500, startTime: Optional[int] = None, endTime: Optional[int] = None) -> Optional[pd.DataFrame]:
        logger.info(
            f"Fetching and preparing klines for {symbol}, {interval}, limit={limit}")
        raw_klines = self.get_klines(
            symbol, interval, limit, startTime, endTime)
        if raw_klines is None:
            return None
        if not raw_klines:
            return pd.DataFrame()
        try:
            df = pd.DataFrame(raw_klines, columns=KLINE_COLUMN_NAMES)
            df['open_time'] = pd.to_datetime(
                df['open_time'], unit='ms', utc=True)
            df['close_time'] = pd.to_datetime(
                df['close_time'], unit='ms', utc=True)
            df = df.set_index('open_time')
            for col in KLINE_DECIMAL_CONVERSION_COLUMNS:
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda x: to_decimal(x, default=None))
                    df[col] = df[col].astype(object)
                else:
                    logger.warning(
                        f"Expected kline column '{col}' not found during conversion.")
            if 'ignore' in df.columns:
                df = df.drop(columns=['ignore'])
            check_cols = [
                c for c in KLINE_DECIMAL_CONVERSION_COLUMNS if c in df.columns]
            if df[check_cols].isnull().values.any():
                logger.warning(
                    f"NaN values found after Decimal conversion for {symbol}.")
            logger.info(
                f"Successfully prepared klines DataFrame for {symbol} with {len(df)} rows.")
            return df
        except KeyError as e:
            logger.error(
                f"Missing expected column in raw kline data: {e}. Raw Kline sample: {raw_klines[0] if raw_klines else 'N/A'}")
            return None
        except Exception as e:
            logger.exception(
                f"Error preparing klines DataFrame for {symbol}: {e}")
            return None

    # === MODIFIED: Renamed to get_symbol_book_ticker, added conversions ===
    def get_symbol_book_ticker(self, symbol: str) -> Optional[Dict]:
        """Gets the best price/qty on the order book for a symbol (using get_symbol_ticker)."""
        if not self.client:
            logger.error(
                "Cannot get symbol book ticker: Binance client not initialized.")
            return None
        logger.debug(f"Fetching symbol book ticker for {symbol}...")
        retries = 0
        while retries < self.max_retries:
            try:
                # *** Use get_symbol_ticker to get best bid/ask ***
                ticker_info = self.client.get_symbol_ticker(symbol=symbol)

                # Get order book data separately for bid/ask qtys
                # Note: get_order_book has different structure, usually depth levels
                # Let's use get_orderbook_ticker for price/qty pair
                book_ticker = self.client.get_orderbook_ticker(symbol=symbol)

                # Convert relevant fields to Decimal
                if book_ticker:
                    # Combine info - price from symbol_ticker, qty from orderbook_ticker?
                    # Let's just use orderbook_ticker as it has both best bid/ask and qty
                    book_ticker['lastPrice'] = to_decimal(
                        # Add last price for reference
                        ticker_info.get('price'))
                    book_ticker['bidPrice'] = to_decimal(
                        book_ticker.get('bidPrice'))
                    book_ticker['bidQty'] = to_decimal(
                        book_ticker.get('bidQty'))
                    book_ticker['askPrice'] = to_decimal(
                        book_ticker.get('askPrice'))
                    book_ticker['askQty'] = to_decimal(
                        book_ticker.get('askQty'))
                    logger.debug(
                        f"Fetched order book ticker for {symbol}: Bid={book_ticker.get('bidPrice')}, Ask={book_ticker.get('askPrice')}")
                    return book_ticker  # Return the combined/converted dictionary
                else:
                    logger.warning(
                        f"Received empty order book ticker for {symbol}.")
                    return None  # Return None if order book ticker failed

            except (BinanceAPIException, BinanceRequestException) as e:
                self._handle_api_error(e, f"get_symbol_book_ticker ({symbol})")
                retries += 1
                if retries < self.max_retries:
                    logger.warning(
                        f"Retrying get_symbol_book_ticker ({symbol}) in {self.retry_delay}s... ({retries}/{self.max_retries})")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"Max retries reached for get_symbol_book_ticker ({symbol}).")
                    return None
            except Exception as e:
                self._handle_api_error(e, f"get_symbol_book_ticker ({symbol})")
                return None
        return None
    # === END MODIFICATION ===

    # --- get_ticker is now redundant with get_symbol_book_ticker, removing ---
    # def get_ticker(self, symbol: str) -> Optional[Dict]: ... REMOVED ...
    # =======================================================================

    # --- REMOVED get_order_book_ticker method ---

    def get_balances(self) -> Optional[Dict[str, Decimal]]:
        if not self.client:
            logger.error(
                "Cannot get balances: Binance client not initialized.")
            return None
        logger.debug("Fetching account balances...")
        retries = 0
        while retries < self.max_retries:
            try:
                account_info = self.client.get_account()
                balances = {}
                if account_info and 'balances' in account_info:
                    for item in account_info['balances']:
                        asset = item['asset']
                        free = to_decimal(item['free'])
                        if free is not None and free > Decimal('0'):
                            balances[asset] = free
                    logger.debug(
                        f"Fetched {len(balances)} non-zero free balances.")
                    return balances
                else:
                    logger.warning(
                        "Could not parse balances from account info or 'balances' key missing.")
                    return None
            except (BinanceAPIException, BinanceRequestException) as e:
                self._handle_api_error(e, "get_balances")
                retries += 1
                if retries < self.max_retries:
                    logger.warning(
                        f"Retrying get_balances in {self.retry_delay}s... ({retries}/{self.max_retries})")
                    time.sleep(self.retry_delay)
                else:
                    logger.error("Max retries reached for get_balances.")
                    return None
            except Exception as e:
                self._handle_api_error(e, "get_balances")
                return None
        return None

    # --- Order Methods ---

    def _prepare_and_validate_order(self, symbol: str, quantity: Decimal, price: Optional[Decimal], order_type: str) -> Optional[Dict]:
        if not self._exchange_info_cache:
            logger.error(
                f"Order Prep Error ({symbol}): Exchange info not available.")
            return None
        adj_price = None
        if price is not None:
            adj_price = apply_filter_rules_to_price(
                symbol, price, self._exchange_info_cache, operation='adjust')
            if adj_price is None or adj_price <= Decimal('0'):
                logger.error(
                    f"Order price {price} invalid after PRICE_FILTER for {symbol}. Adjusted: {adj_price}")
                return None
        qty_op = 'floor'
        adj_qty = apply_filter_rules_to_qty(
            symbol, quantity, self._exchange_info_cache, operation=qty_op)
        if adj_qty is None or adj_qty <= Decimal('0'):
            logger.error(
                f"Order quantity {quantity} invalid after LOT_SIZE filter (Op: {qty_op}) for {symbol}. Adjusted: {adj_qty}")
            return None
        validation_price = adj_price if order_type == 'LIMIT' else Decimal('0')
        estimated_price_for_mkt = None
        if order_type == 'MARKET':
            # <<< Use the new method name >>>
            book_ticker = self.get_symbol_book_ticker(symbol)
            # Use ask price for sell market order check? Or last price? Using last price for now.
            if book_ticker and book_ticker.get('lastPrice'):
                estimated_price_for_mkt = book_ticker['lastPrice']
            # <<< End Use new method >>>
            else:
                logger.warning(
                    f"Could not get current price for MIN_NOTIONAL check on MARKET order for {symbol}.")
                min_notional_filter = get_symbol_filter(get_symbol_info_from_exchange_info(
                    symbol, self._exchange_info_cache), 'MIN_NOTIONAL')
                if min_notional_filter:
                    logger.error(
                        f"MIN_NOTIONAL check required for {symbol} but current price unavailable. Aborting.")
                    return None
        if not validate_order_filters(symbol=symbol, quantity=adj_qty, price=validation_price, exchange_info=self._exchange_info_cache, estimated_price=estimated_price_for_mkt):
            logger.error(
                f"Order (Type:{order_type}, Qty:{adj_qty}, Px:{adj_price or 'MKT'}) failed combined filter checks for {symbol}.")
            return None
        params = {'symbol': symbol, 'quantity': adj_qty}
        if adj_price is not None:
            params['price'] = adj_price
        return params

    def create_limit_buy(self, symbol: str, quantity: Decimal, price: Decimal, newClientOrderId: Optional[str] = None, **kwargs) -> Optional[Dict]:
        if not self.client:
            return None
        validated_params = self._prepare_and_validate_order(
            symbol, quantity, price, 'LIMIT')
        if not validated_params:
            return None
        api_qty = f"{validated_params['quantity']}"
        api_price = f"{validated_params['price']}"
        params_api = {'symbol': symbol,
                      'quantity': api_qty, 'price': api_price}
        if newClientOrderId:
            params_api['newClientOrderId'] = newClientOrderId
        params_api.update(kwargs)
        retries = 0
        while retries < self.max_retries:
            try:
                logger.info(
                    f"Placing Limit BUY: {api_qty} {symbol} @ {api_price} (Client ID: {newClientOrderId or 'N/A'})")
                order = self.client.order_limit_buy(**params_api)
                logger.info(f"Limit BUY placed: {order.get('orderId')}")
                return order
            except (BinanceAPIException, BinanceRequestException) as e:
                self._handle_api_error(e, f"create_limit_buy ({symbol})")
                if e.code == -2010:
                    return None
                retries += 1
                if retries >= self.max_retries:
                    logger.error(
                        f"Max retries reached for create_limit_buy ({symbol}).")
                    return None
                logger.warning(
                    f"Retrying create_limit_buy ({symbol}) in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
            except Exception as e:
                self._handle_api_error(e, f"create_limit_buy ({symbol})")
                return None
        return None

    def create_limit_sell(self, symbol: str, quantity: Decimal, price: Decimal, newClientOrderId: Optional[str] = None, **kwargs) -> Optional[Dict]:
        if not self.client:
            return None
        validated_params = self._prepare_and_validate_order(
            symbol, quantity, price, 'LIMIT')
        if not validated_params:
            return None
        api_qty = f"{validated_params['quantity']}"
        api_price = f"{validated_params['price']}"
        params_api = {'symbol': symbol,
                      'quantity': api_qty, 'price': api_price}
        if newClientOrderId:
            params_api['newClientOrderId'] = newClientOrderId
        params_api.update(kwargs)
        retries = 0
        while retries < self.max_retries:
            try:
                logger.info(
                    f"Placing Limit SELL: {api_qty} {symbol} @ {api_price} (Client ID: {newClientOrderId or 'N/A'})")
                order = self.client.order_limit_sell(**params_api)
                logger.info(f"Limit SELL placed: {order.get('orderId')}")
                return order
            except (BinanceAPIException, BinanceRequestException) as e:
                self._handle_api_error(e, f"create_limit_sell ({symbol})")
                if e.code == -2010:
                    return None
                retries += 1
                if retries >= self.max_retries:
                    logger.error(
                        f"Max retries reached for create_limit_sell ({symbol}).")
                    return None
                logger.warning(
                    f"Retrying create_limit_sell ({symbol}) in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
            except Exception as e:
                self._handle_api_error(e, f"create_limit_sell ({symbol})")
                return None
        return None

    def create_market_sell(self, symbol: str, quantity: Decimal, newClientOrderId: Optional[str] = None, **kwargs) -> Optional[Dict]:
        if not self.client:
            return None
        validated_params = self._prepare_and_validate_order(
            symbol, quantity, None, 'MARKET')
        if not validated_params:
            return None
        api_qty = f"{validated_params['quantity']}"
        params_api = {'symbol': symbol, 'quantity': api_qty}
        if newClientOrderId:
            params_api['newClientOrderId'] = newClientOrderId
        params_api.update(kwargs)
        retries = 0
        while retries < self.max_retries:
            try:
                logger.info(
                    f"Placing Market SELL: {api_qty} {symbol} (Client ID: {newClientOrderId or 'N/A'})")
                order = self.client.order_market_sell(**params_api)
                logger.info(f"Market SELL placed: {order.get('orderId')}")
                return order
            except (BinanceAPIException, BinanceRequestException) as e:
                self._handle_api_error(e, f"create_market_sell ({symbol})")
                if e.code == -2010:
                    return None
                retries += 1
                if retries >= self.max_retries:
                    logger.error(
                        f"Max retries reached for create_market_sell ({symbol}).")
                    return None
                logger.warning(
                    f"Retrying create_market_sell ({symbol}) in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
            except Exception as e:
                self._handle_api_error(e, f"create_market_sell ({symbol})")
                return None
        return None

    def get_order_status(self, symbol: str, orderId: Optional[str] = None, origClientOrderId: Optional[str] = None) -> Optional[Dict]:
        if not self.client:
            return None
        if not orderId and not origClientOrderId:
            logger.error(
                "Cannot get order status: orderId or origClientOrderId required.")
            return None
        params = {'symbol': symbol}
        if orderId:
            params['orderId'] = str(orderId)
        if origClientOrderId:
            params['origClientOrderId'] = str(origClientOrderId)
        id_to_log = orderId or origClientOrderId
        retries = 0
        while retries < self.max_retries:
            try:
                status = self.client.get_order(**params)
                if status:
                    numeric_fields = [
                        'price', 'origQty', 'executedQty', 'cummulativeQuoteQty', 'stopPrice']
                    for field in numeric_fields:
                        if field in status and status[field] is not None:
                            status[field] = to_decimal(
                                status[field], Decimal('0'))
                return status
            except (BinanceAPIException, BinanceRequestException) as e:
                if e.code == -2013:
                    logger.warning(
                        f"Order {id_to_log} not found. Code: {e.code}")
                    return None
                else:
                    self._handle_api_error(
                        e, f"get_order_status ({id_to_log})")
                    retries += 1
                if retries >= self.max_retries:
                    logger.error(
                        f"Max retries reached for get_order_status ({id_to_log}).")
                    return None
                logger.warning(
                    f"Retrying get_order_status ({id_to_log}) in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
            except Exception as e:
                self._handle_api_error(e, f"get_order_status ({id_to_log})")
                return None
        return None

    def get_open_orders(self, symbol: Optional[str] = None) -> Optional[List[Dict]]:
        if not self.client:
            return None
        params = {}
        context = f"get_open_orders ({symbol or 'all'})"
        if symbol:
            params['symbol'] = symbol
        retries = 0
        while retries < self.max_retries:
            try:
                open_orders = self.client.get_open_orders(**params)
                logger.debug(
                    f"Fetched {len(open_orders)} open orders for {symbol or 'all'}.")
                if open_orders:
                    numeric_fields = [
                        'price', 'origQty', 'executedQty', 'cummulativeQuoteQty', 'stopPrice']
                    for order in open_orders:
                        for field in numeric_fields:
                            if field in order and order[field] is not None:
                                order[field] = to_decimal(
                                    order[field], Decimal('0'))
                return open_orders
            except (BinanceAPIException, BinanceRequestException) as e:
                self._handle_api_error(e, context)
                retries += 1
                if retries >= self.max_retries:
                    logger.error(f"Max retries reached for {context}.")
                    return None
                logger.warning(f"Retrying {context} in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
            except Exception as e:
                self._handle_api_error(e, context)
                return None
        return None

    def cancel_order(self, symbol: str, orderId: Optional[str] = None, origClientOrderId: Optional[str] = None) -> bool:
        if not self.client:
            return False
        if not orderId and not origClientOrderId:
            logger.error(
                "Cannot cancel order: orderId or origClientOrderId required.")
            return False
        params = {'symbol': symbol}
        if orderId:
            params['orderId'] = str(orderId)
        if origClientOrderId:
            params['origClientOrderId'] = str(origClientOrderId)
        id_to_log = orderId or origClientOrderId
        context = f"cancel_order ({id_to_log})"
        retries = 0
        while retries < self.max_retries:
            try:
                result = self.client.cancel_order(**params)
                logger.info(
                    f"Order cancellation request successful for {id_to_log}. Response: {result}")
                return True
            except (BinanceAPIException, BinanceRequestException) as e:
                if e.code == -2011 or e.code == -2013:
                    logger.warning(
                        f"Order {id_to_log} not found for cancellation. Code: {e.code}")
                    return True
                else:
                    self._handle_api_error(e, context)
                    retries += 1
                if retries >= self.max_retries:
                    logger.error(f"Max retries reached for {context}.")
                    return False
                logger.warning(f"Retrying {context} in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
            except Exception as e:
                self._handle_api_error(e, context)
                return False
        return False

    def get_filter_value(self, symbol: str, filter_type: str, filter_key: str) -> Optional[str]:
        if not self._exchange_info_cache:
            logger.warning("Exchange info cache is empty.")
            return None
        symbol_info = get_symbol_info_from_exchange_info(
            symbol, self._exchange_info_cache)
        if not symbol_info:
            logger.warning(
                f"Symbol {symbol} not found in cached exchange info.")
            return None
        f = get_symbol_filter(symbol_info, filter_type)
        if f:
            return f.get(filter_key)
        else:
            return None


if __name__ == '__main__':
    # --- Test block requires imports and setup ---
    print("Running BinanceUS Connector Example (requires .env file with API keys)")
    # Basic logging for test block
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Need to load config for paths etc., and env vars for keys
    try:
        # Assuming settings.py is usable after path fix
        from config.settings import load_config, get_config_value  # Removed get_env_variable
        import sys
    except ImportError as ie:
        print(
            f"Import Error in example block (ensure project root is in path): {ie}")
        sys.exit(1)

    config = load_config()  # Load the combined config (YAML + Env Vars)
    if not config:
        print(
            "Failed to load config. Ensure config/config.yaml and potentially .env exist.")
        sys.exit(1)

    # <<< Get API keys from the loaded config dict >>>
    api_key = get_config_value(config, ('binance_us', 'api_key'))
    api_secret = get_config_value(config, ('binance_us', 'api_secret'))
    # <<< End Key Retrieval >>>

    if not api_key or not api_secret:
        print("Error: BINANCE_US_API_KEY and BINANCE_US_API_SECRET must be set in .env file or defined in config")
        sys.exit(1)
    # --- End Test Setup ---

    try:  # Add try block for connector instantiation and tests
        # Pass the loaded config to the constructor
        connector = BinanceUSConnector(api_key, api_secret, config, tld='us')

        # Test Server Time
        server_time = connector.get_server_time()
        print(f"\nServer Time: {server_time}")

        # Test Exchange Info (cached)
        ex_info = connector.get_exchange_info()
        # print(f"\nExchange Info (BTCUSD): {get_symbol_info_from_exchange_info('BTCUSD', ex_info)}")

        # <<< Test the CORRECTED method >>>
        book_ticker = connector.get_symbol_book_ticker('BTCUSDT')
        print(f"\nSymbol Book Ticker (BTCUSDT): {book_ticker}")
        # <<< END Test >>>

        # Test Get Balances
        balances = connector.get_balances()
        print(f"\nBalances (Non-zero Free): {balances}")

        # Test Get Klines
        klines_df = connector.fetch_prepared_klines('BTCUSDT', '1h', limit=5)
        print(f"\nLatest 5 Klines (BTCUSDT 1h):\n{klines_df}")

        # Test Get Open Orders (might be empty)
        open_orders = connector.get_open_orders('BTCUSDT')
        print(f"\nOpen Orders (BTCUSDT): {open_orders}")

    except ConnectionError as ce:
        print(f"Connection Error during example: {ce}")
    except Exception as ex:
        print(f"An unexpected error occurred during example: {ex}")
        logging.exception("Example block error details:")


# END OF FILE: src/connectors/binance_us.py
