# src/data/kline_fetcher.py

import logging
import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import sys  # Import sys for stderr output

# Use typing for better hints
from typing import Optional, List, Dict, Any

# Attempt to import connector and settings
try:
    from config.settings import settings
    # Import the connector class itself
    from src.connectors.binance_us import BinanceUSConnector
except ImportError:
    print("WARN: Could not import settings/connector. Ensure files exist and PYTHONPATH is correct.", file=sys.stderr)
    # Define dummy settings/connector for standalone testing if needed
    settings = {'data': {'kline_limit': 1000}}
    # Dummy connector for type hinting if needed, real one should be passed or instantiated

    class BinanceUSConnector:  # Dummy
        def __init__(self, *args, **kwargs): self.client = None
        def get_klines(*args, **kwargs): return []  # Dummy method
        def get_historical_klines(*args, **kwargs): return []  # Dummy method

log = logging.getLogger(__name__)

# Define standard Kline columns based on python-binance output
KLINE_COLUMN_NAMES = [
    'open_time', 'open', 'high', 'low', 'close', 'volume',
    'close_time', 'quote_asset_volume', 'number_of_trades',
    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
]
NUMERIC_KLINE_COLUMNS = [
    'open', 'high', 'low', 'close', 'volume', 'quote_asset_volume',
    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume'
]


def fetch_and_prepare_klines(
    connector: BinanceUSConnector,
    symbol: str,
    interval: str,
    start_str: Optional[str] = None,
    end_str: Optional[str] = None,
    limit: Optional[int] = None
) -> Optional[pd.DataFrame]:
    """
    Fetches historical Klines (candlesticks) for a symbol and interval from Binance.US,
    parses them into a pandas DataFrame with appropriate types (Decimal, datetime).

    Args:
        connector (BinanceUSConnector): An initialized instance of the BinanceUSConnector.
        symbol (str): The trading symbol (e.g., 'BTCUSD').
        interval (str): The kline interval (e.g., '1m', '5m', '1h', '1d').
                        Use Client.KLINE_INTERVAL_* constants if preferred.
        start_str (str, optional): Start date string in format 'YYYY-MM-DD HH:MM:SS' or any
                                   format recognized by binance client (e.g., "1 day ago UTC").
                                   Defaults to None (fetches most recent klines).
        end_str (str, optional): End date string in format 'YYYY-MM-DD HH:MM:SS' or similar.
                                 Defaults to None.
        limit (int, optional): Number of klines to fetch. Defaults to value in config
                               or Binance API default (usually 500, max 1000).

    Returns:
        pd.DataFrame or None: A pandas DataFrame containing the kline data with:
                              - open_time and close_time as UTC datetimes (index).
                              - open, high, low, close, volume, etc. as Decimals.
                              Returns None on failure or if no data is returned.
    """
    if not connector or not connector.client:
        log.error(
            f"Cannot fetch klines for {symbol}: Connector not initialized.")
        return None

    symbol = symbol.upper()
    if limit is None:
        limit = settings.get('data', {}).get(
            'kline_limit', 1000)  # Use config default

    log.info(
        f"Fetching klines for {symbol} ({interval}). Start: {start_str}, End: {end_str}, Limit: {limit}")

    try:
        # Use the get_historical_klines method for fetching older data if start_str is provided
        if start_str:
            klines = connector.client.get_historical_klines(
                symbol=symbol,
                interval=interval,
                start_str=start_str,
                end_str=end_str,
                limit=limit
            )
            log.info(
                f"Fetched {len(klines)} historical klines using get_historical_klines.")
        else:
            # Use get_klines for fetching most recent data (or data up to end_str if specified without start)
            klines = connector.client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            log.info(f"Fetched {len(klines)} recent klines using get_klines.")

        if not klines:
            log.warning(
                f"No kline data returned for {symbol} with the given parameters.")
            # Return an empty DataFrame instead of None for consistency? Let's stick to None for now.
            return None

        # --- Convert to DataFrame and Process ---
        df = pd.DataFrame(klines, columns=KLINE_COLUMN_NAMES)

        # Convert timestamp columns (milliseconds UTC) to datetime objects (UTC)
        try:
            df['open_time'] = pd.to_datetime(
                df['open_time'], unit='ms', utc=True)
            df['close_time'] = pd.to_datetime(
                df['close_time'], unit='ms', utc=True)
        except Exception as e:
            log.error(
                f"Error converting timestamp columns to datetime: {e}", exc_info=True)
            return None  # Cannot proceed without valid timestamps

        # Set open_time as the index
        df.set_index('open_time', inplace=True)

        # Convert numeric columns from string to Decimal for precision
        for col in NUMERIC_KLINE_COLUMNS:
            try:
                # Ensure conversion happens via string representation
                df[col] = df[col].apply(lambda x: Decimal(str(x)))
            except (InvalidOperation, TypeError, ValueError) as e:
                log.error(
                    f"Error converting column '{col}' to Decimal: {e}. Sample value: {df[col].iloc[0] if not df.empty else 'N/A'}", exc_info=True)
                return None

        # Convert 'number_of_trades' to integer
        try:
            df['number_of_trades'] = df['number_of_trades'].astype(int)
        except (ValueError, TypeError) as e:
            log.warning(
                f"Could not convert 'number_of_trades' to int: {e}", exc_info=True)
            # Continue even if this column fails? Seems reasonable.

        # Drop the 'ignore' column as it's usually unused
        if 'ignore' in df.columns:
            df.drop(columns=['ignore'], inplace=True)

        log.info(
            f"Successfully prepared DataFrame for {symbol} with {len(df)} rows. Index: {df.index.min()} to {df.index.max()}")
        return df

    except (BinanceAPIException, BinanceRequestException) as e:  # Catch specific API errors
        log.error(f"API error fetching klines for {symbol}: {e}")
        return None
    except Exception as e:  # Catch any other unexpected errors
        log.error(
            f"Unexpected error fetching/processing klines for {symbol}: {e}", exc_info=True)
        return None


