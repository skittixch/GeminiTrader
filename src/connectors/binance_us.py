# START OF FILE: src/connectors/binance_us.py

import logging
import time
import hashlib
import hmac
import requests
import json
from decimal import Decimal
from typing import Dict, List, Optional, Any
from pathlib import Path
import pandas as pd  # Added missing import

# --- Add project root ---
# import sys
# _project_root = Path(__file__).resolve().parent.parent.parent
# if str(_project_root) not in sys.path:
#     sys.path.insert(0, str(_project_root))
# --- End ---

# Import base class if you have one, otherwise remove
# from src.connectors.base_connector import BaseConnector

# Import utilities carefully, handle potential ImportErrors during startup
try:
    from config.settings import get_config_value
    # Import the utility only if absolutely needed here, prefer passing data
    from src.utils.formatting import to_decimal, get_symbol_filter, get_symbol_info_from_exchange_info
except ImportError:
    # Fallback or raise error if essential utilities are missing
    logging.critical(
        "Failed to import necessary modules (settings/formatting) in binance_us.py", exc_info=True)
    raise

# Use standard python-binance client
from binance.client import Client  # Use standard client
from binance.exceptions import BinanceAPIException, BinanceRequestException


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

    # Class level cache for exchange info
    _exchange_info_cache: Optional[Dict] = None
    # Changed from Timestamp to float (seconds since epoch)
    _exchange_info_last_update: float = 0.0

    def __init__(self, api_key: str, api_secret: str, config: Dict, tld: str = 'us'):
        self.api_key = api_key
        self.api_secret = api_secret
        self.config = config
        self.tld = tld  # Store tld ('us' or 'com')
        # self.base_url = f"https://api.binance.{tld}" # Base URL handled by client tld

        # Initialize the python-binance client
        try:
            # Explicitly pass tld
            self.client = Client(api_key, api_secret, tld=self.tld)
            logger.info(f"Binance Client initialized for tld='{self.tld}'.")
            # Test connection during init
            self.get_server_time()
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.critical(
                f"Failed to initialize Binance Client (API/Request Error): {e}", exc_info=False)
            # Set client to None or re-raise to prevent usage
            self.client = None
            raise ConnectionError(
                f"Failed to connect to Binance.{self.tld}: {e}") from e
        except Exception as e:
            logger.critical(
                f"Failed to initialize Binance Client (Unexpected Error): {e}", exc_info=True)
            self.client = None
            raise ConnectionError(
                f"Unexpected error connecting to Binance.{self.tld}: {e}") from e

        # Cache configuration
        self.exchange_info_cache_path = Path(get_config_value(
            config, ('data', 'exchange_info_cache'), 'data/cache/exchange_info.json'))
        self.exchange_info_cache_minutes = get_config_value(
            # Default 24 hours
            config, ('trading', 'exchange_info_cache_minutes'), 1440)
        # Using different path based on thought process
        self.max_retries = get_config_value(config, ('api', 'max_retries'), 3)
        # Using different path based on thought process
        self.retry_delay = get_config_value(
            config, ('api', 'retry_delay_seconds'), 5)

        # Ensure cache directory exists
        self.exchange_info_cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Load exchange info on initialization (fetch if needed)
        self.get_exchange_info(force_refresh=False)
        if not self._exchange_info_cache:
            logger.warning(
                "Failed to load exchange info during initialization.")
            # Depending on strictness, could raise an error here

    def _handle_api_error(self, e: Exception, context: str = "API call") -> None:
        """Logs standardized API errors."""
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
        """Gets the current server time from Binance."""
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
        """Gets exchange information (symbols, filters, etc.). Uses caching."""
        cache_duration_seconds = self.exchange_info_cache_minutes * 60
        now = time.time()

        # Check memory cache validity
        if not force_refresh and BinanceUSConnector._exchange_info_cache and \
           (now - BinanceUSConnector._exchange_info_last_update < cache_duration_seconds):
            logger.debug("Returning cached exchange info (memory).")
            return BinanceUSConnector._exchange_info_cache

        # Try loading from file cache if memory cache is invalid/missing
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

        # Fetch fresh data from API
        if not self.client:
            logger.error(
                "Cannot fetch exchange info: Binance client not initialized.")
            # Return old cache if available, otherwise None
            return BinanceUSConnector._exchange_info_cache

        logger.info("Fetching fresh exchange info from API...")
        try:
            exchange_info = self.client.get_exchange_info()
            BinanceUSConnector._exchange_info_cache = exchange_info
            BinanceUSConnector._exchange_info_last_update = now
            logger.info("Successfully fetched fresh exchange info.")

            # Save to file cache
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
            # Return old cache if fetch fails
            return BinanceUSConnector._exchange_info_cache
        except Exception as e:
            self._handle_api_error(e, "get_exchange_info")
            # Return old cache if fetch fails
            return BinanceUSConnector._exchange_info_cache

    def get_exchange_info_cached(self) -> Optional[Dict]:
        """Returns the cached exchange info without fetching."""
        if BinanceUSConnector._exchange_info_cache:
            cache_age = time.time() - BinanceUSConnector._exchange_info_last_update
            max_age_seconds = self.exchange_info_cache_minutes * 60 * 1.1
            if cache_age > max_age_seconds:
                logger.warning(
                    f"Cached exchange info is older than configured max age ({cache_age/60:.1f}m > {self.exchange_info_cache_minutes*1.1:.1f}m). May be stale.")
            return BinanceUSConnector._exchange_info_cache
        else:
            # If no memory cache, try loading from file without forcing API fetch
            logger.info(
                "Memory cache empty, attempting to load from file cache...")
            # Re-call get_exchange_info which handles file loading logic
            return self.get_exchange_info(force_refresh=False)

    def get_klines(self, symbol: str, interval: str, limit: int = 500, startTime: Optional[int] = None, endTime: Optional[int] = None) -> Optional[List[List[Any]]]:
        """Gets Kline/candlestick data for a symbol."""
        if not self.client:
            logger.error("Cannot get klines: Binance client not initialized.")
            return None

        params = {'symbol': symbol, 'interval': interval, 'limit': limit}
        # Use string representation for start/end times if needed by client method
        if startTime:
            params['startTime'] = startTime
        if endTime:
            params['endTime'] = endTime

        retries = 0
        while retries < self.max_retries:
            try:
                # Use get_historical_klines if start is provided, otherwise get_klines
                # Check documentation if get_klines also supports start/end time args
                if startTime:
                    klines = self.client.get_historical_klines(symbol, interval, str(
                        startTime), end_str=str(endTime) if endTime else None, limit=limit)
                else:
                    klines = self.client.get_klines(**params)

                # logger.debug(f"Fetched {len(klines)} klines for {symbol} ({interval})")
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
        """Fetches klines and prepares them into a pandas DataFrame with Decimal types."""
        # Using the method from user's file structure
        logger.info(
            f"Fetching and preparing klines for {symbol}, {interval}, limit={limit}")
        raw_klines = self.get_klines(
            symbol, interval, limit, startTime, endTime)

        if raw_klines is None:
            logger.error("Failed to fetch raw klines.")
            return None
        if not raw_klines:
            logger.warning("Fetched raw klines list is empty.")
            return pd.DataFrame()  # Return empty DataFrame

        try:
            # Create DataFrame
            df = pd.DataFrame(raw_klines, columns=KLINE_COLUMN_NAMES)

            # Convert timestamp columns to datetime objects (UTC)
            df['open_time'] = pd.to_datetime(
                df['open_time'], unit='ms', utc=True)
            df['close_time'] = pd.to_datetime(
                df['close_time'], unit='ms', utc=True)

            # Set index
            df = df.set_index('open_time')

            # Convert numerical columns to Decimal using safe utility
            for col in KLINE_DECIMAL_CONVERSION_COLUMNS:
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda x: to_decimal(x, default=None))
                    # Keep as object to hold Decimals/None
                    df[col] = df[col].astype(object)
                else:
                    logger.warning(
                        f"Expected kline column '{col}' not found during conversion.")

            # Drop the 'ignore' column if it exists
            if 'ignore' in df.columns:
                df = df.drop(columns=['ignore'])

            # Basic validation after conversion
            check_cols = [
                c for c in KLINE_DECIMAL_CONVERSION_COLUMNS if c in df.columns]
            if df[check_cols].isnull().values.any():
                logger.warning(
                    f"NaN values found after Decimal conversion for {symbol}. Check raw data or conversion logic.")

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

    # === ADDED: get_ticker method ===

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Gets the latest price ticker information for a specific symbol."""
        if not self.client:
            logger.error("Cannot get ticker: Binance client not initialized.")
            return None
        logger.debug(f"Fetching ticker for {symbol}...")
        retries = 0
        while retries < self.max_retries:
            try:
                ticker_info = self.client.get_symbol_ticker(symbol=symbol)
                # Convert price to Decimal for consistency, handle potential None
                if ticker_info and 'price' in ticker_info:
                    # Standardize key 'lastPrice' for easier use elsewhere
                    ticker_info['lastPrice'] = to_decimal(ticker_info['price'])
                    # Remove original 'price' key? Optional, depends on usage. Let's keep it for now.
                    # ticker_info.pop('price', None)
                else:
                    logger.warning(
                        f"Ticker info received but 'price' key missing: {ticker_info}")
                    # Set lastPrice to None if missing
                    ticker_info['lastPrice'] = None

                # logger.debug(f"Fetched ticker for {symbol}: {ticker_info}")
                return ticker_info
            except (BinanceAPIException, BinanceRequestException) as e:
                self._handle_api_error(e, f"get_ticker ({symbol})")
                retries += 1
                if retries < self.max_retries:
                    logger.warning(
                        f"Retrying get_ticker ({symbol}) in {self.retry_delay}s... ({retries}/{self.max_retries})")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(
                        f"Max retries reached for get_ticker ({symbol}).")
                    return None
            except Exception as e:
                self._handle_api_error(e, f"get_ticker ({symbol})")
                return None
        return None
    # =============================

    def get_balances(self) -> Optional[Dict[str, Decimal]]:
        """Gets account balances, filtering for non-zero free assets."""
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
                        # Only include assets with a positive free balance
                        if free is not None and free > Decimal('0'):
                            balances[asset] = free
                    logger.debug(
                        f"Fetched {len(balances)} non-zero free balances.")
                    return balances
                else:
                    logger.warning(
                        "Could not parse balances from account info or 'balances' key missing.")
                    return None  # Indicate parsing failure or missing data
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
    # Using python-binance built-in order methods now, less need for _place_order wrapper

    def _prepare_and_validate_order(self, symbol: str, quantity: Decimal, price: Optional[Decimal], order_type: str) -> Optional[Dict]:
        """Internal helper to adjust params using filters and validate."""
        # exchange_info = self.get_exchange_info_cached() # Already fetched in init
        if not self._exchange_info_cache:
            logger.error(
                f"Order Prep Error ({symbol}): Exchange info not available.")
            return None

        # Apply filters based on order type
        # Price adjustment needed for LIMIT orders
        adj_price = None
        if price is not None:
            adj_price = apply_filter_rules_to_price(
                symbol, price, self._exchange_info_cache, operation='adjust')
            if adj_price is None or adj_price <= Decimal('0'):
                logger.error(
                    f"Order price {price} invalid after PRICE_FILTER for {symbol}. Adjusted: {adj_price}")
                return None

        # Quantity adjustment always needed
        # Default to 'floor' for safety unless specific need for 'ceil'/'adjust'
        qty_op = 'floor'
        adj_qty = apply_filter_rules_to_qty(
            symbol, quantity, self._exchange_info_cache, operation=qty_op)
        if adj_qty is None or adj_qty <= Decimal('0'):
            logger.error(
                f"Order quantity {quantity} invalid after LOT_SIZE filter (Op: {qty_op}) for {symbol}. Adjusted: {adj_qty}")
            return None

        # Validate combined filters (especially MIN_NOTIONAL)
        # Use estimated price = 0 for Market orders during validation check
        validation_price = adj_price if order_type == 'LIMIT' else Decimal('0')
        estimated_price_for_mkt = None
        if order_type == 'MARKET':
            # Try to get current price for market order validation
            ticker = self.get_ticker(symbol)
            if ticker and ticker.get('lastPrice'):
                estimated_price_for_mkt = ticker['lastPrice']
            else:
                logger.warning(
                    f"Could not get current price for MIN_NOTIONAL check on MARKET order for {symbol}. Validation may be inaccurate.")
                # Proceed without estimated price? Risky. Let's fail validation if price needed and unavailable.
                # Check if MIN_NOTIONAL filter exists first. If not, price doesn't matter.
                min_notional_filter = get_symbol_filter(get_symbol_info_from_exchange_info(
                    symbol, self._exchange_info_cache), 'MIN_NOTIONAL')
                if min_notional_filter:
                    logger.error(
                        f"MIN_NOTIONAL check required for {symbol} but current price unavailable for MARKET order. Aborting.")
                    return None  # Abort if check needed but price unknown

        # Pass estimated price only if it's a market order validation
        if not validate_order_filters(symbol=symbol, quantity=adj_qty, price=validation_price, exchange_info=self._exchange_info_cache, estimated_price=estimated_price_for_mkt):
            logger.error(
                f"Order (Type:{order_type}, Qty:{adj_qty}, Px:{adj_price or 'MKT'}) failed combined filter checks (Price/Lot/MinNotional) for {symbol}.")
            return None

        # Return validated and adjusted parameters
        params = {'symbol': symbol, 'quantity': adj_qty}
        if adj_price is not None:  # Only add price for limit orders
            params['price'] = adj_price
        return params

    def create_limit_buy(self, symbol: str, quantity: Decimal, price: Decimal, newClientOrderId: Optional[str] = None, **kwargs) -> Optional[Dict]:
        """Places a limit buy order after validation."""
        if not self.client:
            return None
        validated_params = self._prepare_and_validate_order(
            symbol, quantity, price, 'LIMIT')
        if not validated_params:
            return None

        # Convert validated Decimals back to strings for API
        api_qty = f"{validated_params['quantity']}"
        api_price = f"{validated_params['price']}"

        params_api = {'symbol': symbol,
                      'quantity': api_qty, 'price': api_price}
        if newClientOrderId:
            params_api['newClientOrderId'] = newClientOrderId
        params_api.update(kwargs)  # Add any extra kwargs

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
                    return None  # Insufficient funds - no retry
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
        """Places a limit sell order after validation."""
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
                    return None  # Insufficient funds
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
        """Places a market sell order after validation."""
        if not self.client:
            return None
        # Validate quantity and MIN_NOTIONAL (using estimated price if possible)
        validated_params = self._prepare_and_validate_order(
            symbol, quantity, None, 'MARKET')
        if not validated_params:
            return None

        api_qty = f"{validated_params['quantity']}"

        params_api = {'symbol': symbol, 'quantity': api_qty}
        # Add client ID if provided and supported
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
                # Market orders fill immediately, response contains fill info
                return order
            except (BinanceAPIException, BinanceRequestException) as e:
                self._handle_api_error(e, f"create_market_sell ({symbol})")
                if e.code == -2010:
                    return None  # Insufficient funds
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
        """Gets the status of a specific order."""
        if not self.client:
            return None
        if not orderId and not origClientOrderId:
            logger.error(
                "Cannot get order status: orderId or origClientOrderId required.")
            return None

        params = {'symbol': symbol}
        if orderId:
            params['orderId'] = str(orderId)  # Ensure string
        if origClientOrderId:
            params['origClientOrderId'] = str(
                origClientOrderId)  # Ensure string
        id_to_log = orderId or origClientOrderId

        retries = 0
        while retries < self.max_retries:
            try:
                status = self.client.get_order(**params)
                # logger.debug(f"Fetched order status for {id_to_log}: {status.get('status')}")
                # Convert numeric fields to strings for consistency before returning? Or Decimals?
                # Let's convert to Decimal for internal use, assuming downstream handles it.
                if status:
                    # Add stopPrice etc.
                    numeric_fields = [
                        'price', 'origQty', 'executedQty', 'cummulativeQuoteQty', 'stopPrice']
                    for field in numeric_fields:
                        if field in status and status[field] is not None:
                            status[field] = to_decimal(
                                status[field], Decimal('0'))
                return status
            except (BinanceAPIException, BinanceRequestException) as e:
                if e.code == -2013:  # Order does not exist
                    logger.warning(
                        f"Order {id_to_log} not found (likely filled/cancelled/expired). Code: {e.code}")
                    return None  # Return None to indicate not found
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
        """Gets all open orders, optionally filtered by symbol."""
        if not self.client:
            return None
        params = {}
        if symbol:
            params['symbol'] = symbol
        context = f"get_open_orders ({symbol or 'all'})"

        retries = 0
        while retries < self.max_retries:
            try:
                open_orders = self.client.get_open_orders(**params)
                logger.debug(
                    f"Fetched {len(open_orders)} open orders for {symbol or 'all'}.")
                # Convert numeric fields to Decimal
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
        """Cancels an existing order. Returns True if successful or already gone."""
        if not self.client:
            return False
        if not orderId and not origClientOrderId:
            logger.error(
                "Cannot cancel order: orderId or origClientOrderId required.")
            return False

        params = {'symbol': symbol}
        if orderId:
            params['orderId'] = str(orderId)  # Ensure string
        if origClientOrderId:
            params['origClientOrderId'] = str(
                origClientOrderId)  # Ensure string
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
                if e.code == -2011 or e.code == -2013:  # UNKNOWN_ORDER or Order does not exist
                    logger.warning(
                        f"Order {id_to_log} not found for cancellation (likely already filled/cancelled). Code: {e.code}")
                    return True  # Treat as success as the order is no longer active
                else:
                    self._handle_api_error(e, context)
                    retries += 1
                    if retries >= self.max_retries:
                        logger.error(f"Max retries reached for {context}.")
                        return False
                    logger.warning(
                        f"Retrying {context} in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
            except Exception as e:
                self._handle_api_error(e, context)
                return False
        return False

    # --- Filter Helper ---
    def get_filter_value(self, symbol: str, filter_type: str, filter_key: str) -> Optional[str]:
        """Helper to get a specific value from a specific filter for a symbol."""
        # Use cached info directly
        if not self._exchange_info_cache:
            logger.warning(
                "Attempted to get filter value, but exchange info cache is empty.")
            # Try to load it synchronously? Or rely on init/period refresh?
            # Let's rely on it being populated.
            return None

        symbol_info = get_symbol_info_from_exchange_info(
            symbol, self._exchange_info_cache)
        if not symbol_info:
            logger.warning(
                f"Symbol {symbol} not found in cached exchange info for filter retrieval.")
            return None

        f = get_symbol_filter(symbol_info, filter_type)
        if f:
            return f.get(filter_key)
        else:
            # logger.debug(f"Filter type {filter_type} not found for symbol {symbol}.")
            return None


# Example usage block remains the same conceptually
if __name__ == '__main__':
    # ... (Keep the existing __main__ block for standalone testing) ...
    # Ensure it uses the updated method names and logic if testing orders.
    print("Running BinanceUS Connector Example (requires .env file with API keys)")
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Load config to get paths etc, but API keys MUST be in .env
    try:  # Add try block for imports
        from config.settings import load_config, get_env_variable
        import sys  # Import sys for exit
    except ImportError as ie:
        print(f"Import Error in example block: {ie}")
        sys.exit(1)

    config = load_config()
    if not config:
        print("Failed to load config. Ensure config files exist.")
        sys.exit(1)

    api_key = get_env_variable('BINANCE_US_API_KEY')
    api_secret = get_env_variable('BINANCE_US_API_SECRET')

    if not api_key or not api_secret:
        print(
            "Error: BINANCE_US_API_KEY and BINANCE_US_API_SECRET must be set in .env file")
        sys.exit(1)

    try:  # Add try block for connector instantiation and tests
        connector = BinanceUSConnector(api_key, api_secret, config, tld='us')

        # Test Server Time
        server_time = connector.get_server_time()
        print(f"\nServer Time: {server_time}")

        # Test Exchange Info (cached)
        ex_info = connector.get_exchange_info()
        # print(f"\nExchange Info (BTCUSD): {get_symbol_info_from_exchange_info('BTCUSD', ex_info)}")

        # Test Get Ticker
        ticker = connector.get_ticker('BTCUSDT')  # Use USDT as per config
        print(f"\nTicker (BTCUSDT): {ticker}")

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
