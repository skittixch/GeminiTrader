# server.py

import requests
import datetime
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app) # Allow cross-origin requests

# --- Configuration ---
BASE_URL = "https://api.exchange.coinbase.com"
DEFAULT_PRODUCT_ID = "BTC-USD"
DEFAULT_GRANULARITY = 3600  # Default to 1-hour candles

# --- API Endpoint ---
@app.route('/api/candles')
def get_candles():
    """
    API endpoint to fetch candlestick data from Coinbase.
    Accepts query parameters: product_id, granularity, start, end.
    """
    # Get parameters from query string, with defaults
    product_id = request.args.get('product_id', DEFAULT_PRODUCT_ID)
    try:
        # Ensure granularity is treated as an integer
        granularity = int(request.args.get('granularity', DEFAULT_GRANULARITY))
    except ValueError:
        print("Error: Received invalid granularity value in request.")
        return jsonify({"error": "Invalid granularity value"}), 400

    start_iso = request.args.get('start', None)
    end_iso = request.args.get('end', None)

    # --- Construct the Coinbase Request ---
    endpoint = f"/products/{product_id}/candles"
    url = BASE_URL + endpoint

    params = { "granularity": granularity }
    if start_iso:
        params["start"] = start_iso
    if end_iso:
        params["end"] = end_iso

    print(f"Received request for /api/candles:")
    print(f"  Product: {product_id}, Granularity: {granularity}")
    print(f"  Start: {start_iso}, End: {end_iso}")
    print(f"  Requesting from Coinbase: {url} with params {params}\n")

    # --- Make the API Request to Coinbase ---
    try:
        response = requests.get(url, params=params, timeout=15) # Increased timeout slightly
        response.raise_for_status() # Check for HTTP errors (4xx/5xx)

        candles_data = response.json()

        if not candles_data:
            print("Coinbase returned no data.")
            return jsonify([]) # Return empty list if no data
        else:
            print(f"Coinbase returned {len(candles_data)} candles.")

            # *** ADDED DEBUGGING ***
            if len(candles_data) > 1:
                first_ts = candles_data[0][0]
                last_ts = candles_data[-1][0]
                print(f"  DEBUG (server.py): First candle timestamp: {first_ts} ({datetime.datetime.fromtimestamp(first_ts, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')})")
                print(f"  DEBUG (server.py): Last candle timestamp:  {last_ts} ({datetime.datetime.fromtimestamp(last_ts, tz=datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')})")
                if first_ts > last_ts:
                    print("  DEBUG (server.py): WARNING - Data appears newest-first before sending!")
                else:
                    print("  DEBUG (server.py): Data appears oldest-first before sending (Correct).")
            elif len(candles_data) == 1:
                 print(f"  DEBUG (server.py): Only one candle returned. Timestamp: {candles_data[0][0]}")
            # *** END DEBUGGING ***

            # Send data exactly as received from Coinbase (assuming oldest-first)
            return jsonify(candles_data)

    except requests.exceptions.Timeout:
        print(f"Error: Coinbase request timed out")
        return jsonify({"error": "Coinbase API request timed out"}), 504
    except requests.exceptions.HTTPError as http_err:
        print(f"Error: Coinbase HTTP error: {http_err}")
        try: error_details = response.json()
        except ValueError: error_details = response.text
        return jsonify({"error": f"Coinbase API error {response.status_code}", "details": error_details}), response.status_code
    except requests.exceptions.RequestException as req_err:
        print(f"Error: Coinbase request error: {req_err}")
        return jsonify({"error": f"Failed to connect to Coinbase API: {req_err}"}), 502
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": f"An unexpected server error occurred: {e}"}), 500


# --- Run the Flask App ---
if __name__ == '__main__':
    print("Starting Flask server for chart data...")
    # Make sure debug=True is enabled for auto-reload on save
    app.run(host='0.0.0.0', port=5000, debug=True)