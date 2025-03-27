# server.py

import os
import json
import requests
import datetime
import time

# Import the correct SDK client
from coinbase.rest import RESTClient

from flask import Flask, request, jsonify
from flask_cors import CORS

# --- Configuration ---
CREDENTIALS_FILE_NAME = "cdp_api_key.json"
CREDENTIALS_FOLDER = "credentials"
PUBLIC_BASE_URL = "https://api.exchange.coinbase.com"  # For candles & public ticker
DEFAULT_PRODUCT_ID = "BTC-USD"
DEFAULT_GRANULARITY = 3600

# --- Load Credentials & Init SDK Client ---
COINBASE_API_KEY_NAME = None
COINBASE_API_PRIVATE_KEY_PEM = None
credentials_loaded = False
rest_client = None
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credentials_path = os.path.join(
        script_dir, CREDENTIALS_FOLDER, CREDENTIALS_FILE_NAME)
    print(f"Attempting to load Cloud API Key from: {credentials_path}")
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(f"File not found: {credentials_path}")
    with open(credentials_path, 'r') as f:
        credentials_data = json.load(f)
    COINBASE_API_KEY_NAME = credentials_data.get('name')
    COINBASE_API_PRIVATE_KEY_PEM = credentials_data.get('privateKey')
    if not COINBASE_API_KEY_NAME or not COINBASE_API_PRIVATE_KEY_PEM:
        raise ValueError("Missing 'name' or 'privateKey' in JSON")
    print("Cloud API Key credentials successfully read from file.")
    credentials_loaded = True
    print(f"  API Key Name: {COINBASE_API_KEY_NAME}")
    # Initialize Client only if credentials loaded
    try:
        print("Initializing coinbase.rest.RESTClient with Cloud Key...")
        rest_client = RESTClient(
            api_key=COINBASE_API_KEY_NAME,
            api_secret=COINBASE_API_PRIVATE_KEY_PEM
        )
        print("REST Client initialized successfully.")
    except Exception as client_e:
        print(f"!!! ERROR Initializing REST Client: {client_e}")
        import traceback
        traceback.print_exc()
        rest_client = None
        credentials_loaded = False  # Failed init means not ready
except Exception as e:
    print(f"\n!!! ERROR Loading Credentials or Initializing Client: {e}\n")
    credentials_loaded = False
if not credentials_loaded or not rest_client:
    print("WARNING: Credentials loading or client initialization failed. Authenticated endpoints will fail.")

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

# --- API Status Endpoint ---


@app.route('/api/status')
def get_api_status():
    client_ready = credentials_loaded and (rest_client is not None)
    return jsonify({"credentials_loaded": client_ready})

# --- API Endpoint for Chart Data (Public) ---


@app.route('/api/candles')
def get_candles():
    """ Fetches candlestick data (Public). """
    product_id = request.args.get('product_id', DEFAULT_PRODUCT_ID)
    try:
        granularity = int(request.args.get('granularity', DEFAULT_GRANULARITY))
    except ValueError:
        return jsonify({"error": "Invalid granularity value"}), 400
    start_iso = request.args.get('start', None)
    end_iso = request.args.get('end', None)
    endpoint = f"/products/{product_id}/candles"
    url = PUBLIC_BASE_URL + endpoint
    params = {"granularity": granularity}
    if start_iso:
        params["start"] = start_iso
    if end_iso:
        params["end"] = end_iso
    print(f"Fetching candles: {url} with params {params}")
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        candles_data = response.json()
        print(f"Coinbase returned {len(candles_data)} candles.")
        return jsonify(candles_data)

    # --- CORRECTED ERROR HANDLING for /api/candles ---
    except requests.exceptions.HTTPError as err:
        print(f"HTTP error fetching candles: {err}")
        details = f"HTTP Error {err.response.status_code}"  # Default
        try:
            details_json = err.response.json()
            details = details_json.get('message', details_json)
        except json.JSONDecodeError:
            try:
                details = err.response.text
            except:
                pass  # Ignore if text cannot be accessed
        return jsonify({"error": f"API error {err.response.status_code}", "details": details}), err.response.status_code

    except requests.exceptions.RequestException as err:
        print(f"Request error fetching candles: {err}")
        return jsonify({"error": f"Connection error: {err}"}), 502

    except Exception as e:
        print(f"Unexpected error fetching candles: {e}")
        return jsonify({"error": f"Server error: {e}"}), 500
    # --- END CORRECTION ---


