# START OF FILE: src/connectors/binance_us.py

import logging
import time
import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from decimal import Decimal, InvalidOperation  # Added InvalidOperation
from typing import Dict, List, Optional, Any

# Utilities
try:
    from src.utils.formatting import (
        to_decimal,  # Use this consistently
        get_symbol_info_from_exchange_info,
        apply_filter_rules_to_price,
        apply_filter_rules_to_qty,
        validate_order_filters
    )
    from config.settings import get_config_value
except ImportError:
    logger = logging.getLogger(__name__)
    if not logger.hasHandlers():
        logging.basicConfig(level=logging.ERROR)
    logger.critical(
        "CRITICAL: Failed imports in binance_us.py.", exc_info=True)
    # Define dummies
    def get_symbol_info_from_exchange_info(*args, **kwargs): return None

    def apply_filter_rules_to_price(
        *args, **kwargs): return kwargs.get('price')
    def apply_filter_rules_to_qty(
        *args, **kwargs): return kwargs.get('quantity')

    def validate_order_filters(*args, **kwargs): return False
    def get_config_value(cfg, path, default=None): return default

    def to_decimal(v, default=None):
        try:
            return Decimal(str(v)) if v is not None else default
        except (InvalidOperation, TypeError):
            return default

logger = logging.getLogger(__name__)

# Kline columns based on Binance API response structure
KLINE_COLUMN_NAMES = [
    'open_time', 'open', 'high', 'low', 'close', 'volume',
    'close_time', 'quote_asset_volume', 'number_of_trades',
    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
]
KLINE_DECIMAL_CONVERSION_COLUMNS = [
    'open', 'high', 'low', 'close', 'volume', 'quote_asset_volume',
    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume'
]


