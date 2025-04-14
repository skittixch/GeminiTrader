# START OF FILE: src/connectors/binance_us.py

import logging
import time  # Added for potential rate limiting
import pandas as pd  # Added for Timestamp
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from decimal import Decimal
from typing import Dict, List, Optional, Any

# Utilities are needed within order methods
try:
    from src.utils.formatting import (
        to_decimal,
        get_symbol_info_from_exchange_info,
        apply_filter_rules_to_price,
        apply_filter_rules_to_qty,
        validate_order_filters
    )
    from config.settings import get_config_value  # For config access if needed
except ImportError:
    # Setup basic logging/print if imports fail during init/testing
    logger = logging.getLogger(__name__)
    if not logger.hasHandlers():
        logging.basicConfig(level=logging.ERROR)
    logger.critical(
        "CRITICAL: Failed imports in binance_us.py.", exc_info=True)
    # Define dummies or raise error
    def get_symbol_info_from_exchange_info(*args, **kwargs): return None

    def apply_filter_rules_to_price(
        *args, **kwargs): return kwargs.get('price')
    def apply_filter_rules_to_qty(
        *args, **kwargs): return kwargs.get('quantity')

    def validate_order_filters(*args, **kwargs): return False
    def get_config_value(cfg, path, default=None): return default
    def to_decimal(v, default=None): return Decimal(
        v) if v is not None else default
    # raise ImportError("CRITICAL: Missing essential imports for BinanceUSConnector.")


logger = logging.getLogger(__name__)


