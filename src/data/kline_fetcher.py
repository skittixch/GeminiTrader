# src/data/kline_fetcher.py

import logging
import pandas as pd
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Dict, Any

# Assuming connector is imported where this function is called
# from src.connectors.binance_us import BinanceUSConnector

# --- Add project root to sys.path FIRST (for testing block) ---
import os
import sys
_project_root_for_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root_for_path not in sys.path:
    sys.path.insert(0, _project_root_for_path)
# --- End sys.path modification ---

# Project Imports (mainly for testing block)
try:
    from src.utils.logging_setup import setup_logging
    from src.utils.formatting import to_decimal
    from src.connectors.binance_us import BinanceUSConnector
    from config.settings import load_config
except ImportError as e:
    print(
        f"WARNING: Could not import modules for kline_fetcher test block: {e}")
    # Define dummies only if absolutely necessary for script structure
    def setup_logging(*args, **kwargs): pass
    def to_decimal(v, default=None): return Decimal(
        v) if v is not None else default
    # Cannot easily dummy Connector or load_config

log = logging.getLogger(__name__)

# Define constants for kline indices
KLINE_OPEN_TIME = 0
KLINE_OPEN = 1
KLINE_HIGH = 2
KLINE_LOW = 3
KLINE_CLOSE = 4
KLINE_VOLUME = 5
KLINE_CLOSE_TIME = 6
KLINE_QUOTE_ASSET_VOLUME = 7
KLINE_NUMBER_OF_TRADES = 8
KLINE_TAKER_BUY_BASE_ASSET_VOLUME = 9
KLINE_TAKER_BUY_QUOTE_ASSET_VOLUME = 10
KLINE_IGNORE = 11


def fetch_and_prepare_klines(
    connector: 'BinanceUSConnector',  # Use forward reference if needed
    symbol: str,
    interval: str,
    start_str: Optional[str] = None,
    end_str: Optional[str] = None,
    limit: int = 1000
) -> Optional[pd.DataFrame]:
    """
    Fetches historical Klines (candlesticks) for a symbol and interval from Binance.US,
    parses them into a pandas DataFrame with appropriate types (Decimal, datetime).

    Args:
        connector (BinanceUSConnector): An initialized BinanceUSConnector instance.
        symbol (str): The trading symbol (e.g., 'BTCUSD').
        interval (str): The kline interval (e.g., '1m', '1h', '1d').
        start_str (Optional[str]): Start date string (e.g., "1 Jan, 2020").
        end_str (Optional[str]): End date string (e.g., "1 Feb, 2020").
        limit (int): Max number of klines to retrieve per API call (max 1000).
                     Note: The underlying library handles fetching more if the
                     date range requires it, by making multiple calls.

    Returns:
        Optional[pd.DataFrame]: A pandas DataFrame with the kline data, indexed by
                                UTC timestamp. Columns: 'Open', 'High', 'Low',
                                'Close', 'Volume'. Values are Decimals.
                                Returns None on failure or if no data is returned.
    """
    # CORRECTED: Check connector and its internal _client status via get_client() perhaps, or directly _client
    # Simpler check: rely on connector methods to handle uninitialized client.
    if not connector:
        log.error(
            f"Cannot fetch klines for {symbol}: Connector object is None.")
        return None

    log.info(
        f"Fetching klines for {symbol} ({interval}) from {start_str} to {end_str}")
    try:
        # CORRECTED: Use the connector's method
        raw_klines = connector.get_klines(
            symbol=symbol, interval=interval, start_str=start_str, end_str=end_str, limit=limit
        )

        if not raw_klines:
            log.warning(
                f"No kline data returned for {symbol} with the given parameters.")
            return None

        # Define column names
        columns = [
            'Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time',
            'Quote asset volume', 'Number of trades', 'Taker buy base asset volume',
            'Taker buy quote asset volume', 'Ignore'
        ]
        df = pd.DataFrame(raw_klines, columns=columns)

        # Convert timestamp columns to datetime (UTC)
        df['Open time'] = pd.to_datetime(df['Open time'], unit='ms', utc=True)
        # df['Close time'] = pd.to_datetime(df['Close time'], unit='ms', utc=True) # Close time might not be needed

        # Set the 'Open time' as the index
        df.set_index('Open time', inplace=True)
        df.index.name = 'Timestamp'  # Rename index

        # Select and convert relevant columns to Decimal
        ohlcv_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in ohlcv_cols:
            try:
                # Use the utility function for robust conversion
                df[col] = df[col].apply(lambda x: to_decimal(x))
            except (TypeError, ValueError, InvalidOperation) as e:
                log.error(
                    f"Error converting column '{col}' to Decimal: {e}. Data sample: {df[col].head()}")
                # Depending on severity, might return None or try to continue
                return None  # Fail if essential OHLCV data cannot be converted

        # Keep only the essential columns
        df = df[ohlcv_cols]

        log.info(
            f"Successfully fetched and prepared {len(df)} klines for {symbol}.")
        return df

    except Exception as e:
        # Log the exception originating from the connector or pandas processing
        log.exception(
            f"An error occurred during fetch_and_prepare_klines for {symbol}: {e}")
        return None


# --- Example Usage / Test Block ---
if __name__ == '__main__':
    # Setup basic logging for testing
    project_root = Path(__file__).parent.parent.parent
    log_file_path = project_root / "data" / "logs" / "test_kline_fetcher.log"
    try:
        setup_logging(log_file=log_file_path,
                      console_logging=True, log_level=logging.DEBUG)
    except NameError:
        print(
            "WARNING: setup_logging not defined (likely import issue). Using basic config.")
        logging.basicConfig(
            level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    except Exception as log_e:
        print(f"ERROR setting up logging: {log_e}. Using basic config.")
        logging.basicConfig(
            level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    log.info("--- Testing Kline Fetcher ---")

    try:
        test_config = load_config()
        if not test_config:
            log.error("Failed to load config for test.")
            sys.exit(1)

        api_key = test_config.get('binance_us', {}).get('api_key')
        api_secret = test_config.get('binance_us', {}).get('api_secret')

        if not api_key or not api_secret or 'YOUR_ACTUAL' in api_key:
            log.warning(
                "API Key/Secret not found or using placeholders. Skipping live fetch test.")
        else:
            log.info("Initializing connector for live fetch test...")
            test_connector = BinanceUSConnector(
                api_key=api_key, api_secret=api_secret, config=test_config)

            if test_connector.get_client():  # Check if connection was successful
                log.info("Fetching recent 1h BTCUSD klines...")
                df_klines = fetch_and_prepare_klines(
                    connector=test_connector,
                    symbol='BTCUSD',
                    interval='1h',
                    start_str='1 day ago UTC'  # Fetch only a small amount for test
                )

                if df_klines is not None and not df_klines.empty:
                    log.info(f"Successfully fetched {len(df_klines)} klines.")
                    print("\nFetched Data Sample (Head):")
                    print(df_klines.head().to_markdown(
                        numalign="right", stralign="right"))
                    print("\nFetched Data Sample (Tail):")
                    print(df_klines.tail().to_markdown(
                        numalign="right", stralign="right"))
                    print("\nData Types:")
                    print(df_klines.dtypes)
                else:
                    log.error(
                        "Failed to fetch klines or returned empty DataFrame.")
            else:
                log.error("Failed to initialize Binance client in connector.")

    except NameError as ne:
        log.error(
            f"NameError during test setup (likely missing import/dummy): {ne}")
    except Exception as e:
        log.exception(f"An error occurred during the kline fetcher test: {e}")

    log.info("--- Kline Fetcher Test Complete ---")


# File path: src/data/kline_fetcher.py
