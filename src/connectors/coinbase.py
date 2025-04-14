# src/connectors/coinbase.py

import sys
import os
from pathlib import Path
import requests
import json
import uuid
import logging
from decimal import Decimal
from typing import Dict, Optional, List, Any
# === Use the OFFICIAL library installed via pip install coinbase-advanced-py ===
from coinbase.rest import RESTClient
logger = logging.getLogger(__name__)  # Initialize logger early
try:
    from coinbase.rest.error import CoinbaseAdvancedTradeAPIError
except ImportError:
    try:
        from coinbase.exceptions import CoinbaseAdvancedTradeAPIError
    except ImportError:
        try:
            from coinbase.rest.client import CoinbaseAdvancedTradeAPIError
        except ImportError:
            CoinbaseAdvancedTradeAPIError = Exception
            logger.warning("Using generic Exception for Coinbase API errors.")


# --- Add project root to sys.path FIRST ---
_project_root_for_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if str(_project_root_for_path) not in sys.path:
    sys.path.insert(0, str(_project_root_for_path))

# --- Project Imports ---
try:
    from src.utils.formatting import to_decimal, InvalidOperation
    from src.utils.logging_setup import setup_logging
    from config.settings import load_config
except ImportError as e:
    logger.error(f"ERROR: Could not import project modules: {e}")
    def to_decimal(v, default=None): return Decimal(
        str(v)) if v is not None else default


