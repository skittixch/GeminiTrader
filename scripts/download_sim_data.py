# scripts/download_sim_data.py

import argparse
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

# --- Add project root to sys.path ---
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
# --- End ---

try:
    from config.settings import load_config, get_config_value
    from src.connectors.binance_us import BinanceUSConnector
    from src.data.kline_fetcher import fetch_and_prepare_klines
    from src.utils.logging_setup import setup_logging
except ImportError as e:
    print(f"FATAL ERROR: Module import failed. Make sure you run from the project root or have PYTHONPATH set. Error: {e}", file=sys.stderr)
    sys.exit(1)

# --- Setup Logger ---
# Basic logging setup for the script itself
log_file_path = _project_root / 'data' / 'logs' / 'download_sim_data.log'
log_file_path.parent.mkdir(parents=True, exist_ok=True) # Ensure log dir exists
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler(sys.stdout) # Also print logs to console
    ]
)
logger = logging.getLogger(__name__)

def download_data(symbol: str, interval: str, start_dt_str: str, end_dt_str: str, output_path: Path):
    """
    Downloads historical kline data and saves it to a CSV file.
    """
    logger.info(f"Starting download for {symbol} ({interval}) from {start_dt_str} to {end_dt_str}")

    # 1. Load Config and Initialize Connector
    config = load_config()
    if not config:
        logger.critical("Failed to load configuration.")
        return False

    api_key = get_config_value(config, ('binance_us', 'api_key'))
    api_secret = get_config_value(config, ('binance_us', 'api_secret'))
    if not api_key or not api_secret or 'YOUR_ACTUAL' in str(api_key):
        logger.critical("Binance API Key/Secret missing/invalid in config/.env.")
        return False

    connector = None
    try:
        connector = BinanceUSConnector(api_key=api_key, api_secret=api_secret, config=config)
        if not connector.get_client():
            logger.critical("Failed to initialize Binance client.")
            return False
        logger.info("BinanceUS Connector initialized.")
    except Exception as e:
        logger.critical(f"Connector initialization failed: {e}", exc_info=True)
        return False

    # 2. Parse Dates and Convert to Milliseconds Timestamps (UTC)
    try:
        # Assume input dates are UTC
        start_dt = datetime.strptime(start_dt_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        # End date is inclusive, so we go to the end of that day
        end_dt = datetime.strptime(end_dt_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)

        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)
        logger.info(f"Date range converted to ms: {start_ms} to {end_ms}")

    except ValueError as e:
        logger.error(f"Invalid date format. Please use YYYY-MM-DD. Error: {e}")
        return False

    # 3. Fetch Data using fetch_and_prepare_klines
    try:
        # Note: fetch_and_prepare_klines internally calls get_historical_klines which handles pagination
        # We pass the timestamps as strings, as required by the underlying library.
        df_klines = fetch_and_prepare_klines(
            connector=connector,
            symbol=symbol,
            interval=interval,
            start_str=str(start_ms),
            end_str=str(end_ms),
            limit=None # Let the function fetch all data within the range
        )

        if df_klines is None or df_klines.empty:
            logger.warning(f"No kline data returned for the specified range {start_dt_str} to {end_dt_str}.")
            return False

        logger.info(f"Successfully fetched {len(df_klines)} klines.")

    except Exception as e:
        logger.exception(f"Error during data fetching for {symbol}")
        return False

    # 4. Prepare DataFrame for CSV Output
    # Ensure columns are in the desired order and Timestamp is included
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if not all(col in df_klines.columns for col in required_cols):
        logger.error(f"Fetched data is missing required columns. Found: {df_klines.columns.tolist()}")
        return False

    # Reset index to make the DatetimeIndex a column named 'Timestamp' (in UTC)
    df_klines.reset_index(inplace=True)
    # Convert Timestamp to Unix milliseconds integer
    try:
        df_klines['Timestamp'] = (df_klines['Timestamp'].astype(int) / 1_000_000).astype(int)
    except Exception as e:
        logger.error(f"Failed to convert timestamp index to milliseconds: {e}")
        return False


    # Reorder columns for clarity in CSV
    output_cols = ['Timestamp'] + required_cols
    df_output = df_klines[output_cols]

    # 5. Save to CSV
    try:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Save without pandas index column
        df_output.to_csv(output_path, index=False)
        logger.info(f"Data successfully saved to: {output_path}")
        return True
    except Exception as e:
        logger.exception(f"Error saving data to CSV file: {output_path}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download historical kline data for simulation.")
    parser.add_argument("--symbol", type=str, required=True, help="Trading symbol (e.g., BTCUSD)")
    parser.add_argument("--interval", type=str, default="1h", help="Kline interval (e.g., 1h, 4h, 1d)")
    parser.add_argument("--start-date", type=str, required=True, help="Start date (inclusive) in YYYY-MM-DD format (UTC)")
    parser.add_argument("--end-date", type=str, required=True, help="End date (inclusive) in YYYY-MM-DD format (UTC)")
    parser.add_argument("--output-dir", type=str, default="data/simulation", help="Directory to save the output CSV file.")
    parser.add_argument("--output-filename", type=str, default=None, help="Optional output filename. Defaults to SYMBOL_INTERVAL_START_END.csv")

    args = parser.parse_args()

    # Determine output filename
    if args.output_filename:
        filename = args.output_filename
    else:
        filename = f"{args.symbol}_{args.interval}_{args.start_date}_{args.end_date}.csv"

    output_file_path = _project_root / args.output_dir / filename

    # Execute download
    success = download_data(
        symbol=args.symbol,
        interval=args.interval,
        start_dt_str=args.start_date,
        end_dt_str=args.end_date,
        output_path=output_file_path
    )

    if success:
        logger.info("Download script finished successfully.")
        sys.exit(0)
    else:
        logger.error("Download script finished with errors.")
        sys.exit(1)

# end of scripts/download_sim_data.py
