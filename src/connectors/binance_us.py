# src/connectors/binance_us.py

import logging
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from decimal import Decimal
from typing import Dict, List, Optional, Any

# Note: No 'from config.settings import load_config' here usually.
# Config is typically passed into the constructor.

logger = logging.getLogger(__name__)


class BinanceUSConnector:
    """Handles connection and API calls to Binance.US."""

    def __init__(self, api_key: str, api_secret: str, config: Dict, tld: str = 'us'):
        """
        Initializes the Binance US Connector.

        Args:
            api_key (str): Binance.US API Key.
            api_secret (str): Binance.US API Secret.
            config (Dict): Loaded application configuration (might be used for timeouts etc.).
            tld (str): Top-level domain for the API ('us' for Binance.US).
        """
        if not api_key or not api_secret:
            logger.error(
                "API Key or Secret not provided for BinanceUSConnector.")
            # Depending on use case, might raise an error or allow limited functionality
            # For trading, keys are essential.
            raise ValueError(
                "API Key and Secret are required for BinanceUSConnector")

        self.api_key = api_key
        self.api_secret = api_secret
        self.tld = tld
        self.config = config  # Store config if needed later
        self._client: Optional[Client] = None
        self._connect()

    def _connect(self):
        """Establishes the connection to the Binance API."""
        try:
            self._client = Client(self.api_key, self.api_secret, tld=self.tld)
            # Test connection with a simple call like getting server time or account info
            self.get_server_time()
            logger.info("Binance.US connection established successfully.")
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"Failed to connect to Binance.US API: {e}")
            self._client = None  # Ensure client is None if connection failed
        except Exception as e:
            logger.exception(
                f"An unexpected error occurred during Binance.US connection: {e}")
            self._client = None

    def get_client(self) -> Optional[Client]:
        """Returns the initialized Binance API client instance."""
        if self._client is None:
            logger.warning(
                "Binance client is not initialized. Attempting to reconnect...")
            self._connect()  # Attempt to reconnect
        return self._client

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
            logger.error(f"API Error getting server time: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error getting server time: {e}")
            return None

    def get_account_info(self) -> Optional[Dict]:
        """Retrieves account information."""
        client = self.get_client()
        if not client:
            return None
        try:
            account_info = client.get_account()
            logger.info("Account information retrieved.")
            # Optionally process/filter balances here
            return account_info
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error getting account info: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error getting account info: {e}")
            return None

    def get_asset_balance(self, asset: str) -> Optional[Decimal]:
        """Retrieves the free balance for a specific asset."""
        client = self.get_client()
        if not client:
            return None
        try:
            balance = client.get_asset_balance(asset=asset)
            if balance:
                free_balance = Decimal(balance['free'])
                logger.debug(f"Free balance for {asset}: {free_balance}")
                return free_balance
            else:
                logger.warning(f"Asset {asset} not found in account balance.")
                return Decimal('0.0')  # Return zero if asset not found
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error getting asset balance for {asset}: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error getting asset balance for {asset}: {e}")
            return None

    def get_exchange_info(self) -> Optional[Dict]:
        """Retrieves exchange information (symbols, filters, etc.)."""
        client = self.get_client()
        if not client:
            return None
        try:
            info = client.get_exchange_info()
            logger.info("Exchange information retrieved.")
            return info
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error getting exchange info: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error getting exchange info: {e}")
            return None

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Retrieves information for a specific symbol."""
        client = self.get_client()
        if not client:
            return None
        try:
            info = client.get_symbol_info(symbol=symbol)
            logger.debug(f"Information retrieved for symbol {symbol}.")
            return info
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error getting symbol info for {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error getting symbol info for {symbol}: {e}")
            return None

    def get_klines(self, symbol: str, interval: str, start_str: Optional[str] = None, end_str: Optional[str] = None, limit: int = 1000) -> Optional[List[List[Any]]]:
        """Retrieves kline/candlestick data for a symbol."""
        client = self.get_client()
        if not client:
            return None
        try:
            klines = client.get_historical_klines(
                symbol, interval, start_str=start_str, end_str=end_str, limit=limit)
            logger.debug(
                f"Retrieved {len(klines)} klines for {symbol} ({interval}).")
            return klines
        except (BinanceAPIException, BinanceRequestException) as e:
            logger.error(f"API Error getting klines for {symbol}: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error getting klines for {symbol}: {e}")
            return None

    # --- Add more methods for placing/cancelling orders, getting order book etc. as needed ---
    # Example:
    # def create_limit_buy_order(self, symbol: str, quantity: Decimal, price: Decimal) -> Optional[Dict]:
    #     client = self.get_client()
    #     if not client: return None
    #     try:
    #         # Ensure quantity and price are formatted correctly for the API
    #         # Use helper functions from formatting.py if needed, based on exchange filters
    #         formatted_quantity = f"{quantity:.8f}" # Example formatting, adjust based on filters
    #         formatted_price = f"{price:.2f}"    # Example formatting, adjust based on filters
    #
    #         order = client.order_limit_buy(
    #             symbol=symbol,
    #             quantity=formatted_quantity,
    #             price=formatted_price
    #         )
    #         logger.info(f"Limit BUY order created for {symbol}: {order}")
    #         return order
    #     except (BinanceAPIException, BinanceRequestException) as e:
    #         logger.error(f"API Error creating limit buy order for {symbol}: {e}")
    #         return None
    #     except Exception as e:
    #         logger.exception(f"Unexpected error creating limit buy order for {symbol}: {e}")
    #         return None


# Example usage block (optional, for direct testing)
if __name__ == '__main__':
    # This block needs access to load_config to run standalone
    # Add temporary import or structure differently for testing
    print("Running BinanceUSConnector example...")
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    try:
        # Need to load config here for testing
        # temp_project_root = Path(__file__).parent.parent.parent
        # sys.path.insert(0, str(temp_project_root))
        from config.settings import load_config
        test_config = load_config()

        if not test_config.get('binance_us', {}).get('api_key') or \
           not test_config.get('binance_us', {}).get('api_secret'):
            print("API Key/Secret not found in config or .env. Skipping connection test.")
        else:
            connector = BinanceUSConnector(
                api_key=test_config['binance_us']['api_key'],
                api_secret=test_config['binance_us']['api_secret'],
                config=test_config
            )

            if connector.get_client():
                print("Connection test successful.")
                # Test getting balance (replace with an asset you hold)
                # balance = connector.get_asset_balance('USD')
                # print(f"USD Balance: {balance}")
                # Test getting symbol info
                info = connector.get_symbol_info('BTCUSD')
                if info:
                    print("BTCUSD Info retrieved.")
                    # print(info)
            else:
                print("Connection test failed.")

    except ImportError:
        print("Could not import load_config. Ensure config/settings.py is runnable or restructure test.")
    except Exception as main_e:
        print(f"An error occurred in the example block: {main_e}")

# File path: src/connectors/binance_us.py
