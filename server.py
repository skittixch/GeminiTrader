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

# --- Helper Function to Safely Convert SDK Objects ---


def sdk_object_to_dict(obj):
    """ Converts SDK objects with to_dict() method, handles nested structures. """
    if hasattr(obj, 'to_dict') and callable(obj.to_dict):
        return sdk_object_to_dict(obj.to_dict())  # Recursively convert result
    elif isinstance(obj, dict):
        return {k: sdk_object_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sdk_object_to_dict(item) for item in obj]
    else:
        # Convert datetime or other specific types if needed, otherwise return as is
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()  # Example: Convert datetime to ISO string
        return obj


# --- Handle SDK Errors Gracefully ---
def handle_sdk_error(e, context="SDK call"):
    """ Standard way to log and format SDK errors for JSON response. """
    print(f"!!! ERROR during {context}: {e}")
    error_message = f"Failed during {context}: {str(e)}"
    status_code = 500
    details = None
    if hasattr(e, 'response') and e.response is not None:
        status_code = e.response.status_code
        try:
            error_details = e.response.json()
        except json.JSONDecodeError:
            try:
                error_details = e.response.text
            except:
                error_details = "(Could not get error details)"
        print(f"--- SDK API Error Details (Status: {status_code}) ---")
        print(error_details)
        if isinstance(error_details, dict):
            details = error_details.get('message', error_details)
        else:
            details = str(error_details)

        if status_code == 401:
            error_message = f"SDK Auth failed (401): Check Cloud Key Permissions/Clock."
        elif status_code == 429:
            error_message = "SDK Rate Limit Exceeded (429)."
        elif status_code == 400:
            error_message = f"SDK Bad Request (400)"  # Details usually helpful
        else:
            error_message = f"SDK API Error ({status_code})"
    else:
        import traceback
        traceback.print_exc()
    return jsonify({"error": error_message, "details": details}), status_code


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
    except requests.exceptions.HTTPError as err:
        print(f"HTTP error fetching candles: {err}")
        details = f"HTTP Error {err.response.status_code}"
        try:
            details_json = err.response.json()
            details = details_json.get('message', details_json)
        except:
            pass
        return jsonify({"error": f"API error {err.response.status_code}", "details": details}), err.response.status_code
    except requests.exceptions.RequestException as err:
        print(f"Request error fetching candles: {err}")
        return jsonify({"error": f"Connection error: {err}"}), 502
    except Exception as e:
        print(f"Unexpected error fetching candles: {e}")
        return jsonify({"error": f"Server error: {e}"}), 500

# --- Public Ticker Endpoint ---


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
    except requests.exceptions.HTTPError as err:
        status_code = err.response.status_code
        print(f"HTTP error fetching ticker for {product_id}: {err}")
        if status_code == 404:
            return jsonify({"error": f"Product ID '{product_id}' not found."}), 404
        details = f"HTTP Error {status_code}"
        try:
            details_json = err.response.json()
            details = details_json.get('message', details_json)
        except:
            pass
        return jsonify({"error": f"API error {status_code}", "details": details}), status_code
    except requests.exceptions.RequestException as err:
        print(f"Request error fetching ticker for {product_id}: {err}")
        return jsonify({"error": f"Connection error: {err}"}), 502
    except Exception as e:
        print(f"Unexpected error fetching ticker for {product_id}: {e}")
        return jsonify({"error": f"Server error: {e}"}), 500

# --- Accounts Endpoint (SDK) ---


@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """ Fetches account balances using SDK. """
    print("Received request for /api/accounts")
    if not rest_client:
        print("-> REST Client not initialized, returning 503.")
        return jsonify({"error": "API Client not ready on server.", "accounts": []}), 503
    try:
        print("Attempting client.get_accounts()...")
        sdk_response = rest_client.get_accounts()
        print(f"Successfully processed SDK response for accounts.")

        # Convert response to dict using helper
        response_dict = sdk_object_to_dict(sdk_response)

        # Extract accounts list (assuming standard structure)
        account_list = response_dict.get('accounts', [])

        print(f"  -> Found {len(account_list)} accounts in response.")
        return jsonify({"accounts": account_list})

    except Exception as e:
        return handle_sdk_error(e, context="get_accounts")

# --- NEW: Open Orders Endpoint (SDK) ---


@app.route('/api/open_orders', methods=['GET'])
def get_open_orders():
    """ Fetches open orders using SDK. """
    print("Received request for /api/open_orders")
    if not rest_client:
        print("-> REST Client not initialized, returning 503.")
        return jsonify({"error": "API Client not ready on server.", "orders": []}), 503
    try:
        print("Attempting client.list_orders(order_status=['OPEN'])...")
        # Fetch only OPEN orders
        # Note: The SDK might use different parameter names/values than the raw API.
        # Check SDK docs if `order_status=['OPEN']` doesn't work.
        # Common alternatives: `open_orders=True` or specific statuses like PENDING, ACTIVE.
        # Based on coinbase-advanced-py source, order_status seems correct.
        sdk_response = rest_client.list_orders(order_status=['OPEN'])
        print("Successfully processed SDK response for open orders.")

        # Convert response to dict using helper
        response_dict = sdk_object_to_dict(sdk_response)

        # Extract orders list
        order_list = response_dict.get('orders', [])

        print(f"  -> Found {len(order_list)} open orders.")
        return jsonify({"orders": order_list})

    except Exception as e:
        return handle_sdk_error(e, context="list_orders (open)")


# --- Order Placement Endpoint (Not Implemented) ---
@app.route('/api/orders', methods=['POST'])
def place_order():
    print("Received request for POST /api/orders")
    if not rest_client:
        return jsonify({"error": "API Client not ready."}), 503
    # --- Order Placement Logic Would Go Here ---
    # 1. Get order details from request.json
    #    product_id = request.json.get('product_id')
    #    side = request.json.get('side') # 'BUY' or 'SELL'
    #    order_type = request.json.get('type') # 'LIMIT' or 'MARKET'
    #    size = request.json.get('size') # Base size
    #    price = request.json.get('price') # For limit orders
    #    client_order_id = str(uuid.uuid4()) # Generate unique ID
    #
    # 2. Validate input
    #
    # 3. Call appropriate SDK method (e.g., client.create_order)
    #    try:
    #        if order_type == 'LIMIT':
    #           sdk_response = rest_client.create_order(
    #               client_order_id=client_order_id,
    #               product_id=product_id,
    #               side=side,
    #               order_configuration={ # Structure depends on SDK version
    #                   "limit_limit_gtd": {
    #                       "base_size": size,
    #                       "limit_price": price,
    #                       "post_only": False, # Example
    #                       # "end_time": ... # For GTD
    #                   }
    #               }
    #           )
    #        elif order_type == 'MARKET':
    #            # Market order structure might differ (quote_size or base_size)
    #            sdk_response = rest_client.create_order(...)
    #        else:
    #            return jsonify({"error": "Unsupported order type"}), 400
    #
    #        response_dict = sdk_object_to_dict(sdk_response)
    #        return jsonify(response_dict), 201 # Created
    #
    #    except Exception as e:
    #        return handle_sdk_error(e, context="create_order")
    #
    print("-> Actual order placement using SDK not implemented. Returning 501.")
    return jsonify({"error": "Order placement not implemented."}), 501


# --- Run App ---
if __name__ == '__main__':
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=True)