class BinanceUSConnector:
    """Handles connection and API calls to Binance.US."""

    def __init__(self, api_key: str, api_secret: str, config: Dict, tld: str = 'us'):
        """ Initializes the Binance US Connector. """
        if not api_key or not api_secret:
            logger.error(
                "API Key or Secret not provided for BinanceUSConnector.")
            raise ValueError(
                "API Key and Secret are required for BinanceUSConnector")

        self.api_key = api_key
        self.api_secret = api_secret
        self.tld = tld
        self.config = config
        self._client: Optional[Client] = None
        self._exchange_info_cache: Optional[Dict] = None
        self._exchange_info_cache_time: Optional[pd.Timestamp] = None
        self._connect()
        # Fetch and cache exchange info immediately after connecting if possible
        if self._client:
            self.get_exchange_info()

    def _connect(self):
        """Establishes the connection to the Binance API."""
        try:
            self._client = Client(self.api_key, self.api_secret, tld=self.tld)
            self.get_server_time()  # Test connection
            logger.info("Binance.US connection established successfully.")
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"Failed to connect to Binance.US API: {e}")
            self._client = None
        except Exception as e:
            logger.exception(
                f"Unexpected error during Binance.US connection: {e}")
            self._client = None

    def get_client(self) -> Optional[Client]:
        """Returns the initialized Binance API client instance, attempting reconnect if needed."""
        if self._client is None:
            logger.warning(
                "Binance client not initialized. Attempting reconnect...")
            self._connect()
        return self._client

    # --- Exchange Info Caching Methods ---
    def get_exchange_info(self, force_refresh: bool = False) -> Optional[Dict]:
        """Retrieves/caches exchange info."""
        cache_duration_cfg = get_config_value(
            self.config, ('trading', 'exchange_info_cache_minutes'), 60 * 24)
        cache_duration_minutes = int(cache_duration_cfg)
        now = pd.Timestamp.utcnow()
        if not force_refresh and self._exchange_info_cache and self._exchange_info_cache_time and \
           (now - self._exchange_info_cache_time) < pd.Timedelta(minutes=cache_duration_minutes):
            logger.debug("Using cached exchange info.")
            return self._exchange_info_cache
        client = self.get_client()
        if not client:
            return None
        try:
            logger.info(
                f"Fetching fresh exchange info (Cache duration: {cache_duration_minutes} mins)...")
            info = client.get_exchange_info()
            self._exchange_info_cache = info
            self._exchange_info_cache_time = now
            logger.info("Exchange info retrieved and cached.")
            return info
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error get exchange info: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error get exchange info: {e}")
            return None

    def get_exchange_info_cached(self) -> Optional[Dict]:
        """Returns the cached exchange info, if available."""
        if not self._exchange_info_cache:
            logger.warning("Exchange info cache is empty.")
        return self._exchange_info_cache

    # --- Wrapper Methods for Common API Calls (Read-only) ---
    def get_server_time(self) -> Optional[int]:
        """Gets the current server time."""
        client = self.get_client()
        if not client:
            return None
        try:
            return client.get_server_time()['serverTime']
        except Exception as e:
            logger.error(f"API Error get server time: {e}")
            return None

    def get_account_info(self) -> Optional[Dict]:
        """Retrieves account information."""
        client = self.get_client()
        if not client:
            return None
        try:
            return client.get_account()
        except Exception as e:
            logger.error(f"API Error get account info: {e}")
            return None

    def get_asset_balance(self, asset: str) -> Optional[Decimal]:
        """Retrieves the free balance for a specific asset."""
        client = self.get_client()
        if not client:
            return None
        try:
            balance = client.get_asset_balance(asset=asset)
            if balance:
                free_balance = to_decimal(balance['free'])
                return free_balance if free_balance is not None else Decimal('0.0')
            else:
                logger.warning(f"Asset {asset} not found.")
                return Decimal('0.0')
        except Exception as e:
            logger.error(f"API Error get balance {asset}: {e}")
            return None

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Retrieves information for a specific symbol using cache."""
        exchange_info = self.get_exchange_info()  # Uses internal cache logic
        if exchange_info:
            symbol_info = get_symbol_info_from_exchange_info(
                symbol, exchange_info)
            if symbol_info:
                logger.debug(f"Cache: Info retrieved for {symbol}.")
                return symbol_info
            else:
                logger.warning(f"Cache: Symbol {symbol} not found.")
                return None
        else:
            logger.error("Failed get exchange info for symbol info.")
            return None

    def get_klines(self, symbol: str, interval: str, start_str: Optional[str] = None, end_str: Optional[str] = None, limit: int = 1000) -> Optional[List[List[Any]]]:
        """Retrieves kline/candlestick data."""
        client = self.get_client()
        if not client:
            return None
        try:
            return client.get_historical_klines(symbol, interval, start_str=start_str, end_str=end_str, limit=limit)
        except Exception as e:
            logger.error(f"API Error get klines {symbol} ({interval}): {e}")
            return None

    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """ Gets the latest price for a symbol. """
        client = self.get_client()
        if not client:
            return None
        try:
            ticker = client.get_symbol_ticker(symbol=symbol)
            price = to_decimal(ticker.get('price'))
            if price:
                logger.debug(f"Current price for {symbol}: {price}")
                return price
            else:
                logger.error(f"Could not parse price from ticker: {ticker}")
                return None
        except Exception as e:
            logger.error(f"API Error get ticker price {symbol}: {e}")
            return None

    # --- Order Management Methods ---

    def _prepare_order_params(self, symbol: str, quantity: Decimal, price: Optional[Decimal] = None) -> Optional[Dict[str, Any]]:
        """Internal helper to adjust quantity/price and check filters."""
        exchange_info = self.get_exchange_info_cached()
        if not exchange_info:
            logger.error(
                f"Cannot prepare order for {symbol}: Exchange info not cached.")
            return None

        adj_price = price  # For market orders, price is None initially
        if price is not None:  # Adjust price for limit orders
            # Use 'adjust' for limit orders - let exchange match best possible if needed
            # Use 'floor'/'ceil' depending on BUY/SELL? Let's stick with 'adjust' for now.
            adj_price = apply_filter_rules_to_price(
                symbol, price, exchange_info, operation='adjust')
            if adj_price is None or adj_price <= 0:
                logger.error(
                    f"Order price {price} invalid after filter adjustment for {symbol}. Adjusted: {adj_price}")
                return None

        # Adjust quantity (use floor)
        adj_qty = apply_filter_rules_to_qty(
            symbol, quantity, exchange_info, operation='floor')
        if adj_qty is None or adj_qty <= 0:
            logger.error(
                f"Order quantity {quantity} invalid after filter adjustment for {symbol}. Adjusted: {adj_qty}")
            return None

        # Use adjusted price for min_notional check if it's a limit order,
        # otherwise need current market price for market order check (complex!)
        # For simplicity now, only check MIN_NOTIONAL for limit orders where price is known.
        # Market order notional check should happen *before* calling create_market_sell
        if price is not None:
            if not validate_order_filters(symbol, adj_price, adj_qty, exchange_info):
                logger.error(
                    f"Order failed MIN_NOTIONAL check: Price={adj_price}, Qty={adj_qty} for {symbol}.")
                return None

        # API expects string quantity
        params = {'symbol': symbol, 'quantity': f"{adj_qty}"}
        if adj_price is not None:
            params['price'] = f"{adj_price}"  # API expects string price

        return params

    def create_limit_buy(self, symbol: str, quantity: Decimal, price: Decimal, **kwargs) -> Optional[Dict]:
        """Places a limit buy order after applying filters."""
        client = self.get_client()
        if not client:
            return None

        params = self._prepare_order_params(symbol, quantity, price)
        if not params:
            return None  # Filter validation failed

        try:
            logger.info(
                f"Placing Limit BUY: {params['quantity']} {symbol} @ {params['price']}")
            order = client.order_limit_buy(
                symbol=params['symbol'],
                quantity=params['quantity'],
                price=params['price'],
                **kwargs  # Pass any extra args like timeInForce, newClientOrderId
            )
            logger.info(
                f"Limit BUY order placed successfully: {order.get('orderId')}")
            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error placing limit buy for {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error placing limit buy for {symbol}: {e}")
            return None

    def create_limit_sell(self, symbol: str, quantity: Decimal, price: Decimal, **kwargs) -> Optional[Dict]:
        """Places a limit sell order (e.g., Take Profit) after applying filters."""
        client = self.get_client()
        if not client:
            return None

        params = self._prepare_order_params(symbol, quantity, price)
        if not params:
            return None

        try:
            logger.info(
                f"Placing Limit SELL: {params['quantity']} {symbol} @ {params['price']}")
            order = client.order_limit_sell(
                symbol=params['symbol'],
                quantity=params['quantity'],
                price=params['price'],
                **kwargs
            )
            logger.info(
                f"Limit SELL order placed successfully: {order.get('orderId')}")
            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error placing limit sell for {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error placing limit sell for {symbol}: {e}")
            return None

    def create_market_sell(self, symbol: str, quantity: Decimal, **kwargs) -> Optional[Dict]:
        """Places a market sell order (e.g., Stop Loss / Exit) after applying quantity filter."""
        client = self.get_client()
        if not client:
            return None

        # Only apply quantity filter for market orders
        exchange_info = self.get_exchange_info_cached()
        if not exchange_info:
            logger.error(
                f"Market Sell {symbol}: Exchange info needed for qty filter.")
            return None
        adj_qty = apply_filter_rules_to_qty(
            symbol, quantity, exchange_info, operation='floor')
        if adj_qty is None or adj_qty <= 0:
            logger.error(
                f"Market Sell {symbol}: Invalid quantity {quantity} after filter: {adj_qty}")
            return None

        # MIN_NOTIONAL check for market orders is tricky as price isn't fixed.
        # Binance might check it based on recent price. Could pre-fetch price and check.
        # For now, skipping explicit MIN_NOTIONAL check here, rely on exchange rejection.
        # current_price = self.get_current_price(symbol)
        # if not validate_order_filters(symbol, current_price if current_price else Decimal('0'), adj_qty, exchange_info):
        #      logger.error(f"Market Sell {symbol} might fail MIN_NOTIONAL.")
        #      # return None # Option: fail pre-emptively

        try:
            qty_str = f"{adj_qty}"
            logger.info(f"Placing Market SELL: {qty_str} {symbol}")
            order = client.order_market_sell(
                symbol=symbol,
                quantity=qty_str,
                **kwargs
            )
            logger.info(
                f"Market SELL order placed successfully: {order.get('orderId')}")
            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error placing market sell for {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error placing market sell for {symbol}: {e}")
            return None

    def cancel_order(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Cancels an open order."""
        client = self.get_client()
        if not client:
            return None
        try:
            logger.info(
                f"Attempting to cancel order {order_id} for {symbol}...")
            result = client.cancel_order(symbol=symbol, orderId=order_id)
            logger.info(f"Order cancellation result for {order_id}: {result}")
            return result
        except (BinanceAPIException, BinanceRequestException) as e:
            # Handle specific error codes, e.g., if order doesn't exist or already filled
            if e.code == -2011:  # Unknown order sent.
                logger.warning(
                    f"Order {order_id} not found or already filled/cancelled on exchange: {e.message}")
                # Return custom status
                return {'status': 'UNKNOWN', 'message': e.message}
            else:
                logger.error(
                    f"API Error cancelling order {order_id} for {symbol}: {e}")
                return None
        except Exception as e:
            logger.exception(
                f"Unexpected error cancelling order {order_id} for {symbol}: {e}")
            return None

    def get_order_status(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Retrieves the status of a specific order."""
        client = self.get_client()
        if not client:
            return None
        try:
            order = client.get_order(symbol=symbol, orderId=order_id)
            logger.debug(
                f"Status for order {order_id} ({symbol}): {order.get('status')}")
            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            if e.code == -2013:  # Order does not exist.
                logger.warning(
                    f"Order {order_id} not found on exchange: {e.message}")
                # Custom status
                return {'status': 'UNKNOWN', 'message': e.message}
            logger.error(
                f"API Error getting order status {order_id} for {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error getting order status {order_id} for {symbol}: {e}")
            return None

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Retrieves all open orders, optionally filtered by symbol."""
        client = self.get_client()
        if not client:
            return []
        try:
            if symbol:
                orders = client.get_open_orders(symbol=symbol)
                logger.info(
                    f"Retrieved {len(orders)} open orders for {symbol}.")
            else:
                orders = client.get_open_orders()
                logger.info(
                    f"Retrieved {len(orders)} open orders for all symbols.")
            return orders
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(
                f"API Error getting open orders (symbol={symbol}): {e}")
            return []
        except Exception as e:
            logger.exception(
                f"Unexpected error getting open orders (symbol={symbol}): {e}")
            return []


# --- Example usage block (optional) ---
if __name__ == '__main__':
    print("Running BinanceUSConnector example...")
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    try:
        from config.settings import load_config
        test_config = load_config()
        if not test_config:
            raise ValueError("Failed load test config")
        api_key = get_config_value(test_config, ('binance_us', 'api_key'))
        api_secret = get_config_value(
            test_config, ('binance_us', 'api_secret'))

        if not api_key or not api_secret or 'YOUR_ACTUAL' in api_key:
            print("API Key/Secret NA. Skipping connection tests.")
        else:
            connector = BinanceUSConnector(
                api_key=api_key, api_secret=api_secret, config=test_config)
            client = connector.get_client()
            if client:
                print("Connection test successful.")
                # --- ADD ORDER PLACEMENT/CANCEL TEST (Use with caution!) ---
                print(
                    "\n--- Testing Order Placement (Requires Funds & Careful Review!) ---")
                test_symbol = 'DOGEUSD'  # Use a low value pair for testing if possible
                test_price = Decimal('0.1000')  # Example price below market
                # Example quantity (check min notional ~ $10)
                test_qty = Decimal('100')

                # 1. Get Current Price (for context)
                current_price = connector.get_current_price(test_symbol)
                print(f"Current {test_symbol} price: {current_price}")

                if current_price and test_price < current_price:
                    # 2. Place Limit Buy
                    print(
                        f"\nAttempting to place Limit BUY {test_qty} {test_symbol} @ {test_price}...")
                    buy_order = connector.create_limit_buy(
                        test_symbol, test_qty, test_price)
                    if buy_order and buy_order.get('orderId'):
                        buy_order_id = buy_order['orderId']
                        print(f"Limit BUY Order ID: {buy_order_id}")
                        time.sleep(2)  # Allow order to register

                        # 3. Get Order Status
                        print(f"\nChecking status for order {buy_order_id}...")
                        status = connector.get_order_status(
                            test_symbol, buy_order_id)
                        print(
                            f"Order Status: {status.get('status') if status else 'Error'}")

                        # 4. Get Open Orders
                        print("\nChecking open orders...")
                        open_orders = connector.get_open_orders(test_symbol)
                        print(
                            f"Found {len(open_orders)} open orders for {test_symbol}.")
                        if open_orders:
                            print(
                                f"First open order ID: {open_orders[0].get('orderId')}")

                        # 5. Cancel Order
                        print(
                            f"\nAttempting to cancel order {buy_order_id}...")
                        cancel_result = connector.cancel_order(
                            test_symbol, buy_order_id)
                        print(f"Cancel Result: {cancel_result}")
                        time.sleep(2)

                        # 6. Verify Cancellation (Get Status Again)
                        print(
                            f"\nRe-checking status for order {buy_order_id}...")
                        status_after_cancel = connector.get_order_status(
                            test_symbol, buy_order_id)
                        print(
                            f"Status after cancel: {status_after_cancel.get('status') if status_after_cancel else 'Error'}")
                    else:
                        print("Failed to place limit buy order.")
                else:
                    print(
                        f"Skipping live order test: Test price {test_price} not below current price {current_price} or current price fetch failed.")
                # --- End Order Test ---
            else:
                print("Connection test failed.")
    except Exception as main_e:
        print(f"An error occurred in the example block: {main_e}")


# END OF FILE: src/connectors/binance_us.py
