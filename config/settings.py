# config/settings.py

import os
import yaml
from dotenv import load_dotenv
from decimal import Decimal, InvalidOperation
import logging

# --- Setup Logging for Config Loading ---
# Basic config for bootstrapping logging before the main setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Determine Project Root and Paths ---
# Assumes settings.py is in the config/ directory, one level below the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'config.yaml')
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')

# --- Load Environment Variables ---
try:
    if os.path.exists(ENV_PATH):
        load_dotenv(dotenv_path=ENV_PATH)
        log.info(f"Loaded environment variables from: {ENV_PATH}")
    else:
        log.warning(f".env file not found at: {ENV_PATH}. Relying on system environment variables.")
except Exception as e:
    log.error(f"Error loading .env file from {ENV_PATH}: {e}", exc_info=True)
    # Decide if this is fatal? For now, we continue, hoping env vars are set system-wide

# --- Load Base Configuration from YAML ---
try:
    with open(CONFIG_PATH, 'r') as stream:
        try:
            config_base = yaml.safe_load(stream)
            if config_base is None:
                 config_base = {} # Handle empty YAML file
                 log.warning(f"Config file {CONFIG_PATH} is empty.")
            log.info(f"Loaded base configuration from: {CONFIG_PATH}")
        except yaml.YAMLError as exc:
            log.error(f"Error parsing YAML file {CONFIG_PATH}: {exc}", exc_info=True)
            raise # Parsing error is likely fatal for config
except FileNotFoundError:
    log.error(f"Configuration file not found: {CONFIG_PATH}. Cannot proceed.")
    raise # Missing config file is fatal

# --- Helper Function to Get Env Var ---
def get_env_var(var_name, default=None):
    """Gets an environment variable, logging whether it was found."""
    value = os.environ.get(var_name, default)
    if value is not default:
        # Mask sensitive values partially in logs if needed (e.g., API keys)
        display_value = value[:3] + '...' + value[-3:] if 'KEY' in var_name.upper() or 'SECRET' in var_name.upper() and value and len(value) > 6 else value
        log.info(f"Loaded '{var_name}' from environment variable (value='{display_value}')")
        # Optional: Add more rigorous checks for required env vars
        if not value and not default:
             log.warning(f"Required environment variable '{var_name}' is not set.")
    elif default is not None:
         log.info(f"Environment variable '{var_name}' not found, using default from config.yaml.")
    else:
         log.warning(f"Environment variable '{var_name}' not found and no default provided in config.yaml.")
    return value

# --- Override YAML with Environment Variables (Especially for Secrets) ---
# API Keys
config_base.setdefault('api', {}) # Ensure 'api' key exists
config_base['api'].setdefault('binance_us', {})
config_base['api']['binance_us']['key'] = get_env_var('BINANCE_US_API_KEY', config_base['api']['binance_us'].get('key'))
config_base['api']['binance_us']['secret'] = get_env_var('BINANCE_US_SECRET', config_base['api']['binance_us'].get('secret'))

config_base['api'].setdefault('coinbase', {})
config_base['api']['coinbase']['key'] = get_env_var('COINBASE_API_KEY', config_base['api']['coinbase'].get('key'))
config_base['api']['coinbase']['secret'] = get_env_var('COINBASE_API_SECRET', config_base['api']['coinbase'].get('secret'))

config_base['api'].setdefault('plaid', {})
config_base['api']['plaid']['client_id'] = get_env_var('PLAID_CLIENT_ID', config_base['api']['plaid'].get('client_id'))
config_base['api']['plaid']['secret'] = get_env_var('PLAID_SECRET', config_base['api']['plaid'].get('secret'))
config_base['api']['plaid']['environment'] = get_env_var('PLAID_ENVIRONMENT', config_base['api']['plaid'].get('environment', 'sandbox'))

