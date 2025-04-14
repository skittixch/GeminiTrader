# START OF FILE: src/connectors/binance_us.py

import logging
import time  # Added for potential rate limiting
import pandas as pd  # Added for Timestamp
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from decimal import Decimal
from typing import Dict, List, Optional, Any

# Avoid config import here; pass config object instead.

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
        # --- ADDED Cache attributes ---
        self._exchange_info_cache: Optional[Dict] = None
        self._exchange_info_cache_time: Optional[pd.Timestamp] = None
        # --- End Add ---
        self._connect()

    def _connect(self):
        """Establishes the connection to the Binance API."""
        try:
            # TODO: Consider adding request params from config (e.g., timeout)
            # requests_params = {"timeout": self.config.get('binance_us',{}).get('request_timeout', 10)}
            # , requests_params=requests_params)
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
        """
        Retrieves exchange information (symbols, filters, etc.).
        Uses cache unless force_refresh is True or cache is old.
        """
        # Get cache duration from config or use default (e.g., 24 hours)
        cache_duration_cfg = get_config_value(
            self.config, ('trading', 'exchange_info_cache_minutes'), 60 * 24)
        cache_duration_minutes = int(cache_duration_cfg)  # Ensure int
        now = pd.Timestamp.utcnow()

        # Check cache validity
        if not force_refresh and self._exchange_info_cache and self._exchange_info_cache_time and \
           (now - self._exchange_info_cache_time) < pd.Timedelta(minutes=cache_duration_minutes):
            logger.debug("Using cached exchange info.")
            return self._exchange_info_cache

        # Fetch from API if cache invalid or forced
        client = self.get_client()
        if not client:
            return None
        try:
            logger.info(
                f"Fetching fresh exchange information from API (Cache duration: {cache_duration_minutes} mins)...")
            info = client.get_exchange_info()
            # --- Cache the result ---
            self._exchange_info_cache = info
            self._exchange_info_cache_time = now
            logger.info("Exchange information retrieved and cached.")
            # TODO: Optionally save cache to file (e.g., config['data']['exchange_info_cache'])
            return info
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error getting exchange info: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error getting exchange info: {e}")
            return None

    def get_exchange_info_cached(self) -> Optional[Dict]:
        """Returns the cached exchange info, if available (does not fetch)."""
        if not self._exchange_info_cache:
            logger.warning(
                "Attempted to get cached exchange info, but cache is empty.")
        return self._exchange_info_cache

    # --- Wrapper Methods for Common API Calls ---

    def get_server_time(self) -> Optional[int]:
        """Gets the current server time from Binance."""
        client = self.get_client()
        if not client:
            return None
        try:
            server_time = client.get_server_time()
            logger.debug(f"Binance server time: {server_time['serverTime']}")
            return server_time['serverTime']
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error get server time: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error get server time: {e}")
            return None

    def get_account_info(self) -> Optional[Dict]:
        """Retrieves account information."""
        client = self.get_client()
        if not client:
            return None
        try:
            account_info = client.get_account()
            logger.info("Account information retrieved.")
            return account_info
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error get account info: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error get account info: {e}")
            return None

    def get_asset_balance(self, asset: str) -> Optional[Decimal]:
        """Retrieves the free balance for a specific asset."""
        client = self.get_client()
        if not client:
            return None
        try:
            balance = client.get_asset_balance(asset=asset)
            if balance:
                # Use helper for safe conversion
                from src.utils.formatting import to_decimal  # Local import ok here
                free_balance = to_decimal(balance['free'])
                logger.debug(f"Free balance for {asset}: {free_balance}")
                return free_balance if free_balance is not None else Decimal('0.0')
            else:
                logger.warning(f"Asset {asset} not found in account balance.")
                return Decimal('0.0')
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error get balance {asset}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error get balance {asset}: {e}")
            return None

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Retrieves information for a specific symbol.
        Uses cached exchange_info if available, otherwise hits the API.
        """
        # Use cached exchange info first for efficiency
        exchange_info = self.get_exchange_info()  # Uses internal cache logic
        if exchange_info:
            # Need the helper function here too
            from src.utils.formatting import get_symbol_info_from_exchange_info
            symbol_info = get_symbol_info_from_exchange_info(
                symbol, exchange_info)
            if symbol_info:
                logger.debug(f"Cache: Info retrieved for {symbol}.")
                return symbol_info
            else:
                # Symbol not in cache - this might mean cache is stale or symbol invalid
                logger.warning(
                    f"Cache: Symbol {symbol} not found in cached exchange info. Trying direct API call...")
                # Fall through to direct API call might be risky if cache *should* be current
                # Let's just return None if not in cache for now, rely on scheduled updates
                return None

        # Fallback or if cache failed: Hit API directly (less efficient)
        # logger.warning("Exchange info cache miss/fail, hitting get_symbol_info API directly...")
        # client = self.get_client();
        # if not client: return None
        # try:
        #     info = client.get_symbol_info(symbol=symbol)
        #     logger.debug(f"API: Info retrieved for {symbol}.")
        #     return info
        # except (BinanceAPIException, BinanceRequestException) as e: logger.error(f"API Error get symbol info {symbol}: {e}"); return None
        # except Exception as e: logger.exception(f"Unexpected err get symbol info {symbol}: {e}"); return None
        else:
            logger.error(
                "Failed to get exchange info to retrieve symbol info.")
            return None

    def get_klines(self, symbol: str, interval: str, start_str: Optional[str] = None, end_str: Optional[str] = None, limit: int = 1000) -> Optional[List[List[Any]]]:
        """Retrieves kline/candlestick data for a symbol."""
        client = self.get_client()
        if not client:
            return None
        try:
            klines = client.get_historical_klines(
                symbol, interval, start_str=start_str, end_str=end_str, limit=limit)
            # Avoid overly verbose logging for frequent calls
            # logger.debug(f"Retrieved {len(klines)} klines for {symbol} ({interval}).")
            return klines
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error get klines {symbol} ({interval}): {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error get klines {symbol} ({interval}): {e}")
            return None

    # --- Add Order Methods Later ---
    # def create_limit_buy_order(...)
    # def create_limit_sell_order(...)
    # def cancel_order(...)
    # def get_order(...)
    # def get_open_orders(...)


# --- Helper import (only used in __init__) ---
# Moved here to avoid potential circular import if settings imports connector
try:
    from config.settings import get_config_value
except ImportError:
    # Dummy if needed for standalone testing, but should exist in real run
    def get_config_value(cfg, path, default=None): return default

# Example usage block (optional)
if __name__ == '__main__':
    print("Running BinanceUSConnector example...")
    # Setup basic logging for direct script run
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Need to load config for testing
    try:
        # Assumes being run from project root or sys.path is set correctly
        from config.settings import load_config
        test_config = load_config()
        if not test_config:
            raise ValueError("Failed to load test config")

        api_key = get_config_value(test_config, ('binance_us', 'api_key'))
        api_secret = get_config_value(
            test_config, ('binance_us', 'api_secret'))

        if not api_key or not api_secret or 'YOUR_ACTUAL' in api_key:
            print("API Key/Secret not found or invalid. Skipping connection tests.")
        else:
            connector = BinanceUSConnector(
                api_key=api_key, api_secret=api_secret, config=test_config)
            client = connector.get_client()
            if client:
                print("Connection test successful.")
                # Test caching
                print("\n--- Testing Exchange Info Cache ---")
                info1 = connector.get_exchange_info()  # First fetch
                if info1:
                    print("Fetched initial exchange info.")
                time.sleep(1)
                info2 = connector.get_exchange_info()  # Should use cache
                if info2:
                    print("Fetched exchange info again (should be cached).")
                print(f"Cache time: {connector._exchange_info_cache_time}")
                info3 = connector.get_exchange_info(
                    force_refresh=True)  # Force refresh
                if info3:
                    print("Fetched exchange info with force_refresh=True.")
                print(
                    f"Cache time after refresh: {connector._exchange_info_cache_time}")

                # Test symbol info retrieval (will use cache now)
                print("\n--- Testing Symbol Info (from Cache) ---")
                sym_info = connector.get_symbol_info('BTCUSD')
                if sym_info:
                    print(
                        f"BTCUSD Info retrieved (likely from cache). Keys: {list(sym_info.keys())[:5]}...")
                else:
                    print("Failed to get BTCUSD info.")
                sym_info_eth = connector.get_symbol_info('ETHUSD')
                if sym_info_eth:
                    print(
                        f"ETHUSD Info retrieved (likely from cache). Keys: {list(sym_info_eth.keys())[:5]}...")
                else:
                    print("Failed to get ETHUSD info.")
                sym_info_bad = connector.get_symbol_info('NOSYMBOL')
                if not sym_info_bad:
                    print("Correctly failed to get info for NOSYMBOL.")

            else:
                print("Connection test failed.")
    except Exception as main_e:
        print(f"An error occurred in the example block: {main_e}")


# END OF FILE: src/connectors/binance_us.py
