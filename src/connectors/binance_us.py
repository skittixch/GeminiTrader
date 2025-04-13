# src/connectors/binance_us.py

import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, List, Any  # Good practice for type hinting

# Attempt to import settings, handle potential ImportError during early setup/testing
try:
    from config.settings import settings
except ImportError:
    # This fallback is mainly for clarity during isolated testing, shouldn't happen when run via -m
    print("WARN: Could not import settings. Ensure settings.py exists and PYTHONPATH is correct.")
    settings = {'api': {'binance_us': {'key': None, 'secret': None}}}

# Get a logger instance specific to this module
log = logging.getLogger(__name__)


class BinanceUSConnector:
    """
    Handles communication with the Binance.US API using python-binance.
    Manages client initialization, API calls, error handling, and filter caching.
    """

    def __init__(self, config_settings=None):
        """
        Initializes the BinanceUSConnector.

        Args:
            config_settings (dict, optional): The application's settings dictionary.
                                            Defaults to importing global settings.
        """
        if config_settings is None:
            config_settings = settings  # Use imported global settings if none provided

        self.api_key = config_settings.get(
            'api', {}).get('binance_us', {}).get('key')
        self.api_secret = config_settings.get(
            'api', {}).get('binance_us', {}).get('secret')

        if not self.api_key or not self.api_secret or \
           self.api_key == "YOUR_BINANCE_US_API_KEY" or \
           self.api_secret == "YOUR_BINANCE_US_SECRET":
            log.error(
                "Binance.US API Key or Secret not found or is still a placeholder in settings/env.")
            self.client = None  # Indicate client couldn't be initialized
        else:
            try:
                # IMPORTANT: Specify tld='us' for Binance.US
                self.client = Client(self.api_key, self.api_secret, tld='us')
                log.info("Binance.US client initialized successfully.")
            except Exception as e:
                log.error(
                    f"Failed to initialize Binance.US client: {e}", exc_info=True)
                self.client = None

        # Exchange info and filters are loaded lazily on demand
        self._exchange_info = None  # Raw exchange info
        self._symbol_filters = {}  # Parsed filters per symbol { "BTCUSD": {...}, ... }

    def test_connection(self) -> bool:
        """
        Tests the API connection by attempting to fetch account information.

        Returns:
            bool: True if the connection is successful, False otherwise.
        """
        if not self.client:
            log.error(
                "Cannot test connection: Binance.US client not initialized.")
            return False

        try:
            account_info = self.client.get_account()
            log.info(
                f"Binance.US API connection successful. Account status: {account_info.get('accountType', 'N/A')}")
            return True
        except (BinanceAPIException, BinanceRequestException) as e:
            log.error(f"Binance.US API connection test failed: {e}")
            return False
        except Exception as e:
            log.error(
                f"An unexpected error occurred during connection test: {e}", exc_info=True)
            return False

    def _fetch_exchange_info(self) -> Optional[Dict[str, Any]]:
        """Fetches raw exchange information from the API."""
        if not self.client:
            log.error("Cannot fetch exchange info: Client not initialized.")
            return None
        try:
            log.info("Fetching exchange information from Binance.US API...")
            self._exchange_info = self.client.get_exchange_info()
            log.info("Successfully fetched exchange information.")
            # Clear previously parsed filters as they might be stale
            self._symbol_filters = {}
            return self._exchange_info
        except (BinanceAPIException, BinanceRequestException) as e:
            log.error(f"Failed to fetch exchange info: {e}")
            self._exchange_info = None  # Ensure stale data isn't kept on error
            return None
        except Exception as e:
            log.error(
                f"An unexpected error occurred fetching exchange info: {e}", exc_info=True)
            self._exchange_info = None
            return None

    def _get_exchange_info(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Retrieves exchange info, fetching from API if not cached or forced.
        Internal use primarily.

        Args:
            force_refresh (bool): If True, always fetches fresh data from the API.

        Returns:
            dict or None: The raw exchange information dictionary, or None on failure.
        """
        if force_refresh or self._exchange_info is None:
            log.info(
                f"Exchange info cache {'empty' if self._exchange_info is None else 'refresh forced'}. Fetching...")
            return self._fetch_exchange_info()
        else:
            log.debug("Using cached exchange information.")
            return self._exchange_info

    def _parse_symbol_filters(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Parses and caches filters for a specific symbol from the raw exchange info.
        Converts relevant filter values to Decimal.

        Args:
            symbol (str): The trading symbol (e.g., 'BTCUSD').

        Returns:
            dict or None: A dictionary containing the parsed filters for the symbol,
                          or None if the symbol or its filters are not found.
        """
        symbol = symbol.upper()  # Ensure consistent casing internally
        if symbol in self._symbol_filters:
            log.debug(f"Using cached filters for symbol: {symbol}")
            return self._symbol_filters[symbol]

        exchange_info = self._get_exchange_info()  # Ensure exchange info is loaded
        if not exchange_info:
            log.error(
                f"Cannot parse filters for {symbol}: Exchange info not available.")
            return None

        symbol_data = None
        for s in exchange_info.get('symbols', []):
            if s['symbol'] == symbol:
                symbol_data = s
                break

        if not symbol_data:
            log.error(f"Symbol '{symbol}' not found in exchange information.")
            return None

        filters = {}
        try:
            raw_filters = symbol_data.get('filters', [])
            for f in raw_filters:
                filter_type = f.get('filterType')
                if filter_type == 'PRICE_FILTER':
                    filters['price_filter'] = {
                        'minPrice': Decimal(f['minPrice']),
                        'maxPrice': Decimal(f['maxPrice']),
                        'tickSize': Decimal(f['tickSize'])
                    }
                elif filter_type == 'LOT_SIZE' or filter_type == 'MARKET_LOT_SIZE':
                    # Prioritize LOT_SIZE if both exist (unlikely but possible)
                    if 'lot_size' not in filters:
                        filters['lot_size'] = {
                            'minQty': Decimal(f['minQty']),
                            'maxQty': Decimal(f['maxQty']),
                            'stepSize': Decimal(f['stepSize'])
                        }
                elif filter_type == 'MIN_NOTIONAL':
                    filters['min_notional'] = {
                        'minNotional': Decimal(f['minNotional']),
                        'applyToMarket': f.get('applyToMarket', False),
                        'avgPriceMins': int(f.get('avgPriceMins', 0))
                    }
                # Add other filters here if needed (e.g., PERCENT_PRICE, MAX_NUM_ORDERS)

            # Add basic symbol info for convenience
            filters['baseAsset'] = symbol_data.get('baseAsset')
            filters['quoteAsset'] = symbol_data.get('quoteAsset')
            filters['status'] = symbol_data.get('status')

            if not all(k in filters for k in ['price_filter', 'lot_size', 'min_notional']):
                log.warning(
                    f"One or more critical filters (PRICE_FILTER, LOT_SIZE, MIN_NOTIONAL) missing for {symbol}. Filters found: {list(filters.keys())}")

            self._symbol_filters[symbol] = filters
            log.info(f"Parsed and cached filters for symbol: {symbol}")
            return filters

        except (InvalidOperation, TypeError, KeyError) as e:
            log.error(
                f"Error parsing filters for symbol {symbol}: {e}. Filter data being parsed: {f if 'f' in locals() else 'N/A'}", exc_info=True)
            return None
        except Exception as e:
            log.error(
                f"Unexpected error parsing filters for {symbol}: {e}", exc_info=True)
            return None

    def get_cached_symbol_filters(self, symbol: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Public method to get the trading filters for a specific symbol.
        Loads exchange info and parses filters if not already cached or if refresh is forced.

        Args:
            symbol (str): The trading symbol (e.g., 'BTCUSD').
            force_refresh (bool): If True, fetches fresh exchange info before getting filters.

        Returns:
            dict or None: A dictionary containing the parsed filters (using Decimal type),
                          or None if filters cannot be retrieved.
        """
        if not self.client:
            log.error("Cannot get filters: Client not initialized.")
            return None

        symbol = symbol.upper()  # Ensure consistent casing

        if force_refresh:
            log.info(f"Forcing refresh for symbol filters: {symbol}")
            # Fetch fresh exchange info
            self._get_exchange_info(force_refresh=True)

        # Attempt to parse/retrieve from cache (will load exchange info if needed)
        filters = self._parse_symbol_filters(symbol)

        if filters is None:
            log.error(f"Failed to get or parse filters for symbol: {symbol}")
            return None

        # Optional: Check symbol status
        if filters.get('status') != 'TRADING':
            log.warning(
                f"Symbol {symbol} status is not TRADING ({filters.get('status')}). Filters retrieved but trading may be unavailable.")

        return filters

    # --- Basic API Interaction Methods ---

    def get_account_balances(self) -> Optional[Dict[str, Dict[str, Decimal]]]:
        """
        Fetches account balances for all assets.

        Returns:
            dict or None: A dictionary where keys are asset symbols (e.g., 'BTC', 'USD')
                          and values are dicts containing 'free' and 'locked' balances
                          as Decimal objects. Returns None on failure.
                          Example: {'BTC': {'free': Decimal('0.1'), 'locked': Decimal('0.0')}, ...}
        """
        if not self.client:
            log.error("Cannot get account balances: Client not initialized.")
            return None
        try:
            account_info = self.client.get_account()
            balances = {}
            for asset_balance in account_info.get('balances', []):
                asset = asset_balance['asset']
                try:
                    balances[asset] = {
                        'free': Decimal(asset_balance['free']),
                        'locked': Decimal(asset_balance['locked'])
                    }
                except (InvalidOperation, TypeError, KeyError) as e:
                    log.error(
                        f"Error parsing balance for asset {asset}: {e}. Data: {asset_balance}", exc_info=True)
                    continue  # Skip this asset if parsing fails
            log.info(
                f"Successfully retrieved {len(balances)} account balances.")
            return balances
        except (BinanceAPIException, BinanceRequestException) as e:
            log.error(f"API error getting account balances: {e}")
            return None
        except Exception as e:
            log.error(
                f"Unexpected error getting account balances: {e}", exc_info=True)
            return None

    def get_latest_price(self, symbol: str) -> Optional[Decimal]:
        """
        Gets the latest market price for a specific symbol.

        Args:
            symbol (str): The trading symbol (e.g., 'BTCUSD').

        Returns:
            Decimal or None: The latest price as a Decimal, or None on failure.
        """
        if not self.client:
            log.error(
                f"Cannot get latest price for {symbol}: Client not initialized.")
            return None
        symbol = symbol.upper()
        try:
            ticker = self.client.get_ticker(symbol=symbol)
            price_str = ticker.get('lastPrice')
            if price_str is not None:
                try:
                    price = Decimal(price_str)
                    log.debug(f"Latest price for {symbol}: {price}")
                    return price
                except (InvalidOperation, TypeError) as e:
                    log.error(
                        f"Error converting latest price '{price_str}' for {symbol} to Decimal: {e}")
                    return None
            else:
                log.error(
                    f"Could not find 'lastPrice' in ticker response for {symbol}: {ticker}")
                return None
        except (BinanceAPIException, BinanceRequestException) as e:
            log.error(f"API error getting latest price for {symbol}: {e}")
            return None
        except Exception as e:
            log.error(
                f"Unexpected error getting latest price for {symbol}: {e}", exc_info=True)
            return None

    def get_order_book_depth(self, symbol: str, limit: int = 100) -> Optional[Dict[str, List[List[Decimal]]]]:
        """
        Gets the order book depth (bids and asks) for a symbol.

        Args:
            symbol (str): The trading symbol (e.g., 'BTCUSD').
            limit (int): The number of bids/asks to retrieve (default/max usually 100 or 500 via API). Check API docs.

        Returns:
            dict or None: A dictionary with 'bids' and 'asks' keys. Each contains a list of
                          [price, quantity] lists, with values as Decimals. Returns None on failure.
                          Example: {'bids': [[Decimal('50000.1'), Decimal('0.1')], ...], 'asks': [...]}
        """
        if not self.client:
            log.error(
                f"Cannot get order book for {symbol}: Client not initialized.")
            return None
        symbol = symbol.upper()
        try:
            depth = self.client.get_order_book(symbol=symbol, limit=limit)
            parsed_depth = {'bids': [], 'asks': []}
            for level_type in ['bids', 'asks']:
                for level in depth.get(level_type, []):
                    try:
                        if isinstance(level, (list, tuple)) and len(level) >= 2:
                            price = Decimal(level[0])
                            qty = Decimal(level[1])
                            parsed_depth[level_type].append([price, qty])
                        else:
                            log.warning(
                                f"Skipping invalid level format in order book for {symbol} ({level_type}): {level}")
                    except (InvalidOperation, TypeError, IndexError) as e:
                        log.error(
                            f"Error parsing order book level for {symbol} ({level_type}): {e}. Level data: {level}", exc_info=True)
                        continue  # Skip invalid level
            log.debug(
                f"Successfully retrieved order book depth for {symbol} (Limit: {limit}).")
            return parsed_depth
        except (BinanceAPIException, BinanceRequestException) as e:
            log.error(f"API error getting order book for {symbol}: {e}")
            return None
        except Exception as e:
            log.error(
                f"Unexpected error getting order book for {symbol}: {e}", exc_info=True)
            return None

    def get_order_status(self, symbol: str, order_id: int) -> Optional[Dict[str, Any]]:
        """
        Gets the status of a specific order.

        Args:
            symbol (str): The trading symbol for the order.
            order_id (int): The order ID returned by place_limit_order.

        Returns:
            dict or None: A dictionary containing the order details from the API,
                          with numerical values converted to Decimal where applicable.
                          Returns None if the order is not found or on API error.
        """
        if not self.client:
            log.error(
                f"Cannot get order status for {symbol} #{order_id}: Client not initialized.")
            return None
        symbol = symbol.upper()
        try:
            order = self.client.get_order(symbol=symbol, orderId=order_id)
            log.info(
                f"Retrieved status for order {symbol} #{order_id}: {order.get('status')}")

            # Convert relevant fields to Decimal
            decimal_fields = ['price', 'origQty',
                              'executedQty', 'cummulativeQuoteQty']
            for field in decimal_fields:
                # Check if field exists and is not None
                if field in order and order[field] is not None:
                    try:
                        order[field] = Decimal(order[field])
                    except (InvalidOperation, TypeError) as e:
                        log.warning(
                            f"Could not convert field '{field}' to Decimal for order {order_id}: {e}. Value: {order[field]}")

            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            if e.code == -2013:  # Error code for 'Order does not exist'
                log.warning(f"Order {symbol} #{order_id} not found.")
                return None
            else:
                log.error(
                    f"API error getting order status for {symbol} #{order_id}: {e}")
                return None
        except Exception as e:
            log.error(
                f"Unexpected error getting order status for {symbol} #{order_id}: {e}", exc_info=True)
            return None

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """
        Cancels an open order.

        Args:
            symbol (str): The trading symbol for the order.
            order_id (int): The order ID to cancel.

        Returns:
            bool: True if the cancel request was successfully sent OR if the order was already closed/non-existent.
                  False on API error or client initialization issue.
        """
        if not self.client:
            log.error(
                f"Cannot cancel order {symbol} #{order_id}: Client not initialized.")
            return False
        symbol = symbol.upper()
        try:
            result = self.client.cancel_order(symbol=symbol, orderId=order_id)
            log.info(
                f"Cancel request sent for order {symbol} #{order_id}. Result status: {result.get('status')}")
            return True
        except (BinanceAPIException, BinanceRequestException) as e:
            # Unknown order sent (often means filled/cancelled/expired)
            if e.code == -2011:
                log.warning(
                    f"Cancel request for order {symbol} #{order_id} failed, likely already filled/cancelled/expired: {e}")
                return True  # Treat as 'not open'
            elif e.code == -2013:  # Order does not exist
                log.warning(
                    f"Cancel request for order {symbol} #{order_id} failed, order not found: {e}")
                return True  # Treat as 'not open'
            else:
                log.error(
                    f"API error cancelling order {symbol} #{order_id}: {e}")
                return False
        except Exception as e:
            log.error(
                f"Unexpected error cancelling order {symbol} #{order_id}: {e}", exc_info=True)
            return False

    def place_limit_order(self, symbol: str, side: str, quantity: Decimal, price: Decimal) -> Optional[Dict[str, Any]]:
        """
        Places a new LIMIT order. **Does NOT perform filter checks here**, assumes pre-validation.

        Args:
            symbol (str): The trading symbol (e.g., 'BTCUSD').
            side (str): 'BUY' or 'SELL'.
            quantity (Decimal): The amount of the base asset to buy/sell.
            price (Decimal): The price at which to place the limit order.

        Returns:
            dict or None: The order response dictionary from the API upon successful placement,
                          with numerical values converted to Decimal. Returns None on failure.
        """
        if not self.client:
            log.error(
                f"Cannot place {side} order for {quantity} {symbol} @ {price}: Client not initialized.")
            return None
        symbol = symbol.upper()
        side = side.upper()
        if side not in ['BUY', 'SELL']:
            log.error(f"Invalid order side: {side}. Must be 'BUY' or 'SELL'.")
            return None

        # Convert Decimal price and quantity back to formatted strings for the API call
        # IMPORTANT: Use engineering string format to avoid scientific notation.
        # Precision will be handled by filter adjustment utils later.
        price_str = price.to_eng_string()
        quantity_str = quantity.to_eng_string()

        try:
            log.info(
                f"Attempting to place {side} limit order: {quantity_str} {symbol} @ {price_str}")
            order = self.client.create_order(
                symbol=symbol,
                side=side,
                type=Client.ORDER_TYPE_LIMIT,
                timeInForce=Client.TIME_IN_FORCE_GTC,
                quantity=quantity_str,
                price=price_str
            )
            log.info(
                f"Successfully placed {side} order for {symbol}. Order ID: {order.get('orderId')}, Status: {order.get('status')}")

            # Convert relevant fields in the response to Decimal
            decimal_fields = ['price', 'origQty',
                              'executedQty', 'cummulativeQuoteQty']
            if order:
                for field in decimal_fields:
                    if field in order and order[field] is not None:
                        try:
                            order[field] = Decimal(order[field])
                        except (InvalidOperation, TypeError) as e:
                            log.warning(
                                f"Could not convert response field '{field}' to Decimal for placed order {order.get('orderId', 'N/A')}: {e}. Value: {order[field]}")

            return order
        except (BinanceAPIException, BinanceRequestException) as e:
            log.error(f"API error placing {side} order for {symbol}: {e}")
            # Log details
            log.error(f"Error Code: {e.code}, Message: {e.message}")
            return None
        except Exception as e:
            log.error(
                f"Unexpected error placing {side} order for {symbol}: {e}", exc_info=True)
            return None


# --- Example Usage (when run directly via python -m src.connectors.binance_us) ---
if __name__ == '__main__':
    # Setup basic logging for direct script execution test
    # Using -m should make config/settings load correctly.
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    log.info("Attempting to initialize BinanceUSConnector for testing...")
    # Rely on the import at the top using global settings, which should work with `python -m`
    connector = BinanceUSConnector()  # Uses global settings by default

    if connector.client:
        log.info("--- Testing Connection ---")
        connection_ok = connector.test_connection()
        log.info(
            f"Connection test result: {'OK' if connection_ok else 'Failed'}")

        if connection_ok:
            log.info("\n--- Testing Filter Fetching ---")
            test_symbol = 'BTCUSD'  # Choose a valid symbol on Binance.US
            log.info(f"Attempting to fetch filters for: {test_symbol}")
            filters = connector.get_cached_symbol_filters(test_symbol)

            if filters:
                log.info(f"Successfully retrieved filters for {test_symbol}:")
                import json
                # Print filters using json for readability, converting Decimals to strings
                log.info(json.dumps(filters, indent=4, default=str))
                tick_size = filters.get('price_filter', {}).get('tickSize')
                if tick_size:
                    log.info(
                        f"Tick Size: {tick_size} (Type: {type(tick_size)})")

                log.info(
                    f"\nAttempting to fetch filters for {test_symbol} with force_refresh=True")
                filters_refresh = connector.get_cached_symbol_filters(
                    test_symbol, force_refresh=True)
                if filters_refresh:
                    log.info(
                        f"Successfully refreshed filters for {test_symbol}.")
                else:
                    log.error(f"Failed to refresh filters for {test_symbol}.")
            else:
                log.error(f"Could not retrieve filters for {test_symbol}.")

            log.info("\n--- Testing Basic API Methods ---")
            log.info("Fetching balances...")
            balances = connector.get_account_balances()
            if balances:
                log.info(
                    f"Found {len(balances)} assets. Example (USD): {balances.get('USD')}, Example (BTC): {balances.get('BTC')}")
                if balances.get('USD'):
                    log.info(
                        f"USD Balance Type: {type(balances['USD']['free'])}")
            else:
                log.error("Failed to fetch balances.")

            log.info("\nFetching latest price for BTCUSD...")
            price = connector.get_latest_price('BTCUSD')
            if price:
                log.info(f"Latest BTCUSD price: {price} (Type: {type(price)})")
            else:
                log.error("Failed to fetch latest price.")

            log.info("\nFetching order book for BTCUSD (limit 5)...")
            depth = connector.get_order_book_depth('BTCUSD', limit=5)
            if depth:
                log.info(
                    f"Order book snapshot (first bid/ask): Bids: {depth['bids'][0] if depth['bids'] else 'N/A'}, Asks: {depth['asks'][0] if depth['asks'] else 'N/A'}")
                if depth['bids']:
                    log.info(f"Bid Price Type: {type(depth['bids'][0][0])}")
            else:
                log.error("Failed to fetch order book.")

            log.info("\nTesting get_order_status for non-existent order (12345)...")
            non_existent_order = connector.get_order_status('BTCUSD', 12345)
            if non_existent_order is None:
                log.info(
                    "Correctly determined order 12345 does not exist (returned None).")
            else:
                log.error(
                    "get_order_status returned something unexpected for a non-existent order.")

            log.info("\nTesting cancel_order for non-existent order (12345)...")
            cancel_result = connector.cancel_order('BTCUSD', 12345)
            if cancel_result is True:
                log.info(
                    "Correctly handled cancel request for non-existent order (returned True).")
            else:
                log.error(
                    "cancel_order returned something unexpected for non-existent order.")

            # --- Placeholder for Manual Testing (Commented Out) ---
            # log.warning("\n--- Manual Order Placement Test Section (COMMENTED OUT) ---")
            # log.warning("Enable this section ONLY for careful manual testing.")
            # if filters and price and False: # Set to True to enable manual test prompt
                # # Calculate a price slightly below current market for a small test buy
                # test_buy_price = price * Decimal('0.99') # 1% below current price
                # min_qty = filters.get('lot_size', {}).get('minQty', Decimal('0.00001'))
                # min_notional_val = filters.get('min_notional',{}).get('minNotional', Decimal('10'))
                # # Calculate required quantity based on min_notional and price
                # required_qty_notional = (min_notional_val / test_buy_price) * Decimal('1.01') # 1% buffer
                # test_qty = max(min_qty, required_qty_notional)

                # # !!! TODO: Replace manual formatting with calls to formatting utils (Phase 0.4) !!!
                # # Adjust price and quantity to filter rules MANUALLY for now
                # tick_size = filters.get('price_filter', {}).get('tickSize', Decimal('0.01'))
                # step_size = filters.get('lot_size', {}).get('stepSize', Decimal('0.00001'))
                # from decimal import ROUND_DOWN, ROUND_UP
                # # Adjust price DOWN to the nearest tick size for BUY orders
                # adjusted_price = (test_buy_price // tick_size) * tick_size
                # # Adjust quantity UP to the nearest step size (usually safer for minNotional)
                # adjusted_qty = ((test_qty + step_size - Decimal('1e-18')) // step_size) * step_size # Add buffer before floor div

                # # Final check for min notional AFTER adjustment
                # final_notional = adjusted_qty * adjusted_price
                # if final_notional < min_notional_val:
                #      log.error(f"Adjusted order fails MIN_NOTIONAL: {final_notional} < {min_notional_val}. Skipping test order.")
                # else:
                #      log.warning(f"Proposed Test Order: BUY {adjusted_qty} BTCUSD @ {adjusted_price}")
                #      confirm = input("!!! LIVE ACCOUNT WARNING !!! Execute this test order? (yes/NO): ")
                #      if confirm.lower() == 'yes':
                #           log.info("Proceeding with test order placement...")
                #           placed_order = connector.place_limit_order('BTCUSD', 'BUY', adjusted_qty, adjusted_price)
                #           if placed_order:
                #                log.info(f"Test order placed successfully: {placed_order}")
                #                # Example: Immediately cancel the test order
                #                test_order_id = placed_order.get('orderId')
                #                if test_order_id:
                #                     log.info(f"Attempting to cancel test order {test_order_id}...")
                #                     time.sleep(1) # Brief pause before cancelling
                #                     cancel_ok = connector.cancel_order('BTCUSD', test_order_id)
                #                     log.info(f"Test order cancellation result: {'OK' if cancel_ok else 'Failed'}")
                #           else:
                #                log.error("Test order placement failed.")
                #      else:
                #           log.info("Test order placement cancelled by user.")

    else:
        log.warning("Connector client was not initialized. Cannot run tests.")