# --- Convert Specific Numerical Values to Decimal ---
def convert_to_decimal(config_dict, path_keys):
    """Recursively searches for path_keys in nested dict and converts value to Decimal."""
    temp_dict = config_dict
    try:
        for i, key in enumerate(path_keys):
            if i == len(path_keys) - 1: # Last key in the path
                if key in temp_dict and temp_dict[key] is not None:
                    original_value = temp_dict[key]
                    try:
                        temp_dict[key] = Decimal(str(original_value)) # Convert via string for precision
                        log.debug(f"Converted '{'.'.join(path_keys)}' to Decimal: {temp_dict[key]} (from {original_value})")
                    except (InvalidOperation, TypeError) as e:
                        log.error(f"Failed to convert '{'.'.join(path_keys)}' value '{original_value}' to Decimal: {e}")
                        # Decide handling: raise error, use default, or leave as is? For now, log error.
                return # Found the key or it doesn't exist at this level
            elif key in temp_dict and isinstance(temp_dict[key], dict):
                temp_dict = temp_dict[key] # Move deeper into the dict
            else:
                return # Path doesn't exist
    except Exception as e:
        log.error(f"Error during Decimal conversion for '{'.'.join(path_keys)}': {e}", exc_info=True)

# List of paths to numerical values that need Decimal conversion
decimal_paths = [
    ['trading', 'grid', 'base_order_size_usd'],
    ['trading', 'grid', 'spacing_factor'],
    ['trading', 'grid', 'geometric_factor'],
    ['trading', 'grid', 'order_size_factor'],
    ['trading', 'grid', 'min_level_separation_pct'],
    ['trading', 'profit_taking', 'fixed_tp_percentage'],
    ['trading', 'profit_taking', 'dynamic_tp_atr_multiple_min'],
    ['trading', 'profit_taking', 'dynamic_tp_atr_multiple_max'],
    ['trading', 'risk', 'max_total_position_usd_per_symbol'],
    ['trading', 'risk', 'time_stop_profit_threshold'],
    ['trading', 'risk', 'confidence_floor_exit'],
    ['trading', 'risk', 'portfolio_max_drawdown'],
    ['trading', 'dca', 'base_amount_usd'],
]

log.info("Converting specified configuration values to Decimal...")
for path in decimal_paths:
    convert_to_decimal(config_base, path)

# --- Final Configuration Object ---
# Make the loaded and processed config available for import
settings = config_base

# --- Optional: Define helper functions/accessors ---
def get_setting(path_string, default=None):
    """Helper to get nested setting using dot notation string e.g., 'trading.grid.max_levels'"""
    keys = path_string.split('.')
    value = settings
    try:
        for key in keys:
            if isinstance(value, dict):
                value = value[key]
            else: # Handle lists/indices if needed in future
                 log.warning(f"Path '{path_string}' encountered non-dict element at '{key}'")
                 return default
        return value
    except KeyError:
        log.debug(f"Setting '{path_string}' not found, returning default: {default}")
        return default
    except Exception as e:
        log.error(f"Error accessing setting '{path_string}': {e}", exc_info=True)
        return default

# --- Example Usage (for testing when run directly) ---
if __name__ == "__main__":
    log.info("--- Configuration Loaded ---")
    import json
    # Pretty print the loaded settings (excluding potentially sensitive API parts for direct run)
    printable_settings = settings.copy()
    if 'api' in printable_settings:
        # Avoid printing full secrets if run directly
        for api_name, creds in printable_settings['api'].items():
            if 'secret' in creds: creds['secret'] = '********'
            if 'key' in creds: creds['key'] = creds['key'][:3]+'********' if creds['key'] else None
    log.info(json.dumps(printable_settings, indent=4, default=str)) # Use default=str for Decimal

    log.info("\n--- Testing Accessors ---")
    log.info(f"Quote Asset: {get_setting('trading.quote_asset')}")
    log.info(f"Max Grid Levels: {get_setting('trading.grid.max_levels')}")
    log.info(f"Base Order Size (Decimal): {get_setting('trading.grid.base_order_size_usd')} (Type: {type(get_setting('trading.grid.base_order_size_usd'))})")
    log.info(f"Binance Key (Obfuscated): {get_setting('api.binance_us.key')}")
    log.info(f"Non-existent setting: {get_setting('some.fake.setting', default='Not Found')}")