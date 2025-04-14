# config/settings.py

import yaml
import os
import logging
from dotenv import load_dotenv
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger(__name__)

# --- Environment Loading ---
project_root = Path(__file__).parent.parent
dotenv_path = project_root / '.env'

if dotenv_path.exists():
    # Load existing variables THEN load our file to potentially override
    load_dotenv(dotenv_path=dotenv_path, override=True)
    logger.info(f"Loaded/Overridden environment variables from: {dotenv_path}")
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
        config_path = Path(config_path)

    config = {}

    # 1. Load base configuration from YAML file
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        if config is None:
            config = {}
        logger.info(f"Loaded base configuration from: {config_path}")
    except FileNotFoundError:
        logger.error(f"Configuration file not found at: {config_path}")
        return {}
    except yaml.YAMLError as e:
        logger.error(
            f"Error parsing YAML configuration file {config_path}: {e}")
        return {}
    except Exception as e:
        logger.error(
            f"An unexpected error occurred loading config file {config_path}: {e}")
        return {}

    # 2. Override with Environment Variables
    env_vars_to_load = {
        'BINANCE_US_API_KEY': ('binance_us', 'api_key'),
        'BINANCE_US_SECRET': ('binance_us', 'api_secret'),
        # This is the Key Name now
        'COINBASE_API_KEY': ('coinbase', 'api_key'),
        # Legacy/Unused? Keep for now.
        'COINBASE_API_SECRET': ('coinbase', 'api_secret'),
        'COINBASE_PRIVATE_KEY': ('coinbase', 'private_key'),  # <-- ADDED
        'PLAID_CLIENT_ID': ('plaid', 'client_id'),
        'PLAID_SECRET': ('plaid', 'secret'),
        'PLAID_ENVIRONMENT': ('plaid', 'environment'),
    }

    for env_var, config_keys in env_vars_to_load.items():
        value = os.getenv(env_var)
        if value:
            # Special handling for multi-line private key: replace '\n' back to newlines
            if env_var == 'COINBASE_PRIVATE_KEY':
                value = value.replace('\\n', '\n')

            section = config
            try:
                for key in config_keys[:-1]:
                    if key not in section or not isinstance(section[key], dict):
                        section[key] = {}
                    section = section[key]
                last_key = config_keys[-1]
                section[last_key] = value
                # Log loaded value, masking secrets/private key
                log_value = value[:5] + '...' + value[-5:] if len(value) > 10 and (
                    'SECRET' in env_var or 'PRIVATE_KEY' in env_var) else value
                # Prevent multi-line log spam
                log_value = log_value.replace('\n', '\\n')
                logger.info(
                    f"Loaded '{env_var}' from environment variable (value='{log_value}')")
            except Exception as e:
                logger.error(
                    f"Error setting config from env var {env_var}: {e}")
        else:
            # Check if the key exists in the base config loaded from YAML
            key_exists_in_yaml = False
            temp_section = config
            try:
                for key in config_keys:
                    temp_section = temp_section[key]
                key_exists_in_yaml = True
            except (KeyError, TypeError):
                pass

            if not key_exists_in_yaml:
                logger.warning(
                    f"Environment variable '{env_var}' not found and corresponding key '{'.'.join(config_keys)}' not in base config.")

    # 3. Convert specific string values to Decimal where applicable
    decimal_keys = [
        ('strategies', 'geometric_grid', 'base_order_size_usd'),
        # ... (other decimal keys remain the same) ...
        ('portfolio', 'initial_cash'),
        ('fees', 'maker'),
        ('fees', 'taker'),
        ('strategies', 'dca', 'base_amount_usd'),
    ]
    # Changed to debug
    logger.debug("Converting specified configuration values to Decimal...")
    for key_path in decimal_keys:
        section = config
        try:
            for key in key_path[:-1]:
                section = section[key]
            last_key = key_path[-1]
            value_str = section.get(last_key)
            # Avoid re-converting
            if value_str is not None and not isinstance(value_str, Decimal):
                original_type = type(value_str)
                try:
                    decimal_value = Decimal(str(value_str))
                    section[last_key] = decimal_value
                except (InvalidOperation, TypeError, ValueError) as e:
                    logger.warning(
                        f"Could not convert config value '{value_str}' (type: {original_type}) at key '{'.'.join(key_path)}' to Decimal: {e}. Keeping original value.")
        except (KeyError, TypeError):
            pass

    return config

# --- Helper function (remains the same) ---


def get_config_value(config: dict, key_path: Tuple[str, ...], default: Any = None) -> Any:
    """Safely retrieves a value from a nested dictionary using a key path tuple."""
    section = config
    try:
        for key in key_path:
            section = section[key]
        return section
    except (KeyError, TypeError):
        return default

# File path: config/settings.py