# --- NEW: Public Ticker Endpoint ---
@app.route('/api/ticker')
def get_ticker():
    """ Fetches public ticker data for a specific product ID. """
    product_id = request.args.get('product_id')
    if not product_id:
        return jsonify({"error": "Missing 'product_id' query parameter"}), 400
    endpoint = f"/products/{product_id}/ticker"
    url = PUBLIC_BASE_URL + endpoint
    print(f"Fetching public ticker: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        ticker_data = response.json()
        price = ticker_data.get('price')
        if price is None:
            return jsonify({"error": f"Could not find price for {product_id}"}), 404
        return jsonify({"product_id": product_id, "price": price})

    # --- CORRECTED ERROR HANDLING for /api/ticker ---
    except requests.exceptions.HTTPError as err:
        status_code = err.response.status_code
        print(f"HTTP error fetching ticker for {product_id}: {err}")
        if status_code == 404:
            return jsonify({"error": f"Product ID '{product_id}' not found."}), 404
        details = f"HTTP Error {status_code}"  # Default
        try:
            details_json = err.response.json()
            details = details_json.get('message', details_json)
        except json.JSONDecodeError:
            try:
                details = err.response.text
            except:
                pass
        return jsonify({"error": f"API error {status_code}", "details": details}), status_code
    # --- END CORRECTION ---

    except requests.exceptions.RequestException as err:
        print(f"Request error fetching ticker for {product_id}: {err}")
        return jsonify({"error": f"Connection error: {err}"}), 502
    except Exception as e:
        print(f"Unexpected error fetching ticker for {product_id}: {e}")
        return jsonify({"error": f"Server error: {e}"}), 500

# --- Accounts Endpoint (Implemented with SDK) ---


@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """ Fetches account balances using coinbase-advanced-py SDK (Cloud Key Auth). """
    print("Received request for /api/accounts")
    if not rest_client:
        print("-> REST Client not initialized, returning 503.")
        return jsonify({"error": "API Client not ready on server.", "accounts": []}), 503
    try:
        print("Attempting client.get_accounts()...")
        sdk_response = rest_client.get_accounts()
        print(f"Successfully processed SDK response for accounts.")
        account_list = []
        if hasattr(sdk_response, 'accounts') and hasattr(sdk_response.accounts, '__iter__'):
            for account_sdk_obj in sdk_response.accounts:
                if hasattr(account_sdk_obj, 'to_dict'):
                    account_list.append(account_sdk_obj.to_dict())
                elif isinstance(account_sdk_obj, dict):
                    account_list.append(account_sdk_obj)
                else:
                    account_list.append(repr(account_sdk_obj))
            print(f"  -> Found {len(account_list)} accounts in response.")
            return jsonify({"accounts": account_list})
        else:
            print(
                f"Warning: Unexpected response structure from get_accounts(): {type(sdk_response)}")
            return jsonify({"accounts": []})

    # --- CORRECTED ERROR HANDLING for /api/accounts ---
    except Exception as e:
        print(f"!!! ERROR during SDK call (get_accounts): {e}")
        error_message = f"Failed to fetch accounts via SDK: {str(e)}"
        status_code = 500
        # Check if the exception 'e' has a 'response' attribute (like SDK/requests exceptions)
        if hasattr(e, 'response') and e.response is not None:
            status_code = e.response.status_code
            # --- CORRECTED INNER TRY/EXCEPT ---
            try:
                error_details = e.response.json()  # Try parsing JSON first
            except json.JSONDecodeError:
                try:
                    error_details = e.response.text  # Fallback to text
                except:
                    # Final fallback
                    error_details = "(Could not get error details)"
            # --- END CORRECTION ---
            print(f"--- SDK API Error Details (Status: {status_code}) ---")
            print(error_details)
            if status_code == 401:
                error_message = f"SDK Auth failed (401): Check Cloud Key Permissions/Clock."
            elif status_code == 429:
                error_message = "SDK Rate Limit Exceeded (429)."
            else:
                error_message = f"SDK API Error ({status_code})"
        else:
            # If it's a general Python error, print traceback
            import traceback
            traceback.print_exc()
        return jsonify({"error": error_message, "accounts": []}), status_code
    # --- END CORRECTION ---

# --- Orders Endpoint (Still Not Implemented) ---


@app.route('/api/orders', methods=['POST'])
def place_order():
    print("Received request for /api/orders")
    if not rest_client:
        return jsonify({"error": "API Client not ready."}), 503
    print("-> Actual /api/orders call using SDK not implemented. Returning 501.")
    return jsonify({"error": "Order placement not implemented."}), 501


# --- Run App ---
if __name__ == '__main__':
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=True)
