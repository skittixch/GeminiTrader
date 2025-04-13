# scripts/fetch_historical_data.py

from src.utils.logging_setup import setup_logging
from src.data.kline_fetcher import fetch_and_prepare_klines
from src.connectors.binance_us import BinanceUSConnector
from config.settings import load_config
import argparse
import logging
import os
import sys
from pathlib import Path
import pandas as pd

# --- Add project root to sys.path ---
# This allows the script to be run from the project root (e.g., python scripts/fetch_historical_data.py ...)
# And still import modules from 'src' correctly.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# --- End sys.path modification ---


# --- Setup Logging ---
# Configure logging specifically for this script
log_file = Path(project_root) / "data" / "logs" / "fetch_historical.log"
# Ensure log directory exists
log_file.parent.mkdir(parents=True, exist_ok=True)
setup_logging(log_file=log_file, log_level=logging.INFO, console_logging=True)
logger = logging.getLogger(__name__)
# --- End Logging Setup ---


def parse_arguments():
    """Parses command-line arguments for fetching historical data."""
    parser = argparse.ArgumentParser(
        description="Fetch historical kline data from Binance.US and save to CSV."
    )
    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Trading symbol (e.g., BTCUSD, ETHUSD).",
    )
    parser.add_argument(
        "--interval",
        type=str,
        required=True,
        help="Kline interval (e.g., 1m, 5m, 1h, 1d).",
    )
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date string (e.g., '2023-01-01', '1 Jan, 2023', '90 days ago UTC').",
    )
    parser.add_argument(
        "--end",
        type=str,
        default="now UTC",
        help="End date string (e.g., '2024-01-01', 'now UTC'). Defaults to 'now UTC'.",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output CSV file path (e.g., data/cache/btc_1h_data.csv).",
    )
    return parser.parse_args()


def main():
    """Main function to fetch and save historical data."""
    args = parse_arguments()
    logger.info(
        f"Starting historical data fetch for {args.symbol} ({args.interval})")
    logger.info(f"Time range: {args.start} to {args.end}")
    logger.info(f"Output file: {args.output}")

    try:
        # --- Load Configuration ---
        config = load_config()
        logger.debug("Configuration loaded.")

        # --- Initialize Connector ---
        connector = BinanceUSConnector(
            api_key=config["binance_us"]["api_key"],
            api_secret=config["binance_us"]["api_secret"],
            config=config,
        )
        logger.debug("BinanceUS Connector initialized.")

        # --- Fetch Data ---
        logger.info("Fetching kline data from Binance.US...")
        df_klines = fetch_and_prepare_klines(
            connector=connector,
            symbol=args.symbol,
            interval=args.interval,
            start_str=args.start,
            end_str=args.end,
        )

        if df_klines is None or df_klines.empty:
            logger.warning(
                f"No data returned for {args.symbol} in the specified range.")
            return

        logger.info(f"Fetched {len(df_klines)} klines for {args.symbol}.")

        # --- Prepare Output Path ---
        output_path = Path(args.output)
        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Saving data to {output_path}...")

        # --- Save Data ---
        # Save with index (which should be the UTC timestamp)
        df_klines.to_csv(output_path, index=True)
        logger.info(f"Successfully saved data to {output_path}")

    except Exception as e:
        logger.exception(
            f"An error occurred during data fetching or saving: {e}")
        sys.exit(1)  # Exit with error code


if __name__ == "__main__":
    main()