class BinanceUSConnector:
    """Handles connection and API calls to Binance.US."""

    def __init__(self, api_key: str, api_secret: str, config: Dict, tld: str = 'us'):
        """ Initializes the Binance US Connector. """
        if not api_key or not api_secret:
            logger.error("API Key or Secret not provided.")
            raise ValueError("API Key and Secret required.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.tld = tld
        self.config = config  # Store the whole config dict
        self._client: Optional[Client] = None
        self._exchange_info_cache: Optional[Dict] = None
        self._exchange_info_cache_time: Optional[pd.Timestamp] = None
        self._connect()
        if self._client:
            self.get_exchange_info()  # Initial cache fetch

    def _connect(self):
        """Establishes connection."""
        try:
            # Allow specifying API URL via config if needed in the future
            # api_url = get_config_value(self.config, ('api_endpoints', 'binance_us_api'), f"https://api.binance.{self.tld}")
            # python-binance handles URL via tld
            self._client = Client(self.api_key, self.api_secret, tld=self.tld)
            self.get_server_time()  # Test connection
            logger.info(f"Binance.{self.tld} connection established.")
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"Failed connect Binance.{self.tld}: {e}")
            self._client = None
        except Exception as e:
            logger.exception(
                f"Unexpected error connecting Binance.{self.tld}: {e}")
            self._client = None

    def get_client(self) -> Optional[Client]:
        """Gets client, attempts reconnect if needed."""
        if self._client is None:
            logger.warning("Binance client gone. Reconnecting...")
            self._connect()
        return self._client

    def get_exchange_info(self, force_refresh: bool = False) -> Optional[Dict]:
        """Retrieves/caches exchange info."""
        cache_duration_cfg = get_config_value(
            self.config, ('trading_options', 'exchange_info_cache_minutes'), 60 * 24)
        cache_duration_minutes = int(cache_duration_cfg)
        now = pd.Timestamp.utcnow()
        # Check cache validity
        if not force_refresh and self._exchange_info_cache and self._exchange_info_cache_time and \
           (now - self._exchange_info_cache_time) < pd.Timedelta(minutes=cache_duration_minutes):
            logger.debug("Using cached exchange info.")
            return self._exchange_info_cache

        client = self.get_client()
        if not client:
            return None
        try:
            logger.info(
                f"Fetching fresh exchange info (Cache: {cache_duration_minutes}m)...")
            info = client.get_exchange_info()
            if not info or 'symbols' not in info:  # Basic validation
                logger.error("Fetched exchange info is invalid or empty.")
                return self._exchange_info_cache  # Return old cache if fetch failed
            self._exchange_info_cache = info
            self._exchange_info_cache_time = now
            logger.info(
                f"Exchange info refreshed and cached ({len(info.get('symbols', []))} symbols).")
            return info
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error fetching exchange info: {e}")
            return self._exchange_info_cache  # Return old cache if fetch failed
        except Exception as e:
            logger.exception(f"Unexpected error fetching exchange info: {e}")
            return self._exchange_info_cache

    def get_exchange_info_cached(self) -> Optional[Dict]:
        """Returns cached exchange info."""
        if not self._exchange_info_cache:
            logger.warning("Attempting to use empty exchange info cache.")
        return self._exchange_info_cache

    def get_filters(self, symbol: str) -> Optional[List[Dict]]:
        """Helper to get filters for a specific symbol from cached info."""
        symbol_info = self.get_symbol_info(symbol)
        if symbol_info and 'filters' in symbol_info:
            return symbol_info['filters']
        logger.warning(
            f"Could not retrieve filters for symbol '{symbol}' from exchange info.")
        return None

    def get_server_time(self) -> Optional[int]:
        """Gets server time (ms)."""
        client = self.get_client()
        if not client:
            return None
        try:
            return client.get_server_time()['serverTime']
        except Exception as e:
            logger.error(f"API Error get server time: {e}")
            return None

    def get_account_info(self) -> Optional[Dict]:
        """Retrieves account info."""
        client = self.get_client()
        if not client:
            return None
        try:
            return client.get_account()
        except Exception as e:
            logger.error(f"API Error get account info: {e}")
            return None

    def get_asset_balance(self, asset: str) -> Optional[Decimal]:
        """Retrieves the free balance for a specific asset as Decimal."""
        client = self.get_client()
        if not client:
            return None
        try:
            balance = client.get_asset_balance(asset=asset)
            if balance:
                free_balance = to_decimal(
                    balance.get('free'))  # Use safe conversion
                return free_balance if free_balance is not None else Decimal('0.0')
            else:
                logger.warning(f"Asset {asset} not found in balance response.")
                return Decimal('0.0')
        except Exception as e:
            logger.error(f"API Error get balance {asset}: {e}")
            return None

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Retrieves info for specific symbol using cache."""
        exchange_info = self.get_exchange_info_cached()  # Rely on cached
        if exchange_info:
            symbol_info = get_symbol_info_from_exchange_info(
                symbol, exchange_info)  # Use utility
            if symbol_info:
                logger.debug(f"Symbol info cache hit for {symbol}.")
            else:
                logger.warning(
                    f"Symbol {symbol} not found in cached exchange info.")
            return symbol_info
        else:
            logger.error("Failed get cached exchange info for symbol info.")
            return None

    def get_klines(self, symbol: str, interval: str, start_str: Optional[str] = None, end_str: Optional[str] = None, limit: int = 1000) -> Optional[List[List[Any]]]:
        """Retrieves raw kline/candlestick data list."""
        client = self.get_client()
        if not client:
            return None
        try:
            # Ensure limit is within bounds if needed (e.g., max 1000 for historical)
            limit = min(limit, 1000)
            logger.debug(
                f"Fetching klines: {symbol}, {interval}, limit={limit}, start={start_str}, end={end_str}")
            # Use get_historical_klines if start_str is provided, else get_klines
            if start_str:
                klines = client.get_historical_klines(
                    symbol, interval, start_str, end_str=end_str, limit=limit)
            else:
                klines = client.get_klines(
                    symbol=symbol, interval=interval, limit=limit)
            logger.debug(f"Fetched {len(klines)} raw kline rows.")
            return klines
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error get klines {symbol} ({interval}): {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error get klines {symbol} ({interval}): {e}")
            return None

    # --- NEW METHOD ---
    def fetch_prepared_klines(self, symbol: str, interval: str, limit: int = 200) -> Optional[pd.DataFrame]:
        """Fetches klines and prepares them into a pandas DataFrame with Decimal types."""
        logger.info(
            f"Fetching and preparing klines for {symbol}, {interval}, limit={limit}")
        raw_klines = self.get_klines(
            symbol=symbol, interval=interval, limit=limit)

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

            # Convert numerical columns to Decimal
            for col in KLINE_DECIMAL_CONVERSION_COLUMNS:
                if col in df.columns:
                    # Apply safe conversion using utility
                    df[col] = df[col].apply(
                        lambda x: to_decimal(x, default=None))
                    # Ensure object dtype for Decimals/None
                    df[col] = df[col].astype(object)
                else:
                    logger.warning(
                        f"Expected kline column '{col}' not found during conversion.")

            # Drop the 'ignore' column if it exists
            if 'ignore' in df.columns:
                df = df.drop(columns=['ignore'])

            # Basic validation after conversion
            if df[KLINE_DECIMAL_CONVERSION_COLUMNS].isnull().values.any():
                logger.warning(
                    f"NaN values found after Decimal conversion for {symbol}. Check raw data.")

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

    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Gets latest price for symbol as Decimal."""
        client = self.get_client()
        if not client:
            return None
        try:
            ticker = client.get_symbol_ticker(symbol=symbol)
            price = to_decimal(ticker.get('price'))  # Use safe conversion
            if price:
                logger.debug(f"Current price {symbol}: {price}")
                return price
            else:
                logger.error(f"Could not parse price from ticker: {ticker}")
                return None
        except Exception as e:
            logger.error(f"API Error get ticker price {symbol}: {e}")
            return None

    # --- Order Management Methods (Logic using _prepare_order_params needs review if config access changed) ---

    def _prepare_order_params(self, symbol: str, quantity: Decimal, price: Optional[Decimal] = None, is_base_asset_qty: bool = True) -> Optional[Dict[str, Any]]:
        """Internal helper to adjust quantity/price and check filters."""
        # --- This function NOW relies on self.config being the dictionary ---
        exchange_info = self.get_exchange_info_cached()
        if not exchange_info:
            logger.error(f"Order Prep {symbol}: Exchange info not cached.")
            return None

        filters = self.get_filters(symbol)
        if not filters:
            logger.error(f"Order Prep {symbol}: Could not get filters.")
            return None

        adj_price = price
        if price is not None:  # Limit orders
            adj_price = apply_filter_rules_to_price(
                price, filters, symbol=symbol)  # Pass symbol
            if adj_price is None or adj_price <= 0:
                logger.error(
                    f"Order price {price} invalid after filters for {symbol}. Adjusted: {adj_price}")
                return None

        # Adjust quantity - Pass symbol
        adj_qty = apply_filter_rules_to_qty(
            quantity, filters, is_base_asset=is_base_asset_qty, symbol=symbol)
        if adj_qty is None or adj_qty <= 0:
            logger.error(
                f"Order quantity {quantity} invalid after filters for {symbol}. Adjusted: {adj_qty}")
            return None

        # Check MIN_NOTIONAL (only for limit orders where price is known)
        if price is not None:
            # Pass symbol
            if not validate_order_filters(adj_price, adj_qty, filters, symbol=symbol):
                logger.error(
                    f"Order failed filter checks (e.g., MIN_NOTIONAL): Price={adj_price}, Qty={adj_qty} for {symbol}.")
                return None

        params = {'symbol': symbol, 'quantity': f"{adj_qty}"}
        if adj_price is not None:
            params['price'] = f"{adj_price}"
        return params

    # Note: The create_* methods implicitly use the config via _prepare_order_params if it accesses self.config
    # Ensure all config access uses get_config_value or direct dict access now.

    def create_limit_buy(self, symbol: str, quantity: Decimal, price: Decimal, **kwargs) -> Optional[Dict]:
        """Places limit buy after applying filters."""
        client = self.get_client()
        if not client:
            return None
        # is_base_asset_qty defaults to True
        params = self._prepare_order_params(symbol, quantity, price)
        if not params:
            return None
        try:
            logger.info(
                f"Placing Limit BUY: {params['quantity']} {symbol} @ {params['price']}")
            order = client.order_limit_buy(
                symbol=params['symbol'], quantity=params['quantity'], price=params['price'], **kwargs)
            logger.info(f"Limit BUY placed: {order.get('orderId')}")
            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error limit buy {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error limit buy {symbol}: {e}")
            return None

    def create_limit_sell(self, symbol: str, quantity: Decimal, price: Decimal, **kwargs) -> Optional[Dict]:
        """Places limit sell after applying filters."""
        client = self.get_client()
        if not client:
            return None
        # is_base_asset_qty defaults to True
        params = self._prepare_order_params(symbol, quantity, price)
        if not params:
            return None
        try:
            logger.info(
                f"Placing Limit SELL: {params['quantity']} {symbol} @ {params['price']}")
            order = client.order_limit_sell(
                symbol=params['symbol'], quantity=params['quantity'], price=params['price'], **kwargs)
            logger.info(f"Limit SELL placed: {order.get('orderId')}")
            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error limit sell {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error limit sell {symbol}: {e}")
            return None

    def create_market_sell(self, symbol: str, quantity: Decimal, **kwargs) -> Optional[Dict]:
        """Places market sell after applying qty filter."""
        client = self.get_client()
        if not client:
            return None
        exchange_info = self.get_exchange_info_cached()
        if not exchange_info:
            logger.error(f"Market Sell {symbol}: Exchange info NA.")
            return None
        filters = self.get_filters(symbol)
        if not filters:
            logger.error(f"Market Sell {symbol}: Filters NA.")
            return None

        # Apply only quantity filter
        adj_qty = apply_filter_rules_to_qty(
            quantity, filters, is_base_asset=True, symbol=symbol)  # Pass symbol
        if adj_qty is None or adj_qty <= 0:
            logger.error(
                f"Market Sell {symbol}: Invalid qty {quantity} after filter: {adj_qty}")
            return None

        # Skipping pre-emptive MIN_NOTIONAL check for market orders
        try:
            qty_str = f"{adj_qty}"
            logger.info(f"Placing Market SELL: {qty_str} {symbol}")
            order = client.order_market_sell(
                symbol=symbol, quantity=qty_str, **kwargs)
            logger.info(f"Market SELL placed: {order.get('orderId')}")
            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error market sell {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error market sell {symbol}: {e}")
            return None

    # --- cancel_order, get_order_status, get_open_orders remain largely the same ---
    # Minor update: Pass origClientOrderId to get_order_status if available
    # Minor update: Add origClientOrderId parameter to cancel_order

    def cancel_order(self, symbol: str, orderId: Optional[str] = None, origClientOrderId: Optional[str] = None) -> Optional[Dict]:
        """Cancels an open order by orderId or origClientOrderId."""
        client = self.get_client()
        if not client:
            return None
        if not orderId and not origClientOrderId:
            logger.error("Cancel order requires orderId or origClientOrderId.")
            return None
        cancel_args = {'symbol': symbol}
        if origClientOrderId:
            cancel_args['origClientOrderId'] = origClientOrderId
        elif orderId:
            cancel_args['orderId'] = orderId
        target_id = origClientOrderId or orderId

        try:
            logger.info(f"Attempting cancel order {target_id} for {symbol}...")
            result = client.cancel_order(**cancel_args)
            logger.info(f"Order cancel result {target_id}: {result}")
            return result
        except (BinanceAPIException, BinanceRequestException) as e:
            if e.code == -2011:
                logger.warning(
                    f"Order {target_id} not found or already filled/cancelled: {e.message}")
                return {'status': 'UNKNOWN', 'message': e.message}
            else:
                logger.error(
                    f"API Error cancel order {target_id} for {symbol}: {e}")
                return None
        except Exception as e:
            logger.exception(
                f"Unexpected error cancel order {target_id} for {symbol}: {e}")
            return None

    def get_order_status(self, symbol: str, orderId: Optional[str] = None, origClientOrderId: Optional[str] = None) -> Optional[Dict]:
        """Retrieves status of order by orderId or origClientOrderId."""
        client = self.get_client()
        if not client:
            return None
        if not orderId and not origClientOrderId:
            logger.error(
                "Get order status requires orderId or origClientOrderId.")
            return None
        status_args = {'symbol': symbol}
        if origClientOrderId:
            status_args['origClientOrderId'] = origClientOrderId
        elif orderId:
            status_args['orderId'] = orderId
        target_id = origClientOrderId or orderId

        try:
            order = client.get_order(**status_args)
            logger.debug(
                f"Status order {target_id} ({symbol}): {order.get('status')}")
            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            if e.code == -2013:
                logger.warning(f"Order {target_id} not found: {e.message}")
                return {'status': 'UNKNOWN', 'message': e.message}
            logger.error(
                f"API Error get order status {target_id} for {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error get order status {target_id} for {symbol}: {e}")
            return None

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Retrieves open orders, optionally filtered by symbol."""
        client = self.get_client()
        if not client:
            return []
        try:
            orders = client.get_open_orders(
                symbol=symbol) if symbol else client.get_open_orders()
            logger.info(
                f"Retrieved {len(orders)} open orders (symbol={symbol or 'All'}).")
            return orders
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error get open orders (symbol={symbol}): {e}")
            return []
        except Exception as e:
            logger.exception(
                f"Unexpected error get open orders (symbol={symbol}): {e}")
            return []


# Example usage block updated slightly
if __name__ == '__main__':
    print("Running BinanceUSConnector example...")
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Starting example...")
    try:
        from config.settings import load_config  # Keep this local for example
        test_config = load_config()
        if not test_config:
            raise ValueError("Failed load test config")
        api_key = get_config_value(test_config, ('binance_us', 'api_key'))
        api_secret = get_config_value(
            test_config, ('binance_us', 'api_secret'))

        if not api_key or not api_secret or 'YOUR_ACTUAL' in api_key:
            logger.warning(
                "API Key/Secret NA or placeholder found. Skipping connection tests.")
        else:
            connector = BinanceUSConnector(
                api_key=api_key, api_secret=api_secret, config=test_config)
            client = connector.get_client()
            if client:
                logger.info("Connection test successful via get_client().")

                # Test fetching prepared klines
                logger.info("\n--- Testing fetch_prepared_klines ---")
                test_symbol_klines = 'BTCUSDT'
                klines_df = connector.fetch_prepared_klines(
                    symbol=test_symbol_klines, interval='1h', limit=5)
                if klines_df is not None:
                    logger.info(
                        f"Prepared klines head for {test_symbol_klines}:\n{klines_df.head().to_markdown()}")
                    klines_df.info()
                else:
                    logger.error(
                        f"Failed to fetch prepared klines for {test_symbol_klines}.")

                # --- Live Order Test (Use with extreme caution!) ---
                logger.warning(
                    "\n--- Live Order Placement Test Block (DISABLED BY DEFAULT) ---")
                # <<< SET TO TRUE ONLY IF YOU INTEND TO PLACE REAL ORDERS >>>
                enable_live_order_test = False
                if enable_live_order_test:
                    logger.warning("!!! LIVE ORDER TEST ENABLED !!!")
                    test_symbol_order = 'DOGEUSDT'  # Use a low value pair if testing!
                    # Example price WAY below market for safety
                    test_price = Decimal('0.0500')
                    # Example quantity (check MIN_NOTIONAL!)
                    test_qty = Decimal('100')
                    current_price = connector.get_current_price(
                        test_symbol_order)
                    logger.info(
                        f"Current {test_symbol_order} price: {current_price}")

                    if current_price and test_price < current_price:
                        logger.info(
                            f"Attempting Limit BUY {test_qty} {test_symbol_order} @ {test_price}...")
                        buy_order = connector.create_limit_buy(
                            test_symbol_order, test_qty, test_price, newClientOrderId=f'test_{int(time.time())}')
                        if buy_order and buy_order.get('orderId'):
                            buy_order_id = buy_order['orderId']
                            buy_oco_id = buy_order.get('origClientOrderId')
                            logger.info(
                                f"BUY Order ID: {buy_order_id}, ClientOrderID: {buy_oco_id}")
                            time.sleep(2)
                            logger.info(
                                f"Checking status for {buy_order_id}...")
                            status = connector.get_order_status(
                                test_symbol_order, orderId=buy_order_id, origClientOrderId=buy_oco_id)
                            logger.info(
                                f"Status: {status.get('status') if status else 'Error'}")
                            logger.info("Checking open orders...")
                            open_orders = connector.get_open_orders(
                                test_symbol_order)
                            logger.info(
                                f"Found {len(open_orders)} open {test_symbol_order} orders.")
                            logger.info(
                                f"Attempting cancel order {buy_order_id}...")
                            cancel_result = connector.cancel_order(
                                test_symbol_order, orderId=buy_order_id, origClientOrderId=buy_oco_id)
                            logger.info(f"Cancel Result: {cancel_result}")
                            time.sleep(2)
                            logger.info(
                                f"Re-checking status for {buy_order_id}...")
                            status_after = connector.get_order_status(
                                test_symbol_order, orderId=buy_order_id, origClientOrderId=buy_oco_id)
                            logger.info(
                                f"Status after cancel: {status_after.get('status') if status_after else 'Error'}")
                        else:
                            logger.error("Failed place limit buy order.")
                    else:
                        logger.warning(
                            f"Skipping live order test: Test price {test_price} not below current {current_price} or price fetch failed.")
                # --- End Live Order Test ---
            else:
                logger.error("Connection test failed.")
    except ImportError:
        logger.error("Could not import load_config for example.")
    except Exception as main_e:
        logger.exception(f"An error occurred in the example block: {main_e}")
    logger.info("Example finished.")


# END OF FILE: src/connectors/binance_us.py
