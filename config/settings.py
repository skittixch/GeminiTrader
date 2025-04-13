# config/settings.py

import yaml
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple, Any  # Add this line


logger = logging.getLogger(__name__)

# --- Environment Loading ---
# Construct the path to the .env file relative to this settings file
# settings.py -> config/ -> project_root/
project_root = Path(__file__).parent.parent
dotenv_path = project_root / '.env'

# Load environment variables from .env file if it exists
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
    logger.info(f"Loaded environment variables from: {dotenv_path}")
else:
    logger.warning(
        f".env file not found at {dotenv_path}. Relying on system environment variables.")


# --- Configuration Loading Function ---
def load_config(config_path: str = None) -> dict:
    """
    Loads configuration from a YAML file and merges it with environment variables.

    Args:
        config_path (str, optional): Path to the YAML configuration file.
                                     Defaults to 'config/config.yaml' relative to project root.

    Returns:
        dict: The loaded and merged configuration dictionary. Returns empty dict on error.
    """
    if config_path is None:
        default_config_path = project_root / 'config' / 'config.yaml'
        config_path = default_config_path
    else:
        config_path = Path(config_path)  # Convert string path to Path object

    config = {}

    # 1. Load base configuration from YAML file
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        if config is None:
            config = {}  # Ensure config is a dict even if YAML is empty
        logger.info(f"Loaded base configuration from: {config_path}")
    except FileNotFoundError:
        logger.error(f"Configuration file not found at: {config_path}")
        return {}  # Return empty dict if base config file is missing
    except yaml.YAMLError as e:
        logger.error(
            f"Error parsing YAML configuration file {config_path}: {e}")
        return {}  # Return empty dict on YAML parsing error
    except Exception as e:
        logger.error(
            f"An unexpected error occurred loading config file {config_path}: {e}")
        return {}

    # 2. Override with Environment Variables (for sensitive data like API keys)
    # Example: Look for BINANCE_US_API_KEY env var to override config['binance_us']['api_key']
    api_keys = {
        'BINANCE_US_API_KEY': ('binance_us', 'api_key'),
        'BINANCE_US_SECRET': ('binance_us', 'api_secret'),
        'COINBASE_API_KEY': ('coinbase', 'api_key'),
        'COINBASE_API_SECRET': ('coinbase', 'api_secret'),
        'PLAID_CLIENT_ID': ('plaid', 'client_id'),
        'PLAID_SECRET': ('plaid', 'secret'),
        'PLAID_ENVIRONMENT': ('plaid', 'environment'),
        # Add other environment variables to override here
    }

    for env_var, config_keys in api_keys.items():
        value = os.getenv(env_var)
        if value:
            # Navigate nested dictionary structure
            section = config
            try:
                # Ensure parent dictionaries exist
                for key in config_keys[:-1]:
                    if key not in section or not isinstance(section[key], dict):
                        section[key] = {}
                    section = section[key]

                # Set the final key
                last_key = config_keys[-1]
                section[last_key] = value
                # Log loaded value, masking secrets
                log_value = value[:3] + '...' + value[-3:] if len(
                    value) > 6 and 'SECRET' in env_var.upper() else value
                logger.info(
                    f"Loaded '{env_var}' from environment variable (value='{log_value}')")
            except Exception as e:
                logger.error(
                    f"Error setting config from env var {env_var}: {e}")
        else:
            # Check if the key was expected but not found in env vars or config
            section = config
            key_exists = True
            try:
                for key in config_keys:
                    section = section[key]
            except (KeyError, TypeError):
                key_exists = False

            if not key_exists:
                logger.warning(
                    f"Environment variable '{env_var}' not found and corresponding key '{'.'.join(config_keys)}' not in base config.")

    # 3. Convert specific string values to Decimal where applicable
    # Define paths to keys that should be Decimal (using tuples for nested keys)
    decimal_keys = [
        ('strategies', 'geometric_grid', 'base_order_size_usd'),
        ('strategies', 'geometric_grid', 'grid_spacing_atr_multiplier'),
        ('strategies', 'geometric_grid', 'grid_spacing_geometric_factor'),
        ('strategies', 'geometric_grid', 'order_size_geometric_factor'),
        ('strategies', 'geometric_grid', 'max_total_grid_quantity_base'),
        ('strategies', 'simple_tp', 'tp_value'),
        ('strategies', 'dca', 'base_amount_usd'),
        ('portfolio', 'initial_cash'),
        ('fees', 'maker'),
        ('fees', 'taker'),
    ]
    logger.info("Converting specified configuration values to Decimal...")
    for key_path in decimal_keys:
        section = config
        try:
            # Traverse the dictionary according to the key path
            for key in key_path[:-1]:
                section = section[key]
            last_key = key_path[-1]
            value_str = section.get(last_key)

            if value_str is not None:
                original_type = type(value_str)
                try:
                    # Convert to string first for safety
                    decimal_value = Decimal(str(value_str))
                    section[last_key] = decimal_value
                    # logger.debug(f"Converted config key '{'.'.join(key_path)}' to Decimal: {decimal_value}")
                except (InvalidOperation, TypeError, ValueError) as e:
                    logger.warning(
                        f"Could not convert config value '{value_str}' (type: {original_type}) at key '{'.'.join(key_path)}' to Decimal: {e}. Keeping original value.")
            # else: logger.debug(f"Key '{'.'.join(key_path)}' not found for Decimal conversion.")

        except (KeyError, TypeError):
            # logger.debug(f"Path '{'.'.join(key_path)}' not found in config for Decimal conversion.")
            pass  # Key path doesn't exist, skip conversion

    return config

# --- Load configuration globally on import (optional, can be explicit) ---
# CONFIG = load_config()
# logger.info("Global CONFIG loaded.")

# --- Helper function to get config value safely ---


def get_config_value(config: dict, key_path: Tuple[str, ...], default: Any = None) -> Any:
    """Safely retrieves a value from a nested dictionary using a key path tuple."""
    section = config
    try:
        for key in key_path:
            section = section[key]
        return section
    except (KeyError, TypeError):
        return default


# Example of accessing config (if loaded globally)
# if __name__ == '__main__':
#     print("Global Config Example:")
#     print(f"Binance API Key (Loaded?): {'api_key' in CONFIG.get('binance_us', {})}")
#     grid_conf = get_config_value(CONFIG, ('strategies', 'geometric_grid'))
#     if grid_conf:
#         print(f"Base Order Size (Decimal?): {grid_conf.get('base_order_size_usd')} (Type: {type(grid_conf.get('base_order_size_usd'))})")

# File path: config/settings.py
