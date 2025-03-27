# test_coinbase_sdk.py

import os
import json
# Import the correct SDK client
from coinbase.rest import RESTClient
import time

# --- Configuration ---
CREDENTIALS_FILE_NAME = "cdp_api_key.json"  # Ensure this matches your file
CREDENTIALS_FOLDER = "credentials"

# --- Load Credentials ---
api_key_name = None
private_key_pem = None
credentials_loaded = False

try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credentials_path = os.path.join(
        script_dir, CREDENTIALS_FOLDER, CREDENTIALS_FILE_NAME)
    print(f"--- Loading Credentials from: {credentials_path} ---")

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(f"File not found at {credentials_path}")

    with open(credentials_path, 'r') as f:
        credentials_data = json.load(f)

    # Use the keys as expected by RESTClient
    # 'name' from JSON goes to 'api_key'
    api_key_name = credentials_data.get('name')
    # 'privateKey' from JSON goes to 'api_secret'
    private_key_pem = credentials_data.get('privateKey')

    if not api_key_name or not private_key_pem:
        raise ValueError("Credentials file is missing 'name' or 'privateKey'.")

    print("Credentials successfully read from file.")
    print(f"  API Key Name (used as api_key): {api_key_name}")
    credentials_loaded = True

except Exception as e:
    print(f"!!! ERROR Loading Credentials: {e}")
    exit(1)


# --- Initialize SDK Client (Using coinbase-advanced-py/RESTClient) ---
rest_client = None  # Renamed variable for clarity
if credentials_loaded:
    try:
        print("\n--- Initializing coinbase.rest.RESTClient ---")
        # Initialize using the correct Client class and arguments
        rest_client = RESTClient(
            api_key=api_key_name,      # 'name' from JSON
            api_secret=private_key_pem  # PEM string from JSON
        )
        print("REST Client initialized successfully.")
    except Exception as e:
        print(f"!!! ERROR Initializing REST Client: {e}")
        import traceback
        traceback.print_exc()
        rest_client = None
else:
    print("Skipping client initialization as credentials failed to load.")


# --- Test API Call (List Accounts) ---
if rest_client:
    try:
        print("\n--- Attempting to List Accounts (client.get_accounts) ---")
        # Use the SDK's get_accounts method
        accounts_data = rest_client.get_accounts()

        # The documentation suggests get_accounts returns a dict directly
        # matching the API response structure, often including an 'accounts' list
        if isinstance(accounts_data, dict) and 'accounts' in accounts_data:
            account_list = accounts_data.get('accounts', [])
            print(f"SUCCESS: Fetched {len(account_list)} accounts.")
            print("--- Accounts Data ---")
            # Pretty print the JSON-like structure
            print(json.dumps(accounts_data, indent=2))

            # Specifically find and print USDT/USD balance if present
            usdt_balance = "Not Found"
            usd_balance = "Not Found"
            for acc in account_list:
                # Accessing values directly based on typical V3 structure
                currency = acc.get('currency')
                # Balances are usually nested under 'available_balance' or similar
                # Use available for trading? Or 'balance'? Check response!
                balance_info = acc.get('available_balance', {})
                value = balance_info.get('value', 'N/A')

                if currency == 'USDT':
                    usdt_balance = value
                elif currency == 'USD':
                    usd_balance = value

            print("\n--- Specific Balances ---")
            print(f"  USD Available Balance: {usd_balance}")
            print(f"  USDT Available Balance: {usdt_balance}")

        else:
            # If the structure is different, print the raw response
            print("SUCCESS: Received response (Unexpected structure?):")
            print(accounts_data)

    except Exception as e:
        print(f"\n!!! ERROR during API call (get_accounts): {e}")
        # Check if the error object has response details (common with requests-based errors)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.json()
                print("--- API Error Details ---")
                print(json.dumps(error_details, indent=2))
                if e.response.status_code == 401:
                    print(
                        "!!! NOTE: 401 Unauthorized - Check API Key Permissions on CDP Portal (need View/Read for accounts) or Clock Skew.")
            except:
                print(
                    f"--- API Raw Error Response Text (Status: {e.response.status_code}) ---")
                print(e.response.text)
        else:
            # Print general exception info if no response details attached
            import traceback
            traceback.print_exc()

else:
    print("\n--- Skipping API call as REST Client was not initialized. ---")

print("\n--- Test Script Finished ---")
