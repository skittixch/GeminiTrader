# test_manual_jwt.py

import os
import json
import http.client  # Use Python's built-in library
import time
import uuid

# Use PyJWT for JWT creation
import jwt
# Cryptography for loading the key
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_private_key
import datetime  # Need this for JWT timestamps

# --- Configuration ---
CREDENTIALS_FILE_NAME = "cdp_api_key.json"  # Ensure this matches
CREDENTIALS_FOLDER = "credentials"
API_HOST = "api.coinbase.com"  # Host for http.client
SERVICE_NAME = "retail_rest_api_proxy"  # Audience for JWT

# --- Load Credentials ---
api_key_name = None
private_key_pem = None
private_key_obj = None  # Store the loaded key object
credentials_loaded = False

try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credentials_path = os.path.join(
        script_dir, CREDENTIALS_FOLDER, CREDENTIALS_FILE_NAME)
    print(f"--- Loading Credentials from: {credentials_path} ---")

    if not os.path.exists(credentials_path):
        raise FileNotFoundError(f"File not found: {credentials_path}")

    with open(credentials_path, 'r') as f:
        credentials_data = json.load(f)
    api_key_name = credentials_data.get('name')
    private_key_pem = credentials_data.get('privateKey')
    if not api_key_name or not private_key_pem:
        raise ValueError("Missing 'name' or 'privateKey'")

    # Load the private key *object*
    try:
        private_key_obj = load_pem_private_key(
            private_key_pem.encode('utf-8'), password=None)
        print("Private key object loaded successfully.")
    except Exception as key_error:
        raise ValueError(f"Could not load key object: {key_error}")

    print("Credentials successfully read.")
    print(f"  API Key Name (kid): {api_key_name}")
    credentials_loaded = True

except Exception as e:
    print(f"!!! ERROR Loading Credentials: {e}")
    exit(1)


# --- Helper Function to Generate JWT ---
def generate_jwt_manual(method, request_path):
    """ Generates a JWT for Coinbase Cloud API authentication (Manual Version). """
    if not credentials_loaded or not private_key_obj:
        print("Error: Cannot generate JWT.")
        return None
    try:
        # e.g., "GET /api/v3/brokerage/accounts"
        uri = f"{method.upper()} {request_path}"
        payload = {
            'sub': api_key_name, 'iss': "coinbase-cloud",
            'nbf': datetime.datetime.now(tz=datetime.timezone.utc),
            'exp': datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(minutes=2),
            'aud': [SERVICE_NAME], 'uri': uri
        }
        headers = {'alg': 'ES256', 'kid': api_key_name,
                   'nonce': uuid.uuid4().hex}
        token = jwt.encode(payload, private_key_obj,
                           algorithm="ES256", headers=headers)
        # Avoid printing full token
        print(f"--- Generated JWT (first 10 chars): {token[:10]}... ---")
        return token
    except Exception as e:
        print(f"Error generating JWT: {e}")
        return None


# --- Make the Authenticated API Call ---
if credentials_loaded:
    try:
        method = "GET"
        # Define the specific path WITH query parameters if needed
        request_path_with_query = "/api/v3/brokerage/accounts"  # Start with base path
        # Add query params like limit=1 ?
        # query_params = "?limit=1" # Optional: Add query parameters here
        # request_path_with_query += query_params

        print(
            f"\n--- Generating JWT for: {method} {request_path_with_query} ---")
        auth_token = generate_jwt_manual(method, request_path_with_query)

        if not auth_token:
            raise Exception("Failed to generate JWT token.")

        print(
            f"--- Making Request: {method} https://{API_HOST}{request_path_with_query} ---")
        conn = http.client.HTTPSConnection(API_HOST)

        # Prepare headers, including the generated JWT
        request_headers = {
            'Authorization': f'Bearer {auth_token}',  # Use JWT as Bearer token
            'Content-Type': 'application/json'  # Still needed even for GET
        }
        # Don't log token
        print(
            f"  Headers: {{'Authorization': 'Bearer ...', 'Content-Type': ...}}")

        # Make the request (payload is empty for GET)
        payload = ''
        conn.request(method, request_path_with_query, payload, request_headers)

        # Get and process the response
        res = conn.getresponse()
        status = res.status
        reason = res.reason
        print(f"\n--- Response Status: {status} {reason} ---")

        data = res.read()
        conn.close()  # Close the connection

        print("--- Response Body (Decoded) ---")
        response_body_str = data.decode("utf-8")
        print(response_body_str)

        # Try parsing JSON and extracting info
        if 200 <= status < 300:
            print("\n--- SUCCESS ---")
            try:
                response_json = json.loads(response_body_str)
                # Look for USD/USDT
                usd_balance = "Not Found"
                usdt_balance = "Not Found"
                for acc in response_json.get('accounts', []):
                    currency = acc.get('currency')
                    balance_info = acc.get('available_balance', {})
                    value = balance_info.get('value', 'N/A')
                    if currency == 'USD':
                        usd_balance = value
                    elif currency == 'USDT':
                        usdt_balance = value
                print(f"  USD Available: {usd_balance}")
                print(f"  USDT Available: {usdt_balance}")
            except json.JSONDecodeError:
                print("  (Could not parse response body as JSON)")
        else:
            print("\n--- FAILED ---")
            if status == 401:
                print(
                    "!!! NOTE: 401 Unauthorized - Check API Key Permissions or Clock Skew.")
            # Further error details are already printed in the body

    except Exception as e:
        print(f"\n!!! ERROR during API call: {e}")
        import traceback
        traceback.print_exc()

else:
    print("\n--- Skipping API call as credentials failed to load. ---")

print("\n--- Test Script Finished ---")