# --- Example Usage (when run directly via python -m src.data.kline_fetcher) ---
if __name__ == '__main__':
    # --- Imports specific to the test block ---
    import logging  # Already imported at top, but good practice if block was standalone
    import sys  # Already imported at top
    # -----------------------------------------

    # Setup basic logging for direct script execution test
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    log.info("--- Testing Kline Fetcher ---")

    # Need an initialized connector instance
    # This relies on config/settings and .env being correct when run with `python -m`
    try:
        # Import settings and connector here, specific to the test execution context
        from config.settings import settings as main_settings
        from src.connectors.binance_us import BinanceUSConnector
        connector_instance = BinanceUSConnector(config_settings=main_settings)
    except ImportError as e:
        log.error(
            f"Could not import dependencies for testing: {e}. Ensure project structure and PYTHONPATH.")
        connector_instance = None  # Set to None to skip tests

    if connector_instance and connector_instance.client:
        test_symbol_recent = 'BTCUSD'  # Keep recent fetch as BTCUSD
        test_interval = '1h'  # Client.KLINE_INTERVAL_1HOUR

        log.info(
            f"\n--- Fetching recent {test_symbol_recent} {test_interval} klines ---")
        df_recent = fetch_and_prepare_klines(
            connector_instance, test_symbol_recent, test_interval, limit=5)

        if df_recent is not None:
            log.info(
                f"Successfully fetched recent klines. Shape: {df_recent.shape}")
            log.info("First 2 rows:\n" + df_recent.head(2).to_string())
            # Should show 'object' because it contains Decimals
            log.info(f"Close column type: {df_recent['close'].dtype}")
            if not df_recent.empty:
                # Verify Decimal
                log.info(
                    f"Type of first 'close' value: {type(df_recent['close'].iloc[0])}")
        else:
            log.error("Failed to fetch recent klines.")

        # --- Debugging Historical Fetch ---
        log.info(f"\n--- Fetching historical klines (DEBUG: Trying BTCUSDT) ---")
        # Example: Fetch data for a specific past period using USDT pair
        test_symbol_hist = 'BTCUSDT'  # <<< Use USDT pair for this test
        df_historical = fetch_and_prepare_klines(
            connector=connector_instance,
            symbol=test_symbol_hist,  # <<< Use the USDT symbol variable
            interval=test_interval,
            start_str="2024-04-01 00:00:00",  # Same start date
            end_str="2024-04-01 05:00:00",  # Same end date
            limit=1000  # Ensure limit is high enough if range is large
        )

        if df_historical is not None and not df_historical.empty:  # Check if DataFrame exists AND is not empty
            log.info(
                f"Successfully fetched historical klines for {test_symbol_hist}. Shape: {df_historical.shape}")
            log.info("Last 2 rows:\n" + df_historical.tail(2).to_string())
        else:
            # Log more specific info if empty or None
            status = "None (Error)" if df_historical is None else "Empty DataFrame"
            log.warning(
                f"Could not fetch historical klines for {test_symbol_hist} (Status: {status}). Check date range and symbol validity.")
        # --- End Debugging Historical Fetch ---

    else:
        log.warning(
            "BinanceUSConnector not initialized. Skipping kline fetching tests.")

    log.info("\n--- Kline Fetcher Test Complete ---")