class CoinbaseConnector:
    """
    Handles connection and API calls to Coinbase using the official
    `coinbase-advanced-py` library (imports as `coinbase.rest`).
    Works with model objects where available, uses V2 API for withdrawals.
    """

    def __init__(self, api_key: str, private_key: str, config: Dict):
        """Initializes the Connector using API Key Name and Private Key."""
        if not api_key:
            raise ValueError("API Key Name required")
        if not private_key or "-----BEGIN" not in private_key:
            raise ValueError("Valid Private Key required")
        self.api_key_name = api_key
        self.private_key = private_key
        self.config = config
        self._client: Optional[RESTClient] = None
        # === Cache now stores Account objects ===
        # Store Account model objects keyed by currency
        self._accounts_cache: Dict[str, Any] = {}
        # === End Cache Change ===
        if not self._connect():
            raise ConnectionError("Failed initial Coinbase connection.")

    def _connect(self) -> bool:
        """Establishes connection using RESTClient and caches Account objects."""
        try:
            logger.info("Connecting to Coinbase (Official SDK)...")
            self._client = RESTClient(
                api_key=self.api_key_name, api_secret=self.private_key)
            logger.info("Testing connection via get_accounts()...")
            accounts_response = self._client.get_accounts()
            # Response object should have an 'accounts' attribute which is a list
            if accounts_response and hasattr(accounts_response, 'accounts') and isinstance(accounts_response.accounts, list):
                logger.info(
                    f"Connection OK. Found {len(accounts_response.accounts)} accounts.")
                # Pass the list of Account objects
                self._cache_accounts(accounts_response.accounts)
                return True
            else:
                logger.error(
                    f"get_accounts response invalid. Response: {accounts_response}")
                self._client = None
                return False
        except CoinbaseAdvancedTradeAPIError as e:
            logger.error(f"API Error connecting: {e}")
            self._client = None
            return False
        except Exception as e:
            logger.exception(f"Unexpected error connecting: {e}")
            self._client = None
            return False

    # === MODIFIED: Cache Account objects, access attributes ===
    def _cache_accounts(self, accounts_list: Optional[List[Any]]):
        """Caches Account objects by currency code, extracting needed IDs."""
        if not accounts_list:
            logger.warning("No accounts list provided to cache.")
            return
        self._accounts_cache = {}
        count = 0
        for acc in accounts_list:
            # Use getattr for safe access, assuming 'acc' is an object
            currency = getattr(acc, 'currency', None)
            uuid = getattr(acc, 'uuid', None)       # v3 UUID
            v2_id = getattr(acc, 'id', None)        # v2 legacy ID
            # Assume False if not present
            active = getattr(acc, 'active', False)
            balance_obj = getattr(acc, 'available_balance', None)
            balance_value = getattr(balance_obj, 'value', None)

            if currency and uuid and v2_id:  # Require currency and BOTH IDs for full functionality
                # Add converted balance to object
                acc.balance_decimal = to_decimal(
                    balance_value, default=Decimal('0.0'))
                # Store the whole Account object
                self._accounts_cache[currency] = acc
                count += 1
                # Log if active status is missing/false? Assume active=True from list_accounts? Check API behavior.
                # logger.debug(f"Cached {currency}: UUID={uuid}, ID={v2_id}, Active={active}, Balance={acc.balance_decimal}")
            else:
                logger.debug(
                    f"Skipping cache (missing currency/uuid/v2_id): Currency={currency}, UUID={uuid}, V2_ID={v2_id}")
        logger.info(f"Cached {count} accounts with required IDs.")
    # === END MODIFICATION ===

    # === MODIFIED: Get account object from cache ===
    def _get_account_data(self, currency_code: str, refresh: bool = False) -> Optional[Any]:
        """Gets the cached Account object for a currency, optionally refreshing."""
        currency_code = currency_code.upper()
        account_obj = self._accounts_cache.get(currency_code)
        needs_refresh = account_obj is None or refresh
        v2_id = getattr(account_obj, 'id', None)
        if account_obj and not v2_id:
            needs_refresh = True  # Refresh if v2 ID missing

        if needs_refresh:
            if refresh:
                logger.info(f"Refreshing cache for {currency_code}...")
            else:
                logger.warning(
                    f"Account data for '{currency_code}' needs fetch/refresh.")
            client = self.get_client()
            if not client:
                return None
            try:
                accounts_response = client.get_accounts()
                if accounts_response and hasattr(accounts_response, 'accounts') and isinstance(accounts_response.accounts, list):
                    self._cache_accounts(accounts_response.accounts)
                    account_obj = self._accounts_cache.get(currency_code)
                else:
                    logger.error("Failed to re-fetch accounts.")
            except Exception as e:
                logger.error(f"Error re-fetching accounts: {e}")

        v2_id = getattr(account_obj, 'id', None)
        if account_obj is None:
            logger.error(f"Account object for '{currency_code}' not found.")
        elif not v2_id:
            logger.error(
                f"V2 Account ID ('id') still missing for {currency_code} after refresh.")
        return account_obj
    # === END MODIFICATION ===

    def get_client(self) -> Optional[RESTClient]:
        """Returns the initialized client instance, attempting reconnect if needed."""
        if self._client is None:
            logger.warning(
                "Coinbase client not initialized. Attempting reconnect...")
            if not self._connect():
                logger.error("Reconnection failed.")
                return None
        return self._client

    # === MODIFIED: Get balance from cached Account object ===
    def get_asset_balance(self, asset: str) -> Optional[Decimal]:
        """Retrieves the available balance from the cached Account object."""
        asset = asset.upper()
        account_obj = self._get_account_data(asset)
        if account_obj:
            # Access pre-converted balance stored on the object during cache
            balance = getattr(account_obj, 'balance_decimal', None)
            if balance is not None:
                logger.debug(
                    f"Available balance for {asset} (from cache): {balance}")
                return balance
            else:  # Fallback if pre-conversion failed or attribute missing
                logger.warning(
                    f"Pre-converted balance missing for {asset}, trying direct access.")
                balance_obj = getattr(account_obj, 'available_balance', None)
                balance_value = getattr(balance_obj, 'value', None)
                balance = to_decimal(balance_value)
                if balance is not None:
                    return balance
                else:
                    logger.error(f"Could not get valid balance for {asset}.")
                    return Decimal('0.0')
        else:
            logger.warning(
                f"No account data found for {asset}. Returning zero balance.")
            return Decimal('0.0')
    # === END MODIFICATION ===

    # --- buy_crypto using dict response ---
    def buy_crypto(self, amount_quote: Decimal, currency_pair: str, **kwargs) -> Optional[Dict]:
        """Executes a market buy order using the Advanced Trade API."""
        client = self.get_client()
        if not client:
            return None
        try:
            base, quote = currency_pair.upper().split('-')
            product_id = f"{base}-{quote}"
        except ValueError:
            logger.error(f"Invalid pair: '{currency_pair}'.")
            return None
        quote_size_str = f"{amount_quote:.2f}"
        try:
            logger.info(
                f"Attempting Market BUY for {product_id} quote_size {quote_size_str}...")
            cid = kwargs.get('client_order_id',
                             f"dca_buy_{str(uuid.uuid4())[:8]}")
            order_response = client.market_order_buy(
                client_order_id=cid, product_id=product_id, quote_size=quote_size_str)
            logger.info(f"Market BUY response: {order_response}")
            if isinstance(order_response, dict) and order_response.get('order_id'):
                order_dict = {"order_id": order_response.get('order_id'), "success": order_response.get('success', True),
                              "failure_reason": order_response.get('failure_reason'), "client_order_id": order_response.get('client_order_id')}
                if not order_dict["success"]:
                    logger.error(
                        f"Market buy failed: {order_dict['failure_reason']}")
                    return None
                return order_dict
            else:
                logger.error(
                    f"Market buy response unexpected: {order_response}")
                return None
        except CoinbaseAdvancedTradeAPIError as e:
            logger.error(f"API Error during market buy: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error during market buy: {e}")
            return None

    # --- withdraw_crypto using direct V2 API call ---
    def withdraw_crypto(self, amount: Decimal, currency: str, crypto_address: str, crypto_memo: Optional[str] = None, **kwargs) -> Optional[Dict]:
        """Attempts withdrawal using a direct V2 API call via the client's post method."""
        client = self.get_client()
        if not client:
            return None
        currency = currency.upper()
        account_obj = self._get_account_data(currency)  # Get cached object
        # Get V2 ID from object
        account_id_v2 = getattr(account_obj, 'id', None)
        if not account_id_v2:
            logger.error(f"Cannot withdraw: V2 ID for {currency} not found.")
            return None
        if not crypto_address:
            logger.error("Address required.")
            return None
        try:
            precision = 7 if currency == 'XLM' else 8
            amount_str = f"{amount:.{precision}f}"
            idem = kwargs.get('idem', str(uuid.uuid4()))
            path = f"/v2/accounts/{account_id_v2}/transactions"
            body = {"type": "send", "to": crypto_address, "amount": amount_str, "currency": currency, "idem": idem,
                    "description": f"GeminiTrader Funding Pipeline ({currency})"}
            if crypto_memo:
                body["destination_tag"] = crypto_memo
            log_msg = f"Attempting V2 Send {amount_str} {currency} to {crypto_address[:5]}..." + (
                f" memo {crypto_memo}" if crypto_memo else "")
            logger.info(log_msg)
            logger.debug(f"Calling client.post('{path}', data={body})")

            if hasattr(client, 'post'):
                response = client.post(path, data=body)
                logger.info(f"V2 Send response: {response}")
                if isinstance(response, dict) and 'data' in response and response['data'].get('id'):
                    logger.info(f"V2 send OK: ID {response['data'].get('id')}")
                    return response['data']
                else:
                    errors = response.get('errors')
                    logger.error(f"V2 send failed: {errors or response}")
                    return None
            else:
                logger.error("'post' method not found on RESTClient.")
                return None
        except CoinbaseAdvancedTradeAPIError as e:
            logger.error(f"API Error during V2 send: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error during V2 send: {e}")
            return None


# --- Example usage block ---
if __name__ == '__main__':
    # (Test block code omitted for brevity - use previous version)
    pass

# File path: src/connectors/coinbase.py
