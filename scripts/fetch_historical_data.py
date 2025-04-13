# scripts/fetch_historical_data.py

import argparse
import logging
import os
import sys
from pathlib import Path
import pandas as pd
import time  # Import time for potential unique naming

# --- Add project root to sys.path ---
# This allows the script to be run from the project root (e.g., python scripts/fetch_historical_data.py ...)
# And still import modules from 'src' correctly.
try:
    # More robust path finding
    project_root = Path(__file__).parent.parent.resolve()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    print(f"Project Root added to sys.path: {project_root}")
except NameError:
    # __file__ might not be defined if run in interactive (%run) context
    project_root = Path('.').resolve()  # Assume running from project root
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    print(
        f"Could not detect script path, assuming running from project root: {project_root}")


# --- Project Imports ---
try:
    from config.settings import load_config
    from src.connectors.binance_us import BinanceUSConnector
    from src.data.kline_fetcher import fetch_and_prepare_klines
    from src.utils.logging_setup import setup_logging
except ImportError as e:
    print(f"ERROR: Failed to import project modules: {e}")
    print("Ensure script is run from the project root directory or PYTHONPATH is set.")
    sys.exit(1)  # Exit if core components can't be imported

# --- Setup Logging ---
# Configure logging specifically for this script
log_dir = project_root / "data" / "logs"
log_filename = "fetch_historical.log"
try:
    log_dir.mkdir(parents=True, exist_ok=True)  # Ensure log directory exists
    setup_logging(log_file=(log_dir / log_filename),
                  log_level=logging.INFO, console_logging=True)
    logger = logging.getLogger(__name__)
    logger.info("Logging setup complete for fetch_historical_data.")
except Exception as log_setup_e:
    print(
        f"ERROR setting up logging: {log_setup_e}. Continuing without file logging.")
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    logger = logging.getLogger(__name__)


def parse_arguments():
    """Parses command-line arguments for fetching historical data."""
    parser = argparse.ArgumentParser(
        description="Fetch historical kline data from Binance.US and save to CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter  # Show defaults in help
    )
    parser.add_argument(
        "-s", "--symbol",
        type=str,
        required=True,
        help="Trading symbol (e.g., BTCUSD, ETHUSD).",
    )
    parser.add_argument(
        "-i", "--interval",
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
        help="End date string (e.g., '2024-01-01', 'now UTC').",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        required=True,
        help="Output CSV file path relative to project root (e.g., data/cache/btc_1h_data.csv).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Limit for the number of klines per API request (max 1000). Library handles multiple requests if needed for date range.",
    )
    return parser.parse_args()


def main():
    """Main function to fetch and save historical data."""
    args = parse_arguments()
    start_run_time = time.time()
    logger.info(f"--- Starting Historical Data Fetch ---")
    logger.info(f"Symbol: {args.symbol}")
    logger.info(f"Interval: {args.interval}")
    logger.info(f"Time Range: {args.start} to {args.end}")
    logger.info(f"Output File: {args.output}")
    logger.info(f"API Request Limit: {args.limit}")

    try:
        # --- Load Configuration ---
        logger.info("Loading configuration...")
        config = load_config()
        if not config:
            logger.error("Failed to load configuration. Exiting.")
            sys.exit(1)

        # --- Check API Keys ---
        binance_config = config.get('binance_us', {})
        api_key = binance_config.get('api_key')
        api_secret = binance_config.get('api_secret')
        if not api_key or not api_secret or 'YOUR_ACTUAL' in str(api_key) or 'YOUR_ACTUAL' in str(api_secret):
            logger.error(
                "Valid Binance.US API Key/Secret not found in config/env.")
            logger.error("Please ensure .env file is populated correctly.")
            sys.exit(1)
        logger.info("API credentials found.")

        # --- Initialize Connector ---
        logger.info("Initializing BinanceUS Connector...")
        connector = BinanceUSConnector(
            api_key=api_key,
            api_secret=api_secret,
            config=config,  # Pass full config if needed by connector
        )
        # Verify connection
        if not connector.get_client():
            logger.error(
                "Failed to initialize or connect Binance client. Exiting.")
            sys.exit(1)
        logger.info("BinanceUS Connector initialized successfully.")

        # --- Fetch Data ---
        logger.info("Fetching kline data from Binance.US...")
        df_klines = fetch_and_prepare_klines(
            connector=connector,
            symbol=args.symbol,
            interval=args.interval,
            start_str=args.start,
            end_str=args.end,
            limit=args.limit  # Pass limit to underlying fetcher
        )

        if df_klines is None or df_klines.empty:
            logger.error(
                f"No data returned for {args.symbol} in the specified range or an error occurred during fetch.")
            sys.exit(1)  # Exit if no data was fetched

        logger.info(
            f"Successfully fetched and prepared {len(df_klines)} klines for {args.symbol}.")

        # --- Prepare Output Path ---
        # Interpret output path relative to project root
        output_path = project_root / args.output
        try:
            # Ensure directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"Ensured output directory exists: {output_path.parent}")
        except OSError as e:
            logger.error(
                f"Could not create output directory {output_path.parent}: {e}")
            sys.exit(1)

        # --- Save Data ---
        logger.info(f"Saving data to {output_path}...")
        try:
            # Save with index (which should be the UTC timestamp)
            # Ensure index name is set for clarity in CSV
            if df_klines.index.name is None:
                df_klines.index.name = 'Timestamp'
            df_klines.to_csv(output_path, index=True)
            logger.info(f"Successfully saved data to {output_path}")
        except Exception as e:
            logger.exception(
                f"Failed to save data to CSV file {output_path}: {e}")
            sys.exit(1)

    except KeyboardInterrupt:
        logger.warning("Data fetch interrupted by user (Ctrl+C).")
        sys.exit(1)
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during data fetching or saving: {e}")
        sys.exit(1)  # Exit with error code
    finally:
        end_run_time = time.time()
        logger.info(
            f"--- Historical Data Fetch Finished ({end_run_time - start_run_time:.2f} seconds) ---")


if __name__ == "__main__":
    main()

# File path: scripts/fetch_historical_data.py
