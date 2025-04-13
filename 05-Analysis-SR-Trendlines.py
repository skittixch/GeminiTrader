#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# Cell 1: Environment Setup, Logging, Configuration

import pandas as pd
import numpy as np
import logging
import sys
import os
from decimal import Decimal, getcontext

# --- Core Configuration ---
SYMBOL = "BTCUSDT" # Define the primary symbol we are working with
QUOTE_ASSET = 'USDT' # Quote asset for calculations
BASE_ASSET = SYMBOL.replace(QUOTE_ASSET, '') # Base asset

# --- Precision ---
# Set precision for Decimal calculations (adjust as needed, high enough for crypto)
getcontext().prec = 18 # Example: 18 decimal places

# --- Logging Setup ---
# Clear existing root handlers to avoid duplicate logs in Jupyter environments
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    stream=sys.stdout) # Explicitly direct logs to stdout

# --- Pandas Display Options ---
pd.set_option('display.max_rows', 100)
pd.set_option('display.max_columns', 20)
pd.set_option('display.width', 1000)
# CRITICAL: Ensure Decimal/float output is not in scientific notation
# Use a lambda function for more robust Decimal formatting if needed
pd.set_option('display.float_format', lambda x: f'{Decimal(str(x)):.8f}') # Format as Decimal with 8 places for display

logging.info("✅ Cell 1 Setup Complete: Imports, Logging, Config.")

# End of Cell 1


# In[ ]:


# Cell 2: Get Exchange Filters and Define Adjustment Helpers

import logging
import os
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import math
from binance.client import Client
from dotenv import load_dotenv
import sys # Import sys here for logging stream

# --- Prerequisites ---
if 'SYMBOL' not in locals(): raise RuntimeError("Run Cell 1 for SYMBOL.")

# --- Client Initialization (Minimal for Filters) ---\
client_filters = None
try:
    load_dotenv(verbose=False) # Load .env file if it exists
    API_KEY_FILTERS = os.environ.get('BINANCE_API_KEY')
    SECRET_KEY_FILTERS = os.environ.get('BINANCE_SECRET_KEY') or os.environ.get('BINANCE_API_SECRET')
    if API_KEY_FILTERS and SECRET_KEY_FILTERS:
        # Increase timeout settings
        client_filters = Client(API_KEY_FILTERS, SECRET_KEY_FILTERS, tld='us', requests_params={'timeout': 60})
        client_filters.ping() # Test connection
        logging.info("Minimal client initialized for fetching filters.")
    else:
        logging.warning("API keys not found in .env, cannot fetch live filters. Will use hardcoded defaults.")
except Exception as e:
    logging.warning(f"Could not initialize client for filters: {e}. Using hardcoded defaults.")
    client_filters = None # Ensure it's None if init fails

# --- Fetch/Define Symbol Filters ---
price_tick_size_bt = None
min_qty_bt = None
qty_step_size_bt = None
min_notional_bt = Decimal('0') # Default

if client_filters:
    logging.info(f"Fetching exchange filters for {SYMBOL}...")
    try:
        exchange_info_bt = client_filters.get_exchange_info()
        all_symbols_info_bt = exchange_info_bt.get('symbols', [])
        symbol_info_lookup_bt = {s['symbol']: s for s in all_symbols_info_bt}
        symbol_info_bt = symbol_info_lookup_bt.get(SYMBOL)
        if symbol_info_bt:
            for f in symbol_info_bt.get('filters',[]):
                if f['filterType']=='PRICE_FILTER': price_tick_size_bt=Decimal(f['tickSize'])
                elif f['filterType']=='LOT_SIZE': min_qty_bt=Decimal(f['minQty']); qty_step_size_bt=Decimal(f['stepSize'])
                elif f['filterType'] == 'MIN_NOTIONAL': min_notional_bt = Decimal(f.get('minNotional', '0')) # Handle potential absence

            if not all([price_tick_size_bt is not None, min_qty_bt is not None, qty_step_size_bt is not None, min_notional_bt > 0]):
                 logging.warning(f"Essential filters missing/invalid from API response (Tick:{price_tick_size_bt}, MinQty:{min_qty_bt}, Step:{qty_step_size_bt}, MinNotional:{min_notional_bt}). Falling back to defaults.")
                 client_filters = None # Force fallback
            else:
                logging.info(f"Live Filters Fetched: Tick={price_tick_size_bt}, Step={qty_step_size_bt}, MinQty={min_qty_bt}, MinNotional={min_notional_bt}")
        else:
             logging.warning(f"Symbol {SYMBOL} not found in exchange info. Falling back to defaults.")
             client_filters = None # Force fallback
    except Exception as e:
        logging.error(f"❌ Failed to get/parse live filters: {e}. Falling back to defaults.")
        client_filters = None # Force fallback

# Hardcoded Defaults (Used if client init or fetch fails) - Based on previous BTCUSDT run
if not client_filters or not all([price_tick_size_bt is not None, min_qty_bt is not None, qty_step_size_bt is not None, min_notional_bt > 0]):
    logging.warning(f"Using **HARDCODED DEFAULT FILTERS** for BTCUSDT.")
    price_tick_size_bt = Decimal('0.01000000')
    min_qty_bt = Decimal('0.00001000')
    qty_step_size_bt = Decimal('0.00001000')
    min_notional_bt = Decimal('1.00000000') # Common value for BTCUSDT on Binance.US
    logging.info(f"Defaults Used: Tick={price_tick_size_bt}, Step={qty_step_size_bt}, MinQty={min_qty_bt}, MinNotional={min_notional_bt}")


# --- Adjustment Helper Functions ---
def adjust_price_bt(price, tick_size):
    """Adjusts entry price DOWN to the nearest tick size multiple."""
    try:
        if not (isinstance(price, Decimal) and isinstance(tick_size, Decimal) and tick_size > 0):
            # logging.warning(f"Invalid input for adjust_price_bt: price={price}, tick_size={tick_size}")
            return None
        adjusted_price = (price // tick_size) * tick_size
        # logging.debug(f"Adjust Price Down: Raw={price}, Tick={tick_size}, Adjusted={adjusted_price}")
        return adjusted_price
    except Exception as e:
        logging.error(f"Error in adjust_price_bt: {e}")
        return None

def adjust_qty_bt(quantity, min_q, step_size):
    """Adjusts quantity DOWN to the nearest step size multiple, ensuring it's >= min_q."""
    try:
        if not (isinstance(quantity,Decimal) and isinstance(min_q,Decimal) and isinstance(step_size,Decimal)):
            # logging.warning(f"Invalid input types for adjust_qty_bt: qty={type(quantity)}, min_q={type(min_q)}, step={type(step_size)}")
            return Decimal('0')
        if quantity < min_q:
            # logging.debug(f"Adjust Qty Down: Raw Qty {quantity} < Min Qty {min_q}. Returning 0.")
            return Decimal('0') # Cannot place order if raw quantity is already less than minimum
        if step_size <= 0:
            # logging.warning(f"Invalid step_size for adjust_qty_bt: {step_size}")
            return Decimal('0')

        # Calculate the number of steps, rounding down
        num_steps = math.floor(quantity / step_size)
        adjusted_qty = num_steps * step_size

        # Final check: Ensure adjusted quantity is still >= minimum quantity
        if adjusted_qty < min_q:
            # This should rarely happen if initial check passed, but handles edge cases
            # logging.debug(f"Adjust Qty Down: Adjusted Qty {adjusted_qty} < Min Qty {min_q}. Returning 0.")
            return Decimal('0')

        # logging.debug(f"Adjust Qty Down: Raw={quantity}, MinQ={min_q}, Step={step_size}, Adjusted={adjusted_qty}")
        return adjusted_qty
    except Exception as e:
        logging.error(f"Error in adjust_qty_bt: {e}")
        return Decimal('0')

def adjust_tp_price_bt(price, tick_size):
    """ Adjusts TP price UP to the nearest tick size multiple. """
    try:
        if not (isinstance(price, Decimal) and isinstance(tick_size, Decimal) and tick_size > 0):
             # logging.warning(f"Invalid input for adjust_tp_price_bt: price={price}, tick_size={tick_size}")
             return None
        # Calculate ticks, round UP using ceiling division logic, then multiply back
        ticks = price / tick_size
        adjusted_ticks = ticks.to_integral_value(rounding=ROUND_UP) # Round UP to nearest integer number of ticks
        adjusted_price = adjusted_ticks * tick_size
        # logging.debug(f"Adjust TP Price UP: Raw={price}, Tick={tick_size}, Adjusted={adjusted_price}")
        return adjusted_price
    except Exception as e:
        logging.error(f"Error in adjust_tp_price_bt: {e}")
        return None


# Log the final values being used
logging.info(f"Using Filters: Tick={price_tick_size_bt}, Step={qty_step_size_bt}, MinQty={min_qty_bt}, MinNotional={min_notional_bt}")
logging.info("✅ Cell 3 Complete: Filters and helper functions ready.")

# End of Cell 2


# In[ ]:


# Cell 3: Fetch Multi-Timeframe Data & Calculate Indicators

import pandas as pd
from decimal import Decimal
import logging
import os
from binance.client import Client
from dotenv import load_dotenv
from datetime import datetime
import time # For potential retries

# --- Prerequisites ---
if 'SYMBOL' not in locals(): raise RuntimeError("Run Cell 1 for SYMBOL.")

# --- Configuration ---
TIMEFRAMES = {
    '1d': Client.KLINE_INTERVAL_1DAY,
    '4h': Client.KLINE_INTERVAL_4HOUR,
    '1h': Client.KLINE_INTERVAL_1HOUR
}
# Use consistent date range from original backtest data fetch
DATE_START = "1 Jan, 2023"
DATE_END = "1 Jan, 2024" # get_historical_klines is exclusive of end date for daily+

KLINE_COLUMNS = [
    'Open Time', 'Open', 'High', 'Low', 'Close', 'Volume',
    'Close Time', 'Quote Asset Volume', 'Number of Trades',
    'Taker Buy Base Asset Volume', 'Taker Buy Quote Asset Volume', 'Ignore'
]
DECIMAL_COLS = ['Open', 'High', 'Low', 'Close', 'Volume']
FINAL_COLS = ['Open', 'High', 'Low', 'Close', 'Volume'] # Keep only these for base DFs
ATR_PERIOD = 14 # Standard ATR period

# --- Client Initialization ---
client_data = None
try:
    load_dotenv(verbose=False)
    API_KEY_DATA = os.environ.get('BINANCE_API_KEY')
    SECRET_KEY_DATA = os.environ.get('BINANCE_SECRET_KEY') or os.environ.get('BINANCE_API_SECRET')
    if API_KEY_DATA and SECRET_KEY_DATA:
        # Increase timeout settings
        client_data = Client(API_KEY_DATA, SECRET_KEY_DATA, tld='us', requests_params={'timeout': 60})
        client_data.ping() # Test connection
        logging.info("Binance client initialized successfully for historical data.")
    else:
        logging.error("API keys not found, cannot fetch historical data.")
        raise RuntimeError("API keys missing.")
except Exception as e:
    logging.error(f"Could not initialize client for data fetch: {e}")
    raise

# --- Data Fetching and Processing ---
data_for_sr_calc = {} # Dictionary to hold original DFs: {'1h': df_1h, '4h': df_4h, ...}
all_tf_data_processed = {} # Dictionary for DFs with indicators
required_cols_for_loop = ['Open', 'High', 'Low', 'Close', 'Volume'] # Base columns for backtest loop df

logging.info(f"--- Fetching Multi-Timeframe Data for {SYMBOL} ({DATE_START} to {DATE_END}) ---")

# Use pandas_ta if available for ATR
try:
    import pandas_ta as ta
    use_pandas_ta = True
    logging.info("Using pandas_ta for ATR calculation.")
except ImportError:
    use_pandas_ta = False
    logging.warning("pandas_ta not found. ATR calculation will be skipped.")
    # Potentially add manual ATR calculation here if needed as fallback

for tf_key, tf_interval in TIMEFRAMES.items():
    logging.info(f"Fetching {tf_key} data...")
    retries = 3
    klines_raw = None
    while retries > 0:
        try:
            klines_raw = client_data.get_historical_klines(
                SYMBOL, tf_interval, DATE_START, DATE_END
            )
            break # Success
        except Exception as e:
            retries -= 1
            logging.warning(f"Error fetching {tf_key} data: {e}. Retries left: {retries}")
            if retries == 0:
                logging.error(f"❌ Failed to fetch {tf_key} data after multiple attempts.")
                klines_raw = None # Ensure it's None if all retries fail
            else:
                time.sleep(2) # Wait before retrying

    if not klines_raw:
         logging.warning(f"No {tf_key} data returned for {SYMBOL} in the specified range.")
         data_for_sr_calc[tf_key] = pd.DataFrame(columns=FINAL_COLS)
         all_tf_data_processed[tf_key] = pd.DataFrame(columns=FINAL_COLS + [f'ATR_{ATR_PERIOD}']) # Include ATR col even if empty
         continue

    df = pd.DataFrame(klines_raw, columns=KLINE_COLUMNS)
    df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms', utc=True)
    df.set_index('Open Time', inplace=True)
    for col in DECIMAL_COLS:
         df[col] = df[col].apply(lambda x: Decimal(str(x)))

    # Store the raw-ish data for dynamic S/R calculations
    data_for_sr_calc[tf_key] = df[FINAL_COLS].copy()

    # Calculate ATR
    atr_col_name = f'ATR_{ATR_PERIOD}'
    if use_pandas_ta:
        try:
            # Ensure correct types for pandas_ta
            high_f = df['High'].astype(float)
            low_f = df['Low'].astype(float)
            close_f = df['Close'].astype(float)
            df[atr_col_name] = ta.atr(high=high_f, low=low_f, close=close_f, length=ATR_PERIOD)
            df[atr_col_name] = df[atr_col_name].apply(lambda x: Decimal(str(x)) if pd.notna(x) else None)
            logging.info(f"  Calculated ATR for {tf_key}.")
        except Exception as e_atr:
            logging.error(f"  Error calculating ATR for {tf_key} using pandas_ta: {e_atr}")
            df[atr_col_name] = None # Set to None on error
    else:
        df[atr_col_name] = None # Set to None if pandas_ta not available

    all_tf_data_processed[tf_key] = df[FINAL_COLS + [atr_col_name]].copy()
    if atr_col_name not in required_cols_for_loop:
        required_cols_for_loop.append(atr_col_name)
    logging.info(f"✅ Successfully processed {len(df)} {tf_key} klines. Range: {df.index.min()} to {df.index.max()}")


# --- Align Data to 1H Index & Create Backtest DataFrame ---
logging.info("Aligning multi-timeframe data (with ATR) to 1H index...")
if '1h' not in all_tf_data_processed or all_tf_data_processed['1h'].empty:
    raise RuntimeError("1H data is missing or empty, cannot align for backtest.")

df_1h_processed = all_tf_data_processed['1h'].copy()
aligned_dfs = [df_1h_processed]

for tf_key in ['4h', '1d']:
    if tf_key in all_tf_data_processed and not all_tf_data_processed[tf_key].empty:
        df_aligned = all_tf_data_processed[tf_key].reindex(df_1h_processed.index, method='ffill').add_suffix(f'_{tf_key}')
        aligned_dfs.append(df_aligned)
        # Add the suffixed ATR column name to required columns for the loop data
        atr_col_tf = f'ATR_{ATR_PERIOD}_{tf_key}'
        if atr_col_tf not in required_cols_for_loop:
            required_cols_for_loop.append(atr_col_tf)
    else:
        logging.warning(f"{tf_key} data is missing or empty, cannot include in alignment.")

# Combine aligned data
historical_data_test = pd.concat(aligned_dfs, axis=1)

# Select only the columns genuinely needed for the backtest loop logic
# Remove duplicates just in case, keeping the first occurrence (should be the 1h one)
final_loop_cols = list(dict.fromkeys(required_cols_for_loop))

# Ensure all required columns actually exist after alignment and suffixing
missing_cols = [col for col in final_loop_cols if col not in historical_data_test.columns]
if missing_cols:
    logging.warning(f"Columns missing after alignment: {missing_cols}. Removing them from loop list.")
    final_loop_cols = [col for col in final_loop_cols if col not in missing_cols]

# Drop rows with any NaNs in the essential columns (especially initial ATR NaNs)
rows_before_dropna = len(historical_data_test)
historical_data_test = historical_data_test[final_loop_cols].dropna().copy()
rows_after_dropna = len(historical_data_test)
logging.info(f"Data aligned. Dropped {rows_before_dropna - rows_after_dropna} rows due to NaNs (e.g., initial ATR).")
logging.info(f"Backtest will run on {rows_after_dropna} 1H candles.")

if historical_data_test.empty:
    raise ValueError("No data left after dropping NaNs from ATR/Alignment. Cannot proceed.")

# Create the specific TF variables for convenience if needed elsewhere (though data_for_sr_calc is primary)
df_1h = data_for_sr_calc.get('1h', pd.DataFrame())
df_4h = data_for_sr_calc.get('4h', pd.DataFrame())
df_1d = data_for_sr_calc.get('1d', pd.DataFrame())

logging.info("✅ Cell 2 Complete: Multi-TF Data Fetched, Indicators Calculated, Aligned for Backtest.")
print("\n--- Sample of Aligned Backtest Data (historical_data_test) ---")
print(historical_data_test.head().to_string())
print("\n--- Sample of Raw Data for S/R Calc (data_for_sr_calc['1h']) ---")
print(data_for_sr_calc['1h'].head().to_string())


# End of Cell 3


# In[ ]:


# Cell 4: Dynamic S/R Zone Calculation Helper Function (SIMPLIFIED DEFINITION FOR DEBUG)

import pandas as pd
from decimal import Decimal
import logging
import sys
import numpy as np

# --- Logging Setup (Basic fallback) ---
if not logging.getLogger().hasHandlers():
     logging.basicConfig(level=logging.INFO,
                         format='%(asctime)s - %(levelname)s - %(message)s',
                         stream=sys.stdout)

# --- SIMPLIFIED Helper Function Definition ---
def calculate_dynamic_zones(data_slice, n_periods, sup_thresh_pct, res_thresh_pct):
    """
    SIMPLIFIED VERSION FOR DEBUGGING: Returns empty DataFrames.
    """
    logging.debug("SIMPLIFIED calculate_dynamic_zones called.") # Log if called
    # Return empty dataframes matching the expected structure
    empty_df = pd.DataFrame(columns=['zone_min_price', 'zone_max_price', 'points', 'timestamps', 'num_points'])
    return empty_df.copy(), empty_df.copy()

# *** ADDED DEBUG PRINT HERE ***
print("<<<<< DEBUG: calculate_dynamic_zones SIMPLIFIED FUNCTION DEFINITION COMPLETE >>>>>")
# *** END ADDITION ***

logging.info("✅ Cell 4 Complete: Dynamic S/R Zone calculation function defined (SIMPLIFIED).")

# End of Cell 4 (Simplified)


# In[ ]:


# Cell 5 (Revised v8 - Check This is Correct): Replicate Bitcoin Long-Term Power Law - Adjusted X-Axis Limit

import pandas as pd
import numpy as np
import logging
import sys
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy import stats # For linear regression
from datetime import datetime, timedelta, timezone # Ensure timezone is imported
import os
from decimal import Decimal # Ensure Decimal is imported

# Install yfinance if needed
# !pip install yfinance scipy pandas_ta matplotlib numpy

import yfinance as yf
try:
    import pandas_ta as ta
    # logging.info("Successfully imported pandas_ta.") # Keep logging less verbose
except ImportError:
    logging.warning("pandas_ta not found, but not required for this cell.")

# --- Configuration ---\
TICKER_PL = "BTC-USD"
INTERVAL_PL = "1d"
# Use a very early start date to get max history from yfinance
# yfinance will automatically adjust if data isn't available that far back
START_DATE_PL = "2010-07-17"
END_DATE_PL = datetime.now().strftime('%Y-%m-%d')
FORECAST_YEARS = 20 # Keep calculating the full forecast in df_lines
PLOT_FUTURE_YEARS = 2 # How many years past the last data point to show on the plot

# --- Logging & Display Setup ---
# Ensure logging is configured (should be by Cell 1, but safeguard)
if not logging.getLogger().hasHandlers():
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
# Set display options
pd.set_option('display.float_format', '{:.2f}'.format)
# ---

# --- Fetch Data ---\
logging.info(f"--- Fetching Long-Term Daily Data for {TICKER_PL} for Power Law ({START_DATE_PL} to {END_DATE_PL}) ---")
df_daily_pl_raw = pd.DataFrame()
close_prices_series_pl = pd.Series(dtype=float) # Initialize empty Series

try:
    # Use auto_adjust=True for simplicity with yfinance daily data
    df_fetched_pl = yf.download(TICKER_PL, start=START_DATE_PL, end=END_DATE_PL, interval=INTERVAL_PL, progress=False, auto_adjust=True)
    if df_fetched_pl.empty: raise ValueError("No data returned from yfinance for Power Law.")
    logging.info(f"✅ Successfully fetched {len(df_fetched_pl)} daily data points for PL.")
    logging.info(f"PL Data range: {df_fetched_pl.index.min()} to {df_fetched_pl.index.max()}")

    # Robustly select 'Close' column AND ensure it's a Series
    if 'Close' not in df_fetched_pl.columns: raise ValueError(f"'Close' column not found in PL data. Columns: {df_fetched_pl.columns}")
    close_data_pl = df_fetched_pl['Close']
    if isinstance(close_data_pl, pd.DataFrame):
        if not close_data_pl.empty: close_prices_series_pl = close_data_pl.iloc[:, 0].copy()
        else: raise ValueError("Selected 'Close' (PL) resulted in an empty DataFrame.")
    elif isinstance(close_data_pl, pd.Series): close_prices_series_pl = close_data_pl.copy()
    else: raise TypeError(f"Unexpected data type after selecting 'Close' (PL): {type(close_data_pl)}")

    if not isinstance(close_prices_series_pl, pd.Series): raise TypeError(f"Could not extract Close (PL) as a Pandas Series. Final type was: {type(close_prices_series_pl)}")

    # Store in df_daily_pl_raw and clean
    df_daily_pl_raw = pd.DataFrame({'Close': close_prices_series_pl})
    df_daily_pl_raw.dropna(inplace=True)
    # Convert 'Close' to Decimal AFTER initial processing and NaN drop
    df_daily_pl_raw['Close'] = df_daily_pl_raw['Close'].apply(lambda x: Decimal(str(x)))
    df_daily_pl_raw = df_daily_pl_raw[df_daily_pl_raw['Close'] > 0] # Filter for positive prices

    if df_daily_pl_raw.empty: raise ValueError("No positive Close price data remaining after cleaning for PL.")

except Exception as e:
    logging.error(f"❌ Failed to download or process data for Power Law: {e}", exc_info=True)
    # Ensure df_lines is not created or is empty on failure
    df_lines = pd.DataFrame() # Explicitly clear df_lines on error
    raise # Re-raise the error to stop execution if PL calc fails


# --- Prepare Data for Log-Linear Regression (Only if data fetch succeeded) ---\
if not df_daily_pl_raw.empty:
    try:
        # Ensure index is DatetimeIndex and localized to UTC
        if not isinstance(df_daily_pl_raw.index, pd.DatetimeIndex):
            raise TypeError("Index is not DatetimeIndex after fetching PL data.")
        if df_daily_pl_raw.index.tz is None:
            df_daily_pl_raw.index = df_daily_pl_raw.index.tz_localize('UTC')
        elif df_daily_pl_raw.index.tz != timezone.utc:
            df_daily_pl_raw.index = df_daily_pl_raw.index.tz_convert('UTC')

        actual_start_date_pl = df_daily_pl_raw.index[0]
        start_num_date_pl = mdates.date2num(actual_start_date_pl)

        # Convert Days and Log_Close to float for regression
        df_daily_pl_raw['Days_float'] = (df_daily_pl_raw.index - actual_start_date_pl).days.astype(float)
        df_daily_pl_raw['Log_Close_float'] = df_daily_pl_raw['Close'].apply(lambda x: np.log(float(x)))

        # --- Perform Linear Regression ---\
        logging.info("Performing log-linear regression...")
        df_reg = df_daily_pl_raw[['Days_float', 'Log_Close_float']].dropna()
        if df_reg.empty: raise ValueError("No valid data points for regression.")

        slope, intercept, r_value, p_value, std_err = stats.linregress(df_reg['Days_float'], df_reg['Log_Close_float'])
        logging.info(f"Regression Results: Slope={slope:.6f}, Intercept={intercept:.4f}, R^2={r_value**2:.4f}")

        # --- Calculate Regression, Support, Resistance Lines (Historical Min/Max Deviation) ---\
        last_date = df_daily_pl_raw.index[-1]
        # Calculate future dates for the full forecast period
        future_dates = pd.date_range(start=last_date + timedelta(days=1), periods=365 * FORECAST_YEARS, freq='D', tz='UTC')
        all_dates = df_daily_pl_raw.index.union(future_dates) # Index for df_lines includes full forecast

        # Use numeric days directly from the 'Days_float' column where available, calculate for future
        all_days_numeric_float = np.array([(d - actual_start_date_pl).days for d in all_dates], dtype=float)

        log_reg_line_float = intercept + slope * all_days_numeric_float
        log_reg_historical_float = intercept + slope * df_reg['Days_float']
        residuals_float = df_reg['Log_Close_float'] - log_reg_historical_float
        log_offset_resistance_float = residuals_float.max()
        log_offset_support_float = residuals_float.min()
        logging.info(f"Calculated Log Offsets (float): Support={log_offset_support_float:.4f}, Resistance={log_offset_resistance_float:.4f}")
        log_support_line_float = log_reg_line_float + log_offset_support_float
        log_resistance_line_float = log_reg_line_float + log_offset_resistance_float

        # --- Convert Lines Back to Price Scale (Store as Decimal) ---\
        # Important: Exponentiation can lead to very large numbers
        with np.errstate(over='raise'): # Raise error on overflow during exp
             try:
                 reg_line_price_float = np.exp(log_reg_line_float)
                 support_line_price_float = np.exp(log_support_line_float)
                 resistance_line_price_float = np.exp(log_resistance_line_float)
             except FloatingPointError as fpe:
                  logging.error(f"Overflow during np.exp calculation: {fpe}")
                  raise ValueError("Overflow calculating PL lines.") from fpe

        df_lines = pd.DataFrame(index=all_dates) # df_lines still covers the full forecast
        df_lines['Regression'] = [Decimal(str(p)) for p in reg_line_price_float]
        df_lines['Support'] = [Decimal(str(p)) for p in support_line_price_float]
        df_lines['Resistance'] = [Decimal(str(p)) for p in resistance_line_price_float]

        # --- Ensure df_lines Index is Timezone-Aware (UTC) ---
        # This should be guaranteed by index creation/union, but double-check
        if df_lines.index.tz is None or df_lines.index.tz != timezone.utc:
             logging.warning("df_lines index needs UTC conversion/localization.")
             if df_lines.index.tz is None: df_lines.index = df_lines.index.tz_localize('UTC')
             else: df_lines.index = df_lines.index.tz_convert('UTC')

        logging.info("✅ df_lines DataFrame created successfully.")

        # --- Plotting ---\
        logging.info(f"Plotting results (Historical Min/Max Channel)...\")")
        fig, ax = plt.subplots(figsize=(15, 8))
        # Plot using float for consistency with lines
        ax.semilogy(df_daily_pl_raw.index, df_daily_pl_raw['Close'].astype(float), label=f'{TICKER_PL} Close Price', color='orange', linewidth=1, alpha=0.8)
        ax.semilogy(df_lines.index, df_lines['Regression'].astype(float), label='Log-Linear Regression Fit', color='green', linestyle='-', linewidth=1.5)
        ax.semilogy(df_lines.index, df_lines['Support'].astype(float), label='Support (Historical Min Deviation)', color='red', linestyle='-', linewidth=1.5)
        ax.semilogy(df_lines.index, df_lines['Resistance'].astype(float), label='Resistance (Historical Max Deviation)', color='purple', linestyle='-', linewidth=1.5)
        ax.fill_between(df_lines.index, df_lines['Support'].astype(float), df_lines['Resistance'].astype(float), color='grey', alpha=0.1, label='Regression Channel')

        # --- Formatting ---\
        ax.set_title(f'{TICKER_PL} Long Term Price (Log Scale) with Historical Min/Max Deviation Channel')
        ax.set_xlabel('Year'); ax.set_ylabel('Price (USD) - Log Scale')
        ax.grid(True, which="both", linestyle='--', alpha=0.4); ax.legend(loc='lower right')

        # Robust Y-Limit Setting
        min_val_calc = 0.01; max_val_calc = 10000000 # Defaults
        try:
            min_close_price = float(df_daily_pl_raw['Close'].min())
            max_close_price = float(df_daily_pl_raw['Close'].max())
            min_val_calc = max(0.01, min_close_price * 0.5)
            plot_end_date = last_date + pd.DateOffset(years=PLOT_FUTURE_YEARS)
            # Ensure plot_end_date exists in df_lines index before accessing
            if plot_end_date <= df_lines.index[-1]:
                 plot_end_date_actual = df_lines.index.asof(plot_end_date) # Find closest valid index
                 if pd.notna(plot_end_date_actual):
                     max_plot_res = float(df_lines.loc[plot_end_date_actual, 'Resistance'])
                 else: # If asof somehow fails, fallback
                     max_plot_res = float(df_lines['Resistance'].iloc[-1])
            else: # If plot date is beyond calculated forecast, use last forecast value
                 max_plot_res = float(df_lines['Resistance'].iloc[-1])
            max_val_calc = max(max_close_price * 1.2, max_plot_res * 1.2)
        except Exception as e_ylim:
             logging.warning(f"Could not reliably determine ylim: {e_ylim}. Using defaults.")
        ax.set_ylim(bottom=min_val_calc, top=max_val_calc)

        ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.xaxis.set_minor_locator(mdates.YearLocator(1)); fig.autofmt_xdate()

        # Set X-Axis Limit
        plot_right_limit = last_date + pd.DateOffset(years=PLOT_FUTURE_YEARS)
        # Ensure left limit is valid Datetime
        if isinstance(actual_start_date_pl, pd.Timestamp):
             ax.set_xlim(left=actual_start_date_pl, right=plot_right_limit)
             logging.info(f"Plot X-axis range set from {actual_start_date_pl.date()} to {plot_right_limit.date()}")
        else:
             logging.warning("Could not set xlim left boundary - actual_start_date_pl invalid.")


        plt.tight_layout(); plt.show()
        logging.info("✅ Power Law concept plot generated (Adjusted X-axis).")

    except Exception as e_process:
        logging.error(f"❌ Failed during PL processing/regression/plotting: {e_process}", exc_info=True)
        # Ensure df_lines is empty if processing fails after fetch
        df_lines = pd.DataFrame()
        # Don't raise here, allow notebook to continue, but backtester will fail


# Safety check: define df_lines as empty if it wasn't created due to prior error
if 'df_lines' not in locals():
     logging.error("df_lines was not created due to errors in fetching or processing PL data.")
     df_lines = pd.DataFrame()


# End of Cell 5 (Revised v8)


# In[ ]:


# Cell 5.1 (v1.1 - Optimized DataFrame Construction): Calculate Logarithmic Rainbow Bands

import pandas as pd
import numpy as np
import logging
import sys
from decimal import Decimal, getcontext

# --- Prerequisites ---
if 'df_lines' not in locals() or df_lines.empty:
    raise RuntimeError("df_lines is missing or empty. Run Cell 5 (Power Law) first.")

# --- Configuration ---
NUM_RAINBOW_BANDS = 100 # Number of zones/bands (MATCH v13.1 config)

# --- Logging ---
logger_rb = logging.getLogger(__name__ + "_rainbow")
if not logging.getLogger().hasHandlers():
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
     logging.getLogger().setLevel(logging.INFO)
else:
     logging.getLogger().setLevel(logging.INFO)


# --- Calculation ---
logger_rb.info(f"--- Calculating {NUM_RAINBOW_BANDS} Logarithmic Rainbow Bands (Optimized) ---")
# Initialize rainbow_bands_df as empty for now, will construct at the end
rainbow_bands_df = pd.DataFrame()
bands_data = {} # Dictionary to hold the calculated band Series

try:
    # Ensure input columns are Decimal
    pl_support = df_lines['Support'].apply(Decimal)
    pl_resistance = df_lines['Resistance'].apply(Decimal)

    # Calculate log values
    log_support = pl_support.apply(lambda x: x.ln() if x > 0 else Decimal('-Infinity'))
    log_resistance = pl_resistance.apply(lambda x: x.ln() if x > 0 else Decimal('-Infinity'))

    # Calculate the total log height
    log_height = log_resistance - log_support

    # Handle invalid heights
    invalid_height_mask = log_height <= 0
    if invalid_height_mask.any():
        invalid_height_dates = log_height[invalid_height_mask].index.strftime('%Y-%m-%d').tolist()
        logger_rb.warning(f"Invalid non-positive log channel height found on {len(invalid_height_dates)} dates (e.g., {invalid_height_dates[:5]}). Results may be incorrect for these dates.")
        log_height[invalid_height_mask] = Decimal('NaN')


    # Calculate the boundaries for each band and store in dictionary
    for i in range(NUM_RAINBOW_BANDS + 1):
        band_pct = Decimal(i) / Decimal(NUM_RAINBOW_BANDS)
        log_boundary = log_support + (log_height * band_pct)
        # Convert back to price scale (handle potential exp(infinity) or exp(NaN))
        # This calculation produces a pandas Series for each band
        boundary_price_series = log_boundary.apply(lambda x: x.exp() if pd.notna(x) and x != Decimal('-Infinity') else Decimal('NaN'))
        # Add the Series to the dictionary
        bands_data[f'Band_{i}'] = boundary_price_series

    # *** OPTIMIZATION: Construct DataFrame from dictionary ***
    rainbow_bands_df = pd.DataFrame(bands_data, index=df_lines.index)
    # *** END OPTIMIZATION ***

    logger_rb.info(f"✅ Rainbow bands calculated. Shape: {rainbow_bands_df.shape}. Columns: Band_0...Band_{NUM_RAINBOW_BANDS}")
    print("\n--- Sample Rainbow Band Boundaries (Tail) ---")
    print(rainbow_bands_df.tail(5).to_string(float_format='{:,.2f}'.format))


except Exception as e:
    logger_rb.error(f"❌ Error calculating rainbow bands: {e}", exc_info=True)
    rainbow_bands_df = pd.DataFrame() # Ensure it's empty on error


# --- Helper Function to Get Band Index (Defined Here - unchanged) ---
def get_band_index(price: Decimal, timestamp, bands_df: pd.DataFrame, num_bands: int) -> int:
    """
    Determines the index of the rainbow band a given price falls into at a specific time.
    Returns band index (0 to num_bands-1), or -1 if price is outside channel or error.
    """
    if not isinstance(price, Decimal) or price <= 0: return -1 # Invalid price input
    try:
        bands_row_index = bands_df.index.asof(timestamp)
        if pd.isna(bands_row_index): return -1
        band_boundaries = bands_df.loc[bands_row_index]
        if band_boundaries.isnull().any(): return -1
        for i in range(num_bands):
            lower_bound = band_boundaries[f'Band_{i}']
            upper_bound = band_boundaries[f'Band_{i+1}']
            if pd.isna(lower_bound) or pd.isna(upper_bound): continue
            if lower_bound <= price < upper_bound: return i
        highest_band_boundary_price = band_boundaries[f'Band_{num_bands}']
        if pd.notna(highest_band_boundary_price) and price == highest_band_boundary_price: return num_bands - 1
        lowest_band_boundary_price = band_boundaries['Band_0']
        if pd.notna(lowest_band_boundary_price) and price < lowest_band_boundary_price: return -1
        elif pd.notna(highest_band_boundary_price) and price > highest_band_boundary_price: return num_bands - 1
    except KeyError as ke: return -1
    except Exception as e: logger_rb.error(f"Error getting band index for price {price} at {timestamp}: {e}", exc_info=False); return -1
    return -1 # Default return

# Test the function (optional - unchanged)
if not rainbow_bands_df.empty and len(rainbow_bands_df) > 10:
    try:
        test_ts = rainbow_bands_df.dropna().index[-10]
        test_price_low = rainbow_bands_df.loc[test_ts, 'Band_1']
        test_price_mid = (rainbow_bands_df.loc[test_ts, f'Band_{NUM_RAINBOW_BANDS//2}'] + rainbow_bands_df.loc[test_ts, f'Band_{NUM_RAINBOW_BANDS//2 + 1}']) / 2
        test_price_high = rainbow_bands_df.loc[test_ts, f'Band_{NUM_RAINBOW_BANDS-1}']
        test_index_low = get_band_index(test_price_low, test_ts, rainbow_bands_df, NUM_RAINBOW_BANDS)
        test_index_mid = get_band_index(test_price_mid, test_ts, rainbow_bands_df, NUM_RAINBOW_BANDS)
        test_index_high = get_band_index(test_price_high, test_ts, rainbow_bands_df, NUM_RAINBOW_BANDS)
        logger_rb.info(f"Test Band Index: Low Price ({test_price_low:.2f}) -> Band {test_index_low}")
        logger_rb.info(f"Test Band Index: Mid Price ({test_price_mid:.2f}) -> Band {test_index_mid}")
        logger_rb.info(f"Test Band Index: High Price ({test_price_high:.2f}) -> Band {test_index_high}")
    except Exception as test_e:
        logger_rb.error(f"Error during band index test: {test_e}")


# End of Cell 5.1 (v1.1 - Optimized)


# In[ ]:


# Cell 6 (v13.7.4 - Quieter Fills): Backtesting Engine

import pandas as pd
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation, getcontext
import logging
import math
import sys
import numpy as np
from datetime import datetime, timezone, timedelta
from tqdm.notebook import tqdm # Ensure tqdm is imported for progress bar
import uuid
import os # To check log file path
import matplotlib.pyplot as plt # Import Matplotlib here
import matplotlib.ticker as mticker # For formatting y-axis

# --- Prerequisites ---\n
# Ensure these are available from preceding cells
if 'historical_data_test' not in locals() or historical_data_test.empty: raise RuntimeError("Run Cell 3 (Data Fetch) for historical_data_test")
if not all(v in globals() for v in ['price_tick_size_bt', 'min_qty_bt', 'qty_step_size_bt', 'min_notional_bt', 'adjust_price_bt', 'adjust_qty_bt', 'adjust_tp_price_bt']): raise RuntimeError("Run Cell 2 (Filters) for filters/helpers")
if 'rainbow_bands_df' not in locals() or rainbow_bands_df.empty: raise RuntimeError("Run Cell 5.1 (Rainbow Bands) for rainbow_bands_df.")
if 'get_band_index' not in globals(): raise RuntimeError("Run Cell 5.1 (Rainbow Bands) for get_band_index function.")
if 'df_lines' not in locals() or df_lines.empty: raise RuntimeError("Run Cell 5 (Power Law) for df_lines.")


# --- Configuration (v13.7.4) ---\n
getcontext().prec = 28
# Logging Setup - Log DEBUG+ to file, INFO+ to screen (Ultra Quiet)
LOG_FILENAME = 'backtest_log.txt'
# Clear existing handlers
for handler in logging.root.handlers[:]: logging.root.removeHandler(handler)
# File Handler (DEBUG level)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(LOG_FILENAME, mode='w') # Overwrite previous log
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.DEBUG) # <<<< CAPTURE DEBUG TO FILE
# Stream Handler (INFO level - for screen output)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(logging.INFO) # <<<< SHOW INFO ON SCREEN
# Add handlers to the root logger
logging.root.addHandler(file_handler)
logging.root.addHandler(stream_handler)
logging.root.setLevel(logging.DEBUG) # Root needs to be lowest level to capture all

logger = logging.getLogger(__name__) # Get logger instance

STARTING_QUOTE_BALANCE = Decimal('10000.0'); STARTING_BASE_BALANCE = Decimal('0.0') # Adjusted starting balance for demo
SYMBOL = "BTCUSDT"
QUOTE_ASSET = 'USDT'; BASE_ASSET = SYMBOL.replace(QUOTE_ASSET, '')
FEE_RATE = Decimal('0.001');
NUM_RAINBOW_BANDS = 100
ALLOCATION_EXPONENT = Decimal('1.5')

logging.info(f"--- Starting Backtest Simulation v13.7.4 for {SYMBOL} (Quieter Fills) ---") # v13.7.4
logging.info(f"Trigger: Price crossing ANY Rainbow Band boundary")
logging.info(f"Context & Allocation: {NUM_RAINBOW_BANDS} Bands, Exp={ALLOCATION_EXPONENT}")
logging.info(f"Rebalancing: Continuous adjustment on cross, trades executed if > MIN_NOTIONAL")
logging.info(f"Logging DEBUG+ to: {os.path.abspath(LOG_FILENAME)}") # Show log file path
logging.info(f"Simulated Starting Balance: {STARTING_QUOTE_BALANCE:,.2f} {QUOTE_ASSET}")

# --- Allocation Helper Function (Unchanged) ---\n
def target_crypto_allocation_pct(band_index: int, num_bands: int, exponent: Decimal) -> Decimal:
    if band_index < 0 or band_index >= num_bands: return Decimal('0')
    if num_bands <= 1: return Decimal('1.0')
    linear_fraction = (Decimal(num_bands - 1 - band_index) / Decimal(num_bands - 1))
    try:
        target_pct = linear_fraction.copy_abs() ** exponent
    except InvalidOperation:
        logger.error(f"Invalid operation during exponentiation: {linear_fraction} ** {exponent}")
        return Decimal('0')
    if exponent % 1 != 0 and linear_fraction < 0:
         logger.warning(f"Attempting non-integer exponent on negative base ({linear_fraction}, {exponent}). Returning 0.")
         return Decimal('0')
    return max(Decimal('0'), min(Decimal('1.0'), target_pct))

# --- Simulation State Initialization (Unchanged) ---\n
quote_balance = STARTING_QUOTE_BALANCE; base_balance = STARTING_BASE_BALANCE
trade_log = []; portfolio_history = []
total_fees_paid = Decimal('0.0')

# --- HODL Calculation Setup (Unchanged) ---\n
initial_hodl_price = historical_data_test['Close'].iloc[0]
hodl_base_qty = (STARTING_QUOTE_BALANCE / initial_hodl_price) if initial_hodl_price > 0 else Decimal('0')
hodl_portfolio_history = []
logging.info(f"Initial HODL Buy (adjusted): {hodl_base_qty:.8f} {BASE_ASSET} @ {initial_hodl_price:.2f}")

# --- Perform Initial Allocation (Unchanged) ---\n
logging.info("--- Performing Initial Allocation ---")
initial_buy_executed = False
try:
    first_timestamp = historical_data_test.index[0]
    first_close = historical_data_test['Close'].iloc[0]
    initial_band_index = get_band_index(first_close, first_timestamp, rainbow_bands_df, NUM_RAINBOW_BANDS)
    if initial_band_index < 0:
        logging.warning(f"Initial price {first_close:.2f} outside bands. Starting 0% crypto.")
    else:
        initial_target_pct = target_crypto_allocation_pct(initial_band_index, NUM_RAINBOW_BANDS, ALLOCATION_EXPONENT)
        logger.info(f"Initial Price: {first_close:.2f}, Band: {initial_band_index}, Target Alloc: {initial_target_pct:.2%}") # Keep initial alloc INFO
        initial_portfolio_value = STARTING_QUOTE_BALANCE; initial_target_crypto_value = initial_portfolio_value * initial_target_pct
        initial_value_to_trade = initial_target_crypto_value
        if initial_value_to_trade > 0:
            adj_entry_price = adjust_price_bt(first_close, price_tick_size_bt)
            if adj_entry_price and adj_entry_price > 0:
                qty_to_buy_raw = initial_value_to_trade / adj_entry_price; qty_to_buy = adjust_qty_bt(qty_to_buy_raw, min_qty_bt, qty_step_size_bt)
                buy_notional = adj_entry_price * qty_to_buy; cost_with_fee = buy_notional * (1 + FEE_RATE)
                if buy_notional >= min_notional_bt and quote_balance >= cost_with_fee:
                    quote_balance -= cost_with_fee; base_balance += qty_to_buy; total_fees_paid += buy_notional * FEE_RATE
                    trade_log.append({'timestamp': first_timestamp, 'type': f"INITIAL_ALLOC_BUY", 'price': adj_entry_price, 'qty': qty_to_buy, 'value': -buy_notional, 'fee': buy_notional * FEE_RATE, 'signal_band': initial_band_index, 'target_pct': initial_target_pct})
                    # *** Keep initial allocation confirmation as INFO for visibility on screen ***
                    logging.info(f"  +++ INITIAL ALLOCATION BUY Executed @ {adj_entry_price:.2f} Qty {qty_to_buy:.8f} +++")
                    logging.info(f"  Initial Balance: Quote={quote_balance:,.2f}, Base={base_balance:.8f}")
                    initial_buy_executed = True
                else: logging.warning(f"  Skipped Initial Buy: Notional ({buy_notional:.4f} vs {min_notional_bt:.4f}) / Cost ({cost_with_fee:.4f} vs {quote_balance:.4f}) checks failed.")
            else: logging.warning(f"  Skipped Initial Buy: Invalid adjusted entry price.")
except Exception as e_init:
    logging.error(f"Error during initial allocation: {e_init}", exc_info=True)

# --- Simulation Loop ---\n
logging.info(f"Starting simulation loop v13.7.4 through {len(historical_data_test)} candles...") # Log start
candle_count = 0
last_candle_close = historical_data_test['Close'].iloc[0] if not historical_data_test.empty else None

for timestamp, candle_data in tqdm(historical_data_test.iterrows(), total=len(historical_data_test), desc="Backtest (v13.7.4 Quiet)"):
    candle_count += 1
    current_high = candle_data['High']; current_low = candle_data['Low']; current_close = candle_data['Close']
    timestamp_utc = timestamp

    # --- A. Get Current Band Boundaries (Unchanged) ---\n
    try:
        bands_row_index = rainbow_bands_df.index.asof(timestamp_utc)
        if pd.isna(bands_row_index): raise ValueError(f"Timestamp {timestamp_utc} not found in rainbow_bands_df using asof")
        band_boundaries = rainbow_bands_df.loc[bands_row_index]
        if band_boundaries.isnull().any(): raise ValueError("NaNs in boundaries")
    except Exception as e_band:
        logger.warning(f"[{timestamp_utc}] Error getting band boundaries: {e_band}. Skipping rebalance check for this candle.")
        if last_candle_close is not None: last_candle_close = current_close
        current_portfolio_value_eoc = quote_balance + (base_balance * current_close); current_hodl_value = hodl_base_qty * current_close
        strategy_vs_hodl_pct = Decimal('NaN')
        if current_hodl_value and current_hodl_value > 0:
             try: strategy_vs_hodl_pct = (current_portfolio_value_eoc / current_hodl_value) * 100
             except (InvalidOperation, ZeroDivisionError): strategy_vs_hodl_pct = Decimal('NaN')
        portfolio_history.append({'timestamp': timestamp_utc, 'portfolio_value': current_portfolio_value_eoc, 'quote': quote_balance, 'base': base_balance, 'strategy_vs_hodl_pct': strategy_vs_hodl_pct})
        hodl_portfolio_history.append({'timestamp': timestamp_utc, 'hodl_value': current_hodl_value})
        continue

    # --- B. Detect Band Crossing & Determine Target Band (Unchanged) ---\n
    target_band_index = -1; signal_price_for_calc = None; trade_direction = None
    if last_candle_close is not None:
        crossed_boundaries = []
        for i in range(NUM_RAINBOW_BANDS + 1):
            boundary_price = band_boundaries.get(f'Band_{i}', None)
            if boundary_price is None or pd.isna(boundary_price): continue
            boundary_price_dec = Decimal(str(boundary_price))
            if min(current_low, last_candle_close) <= boundary_price_dec < max(current_high, last_candle_close):
                 crossed_boundaries.append({'index': i, 'price': boundary_price_dec})
        if crossed_boundaries:
            if current_close < last_candle_close:
                trade_direction = "DOWN"; crossed_boundaries.sort(key=lambda x: x['price'], reverse=True); highest_crossed_boundary = crossed_boundaries[0]
                signal_price_for_calc = highest_crossed_boundary['price']; target_band_index = highest_crossed_boundary['index'] - 1
                logger.debug(f"[{timestamp_utc}] Crossed DOWN below Band_{highest_crossed_boundary['index']} @ ~{signal_price_for_calc:.2f} -> Target Band: {target_band_index}")
            elif current_close > last_candle_close:
                trade_direction = "UP"; crossed_boundaries.sort(key=lambda x: x['price']); lowest_crossed_boundary = crossed_boundaries[0]
                signal_price_for_calc = lowest_crossed_boundary['price']; target_band_index = lowest_crossed_boundary['index']
                logger.debug(f"[{timestamp_utc}] Crossed UP above Band_{target_band_index} @ ~{signal_price_for_calc:.2f} -> Target Band: {target_band_index}")
            else: # Flat close handling
                 min_crossed = min(b['price'] for b in crossed_boundaries); max_crossed = max(b['price'] for b in crossed_boundaries)
                 if current_close <= min_crossed:
                     trade_direction = "DOWN"; crossed_boundaries.sort(key=lambda x: x['price'], reverse=True); highest_crossed_boundary = crossed_boundaries[0]
                     signal_price_for_calc = highest_crossed_boundary['price']; target_band_index = highest_crossed_boundary['index'] - 1
                     logger.debug(f"[{timestamp_utc}] Flat Close, Crossed DOWN below Band_{highest_crossed_boundary['index']} @ ~{signal_price_for_calc:.2f} -> Target Band: {target_band_index}")
                 elif current_close >= max_crossed:
                     trade_direction = "UP"; crossed_boundaries.sort(key=lambda x: x['price']); lowest_crossed_boundary = crossed_boundaries[0]
                     signal_price_for_calc = lowest_crossed_boundary['price']; target_band_index = lowest_crossed_boundary['index']
                     logger.debug(f"[{timestamp_utc}] Flat Close, Crossed UP above Band_{target_band_index} @ ~{signal_price_for_calc:.2f} -> Target Band: {target_band_index}")

    # --- C. Execute Rebalancing Trade ---\n
    if target_band_index != -1 and signal_price_for_calc is not None:
        target_band_index = max(0, min(NUM_RAINBOW_BANDS - 1, target_band_index))
        logger.debug(f"[{timestamp_utc}] Rebalance Triggered. Direction: {trade_direction}, Target Band: {target_band_index}, Signal Price: {signal_price_for_calc:.2f}")
        target_pct = target_crypto_allocation_pct(target_band_index, NUM_RAINBOW_BANDS, ALLOCATION_EXPONENT)
        logger.debug(f"  Target Crypto Allocation: {target_pct:.2%}")

        current_portfolio_value = quote_balance + (base_balance * signal_price_for_calc)
        if current_portfolio_value <= 0:
            logger.warning(f"[{timestamp_utc}] Portfolio value is zero or negative ({current_portfolio_value:.2f}). Skipping rebalance.")
        else:
            target_crypto_value = current_portfolio_value * target_pct; current_crypto_value = base_balance * signal_price_for_calc
            value_to_trade = target_crypto_value - current_crypto_value; current_pct = current_crypto_value / current_portfolio_value
            logger.debug(f"  Current Value: {current_portfolio_value:,.2f} ({quote_balance:,.2f} Q + {current_crypto_value:,.2f} B | {current_pct:.2%})")
            logger.debug(f"  Target Crypto Value: {target_crypto_value:,.2f} ({target_pct:.2%})")
            logger.debug(f"  Value to Trade: {value_to_trade:,.2f}")

            trade_executed = False; min_trade_value_threshold = min_notional_bt * Decimal("0.5")
            if abs(value_to_trade) > min_trade_value_threshold:
                if value_to_trade > 0: # BUY Rebalance
                    adj_entry_price = adjust_price_bt(signal_price_for_calc, price_tick_size_bt)
                    if not adj_entry_price or adj_entry_price <= 0: logger.warning(f"  Adjusted BUY price invalid ({adj_entry_price}).")
                    else:
                        quote_balance = Decimal(str(quote_balance)); qty_to_buy_raw = value_to_trade / adj_entry_price; qty_to_buy = adjust_qty_bt(qty_to_buy_raw, min_qty_bt, qty_step_size_bt)
                        buy_notional = adj_entry_price * qty_to_buy; cost_with_fee = buy_notional * (1 + FEE_RATE)
                        logger.debug(f"  BUY Needed: Adj Price={adj_entry_price:.4f}, Adj Qty={qty_to_buy:.8f}, Notional={buy_notional:.4f}, Cost={cost_with_fee:.4f}, Avail Quote={quote_balance:.4f}")
                        if buy_notional >= min_notional_bt and quote_balance >= cost_with_fee:
                            quote_balance -= cost_with_fee; base_balance += qty_to_buy; total_fees_paid += buy_notional * FEE_RATE
                            trade_log.append({'timestamp': timestamp_utc, 'type': f"REBALANCE_BUY", 'price': adj_entry_price, 'qty': qty_to_buy, 'value': -buy_notional, 'fee': buy_notional * FEE_RATE, 'target_band': target_band_index, 'target_pct': target_pct, 'current_pct': current_pct})
                            # *** CHANGED to DEBUG ***
                            logger.debug(f"    +++ REBALANCE BUY Executed @ {adj_entry_price:.2f} Qty {qty_to_buy:.8f} +++"); trade_executed = True
                        else: logger.debug(f"    Skipped BUY: Filter fail (Notional {buy_notional:.4f} vs Min {min_notional_bt:.4f} OR Quote {quote_balance:.4f} vs Cost {cost_with_fee:.4f})")
                elif value_to_trade < 0: # SELL Rebalance
                    adj_exit_price = adjust_tp_price_bt(signal_price_for_calc, price_tick_size_bt)
                    if not adj_exit_price or adj_exit_price <= 0: logger.warning(f"  Adjusted SELL price invalid ({adj_exit_price}).")
                    else:
                        base_balance = Decimal(str(base_balance)); qty_to_sell_raw = abs(value_to_trade) / adj_exit_price; qty_to_sell = adjust_qty_bt(qty_to_sell_raw, min_qty_bt, qty_step_size_bt)
                        qty_to_sell = min(qty_to_sell, base_balance); sell_notional = adj_exit_price * qty_to_sell
                        logger.debug(f"  SELL Needed: Adj Price={adj_exit_price:.4f}, Adj Qty={qty_to_sell:.8f}, Notional={sell_notional:.4f}, Avail Base={base_balance:.8f}")
                        if sell_notional >= min_notional_bt and qty_to_sell > 0:
                            gross_proceeds = sell_notional; fee = gross_proceeds * FEE_RATE; net_proceeds = gross_proceeds - fee
                            quote_balance += net_proceeds; base_balance -= qty_to_sell; total_fees_paid += fee
                            trade_log.append({'timestamp': timestamp_utc, 'type': f"REBALANCE_SELL", 'price': adj_exit_price, 'qty': qty_to_sell, 'value': net_proceeds, 'fee': fee, 'target_band': target_band_index, 'target_pct': target_pct, 'current_pct': current_pct})
                            # *** CHANGED to DEBUG ***
                            logger.debug(f"    +++ REBALANCE SELL Executed @ {adj_exit_price:.2f} Qty {qty_to_sell:.8f} +++"); trade_executed = True
                        else: logger.debug(f"    Skipped SELL: Filter fail (Notional {sell_notional:.4f} vs Min {min_notional_bt:.4f} OR Qty <= 0)")
            else: logger.debug(f"  No trade needed (abs(value_to_trade) {abs(value_to_trade):.4f} <= threshold {min_trade_value_threshold:.4f}).")
            if trade_executed:
                 logger.debug(f"  New Balance: Quote={quote_balance:,.2f}, Base={base_balance:.8f}")
                 post_trade_port_value = quote_balance + (base_balance * signal_price_for_calc);
                 if post_trade_port_value > 0: logger.debug(f"  Post-Trade Crypto Alloc: {(base_balance * signal_price_for_calc)/post_trade_port_value:.2%} (Target was: {target_pct:.2%})")

    # --- D. Record Portfolio Values & Update Last Close (Unchanged) ---\n
    current_portfolio_value_eoc = quote_balance + (base_balance * current_close); current_hodl_value = hodl_base_qty * current_close
    strategy_vs_hodl_pct = Decimal('NaN')
    if current_hodl_value and current_hodl_value > 0:
        try: strategy_vs_hodl_pct = (current_portfolio_value_eoc / current_hodl_value) * 100
        except (InvalidOperation, ZeroDivisionError): strategy_vs_hodl_pct = Decimal('NaN')
    portfolio_history.append({'timestamp': timestamp_utc, 'portfolio_value': current_portfolio_value_eoc, 'quote': quote_balance, 'base': base_balance, 'strategy_vs_hodl_pct': strategy_vs_hodl_pct})
    hodl_portfolio_history.append({'timestamp': timestamp_utc, 'hodl_value': current_hodl_value})
    last_candle_close = current_close

# --- Loop End ---\n
logging.info(f"--- Simulation Loop Finished ---\n") # Log finish

# --- Final Portfolio Calculation & Performance Metrics (Unchanged) ---\n
trades_df = pd.DataFrame(trade_log)
if not trades_df.empty:
     trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
     for col in ['price', 'qty', 'value', 'fee', 'target_pct', 'current_pct']:
         if col in trades_df.columns: trades_df[col] = trades_df[col].apply(lambda x: Decimal(str(x)) if pd.notna(x) and x is not None else Decimal('NaN'))

final_quote_balance = quote_balance; final_base_balance = base_balance
last_close_price = historical_data_test['Close'].iloc[-1] if not historical_data_test.empty else Decimal('0')
final_portfolio_value = final_quote_balance + (final_base_balance * last_close_price)
final_hodl_value = hodl_base_qty * last_close_price
print("\n--- Backtest Results (v13.7.4 - Quieter Fills) ---") # Note version
print(f"Simulation Period: {historical_data_test.index.min()} to {historical_data_test.index.max()}")
print(f"Trigger: Price crossing ANY Rainbow Band boundary"); print(f"Context & Allocation: {NUM_RAINBOW_BANDS} Bands, Exponent={ALLOCATION_EXPONENT}")
print(f"Rebalancing: Continuous adjustment on cross, Skipped if < MIN_NOTIONAL"); print(f"Fee Rate Applied: {FEE_RATE*100}%\\n")
print(f"Initial Portfolio Value: {STARTING_QUOTE_BALANCE:,.2f} {QUOTE_ASSET}"); print(f"Final Portfolio Value (Strategy): {final_portfolio_value:,.2f} {QUOTE_ASSET}")
total_profit_loss = final_portfolio_value - STARTING_QUOTE_BALANCE; total_profit_loss_percent = (total_profit_loss / STARTING_QUOTE_BALANCE) * 100 if STARTING_QUOTE_BALANCE > 0 else Decimal('0')
print(f"Total Profit/Loss (Strategy): {total_profit_loss:,.2f} {QUOTE_ASSET} ({total_profit_loss_percent:.2f}%)\"")
print(f"Final Portfolio Value (HODL): {final_hodl_value:,.2f} {QUOTE_ASSET}")
hodl_profit_loss = final_hodl_value - STARTING_QUOTE_BALANCE; hodl_profit_loss_percent = (hodl_profit_loss / STARTING_QUOTE_BALANCE) * 100 if STARTING_QUOTE_BALANCE > 0 else Decimal('0')
print(f"Total Profit/Loss (HODL): {hodl_profit_loss:,.2f} {QUOTE_ASSET} ({hodl_profit_loss_percent:.2f}%)\"")

perf_vs_hodl_pct = Decimal('NaN');
if final_hodl_value and final_hodl_value > 0: perf_vs_hodl_pct = (final_portfolio_value / final_hodl_value) * 100
print(f"Strategy Performance vs HODL: {perf_vs_hodl_pct:.2f}%")

print(f"\nTotal Rebalancing Trades Executed: {len(trades_df)}")
if not trades_df.empty:
    initial_trades = trades_df[trades_df['type'] == 'INITIAL_ALLOC_BUY']; buy_trades = trades_df[trades_df['type'] == 'REBALANCE_BUY']; sell_trades = trades_df[trades_df['type'] == 'REBALANCE_SELL']
    print(f"  Initial Alloc Trades: {len(initial_trades)}"); print(f"  Buy Rebalances: {len(buy_trades)}"); print(f"  Sell Rebalances: {len(sell_trades)}")
    total_buy_value = abs(buy_trades['value'].dropna().sum()) if not buy_trades.empty else Decimal('0'); total_initial_value = abs(initial_trades['value'].dropna().sum()) if not initial_trades.empty else Decimal('0'); total_sell_value = sell_trades['value'].dropna().sum() if not sell_trades.empty else Decimal('0')
    print(f"  Total Buy Value (Quote): {(total_buy_value + total_initial_value):,.2f}"); print(f"  Total Sell Value (Quote): {total_sell_value:,.2f}")
else: print("  Buy Rebalances: 0\\n  Sell Rebalances: 0");
print(f"Total Fees Paid (Strategy): {total_fees_paid:,.4f} {QUOTE_ASSET}")

# --- Plotting (Axes Flipped, Price Scaled) --- V4 (Unchanged Plotting) ---
try:
    portfolio_df = pd.DataFrame(portfolio_history).set_index('timestamp')
    fig, ax1 = plt.subplots(figsize=(15, 8)) # ax1 is now Price axis (Left)

    # --- Plot 1: Price + PL Lines + Trades (LEFT AXIS) ---
    color = 'black'; ax1.set_xlabel('Date'); ax1.set_ylabel('BTC Price (USDT)', color=color)
    price_line, = ax1.plot(historical_data_test.index, historical_data_test['Close'].astype(float), color='grey', linewidth=0.75, alpha=0.8, label='BTC Price (Close)')
    ax1.tick_params(axis='y', labelcolor=color); price_formatter = mticker.FormatStrFormatter('%.0f'); ax1.yaxis.set_major_formatter(price_formatter)
    ax1.grid(True, linestyle=':', alpha=0.6)

    pl_s_line = None; pl_r_line = None
    if not df_lines.empty:
        df_lines_aligned = df_lines.reindex(historical_data_test.index, method='ffill')
        pl_s_line, = ax1.plot(df_lines_aligned.index, df_lines_aligned['Support'].astype(float), color='red', linestyle='--', linewidth=1, alpha=0.7, label='PL Support')
        pl_r_line, = ax1.plot(df_lines_aligned.index, df_lines_aligned['Resistance'].astype(float), color='purple', linestyle='--', linewidth=1, alpha=0.7, label='PL Resistance')

    buy_plot = None; sell_plot = None
    if not trades_df.empty:
        trades_df['price_float'] = trades_df['price'].apply(lambda x: float(x) if isinstance(x, Decimal) and not x.is_nan() else np.nan)
        buy_markers = trades_df[(trades_df['type'] == 'REBALANCE_BUY') | (trades_df['type'] == 'INITIAL_ALLOC_BUY')].dropna(subset=['price_float'])
        sell_markers = trades_df[trades_df['type'] == 'REBALANCE_SELL'].dropna(subset=['price_float'])
        if not buy_markers.empty: buy_plot = ax1.scatter(buy_markers['timestamp'], buy_markers['price_float'] * 1.001, label='Buy Executed', marker='^', color='lime', s=50, alpha=0.9, zorder=5)
        if not sell_markers.empty: sell_plot = ax1.scatter(sell_markers['timestamp'], sell_markers['price_float'] * 0.999, label='Sell Executed', marker='v', color='red', s=50, alpha=0.9, zorder=5)

    # --- Plot 2: Strategy Performance vs HODL (%) (RIGHT AXIS) ---
    ax2 = ax1.twinx(); color = 'tab:blue'; ax2.set_ylabel('Strategy Value (% of HODL)', color=color)
    portfolio_df['strategy_vs_hodl_pct_float'] = portfolio_df['strategy_vs_hodl_pct'].apply(lambda x: float(x) if isinstance(x, Decimal) and not x.is_nan() else np.nan)
    strat_pct_line, = ax2.plot(portfolio_df.index, portfolio_df['strategy_vs_hodl_pct_float'], color=color, linewidth=1.5, label=f'Strategy Perf vs HODL (%)')
    hodl_baseline = ax2.axhline(100, color=color, linestyle=':', linewidth=1, label='100% (HODL Baseline)', alpha=0.7)
    ax2.tick_params(axis='y', labelcolor=color); ax2.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=100)); ax2.grid(False)

    # --- Final Formatting ---
    handles_ax1, labels_ax1 = [price_line], [price_line.get_label()]
    if pl_s_line: handles_ax1.append(pl_s_line); labels_ax1.append(pl_s_line.get_label())
    if pl_r_line: handles_ax1.append(pl_r_line); labels_ax1.append(pl_r_line.get_label())
    if buy_plot: handles_ax1.append(buy_plot); labels_ax1.append(buy_plot.get_label())
    if sell_plot: handles_ax1.append(sell_plot); labels_ax1.append(sell_plot.get_label())
    handles_ax2, labels_ax2 = [strat_pct_line, hodl_baseline], [strat_pct_line.get_label(), hodl_baseline.get_label()]
    ax1.legend(handles_ax1 + handles_ax2, labels_ax1 + labels_ax2, loc='upper left')

    # Adjust Y-axis limits
    min_price_val = historical_data_test['Low'].astype(float).min(); max_price_val = historical_data_test['High'].astype(float).max()
    if pd.notna(min_price_val) and pd.notna(max_price_val): ax1.set_ylim(bottom=float(min_price_val) * 0.99, top=float(max_price_val) * 1.01)
    else: logger.warning("Could not determine valid price range for Y-axis limit on ax1.")
    min_pct = portfolio_df['strategy_vs_hodl_pct_float'].dropna().min(); max_pct = portfolio_df['strategy_vs_hodl_pct_float'].dropna().max()
    lower_bound = min(min_pct * 0.98, 90) if pd.notna(min_pct) else 90; upper_bound = max(max_pct * 1.02, 110) if pd.notna(max_pct) else 110
    ax2.set_ylim(bottom=lower_bound, top=upper_bound)

    freq_str = getattr(historical_data_test.index, 'freqstr', None) or "Hourly"
    fig.suptitle(f'Backtest v13.7.4: Price Context (L) & Strategy Perf vs HODL % (R) - {SYMBOL} ({freq_str})')

    fig.tight_layout(rect=[0, 0.03, 1, 0.95]); plt.show()

except ImportError: logging.warning("matplotlib not installed. Skipping plot generation. `pip install matplotlib`")
except Exception as plot_err: logging.error(f"Error during plotting: {plot_err}", exc_info=True)


# End of Cell 6 (v13.7.4 - Quieter Fills)


# In[ ]:


# Cell 7: Plot Backtest Results with Rainbow Band Shading

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.colors as mcolors # For colormaps
import logging
from decimal import Decimal # Although not used for calcs here, good practice

# --- Prerequisites ---
logger = logging.getLogger(__name__) # Get logger instance

# Check if necessary DataFrames and variables exist from previous cells
required_vars = ['historical_data_test', 'portfolio_df', 'trades_df', 'df_lines', 'rainbow_bands_df', 'NUM_RAINBOW_BANDS', 'SYMBOL']
for var in required_vars:
    if var not in locals() and var not in globals():
         raise NameError(f"Variable '{var}' not found. Please run previous cells (especially Cell 6) first.")

if portfolio_df.empty or historical_data_test.empty:
     raise ValueError("Portfolio history or historical test data is empty. Run Cell 6.")


# --- Plotting (Rainbow Bands Shaded) --- V5 ---
logging.info("--- Generating Plot with Rainbow Band Shading ---")
try:
    # Make copies to avoid modifying original dfs if needed elsewhere
    portfolio_df_plot = portfolio_df.copy()
    trades_df_plot = trades_df.copy() if not trades_df.empty else pd.DataFrame() # Handle empty trades_df

    fig, ax1 = plt.subplots(figsize=(15, 8)) # ax1 is Price axis (Left)

    # --- Plot 1: Price + PL Lines + Trades + RAINBOW BANDS (LEFT AXIS) ---
    color = 'black'; ax1.set_xlabel('Date'); ax1.set_ylabel('BTC Price (USDT)', color=color)
    # Plot price first
    price_line, = ax1.plot(historical_data_test.index, historical_data_test['Close'].astype(float), color='dimgrey', linewidth=1.0, alpha=0.9, label='BTC Price (Close)', zorder=4) # Increase zorder
    ax1.tick_params(axis='y', labelcolor=color); price_formatter = mticker.FormatStrFormatter('%.0f'); ax1.yaxis.set_major_formatter(price_formatter)
    ax1.grid(True, linestyle=':', alpha=0.4, zorder=0) # Send grid behind everything

    # Align daily data to hourly index for plotting
    plot_index = historical_data_test.index # Use the index of the main backtest data
    if not df_lines.empty:
        df_lines_aligned = df_lines.reindex(plot_index, method='ffill')
    if not rainbow_bands_df.empty:
        rainbow_bands_aligned = rainbow_bands_df.reindex(plot_index, method='ffill')

    # --- Plot Rainbow Bands Shading ---
    if not rainbow_bands_aligned.empty:
        # Choose a colormap (e.g., 'rainbow', 'viridis', 'coolwarm', 'RdYlGn')
        cmap = plt.cm.rainbow # Or plt.cm.viridis, plt.cm.coolwarm etc.
        band_alpha = 0.10 # Transparency of the bands

        # Ensure band columns are float for plotting
        for i in range(NUM_RAINBOW_BANDS + 1):
             col_name = f'Band_{i}'
             if col_name in rainbow_bands_aligned.columns:
                  rainbow_bands_aligned[col_name] = rainbow_bands_aligned[col_name].astype(float)


        # Loop through bands and fill_between
        for i in range(NUM_RAINBOW_BANDS):
            lower_band_col = f'Band_{i}'
            upper_band_col = f'Band_{i+1}'
            # Check if columns exist
            if lower_band_col in rainbow_bands_aligned.columns and upper_band_col in rainbow_bands_aligned.columns:
                color_val = cmap(i / NUM_RAINBOW_BANDS) # Normalize index to 0-1 for colormap
                ax1.fill_between(rainbow_bands_aligned.index,
                                 rainbow_bands_aligned[lower_band_col],
                                 rainbow_bands_aligned[upper_band_col],
                                 color=color_val,
                                 alpha=band_alpha,
                                 linewidth=0, # No lines between bands
                                 zorder=1) # Place bands behind price/trades
            # else:
                # logger.warning(f"Columns missing for band {i}: {lower_band_col}, {upper_band_col}")

    # Plot Power Law Lines on ax1 (after bands)
    pl_s_line = None; pl_r_line = None
    if not df_lines_aligned.empty:
        pl_s_line, = ax1.plot(df_lines_aligned.index, df_lines_aligned['Support'].astype(float), color='maroon', linestyle='--', linewidth=1.5, alpha=0.8, label='PL Support', zorder=3) # Darker red
        pl_r_line, = ax1.plot(df_lines_aligned.index, df_lines_aligned['Resistance'].astype(float), color='indigo', linestyle='--', linewidth=1.5, alpha=0.8, label='PL Resistance', zorder=3) # Darker purple

    # Plot Trade Markers on ax1 (after bands)
    buy_plot = None; sell_plot = None
    if not trades_df_plot.empty:
        # Ensure price_float column exists and handle potential prior creation
        if 'price_float' not in trades_df_plot.columns:
             trades_df_plot['price_float'] = trades_df_plot['price'].apply(lambda x: float(x) if isinstance(x, Decimal) and not x.is_nan() else np.nan)

        buy_markers = trades_df_plot[(trades_df_plot['type'] == 'REBALANCE_BUY') | (trades_df_plot['type'] == 'INITIAL_ALLOC_BUY')].dropna(subset=['price_float'])
        sell_markers = trades_df_plot[trades_df_plot['type'] == 'REBALANCE_SELL'].dropna(subset=['price_float'])
        if not buy_markers.empty: buy_plot = ax1.scatter(buy_markers['timestamp'], buy_markers['price_float'] * 1.001, label='Buy Executed', marker='^', color='lime', edgecolor='black', linewidth=0.5, s=60, alpha=1.0, zorder=5) # Adjusted appearance
        if not sell_markers.empty: sell_plot = ax1.scatter(sell_markers['timestamp'], sell_markers['price_float'] * 0.999, label='Sell Executed', marker='v', color='red', edgecolor='black', linewidth=0.5, s=60, alpha=1.0, zorder=5) # Adjusted appearance


    # --- Plot 2: Strategy Performance vs HODL (%) (RIGHT AXIS) ---
    ax2 = ax1.twinx(); color = 'tab:blue'; ax2.set_ylabel('Strategy Value (% of HODL)', color=color)
    if 'strategy_vs_hodl_pct_float' not in portfolio_df_plot.columns: # Calculate if not done in cell 6 history recording
        portfolio_df_plot['strategy_vs_hodl_pct_float'] = portfolio_df_plot['strategy_vs_hodl_pct'].apply(lambda x: float(x) if isinstance(x, Decimal) and not x.is_nan() else np.nan)

    strat_pct_line, = ax2.plot(portfolio_df_plot.index, portfolio_df_plot['strategy_vs_hodl_pct_float'], color=color, linewidth=1.5, label=f'Strategy Perf vs HODL (%)')
    hodl_baseline = ax2.axhline(100, color=color, linestyle=':', linewidth=1, label='100% (HODL Baseline)', alpha=0.7)
    ax2.tick_params(axis='y', labelcolor=color); ax2.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=100)); ax2.grid(False)

    # --- Final Formatting ---
    # Collect handles manually
    handles_ax1, labels_ax1 = [price_line], [price_line.get_label()]
    if pl_s_line: handles_ax1.append(pl_s_line); labels_ax1.append(pl_s_line.get_label())
    if pl_r_line: handles_ax1.append(pl_r_line); labels_ax1.append(pl_r_line.get_label())
    if buy_plot: handles_ax1.append(buy_plot); labels_ax1.append(buy_plot.get_label())
    if sell_plot: handles_ax1.append(sell_plot); labels_ax1.append(sell_plot.get_label())
    handles_ax2, labels_ax2 = [strat_pct_line, hodl_baseline], [strat_pct_line.get_label(), hodl_baseline.get_label()]
    # Place combined legend on ax1
    ax1.legend(handles_ax1 + handles_ax2, labels_ax1 + labels_ax2, loc='upper left', fontsize='small') # Adjust font size if needed

    # Adjust Y-axis limits
    min_price_val = historical_data_test['Low'].astype(float).min(); max_price_val = historical_data_test['High'].astype(float).max()
    if pd.notna(min_price_val) and pd.notna(max_price_val): ax1.set_ylim(bottom=float(min_price_val) * 0.99, top=float(max_price_val) * 1.01)
    else: logger.warning("Could not determine valid price range for Y-axis limit on ax1.")

    # Calculate % axis limits based on plotted data
    min_pct_val = portfolio_df_plot['strategy_vs_hodl_pct_float'].dropna().min()
    max_pct_val = portfolio_df_plot['strategy_vs_hodl_pct_float'].dropna().max()
    lower_pct_bound = min(min_pct_val * 0.98, 90) if pd.notna(min_pct_val) else 85 # Adjust default lower if needed
    upper_pct_bound = max(max_pct_val * 1.02, 110) if pd.notna(max_pct_val) else 115 # Adjust default upper if needed
    ax2.set_ylim(bottom=lower_pct_bound, top=upper_pct_bound)


    # --- Title ---
    # Attempt to get version from Cell 6 output, otherwise use placeholder
    backtest_version = "v13.7.x" # Placeholder
    # This part is tricky as we don't have direct access to Cell 6's print output here.
    # We'll stick to a generic title or manually update if needed.
    # Could potentially parse the log file if absolutely necessary, but likely overkill.
    fig.suptitle(f'Backtest Analysis: Price Context (L) & Strategy Perf vs HODL % (R) - {SYMBOL} (Rainbow Bands)', fontsize=14)

    fig.tight_layout(rect=[0, 0.03, 1, 0.95]); plt.show()

except NameError as ne:
     logger.error(f"Plotting Error: {ne}. Make sure prerequisite cells (esp. Cell 6) have been run.")
except ValueError as ve:
     logger.error(f"Plotting Error: {ve}. Check if DataFrames are empty.")
except Exception as plot_err:
    logger.error(f"Error during plotting: {plot_err}", exc_info=True)


# End of Cell 7: Plot Backtest Results with Rainbow Band Shading


# In[ ]:


# Cell 7 (v3.0 - Verify Input Data & Set Price Y-Limit FIRST): Plot Backtest Results

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import logging
from decimal import Decimal # Although not used for calcs here, good practice

# --- Prerequisites ---
logger = logging.getLogger(__name__) # Get logger instance

# Check if necessary DataFrames and variables exist from previous cells
required_vars = ['historical_data_test', 'portfolio_df', 'trades_df', 'df_lines', 'rainbow_bands_df', 'NUM_RAINBOW_BANDS', 'SYMBOL']
for var in required_vars:
    if var not in locals() and var not in globals():
         raise NameError(f"Variable '{var}' not found. Please run previous cells (especially Cell 6) first.")

# *** ADDED VERIFICATION STEP ***
logger.info("--- Verifying input historical_data_test before plotting ---")
if 'historical_data_test' in locals() or 'historical_data_test' in globals():
    if not historical_data_test.empty:
        try:
            max_high_in_input = historical_data_test['High'].astype(float).max()
            min_low_in_input = historical_data_test['Low'].astype(float).min()
            logger.info(f"VERIFICATION: historical_data_test['High'].max() = {max_high_in_input}")
            logger.info(f"VERIFICATION: historical_data_test['Low'].min() = {min_low_in_input}")
            expected_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'ATR_'] # Check for expected cols prefix
            actual_cols = historical_data_test.columns.tolist()
            logger.info(f"VERIFICATION: historical_data_test columns: {actual_cols}")
            if max_high_in_input > 50000: # Threshold suggesting contamination
                 logger.warning("!!! VERIFICATION FAILED: Max high in historical_data_test seems too large (> 50k), likely contaminated!")
            else:
                 logger.info("VERIFICATION: Max high seems reasonable (< 50k).")

        except Exception as e:
            logger.error(f"Error during verification: {e}")
    else:
        logger.error("VERIFICATION: historical_data_test is empty!")
else:
    logger.error("VERIFICATION: historical_data_test not found!")
# ******************************

# Check required DFs (redundant but safe)
if 'historical_data_test' not in globals() or historical_data_test.empty:
     raise ValueError("historical_data_test is empty. Run Cell 3/6.")
if 'rainbow_bands_df' not in globals() or rainbow_bands_df.empty:
      raise ValueError("rainbow_bands_df is empty. Run Cell 5.1.")
if 'trades_df' not in globals():
     raise ValueError("trades_df is missing. Run Cell 6.")


# --- Plotting (Set Price Y-Limit FIRST) --- V16 ---
logging.info("--- Generating Plot: Price Focus (Setting Y-Limit FIRST) ---")
try:
    trades_df_plot = trades_df.copy() if not trades_df.empty else pd.DataFrame()

    fig, ax1 = plt.subplots(figsize=(15, 8)) # Only one axis needed: ax1 is Price axis (Left)

    # --- *** STEP 1: Calculate and SET Y-Limits for Price Axis FIRST *** ---
    # Use the VERIFIED input max/min if possible
    min_price_val = historical_data_test['Low'].astype(float).min()
    max_price_val = historical_data_test['High'].astype(float).max()

    # *** Check if max_price_val is still contaminated despite verification ***
    # If it seems contaminated, override it for plotting purposes
    if max_price_val > 50000: # Use 50k as a sanity check threshold
        logger.warning(f"Overriding calculated max_price_val ({max_price_val}) with 50000 for plot scaling due to suspected contamination.")
        max_price_val_plot = 50000.0
    else:
        max_price_val_plot = max_price_val # Use the calculated value if it seems okay

    if pd.notna(min_price_val) and pd.notna(max_price_val_plot):
         padding_pct = 0.015
         price_range = max_price_val_plot - min_price_val
         if price_range <= 0: price_range = max_price_val_plot * 0.01 if max_price_val_plot > 0 else 1.0
         plot_bottom = float(min_price_val) - (price_range * padding_pct)
         plot_top = float(max_price_val_plot) + (price_range * padding_pct)

         ax1.set_ylim(bottom=plot_bottom, top=plot_top)
         logger.info(f"PRE-SETTING Y-limit for Price axis (ax1) based on data range [{min_price_val:.2f}, {max_price_val_plot:.2f}] -> [{plot_bottom:.2f}, {plot_top:.2f}]")
    else:
        logger.warning("Could not determine valid price range; using default Y-limit for ax1.")

    # --- *** STEP 2: Now Plot Everything onto the Pre-Scaled Axis *** ---
    color = 'black'; ax1.set_xlabel('Date'); ax1.set_ylabel('BTC Price (USDT)', color=color)
    price_line, = ax1.plot(historical_data_test.index, historical_data_test['Close'].astype(float), color='dimgrey', linewidth=1.0, alpha=0.9, label='BTC Price (Close)', zorder=4)
    ax1.tick_params(axis='y', labelcolor=color); price_formatter = mticker.FormatStrFormatter('%.0f'); ax1.yaxis.set_major_formatter(price_formatter)
    ax1.grid(True, linestyle=':', alpha=0.4, zorder=0)

    # Align daily data
    plot_index = historical_data_test.index
    df_lines_aligned = pd.DataFrame(); rainbow_bands_aligned = pd.DataFrame()
    if not df_lines.empty: df_lines_aligned = df_lines.reindex(plot_index, method='ffill')
    if not rainbow_bands_df.empty: rainbow_bands_aligned = rainbow_bands_df.reindex(plot_index, method='ffill')

    # Plot Rainbow Band Boundary Lines
    band_line_color = 'lightgrey'; band_line_style = ':'; band_line_width = 0.5; band_zorder = 1
    plotted_band_line = False
    if not rainbow_bands_aligned.empty:
        for i in range(1, NUM_RAINBOW_BANDS):
             col_name = f'Band_{i}'
             if col_name in rainbow_bands_aligned.columns:
                  band_data_float = rainbow_bands_aligned[col_name].astype(float)
                  ax1.plot(rainbow_bands_aligned.index, band_data_float, color=band_line_color, linestyle=band_line_style, linewidth=band_line_width, zorder=band_zorder, label='Rainbow Boundaries' if not plotted_band_line else "")
                  plotted_band_line = True

    # Plot Power Law Lines on ax1 (they might be clipped now)
    pl_s_line = None; pl_r_line = None
    if not df_lines_aligned.empty:
        pl_s_line, = ax1.plot(df_lines_aligned.index, df_lines_aligned['Support'].astype(float), color='maroon', linestyle='--', linewidth=1.5, alpha=0.8, label='PL Support (Band 0)', zorder=3)
        pl_r_line, = ax1.plot(df_lines_aligned.index, df_lines_aligned['Resistance'].astype(float), color='indigo', linestyle='--', linewidth=1.5, alpha=0.8, label=f'PL Resistance (Band {NUM_RAINBOW_BANDS})', zorder=3)

    # Plot Trade Markers on ax1
    buy_plot = None; sell_plot = None
    if not trades_df_plot.empty:
        if 'price_float' not in trades_df_plot.columns: trades_df_plot['price_float'] = trades_df_plot['price'].apply(lambda x: float(x) if isinstance(x, Decimal) and not x.is_nan() else np.nan)
        buy_markers = trades_df_plot[(trades_df_plot['type'] == 'REBALANCE_BUY') | (trades_df_plot['type'] == 'INITIAL_ALLOC_BUY')].dropna(subset=['price_float'])
        sell_markers = trades_df_plot[trades_df_plot['type'] == 'REBALANCE_SELL'].dropna(subset=['price_float'])
        if not buy_markers.empty: buy_plot = ax1.scatter(buy_markers['timestamp'], buy_markers['price_float'] * 1.001, label='Buy Executed', marker='^', color='lime', edgecolor='black', linewidth=0.5, s=60, alpha=1.0, zorder=5)
        if not sell_markers.empty: sell_plot = ax1.scatter(sell_markers['timestamp'], sell_markers['price_float'] * 0.999, label='Sell Executed', marker='v', color='red', edgecolor='black', linewidth=0.5, s=60, alpha=1.0, zorder=5)

    # --- REMOVED: Secondary Axis ---

    # --- Final Formatting ---
    # Collect handles manually from ax1 ONLY
    handles_ax1, labels_ax1 = [price_line], [price_line.get_label()]
    if pl_s_line: handles_ax1.append(pl_s_line); labels_ax1.append(pl_s_line.get_label())
    if pl_r_line: handles_ax1.append(pl_r_line); labels_ax1.append(pl_r_line.get_label())
    if plotted_band_line:
        from matplotlib.lines import Line2D
        dummy_band_line = Line2D([0], [0], color=band_line_color, linestyle=band_line_style, linewidth=band_line_width, label='Rainbow Boundaries')
        handles_ax1.append(dummy_band_line); labels_ax1.append(dummy_band_line.get_label())
    if buy_plot: handles_ax1.append(buy_plot); labels_ax1.append(buy_plot.get_label())
    if sell_plot: handles_ax1.append(sell_plot); labels_ax1.append(sell_plot.get_label())

    # Place legend on ax1
    ax1.legend(handles_ax1, labels_ax1, loc='upper left', fontsize='small')

    # --- Y-axis limits for ax1 were already set at the beginning ---

    # --- Title ---
    fig.suptitle(f'Backtest Analysis: Price Focus (Scaled to Data Extents) - {SYMBOL}', fontsize=14)

    fig.tight_layout(rect=[0, 0.03, 1, 0.95]); plt.show()

except NameError as ne:
     logger.error(f"Plotting Error: {ne}. Make sure prerequisite cells (esp. Cell 6) have been run.")
except ValueError as ve:
     logger.error(f"Plotting Error: {ve}. Check if DataFrames are empty.")
except Exception as plot_err:
    logger.error(f"Error during plotting: {plot_err}", exc_info=True)


# End of Cell 7 (v3.0 - Verify Input Data & Set Price Y-Limit FIRST)


# In[ ]:


# Cell 7: Analyze Trades During Performance Jump (v9.3)

import pandas as pd
import logging
from decimal import Decimal # Import Decimal for potential formatting

# --- Prerequisites ---
if 'trades_df' not in locals() or trades_df.empty:
    raise RuntimeError("trades_df is missing or empty. Run Cell 6 (Backtester) first.")

# --- Analysis Configuration ---
# Estimate the period of the jump from the plot
JUMP_START_DATE = pd.Timestamp("2023-06-15", tz='UTC')
JUMP_END_DATE = pd.Timestamp("2023-07-15", tz='UTC')

logging.info(f"--- Analyzing Trades Around Performance Jump ({JUMP_START_DATE.date()} to {JUMP_END_DATE.date()}) ---")

# --- Filter and Display Trades ---
try:
    # Ensure the index is DatetimeIndex for slicing
    if not isinstance(trades_df.index, pd.DatetimeIndex):
        if 'timestamp' in trades_df.columns:
            # Convert timestamp column to datetime and set as index
            trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
            trades_df_indexed = trades_df.set_index('timestamp')
            if trades_df_indexed.index.tz is None: # Localize if needed
                 trades_df_indexed.index = trades_df_indexed.index.tz_localize('UTC')
            elif trades_df_indexed.index.tz != timezone.utc: # Convert if different TZ
                 trades_df_indexed.index = trades_df_indexed.index.tz_convert('UTC')

        else:
            raise ValueError("'timestamp' column not found for setting index.")
    else:
        # Ensure index is UTC if already DatetimeIndex
        trades_df_indexed = trades_df.copy()
        if trades_df_indexed.index.tz is None: trades_df_indexed.index = trades_df_indexed.index.tz_localize('UTC')
        elif trades_df_indexed.index.tz != timezone.utc: trades_df_indexed.index = trades_df_indexed.index.tz_convert('UTC')


    # Filter trades within the specified period
    jump_trades = trades_df_indexed.loc[JUMP_START_DATE:JUMP_END_DATE].copy()

    if jump_trades.empty:
        logging.info("No trades found within the specified jump period.")
    else:
        logging.info(f"Found {len(jump_trades)} trades during the jump period:")

        # Select and format relevant columns for display
        display_cols = ['type', 'price', 'qty', 'value', 'fee', 'buy_fill_price', 'depth_bucket', 'tp_level_pct']
        jump_trades_display = jump_trades[[col for col in display_cols if col in jump_trades.columns]].copy() # Select existing columns

        # Format numeric columns (handle potential non-Decimals if necessary)
        for col in ['price', 'qty', 'value', 'fee', 'buy_fill_price']:
             if col in jump_trades_display.columns:
                 try:
                     prec = 8 if 'qty' in col else 4
                     # Ensure conversion from string/object if needed, then format
                     jump_trades_display[col] = jump_trades_display[col].apply(lambda x: f"{Decimal(str(x)):.{prec}f}" if pd.notna(x) else 'N/A')
                 except Exception:
                      logging.warning(f"Could not format column {col} as Decimal.") # Keep original on error

        # Format percentage
        if 'tp_level_pct' in jump_trades_display.columns:
             jump_trades_display['tp_level_pct'] = jump_trades_display['tp_level_pct'].apply(lambda x: f"{x*100:.0f}%" if pd.notna(x) else 'N/A')


        print(jump_trades_display.to_string())

        # Basic summary statistics for the period
        initial_alloc_trades = jump_trades[jump_trades['type'] == 'INITIAL_ALLOC_BUY']
        buy_trades_period = jump_trades[jump_trades['type'] == 'BUY_PL_GRID']
        sell_trades_period = jump_trades[jump_trades['type'] == 'SELL_PL_GRID_TP']

        # Convert relevant columns back to Decimal for calculation if they exist and are valid
        try: buy_value = sum(Decimal(str(v)) for v in buy_trades_period['value'] if pd.notna(v))
        except: buy_value = Decimal('0')
        try: sell_value = sum(Decimal(str(v)) for v in sell_trades_period['value'] if pd.notna(v))
        except: sell_value = Decimal('0')
        try: fees_period = sum(Decimal(str(v)) for v in jump_trades['fee'] if pd.notna(v))
        except: fees_period = Decimal('0')

        logging.info(f"\nSummary for {JUMP_START_DATE.date()} to {JUMP_END_DATE.date()}:")
        logging.info(f"  Buy Trades: {len(buy_trades_period)}, Total Cost (excl. fee): {-buy_value:.2f}")
        logging.info(f"  Sell Trades: {len(sell_trades_period)}, Total Proceeds (excl. fee): {sell_value:.2f}")
        logging.info(f"  Net Value Change (excl. fee): {buy_value + sell_value:.2f}")
        logging.info(f"  Total Fees: {fees_period:.4f}")

except Exception as e:
    logging.error(f"Error analyzing jump trades: {e}")
    import traceback
    traceback.print_exc()


# End of Cell 7


# In[ ]:


# Cell 8: Dynamic S/R Zone Calculation Helper Function

import pandas as pd
from decimal import Decimal
import logging
import sys

# --- Prerequisites ---
# Needs N_PERIODS_SWING, ZONE_THRESHOLD_PERCENT_SUP, ZONE_THRESHOLD_PERCENT_RES defined
# (These should be available if Cell 12 config was run/copied, but let's define defaults just in case)
if 'N_PERIODS_SWING' not in locals(): N_PERIODS_SWING = 11
if 'ZONE_THRESHOLD_PERCENT_SUP' not in locals(): ZONE_THRESHOLD_PERCENT_SUP = Decimal('0.005')
if 'ZONE_THRESHOLD_PERCENT_RES' not in locals(): ZONE_THRESHOLD_PERCENT_RES = Decimal('0.005')

# --- Helper Function Definition ---
def calculate_dynamic_zones(data_slice, n_periods, sup_thresh_pct, res_thresh_pct):
    """
    Calculates dynamic support and resistance zones based on swing points
    within a given data slice (Pandas DataFrame).

    Args:
        data_slice (pd.DataFrame): DataFrame slice with 'High', 'Low' columns (Decimal type).
        n_periods (int): The odd number of periods to define a swing point (e.g., 11).
        sup_thresh_pct (Decimal): The percentage threshold to cluster support points.
        res_thresh_pct (Decimal): The percentage threshold to cluster resistance points.

    Returns:
        tuple: (pd.DataFrame, pd.DataFrame) containing support zones and resistance zones.
               Columns: ['zone_min_price', 'zone_max_price', 'points', 'timestamps', 'num_points']
    """
    support_zones_list = []
    resistance_zones_list = []

    if len(data_slice) < n_periods:
        # Not enough data for the lookback window
        # logging.debug(f"Not enough data ({len(data_slice)} < {n_periods}) to calculate dynamic zones.")
        return pd.DataFrame(support_zones_list), pd.DataFrame(resistance_zones_list)

    half_n = n_periods // 2
    df_sr = data_slice.copy() # Work on a copy
    # Ensure High/Low are present
    if not all(col in df_sr.columns for col in ['High', 'Low']):
         logging.warning("Missing High/Low columns in data_slice for dynamic zone calculation.")
         return pd.DataFrame(support_zones_list), pd.DataFrame(resistance_zones_list)

    # Initialize swing columns
    df_sr['swing_high'] = pd.Series(index=df_sr.index, dtype=object)
    df_sr['swing_low'] = pd.Series(index=df_sr.index, dtype=object)

    # --- Calculate swing points ---
    # Iterate through the range where a full window is available
    for i in range(half_n, len(df_sr) - half_n):
        idx_label = df_sr.index[i]
        try:
            # Check for Swing High
            is_sh = all(df_sr['High'].iloc[i] >= df_sr['High'].iloc[i-j] for j in range(1, half_n + 1)) and \
                    all(df_sr['High'].iloc[i] > df_sr['High'].iloc[i+j] for j in range(1, half_n + 1))
            if is_sh: df_sr.loc[idx_label, 'swing_high'] = df_sr['High'].iloc[i]

            # Check for Swing Low
            is_sl = all(df_sr['Low'].iloc[i] <= df_sr['Low'].iloc[i-j] for j in range(1, half_n + 1)) and \
                    all(df_sr['Low'].iloc[i] < df_sr['Low'].iloc[i+j] for j in range(1, half_n + 1))
            if is_sl: df_sr.loc[idx_label, 'swing_low'] = df_sr['Low'].iloc[i]
        except IndexError:
            # This can happen near the edges if data_slice is shorter than expected, though the initial check should prevent it.
            logging.warning(f"IndexError during swing point calculation at index {i}. Check data slice length.")
            continue
        except Exception as e:
             logging.error(f"Error calculating swing point at index {i}: {e}")
             continue # Skip this point

    # --- Cluster Support Zones ---
    swing_lows_series = df_sr['swing_low'].dropna()
    current_zone_sup = None
    if not swing_lows_series.empty:
        try:
            swing_lows_df = swing_lows_series.reset_index()
            swing_lows_df.columns = ['timestamp', 'price']
            # Ensure price is Decimal
            swing_lows_df['price'] = swing_lows_df['price'].apply(lambda x: Decimal(str(x)))
            swing_lows_df = swing_lows_df.sort_values(by='price').reset_index(drop=True)

            current_zone_sup = {'zone_min_price': swing_lows_df['price'].iloc[0],
                               'zone_max_price': swing_lows_df['price'].iloc[0],
                               'points': [swing_lows_df['price'].iloc[0]],
                               'timestamps': [swing_lows_df['timestamp'].iloc[0]]}

            for i in range(1, len(swing_lows_df)):
                cp = swing_lows_df['price'].iloc[i]; ct = swing_lows_df['timestamp'].iloc[i]
                mtp = current_zone_sup['zone_max_price'] * (Decimal('1.0') + sup_thresh_pct)
                if cp <= mtp:
                    current_zone_sup['zone_max_price'] = max(current_zone_sup['zone_max_price'], cp)
                    current_zone_sup['points'].append(cp)
                    current_zone_sup['timestamps'].append(ct)
                else:
                    current_zone_sup['num_points'] = len(current_zone_sup['points'])
                    support_zones_list.append(current_zone_sup)
                    current_zone_sup = {'zone_min_price': cp, 'zone_max_price': cp, 'points': [cp], 'timestamps': [ct]}

            if current_zone_sup is not None: # Add the last zone
                current_zone_sup['num_points'] = len(current_zone_sup['points'])
                support_zones_list.append(current_zone_sup)
        except Exception as e:
            logging.error(f"Error clustering support zones: {e}")
            support_zones_list = [] # Reset on error

    # --- Cluster Resistance Zones ---
    swing_highs_series = df_sr['swing_high'].dropna()
    current_zone_res = None
    if not swing_highs_series.empty:
        try:
            swing_highs_df = swing_highs_series.reset_index()
            swing_highs_df.columns = ['timestamp', 'price']
            # Ensure price is Decimal
            swing_highs_df['price'] = swing_highs_df['price'].apply(lambda x: Decimal(str(x)))
            swing_highs_df = swing_highs_df.sort_values(by='price', ascending=False).reset_index(drop=True) # Descending for highs

            current_zone_res = {'zone_min_price': swing_highs_df['price'].iloc[0],
                               'zone_max_price': swing_highs_df['price'].iloc[0],
                               'points': [swing_highs_df['price'].iloc[0]],
                               'timestamps': [swing_highs_df['timestamp'].iloc[0]]}

            for i in range(1, len(swing_highs_df)):
                cp = swing_highs_df['price'].iloc[i]; ct = swing_highs_df['timestamp'].iloc[i]
                # Check if current price is within threshold of the MIN price in the current resistance zone
                mtp = current_zone_res['zone_min_price'] * (Decimal('1.0') - res_thresh_pct)
                if cp >= mtp:
                    current_zone_res['zone_min_price'] = min(current_zone_res['zone_min_price'], cp)
                    current_zone_res['points'].append(cp)
                    current_zone_res['timestamps'].append(ct)
                else:
                    current_zone_res['num_points'] = len(current_zone_res['points'])
                    resistance_zones_list.append(current_zone_res)
                    current_zone_res = {'zone_min_price': cp, 'zone_max_price': cp, 'points': [cp], 'timestamps': [ct]}

            if current_zone_res is not None: # Add the last zone
                current_zone_res['num_points'] = len(current_zone_res['points'])
                resistance_zones_list.append(current_zone_res)
        except Exception as e:
            logging.error(f"Error clustering resistance zones: {e}")
            resistance_zones_list = [] # Reset on error


    sup_df = pd.DataFrame(support_zones_list)
    res_df = pd.DataFrame(resistance_zones_list)
    return sup_df, res_df

logging.info("✅ Cell 4 Complete: Dynamic S/R Zone calculation function defined.")

# End of Cell 8


# In[ ]:


# Cell 9 (Revised - Zigzag Trendlines): Plot Lines Connecting Significant Swing Points (N=11)

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import logging
from decimal import Decimal
import numpy as np

# --- Prerequisites ---
if 'historical_data' not in locals() or historical_data.empty:
    raise RuntimeError("historical_data missing or empty. Run Cell 1.")
if 'swing_low' not in historical_data.columns or 'swing_high' not in historical_data.columns:
     raise RuntimeError("Swing point columns missing. Run Cell 2 (with desired N_PERIODS).")

# --- Configuration ---
PLOT_POINTS = 300 # Number of data points (candles) to plot
# N_PERIODS value used in Cell 2 (e.g., 11) is implicitly used via the data

logging.info(f"--- Plotting Zigzag Trendlines based on N={N_PERIODS} Swing Points (First {PLOT_POINTS} points) ---")

# Select data slice for plotting
plot_data = historical_data.iloc[:PLOT_POINTS].copy()
original_index = plot_data.index

# --- Prepare Data for Plotting ---
try:
    # Convert relevant columns to float for plotting
    plot_data['Close_float'] = plot_data['Close'].apply(lambda x: float(x) if isinstance(x, Decimal) else x)
    plot_data['swing_low_float'] = plot_data['swing_low'].apply(lambda x: float(x) if isinstance(x, Decimal) else np.nan)
    plot_data['swing_high_float'] = plot_data['swing_high'].apply(lambda x: float(x) if isinstance(x, Decimal) else np.nan)
except Exception as e:
    logging.error(f"❌ Error converting Decimal to float for plotting: {e}"); raise

# --- Extract Significant Swing Points ---
support_points = plot_data.dropna(subset=['swing_low_float'])
resistance_points = plot_data.dropna(subset=['swing_high_float'])

# --- Create Plot ---
fig, ax = plt.subplots(figsize=(15, 8))

# Plot Close price
ax.plot(original_index, plot_data['Close_float'], label='Close Price', color='blue', linewidth=1, zorder=2)

# --- Plot Zigzag Trendlines ---
plotted_support = False
plotted_resistance = False
support_lines_plotted_count = 0
resistance_lines_plotted_count = 0

logging.info("Plotting support trendlines (connecting higher lows)...")
if len(support_points) >= 2:
    for i in range(1, len(support_points)):
        prev_point = support_points.iloc[i-1]
        curr_point = support_points.iloc[i]

        # Check if current low is higher than previous low
        if curr_point['swing_low_float'] > prev_point['swing_low_float']:
            # Plot line segment between these two points
            segment_dates = [prev_point.name, curr_point.name] # .name gets the index (timestamp)
            segment_prices = [prev_point['swing_low_float'], curr_point['swing_low_float']]
            ax.plot(segment_dates, segment_prices, color='green', linestyle='--', linewidth=1,
                    label='Support Trendline (Zigzag)' if not plotted_support else "")
            plotted_support = True
            support_lines_plotted_count += 1

logging.info("Plotting resistance trendlines (connecting lower highs)...")
if len(resistance_points) >= 2:
     for i in range(1, len(resistance_points)):
        prev_point = resistance_points.iloc[i-1]
        curr_point = resistance_points.iloc[i]

        # Check if current high is lower than previous high
        if curr_point['swing_high_float'] < prev_point['swing_high_float']:
             # Plot line segment between these two points
            segment_dates = [prev_point.name, curr_point.name]
            segment_prices = [prev_point['swing_high_float'], curr_point['swing_high_float']]
            ax.plot(segment_dates, segment_prices, color='red', linestyle='--', linewidth=1,
                    label='Resistance Trendline (Zigzag)' if not plotted_resistance else "")
            plotted_resistance = True
            resistance_lines_plotted_count += 1


logging.info(f"Plotted {support_lines_plotted_count} support segments.")
logging.info(f"Plotted {resistance_lines_plotted_count} resistance segments.")

# Add dummy lines for legend only if NO lines of that type were plotted
if not plotted_support: ax.plot([], [], color='green', linestyle='--', label='Support Trendline (Zigzag)')
if not plotted_resistance: ax.plot([], [], color='red', linestyle='--', label='Resistance Trendline (Zigzag)')


# --- Formatting ---
# Get N used in Cell 2 if possible (otherwise assume 11)
n_val_display = N_PERIODS if 'N_PERIODS' in locals() else 11 # Show N=11 if N_PERIODS var not found
ax.set_title(f'{SYMBOL} Hourly Price with Zigzag Trendlines (N={n_val_display}, First {PLOT_POINTS} points)')
ax.set_xlabel('Date')
ax.set_ylabel('Price (USDT)')
ax.grid(True, linestyle='--', alpha=0.6)
ax.legend()
fig.autofmt_xdate()
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))

plt.tight_layout()
plt.show()

logging.info(f"✅ Zigzag trendline plot generated.")

# End of Cell 9 (Revised - Zigzag Trendlines)


# In[ ]:


# Cell 10 (Corrected): Plan BUY Orders based on Support Zones - Check globals()

import pandas as pd
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import logging
import math

# --- Prerequisites ---
if 'historical_data' not in locals() or historical_data.empty: raise RuntimeError("Run Cell 1")
if 'support_zones_df' not in locals(): raise RuntimeError("Run Cell 4 for support zones")
# *** MODIFIED: Check globals() instead of locals() ***
if not all(v in globals() for v in ['price_tick_size_bt', 'min_qty_bt', 'qty_step_size_bt', 'min_notional_bt']):
    raise RuntimeError("Filters/helpers not found in global scope. Run Cell 8.1 again.")

# --- Configuration ---
PLANNING_BUDGET_SIM = Decimal('500.0') # Example simulated budget
NUM_ORDERS_TO_PLAN = 5 # Target number of buy levels
TARGET_PRICE_IN_ZONE = 'zone_max_price' # Options: 'zone_min_price', 'zone_max_price', 'zone_mid'
QTY_SCALE_FACTOR_BT = Decimal('1.2') # Geometric scaling factor (same as backtester)
MIN_QTY_VALUE_MULTIPLE_BT = Decimal('1.01') # Buffer for base target value
QUOTE_ASSET = 'USDT' # Make sure this is defined

logging.info(f"--- Planning {NUM_ORDERS_TO_PLAN} BUY Orders for {SYMBOL} using Support Zones ---")
logging.info(f"Simulated Budget: {PLANNING_BUDGET_SIM:.2f} {QUOTE_ASSET}")
logging.info(f"Targeting '{TARGET_PRICE_IN_ZONE}' within zones.")

# --- Get Current Price ---
if historical_data.empty: raise ValueError("Historical data is empty")
current_price = historical_data['Close'].iloc[-1]
logging.info(f"Using last close price as 'current': {current_price:.4f} {QUOTE_ASSET}")

# --- Identify Relevant Support Zones ---
relevant_zones = support_zones_df[support_zones_df['zone_max_price'] < current_price].copy()
if relevant_zones.empty:
    logging.warning("No support zones found below the current price. No orders planned.")
    planned_buy_orders = []
else:
    # Sort by price descending (closest zones first) and take top N
    relevant_zones = relevant_zones.sort_values(by='zone_max_price', ascending=False)
    target_zones = relevant_zones.head(NUM_ORDERS_TO_PLAN).copy()
    if len(target_zones) < NUM_ORDERS_TO_PLAN:
        logging.warning(f"Found only {len(target_zones)} support zones below current price, planning for {len(target_zones)} levels.")
    target_zones = target_zones.sort_values(by='zone_max_price', ascending=True) # Sort deepest first for scaling calc later
    target_zones.reset_index(inplace=True) # Reset index for easy iteration by level
    num_actual_levels = len(target_zones)

    logging.info(f"Targeting {num_actual_levels} zones/levels below current price:")
    for idx, row in target_zones.iterrows():
        logging.info(f"  Level {idx+1} (Deepest={idx==0}): Zone {row['zone_min_price']:.4f}-{row['zone_max_price']:.4f} ({row['num_points']} pts)")

    # --- Calculate Base Target Value ---
    closest_zone_price_target = target_zones[TARGET_PRICE_IN_ZONE].iloc[-1] # Price target in the highest (closest) zone
    min_value_from_qty = min_qty_bt * closest_zone_price_target
    base_target_quote_value = max(min_value_from_qty, min_notional_bt) * MIN_QTY_VALUE_MULTIPLE_BT
    logging.info(f"Calculated Base Target Quote Value (for scaling): {base_target_quote_value:.4f}")

    # --- Plan Orders Iteratively (Deepest First for Budget Check) ---
    planned_buy_orders = []
    remaining_budget = PLANNING_BUDGET_SIM
    temp_plan_cost = Decimal('0')

    for i in range(num_actual_levels):
        zone_row = target_zones.iloc[i] # Deepest zones first due to sorting
        order_level_display = i + 1 # Level 1 is deepest

        raw_target_price = zone_row[TARGET_PRICE_IN_ZONE]
        adjusted_target_price = adjust_price_bt(raw_target_price, price_tick_size_bt)

        if adjusted_target_price is None or adjusted_target_price <= 0:
            logging.warning(f"  Level {order_level_display}: Invalid adjusted price {adjusted_target_price}. Skipping.")
            continue

        # Calculate target quote value using geometric scaling (deepest gets highest scale)
        scale_exponent = i
        target_quote_value = base_target_quote_value * (QTY_SCALE_FACTOR_BT ** scale_exponent)

        # Calculate and adjust quantity
        raw_order_qty = target_quote_value / adjusted_target_price if adjusted_target_price > 0 else Decimal('0')
        adjusted_order_qty = adjust_qty_bt(raw_order_qty, min_qty_bt, qty_step_size_bt)

        if adjusted_order_qty <= 0:
            logging.warning(f"  Level {order_level_display}: Adjusted quantity {adjusted_order_qty} is zero. Skipping (RawQty={raw_order_qty:.8f}, TargetVal={target_quote_value:.4f}).")
            continue

        # Calculate notional value and check filters/budget
        notional_value = adjusted_target_price * adjusted_order_qty
        if notional_value < min_notional_bt:
             logging.warning(f"  Level {order_level_display}: Notional {notional_value:.4f} < MinNotional {min_notional_bt:.4f}. Skipping.")
             continue

        if (remaining_budget - temp_plan_cost) < notional_value:
            logging.warning(f"  Level {order_level_display}: Cost {notional_value:.4f} > Remaining Budget ({remaining_budget - temp_plan_cost:.4f}). Stopping plan.")
            break # Stop planning if budget exceeded

        # Add to potential plan
        planned_buy_orders.append({
            "symbol": SYMBOL,
            "level": order_level_display, # 1 = deepest
            "zone_min": zone_row['zone_min_price'],
            "zone_max": zone_row['zone_max_price'],
            "price_target": adjusted_target_price,
            "qty_target": adjusted_order_qty,
            "notional_target": notional_value
        })
        temp_plan_cost += notional_value
        logging.info(f"  Level {order_level_display}: Planned BUY {adjusted_order_qty:.8f} @ {adjusted_target_price:.4f}, Cost: {notional_value:.4f}")

    # Final budget update
    remaining_budget -= temp_plan_cost
    logging.info(f"Planning complete. Total cost: {temp_plan_cost:.4f}, Remaining budget: {remaining_budget:.4f}")


# --- Display Final Plan ---
print(f"\n--- Final BUY Order Plan ({len(planned_buy_orders)} Orders) ---")
if planned_buy_orders:
    plan_df = pd.DataFrame(planned_buy_orders)
    # Reorder levels for display (1=closest)
    plan_df['display_level'] = plan_df['level'].rank(method='dense', ascending=False).astype(int)
    plan_df = plan_df.sort_values('display_level')
    # Format Decimals for printing
    for col in ['zone_min', 'zone_max', 'price_target', 'qty_target', 'notional_target']:
         prec = 8 if 'qty' in col else 4
         plan_df[col] = plan_df[col].apply(lambda d: f"{d:.{prec}f}")

    print(plan_df[['display_level', 'zone_min', 'zone_max', 'price_target', 'qty_target', 'notional_target']].to_string(index=False))
else:
    print("No BUY orders were planned.")

# End of Cell 9 (Corrected)


# In[ ]:


# Cell 11: Plan Take Profit SELL Order based on Resistance Zones

import pandas as pd
from decimal import Decimal, ROUND_UP # Need ROUND_UP for TP price adjustment
import logging
import math

# --- Prerequisites ---
if 'resistance_zones_df' not in locals(): raise RuntimeError("Run Cell 6 for resistance zones")
if 'planned_buy_orders' not in locals(): raise RuntimeError("Run Cell 9 to generate a buy plan")
if not all(v in globals() for v in ['price_tick_size_bt', 'min_qty_bt', 'qty_step_size_bt', 'min_notional_bt']):
    raise RuntimeError("Run Cell 8.1 for filters and helpers")

# --- Configuration ---
TARGET_PRICE_IN_RES_ZONE = 'zone_min_price' # Target the bottom edge for TP

logging.info(f"--- Planning Take Profit SELL based on Resistance Zones ---")

# --- Simulate a Buy Fill ---
# Let's assume the closest planned buy order (highest price) filled
if not planned_buy_orders:
    logging.warning("No planned buy orders from Cell 9 to simulate a fill from. Skipping TP planning.")
    planned_tp_sell_order = None
else:
    # Get the details of the highest priced buy order planned in Cell 9
    # Note: 'planned_buy_orders' is sorted deepest=level 1, closest=last element
    simulated_fill = planned_buy_orders[-1] # Get the last element (closest/highest price)
    simulated_fill_price = simulated_fill['price_target']
    simulated_fill_qty = simulated_fill['qty_target']
    logging.info(f"Simulating fill of BUY Level {simulated_fill['level']} (Closest): Qty={simulated_fill_qty:.8f} @ Price={simulated_fill_price:.4f}")

    # --- Identify Relevant Resistance Zones ---
    relevant_res_zones = resistance_zones_df[resistance_zones_df['zone_min_price'] > simulated_fill_price].copy()
    if relevant_res_zones.empty:
        logging.warning(f"No resistance zones found above the simulated fill price ({simulated_fill_price:.4f}). Cannot plan TP.")
        planned_tp_sell_order = None
    else:
        # Sort by price ascending (closest resistance zone first)
        relevant_res_zones = relevant_res_zones.sort_values(by='zone_min_price', ascending=True)
        target_res_zone = relevant_res_zones.iloc[0] # Take the first one (closest above fill price)

        logging.info(f"Targeting closest resistance zone: {target_res_zone['zone_min_price']:.4f}-{target_res_zone['zone_max_price']:.4f} ({target_res_zone['num_points']} pts)")

        # --- Calculate and Adjust TP Price ---
        # Helper for TP price adjustment (adjust UP)
        def adjust_tp_price_bt(price, tick_size):
            """ Adjusts TP price UP to the nearest tick size multiple. """
            try:
                if not (isinstance(price, Decimal) and isinstance(tick_size, Decimal) and tick_size > 0): return None
                ticks = price / tick_size; adjusted_ticks = ticks.to_integral_value(rounding=ROUND_UP); return adjusted_ticks * tick_size
            except Exception: return None

        raw_tp_price = target_res_zone[TARGET_PRICE_IN_RES_ZONE]
        adjusted_tp_price = adjust_tp_price_bt(raw_tp_price, price_tick_size_bt) # Adjust UP

        if adjusted_tp_price is None or adjusted_tp_price <= simulated_fill_price:
             logging.warning(f"Invalid adjusted TP price ({adjusted_tp_price}) or not above fill price. Cannot plan TP.")
             planned_tp_sell_order = None
        else:
            # --- Adjust Quantity ---
            # Sell the quantity that was filled
            adjusted_sell_qty = adjust_qty_bt(simulated_fill_qty, min_qty_bt, qty_step_size_bt)

            if adjusted_sell_qty <= 0:
                logging.warning(f"Adjusted SELL quantity ({adjusted_sell_qty}) is zero. Cannot plan TP.")
                planned_tp_sell_order = None
            else:
                 # --- Validate Notional ---
                tp_notional_value = adjusted_tp_price * adjusted_sell_qty
                if tp_notional_value < min_notional_bt:
                    logging.warning(f"Planned TP SELL Notional ({tp_notional_value:.4f}) < MinNotional ({min_notional_bt:.4f}). TP Order would fail.")
                    planned_tp_sell_order = None # Don't plan if it's guaranteed to fail filter
                else:
                    planned_tp_sell_order = {
                        "symbol": SYMBOL,
                        "type": "SELL_TP",
                        "buy_fill_price": simulated_fill_price,
                        "buy_fill_qty": simulated_fill_qty,
                        "target_res_zone_min": target_res_zone['zone_min_price'],
                        "target_res_zone_max": target_res_zone['zone_max_price'],
                        "tp_price_target": adjusted_tp_price,
                        "tp_qty_target": adjusted_sell_qty,
                        "tp_notional_target": tp_notional_value
                    }
                    logging.info(f"Successfully planned TP SELL order: Sell {adjusted_sell_qty:.8f} @ {adjusted_tp_price:.4f}")


# --- Display Final TP Plan ---
print(f"\n--- Final Take Profit SELL Order Plan (Based on simulated fill) ---")
if planned_tp_sell_order:
    # Format Decimals for printing
    tp_plan_series = pd.Series(planned_tp_sell_order)
    for col in tp_plan_series.index:
        val = tp_plan_series[col]
        if isinstance(val, Decimal):
             prec = 8 if 'qty' in col else 4
             tp_plan_series[col] = f"{val:.{prec}f}"
    print(tp_plan_series)

else:
    print("No Take Profit SELL order was planned.")


# End of Cell 10


# In[ ]:


# Cell X (Originally Cell 12, v9.0 - PL Filtered Dyn S/R Entry, Scaled PL% TP, Grid Abandon): Backtesting Engine
# Ensure this code is placed in the correct sequence after its dependencies (Cells 1, 3, 2, 4, 5)

import pandas as pd
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation, getcontext
import logging
import math
import sys
import numpy as np
from datetime import datetime, timezone, timedelta
from tqdm.notebook import tqdm # Progress bar
# pandas_ta might be needed if ATR is used anywhere, kept for safety
try:
    import pandas_ta as ta
except ImportError:
    logging.warning("pandas_ta not found, ATR features might fail if used.")


# --- Prerequisites ---\
# Ensure these are available from preceding cells (using the new numbering)
if 'historical_data_test' not in locals() or historical_data_test.empty: raise RuntimeError("Run Cell 2 for historical_data_test")
if 'data_for_sr_calc' not in locals() or not isinstance(data_for_sr_calc, dict): raise RuntimeError("Run Cell 2 for data_for_sr_calc")
if not all(v in globals() for v in ['price_tick_size_bt', 'min_qty_bt', 'qty_step_size_bt', 'min_notional_bt', 'adjust_price_bt', 'adjust_qty_bt', 'adjust_tp_price_bt']): raise RuntimeError("Run Cell 3 for filters/helpers")
if 'SYMBOL' not in locals(): raise RuntimeError("Run Cell 1 for SYMBOL.")
if 'df_lines' not in locals() or df_lines.empty: raise RuntimeError("Run Cell 5 for df_lines (Power Law).")
if 'calculate_dynamic_zones' not in globals(): raise RuntimeError("Run Cell 4 for calculate_dynamic_zones function.")

# --- Configuration (from original Cell 12) ---
getcontext().prec = 18
logger = logging.getLogger(__name__)
# Ensure INFO level logging
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout, force=True)
logging.getLogger().setLevel(logging.INFO)

STARTING_QUOTE_BALANCE = Decimal('1000.0'); STARTING_BASE_BALANCE = Decimal('0.0')
NUM_ORDERS_PER_TF_LEVEL = 3
QTY_SCALE_FACTOR_BT = Decimal('1.2'); MIN_QTY_VALUE_MULTIPLE_BT = Decimal('1.01')
TARGET_PRICE_IN_SUP_ZONE = 'zone_max_price' # Target top of dynamic support zone
QUOTE_ASSET = 'USDT'; BASE_ASSET = SYMBOL.replace(QUOTE_ASSET, '')
FEE_RATE = Decimal('0.001'); ROLLING_WINDOW_FOR_SR = 500
N_PERIODS_SWING = 11 # Make sure this matches Cell 4 if modified
ZONE_THRESHOLD_PERCENT_SUP = Decimal('0.005')
ZONE_THRESHOLD_PERCENT_RES = Decimal('0.005')
ATR_PERIOD = 14 # Needed for Grid Abandonment (if used)

TF_SETTINGS = {
    '1h': {'replan_interval': 24, 'budget_alloc': Decimal('0.20'), 'num_orders': NUM_ORDERS_PER_TF_LEVEL},
    '4h': {'replan_interval': 24*3, 'budget_alloc': Decimal('0.30'), 'num_orders': NUM_ORDERS_PER_TF_LEVEL},
    '1d': {'replan_interval': 24*7, 'budget_alloc': Decimal('0.50'), 'num_orders': NUM_ORDERS_PER_TF_LEVEL}
}
total_alloc = sum(v['budget_alloc'] for v in TF_SETTINGS.values())
if total_alloc != Decimal('1.0'): logging.warning(f"Budget allocations sum to {total_alloc}, not 1.0!")

# --- Grid Abandonment Config ---
ABANDON_ATR_MULT = Decimal('3.0') # Abandon grid if price > highest_bid + 3*ATR
BUFFER_BELOW_PL = Decimal('0.001') # Allow dynamic zones slightly (0.1%) below PL Support

# --- TP Config: Scaled Percentage levels within the PL Channel ---
TP_INITIAL_TARGET_PCT = {'1h': Decimal('0.25'), '4h': Decimal('0.50'), '1d': Decimal('0.75')}
TP_FALLBACK_PERCENTAGES = [Decimal('0.25'), Decimal('0.50'), Decimal('0.75'), Decimal('1.00')]
TP_MIN_PROFIT_PERCENT = Decimal('0.005')

logging.info(f"--- Starting Backtest Simulation v9.0 for {SYMBOL} (PL Filtered Dyn S/R Entry, Scaled PL% TP, Grid Abandon) ---") # v9.0
logging.info(f"Exit: Scaled PL Channel % Target (Initial: {TP_INITIAL_TARGET_PCT}, Min Profit: {TP_MIN_PROFIT_PERCENT*100}%)\")")
logging.info(f"Entry: Multi-TF Dynamic S/R Zones[{ROLLING_WINDOW_FOR_SR}] filtered by PL Support (floor buffer {BUFFER_BELOW_PL*100:.1f}%). Replan: { {tf: s['replan_interval'] for tf, s in TF_SETTINGS.items()} }\")")
logging.info(f"Grid Abandonment: Enabled for 1h, 4h (Threshold: Price > Highest Bid + {ABANDON_ATR_MULT} * ATR)\")")

# --- Simulation State Initialization ---\
quote_balance = STARTING_QUOTE_BALANCE; base_balance = STARTING_BASE_BALANCE
open_buy_orders = {'1h': [], '4h': [], '1d': []}; open_sell_orders = []
trade_log = []; portfolio_history = []
total_fees_paid = Decimal('0.0')
position_open = False; position_entry_price = None; position_qty = Decimal('0'); position_entry_tf = None
last_replan_candle = {'1h': 0, '4h': 0, '1d': 0}
current_zones = {'1h': {'support': pd.DataFrame(), 'resistance': pd.DataFrame()}, '4h': {'support': pd.DataFrame(), 'resistance': pd.DataFrame()}, '1d': {'support': pd.DataFrame(), 'resistance': pd.DataFrame()}}
abandon_counts = {'1h': 0, '4h': 0} # Counter for abandoned grids

# --- HODL Calculation Setup ---\
initial_hodl_price = historical_data_test['Close'].iloc[0]
hodl_base_qty = (STARTING_QUOTE_BALANCE / initial_hodl_price) if initial_hodl_price > 0 else Decimal('0')
hodl_portfolio_history = []
logging.info(f"Initial HODL Buy (adjusted): {hodl_base_qty:.8f} {BASE_ASSET} @ {initial_hodl_price:.2f}")

# --- Power Law Access ---
# Make df_lines index timezone-aware if needed (should be done in Cell 5)
if df_lines.index.tz is None: df_lines.index = df_lines.index.tz_localize('UTC')
elif df_lines.index.tz != timezone.utc: df_lines.index = df_lines.index.tz_convert('UTC')
power_law_support = df_lines['Support']
power_law_resistance = df_lines['Resistance']

# --- Simulation Loop ---\
logging.info(f"Starting simulation loop v9.0 through {len(historical_data_test)} candles...")
candle_count = 0

for timestamp, candle_data in tqdm(historical_data_test.iterrows(), total=len(historical_data_test), desc="MTF Backtest (v9.0 Dyn S/R)"):
    candle_count += 1
    current_high = candle_data['High']; current_low = candle_data['Low']; current_close = candle_data['Close']
    timestamp_utc = timestamp

    # --- 0. Check for Replan Intervals & Calculate Dynamic Zones ---\
    should_plan_grid = {}
    for tf, settings in TF_SETTINGS.items():
        if candle_count == 1 or (candle_count - last_replan_candle[tf]) >= settings['replan_interval']:
            tf_df = data_for_sr_calc.get(tf) # Use .get() for safety
            if tf_df is None or tf_df.empty:
                 logger.warning(f"No data found in data_for_sr_calc for TF {tf} @ {timestamp_utc}. Skipping zone recalc.")
                 current_zones[tf]['support'], current_zones[tf]['resistance'] = pd.DataFrame(), pd.DataFrame()
                 continue # Skip this TF if data is missing

            try:
                 # Find the index in the specific TF dataframe corresponding to the current backtest timestamp
                 end_ts_for_slice = tf_df.index.asof(timestamp_utc)
                 if pd.isna(end_ts_for_slice):
                     # If exact timestamp not found, try finding the closest preceding one
                     try:
                         loc = tf_df.index.get_loc(timestamp_utc, method='ffill')
                         end_ts_for_slice = tf_df.index[loc]
                         logger.debug(f"Using ffill timestamp {end_ts_for_slice} for {tf} data slice @ {timestamp_utc}")
                     except KeyError:
                          raise KeyError(f"TS {timestamp_utc} not found in {tf} index (asof/ffill).")

                 idx_loc_in_tf = tf_df.index.get_loc(end_ts_for_slice)
                 data_end_index_tf = idx_loc_in_tf + 1
                 data_start_index_tf = max(0, data_end_index_tf - ROLLING_WINDOW_FOR_SR)
                 data_slice_tf = tf_df.iloc[data_start_index_tf:data_end_index_tf]

                 if len(data_slice_tf) >= N_PERIODS_SWING:
                     # Ensure data has correct types before calculating zones
                     if not all(dtype == 'object' or np.issubdtype(dtype, np.number) for dtype in data_slice_tf[['High', 'Low']].dtypes):
                         data_slice_tf = data_slice_tf.copy() # Avoid SettingWithCopyWarning
                         for col in ['High', 'Low']:
                            data_slice_tf[col] = data_slice_tf[col].apply(lambda x: Decimal(str(x)) if not isinstance(x, Decimal) else x)

                     sup_zones, res_zones = calculate_dynamic_zones(data_slice_tf, N_PERIODS_SWING, ZONE_THRESHOLD_PERCENT_SUP, ZONE_THRESHOLD_PERCENT_RES)
                     current_zones[tf]['support'] = sup_zones; current_zones[tf]['resistance'] = res_zones
                     logger.debug(f"Recalculated {tf} zones @ {timestamp_utc}: {len(sup_zones)} support, {len(res_zones)} resistance.")
                 else:
                     current_zones[tf]['support'], current_zones[tf]['resistance'] = pd.DataFrame(), pd.DataFrame()
                     logger.debug(f"Not enough data ({len(data_slice_tf)}<{N_PERIODS_SWING}) for {tf} zones @ {timestamp_utc}")

            except KeyError as ke: logger.warning(f"TS {timestamp_utc} align error in {tf} ({ke}), skipping zone recalc."); current_zones[tf]['support'], current_zones[tf]['resistance'] = pd.DataFrame(), pd.DataFrame()
            except Exception as e_sr: logger.error(f"Error calc {tf} zones @ {timestamp_utc}: {e_sr}"); current_zones[tf]['support'], current_zones[tf]['resistance'] = pd.DataFrame(), pd.DataFrame()

            if not position_open: should_plan_grid[tf] = True # Only flag for planning if not in position
            last_replan_candle[tf] = candle_count

    # --- Grid Abandonment Check (using ATR) ---\
    if not position_open:
        for tf in ['1h', '4h']:
            if open_buy_orders[tf]:
                highest_bid_price = max(order['price'] for order in open_buy_orders[tf])
                atr_col_suffix = '' if tf == '1h' else f'_{tf}'
                atr_col = f'ATR_{ATR_PERIOD}{atr_col_suffix}'
                current_atr = candle_data.get(atr_col, None)

                if current_atr and isinstance(current_atr, Decimal) and current_atr > 0:
                    abandon_threshold = highest_bid_price + (ABANDON_ATR_MULT * current_atr)
                    if current_close > abandon_threshold:
                        logging.info(f"[{timestamp_utc}] Abandoning stale {tf} grid. Price {current_close:.2f} > threshold {abandon_threshold:.2f}")
                        open_buy_orders[tf] = []
                        should_plan_grid[tf] = True # Allow replan
                        abandon_counts[tf] += 1
                # else: logger.debug(f"Cannot check {tf} grid abandonment @ {timestamp_utc}: Invalid ATR {current_atr}")


    # --- 1. Check Fills SELL (Scaled PL Channel % TP) ---\
    if position_open and open_sell_orders:
        sell_order = open_sell_orders[0]
        if current_high >= sell_order['price']:
            fill_price = sell_order['price']; fill_qty = sell_order['qty']
            # Ensure we don't sell more than we have (rounding errors)
            fill_qty = min(fill_qty, base_balance)
            if fill_qty <= 0: # If base balance is zero or negative somehow
                logger.warning(f"[{timestamp_utc}] Attempted SELL TP fill with zero/negative qty. Resetting position.")
                position_open = False; position_entry_price = None; position_qty = Decimal('0'); position_entry_tf = None; open_sell_orders = []; base_balance = Decimal('0')
            else:
                gross_proceeds = fill_price * fill_qty; fee = gross_proceeds * FEE_RATE
                net_proceeds = gross_proceeds - fee; total_fees_paid += fee
                quote_balance += net_proceeds; base_balance -= fill_qty # Should bring base near zero
                trade_log.append({'timestamp': timestamp_utc, 'type': f"SELL_SCALED_PL_TP_{sell_order['entry_tf']}", 'price': fill_price, 'qty': fill_qty, 'value': net_proceeds, 'fee': fee, 'buy_fill_price': sell_order['buy_fill_price'], 'tp_level_pct': sell_order.get('tp_level_pct')})
                logging.info(f"[{timestamp_utc}] +++ SELL_SCALED_PL_TP Filled ({sell_order['entry_tf']} @ {sell_order['buy_fill_price']:.2f}) TP @ {fill_price:.2f} Qty {fill_qty:.8f} +++")
                position_open = False; position_entry_price = None; position_qty = Decimal('0'); position_entry_tf = None
                open_sell_orders = []
                base_balance = max(Decimal('0'), base_balance) # Ensure base doesn't go negative due to rounding
                # Flag all TFs for potential replan after exiting position
                for tf_replan in TF_SETTINGS.keys(): should_plan_grid[tf_replan] = True
                last_replan_candle = {tf_replan: candle_count for tf_replan in TF_SETTINGS.keys()}


    # --- 2. Check Fills BUY ---
    if not position_open:
        all_potential_buys = []
        for tf_key, buy_list in open_buy_orders.items():
             for order in buy_list: all_potential_buys.append({**order, 'tf': tf_key})
        # Sort all potential buys across all TFs by price (highest first)
        all_potential_buys.sort(key=lambda x: x['price'], reverse=True)

        for i, buy_order in enumerate(all_potential_buys):
             if current_low <= buy_order['price']:
                 fill_price = buy_order['price']; fill_qty = buy_order['qty']; cost = buy_order['notional']; fee = cost * FEE_RATE; total_cost_with_fee = cost + fee
                 if quote_balance >= total_cost_with_fee:
                     total_fees_paid += fee; quote_balance -= total_cost_with_fee; base_balance += fill_qty
                     trade_log.append({'timestamp': timestamp_utc, 'type': f"BUY_{buy_order['tf']}", 'price': fill_price, 'qty': fill_qty, 'value': -cost, 'fee': fee, 'level': buy_order['level']})
                     logging.info(f"[{timestamp_utc}] +++ BUY Filled ({buy_order['tf']} Lvl {buy_order['level']}) @ {fill_price:.2f} Qty {fill_qty:.8f} +++")

                     # --- Enter Position ---
                     position_open = True; position_entry_price = fill_price; position_qty = fill_qty; position_entry_tf = buy_order['tf']
                     open_buy_orders = {'1h': [], '4h': [], '1d': []} # Clear ALL Buy orders from all TFs
                     open_sell_orders = [] # Clear any previous TP attempts

                     # --- Plan Scaled PL Channel % TP ---
                     try:
                         pl_s_raw = Decimal(str(power_law_support.asof(timestamp_utc)))
                         pl_r_raw = Decimal(str(power_law_resistance.asof(timestamp_utc)))
                         if pl_s_raw and pl_r_raw and pl_s_raw > 0 and pl_r_raw > pl_s_raw:
                             log_pl_s = pl_s_raw.ln(); log_pl_r = pl_r_raw.ln(); log_channel_height = log_pl_r - log_pl_s
                             if log_channel_height <= 0: raise ValueError("Log channel height non-positive for TP calc.")

                             min_tp_target_price = position_entry_price * (Decimal('1.0') + TP_MIN_PROFIT_PERCENT)
                             chosen_tp_price = None; chosen_tp_pct = None
                             # Determine starting TP level based on entry TF
                             initial_target_pct = TP_INITIAL_TARGET_PCT.get(position_entry_tf, TP_FALLBACK_PERCENTAGES[0])
                             try: start_index = TP_FALLBACK_PERCENTAGES.index(initial_target_pct)
                             except ValueError: start_index = 0

                             # Iterate through potential TP levels starting from the initial target
                             for tp_pct in TP_FALLBACK_PERCENTAGES[start_index:]:
                                 raw_tp_price = Decimal(math.exp(float(log_pl_s + tp_pct * log_channel_height)))
                                 # Check if this level is sufficiently above the entry price
                                 if raw_tp_price > min_tp_target_price:
                                     chosen_tp_price = raw_tp_price
                                     chosen_tp_pct = tp_pct
                                     break # Use the first valid level found

                             if chosen_tp_price:
                                 adjusted_tp_price = adjust_tp_price_bt(chosen_tp_price, price_tick_size_bt)
                                 # Final check: Ensure adjusted TP is still above entry price
                                 if adjusted_tp_price and adjusted_tp_price > position_entry_price:
                                     adjusted_sell_qty = adjust_qty_bt(position_qty, min_qty_bt, qty_step_size_bt)
                                     # Ensure sell qty > 0 (handles case where position_qty was below min_qty)
                                     if adjusted_sell_qty > 0:
                                         tp_notional_value = adjusted_tp_price * adjusted_sell_qty
                                         if tp_notional_value >= min_notional_bt:
                                             open_sell_orders = [{'price': adjusted_tp_price, 'qty': adjusted_sell_qty,'buy_fill_price': position_entry_price, 'entry_tf': position_entry_tf,'tp_level_pct': chosen_tp_pct}]
                                             logging.info(f"  Scaled PL % TP Placed ({position_entry_tf}): Target Lvl {chosen_tp_pct*100:.0f}%, Sell {adjusted_sell_qty:.8f} @ {adjusted_tp_price:.4f}")
                                         else: logger.warning(f"  TP Notional {tp_notional_value:.4f} < MinNotional {min_notional_bt}. TP order invalid.")
                                     else: logger.warning(f"  Adjusted TP Sell Qty is zero ({position_qty=}). Cannot place TP.")
                                 else: logger.warning(f"  Adjusted TP price {adjusted_tp_price} not valid or not above entry {position_entry_price}. No TP placed.")
                             else: logger.warning(f"  No suitable PL Channel TP level found above min profit threshold {min_tp_target_price:.4f}. No TP placed.")
                         else: logger.warning(f"  Invalid PL bounds for TP calc: S={pl_s_raw}, R={pl_r_raw}. No TP placed.")
                     except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError) as pl_tp_err:
                         logger.error(f"  Error calculating/placing Scaled PL % TP @ {timestamp_utc}: {pl_tp_err}. No TP placed.")

                     # Break from buy order check loop once a position is entered
                     break
                 # else: logger.debug(f"[{timestamp_utc}] BUY Fill Skipped (Insufficient Quote {quote_balance:.2f} < {total_cost_with_fee:.2f}) @ {buy_order['price']:.2f}")


    # --- 3. Plan New BUY Grids (Using Dynamic S/R Zones filtered by PL Support) ---\
    if not position_open: # Only plan if not already in a position
        for tf, settings in TF_SETTINGS.items():
             if should_plan_grid.get(tf, False): # Check if flagged for replan
                 open_buy_orders[tf] = [] # Clear previous orders for this TF
                 tf_budget = quote_balance * settings['budget_alloc'] # Allocate budget dynamically
                 tf_planned_orders = []
                 temp_plan_cost = Decimal('0')
                 num_to_place = settings['num_orders']
                 # Calculate base target value considering min qty/notional at current price
                 min_value_from_qty = min_qty_bt * current_close
                 base_target_quote_value = max(min_value_from_qty, min_notional_bt) * MIN_QTY_VALUE_MULTIPLE_BT

                 try:
                     pl_support_now = Decimal(str(power_law_support.asof(timestamp_utc)))
                     price_floor = pl_support_now * (Decimal('1.0') - BUFFER_BELOW_PL)
                 except (KeyError, TypeError, ValueError, InvalidOperation) as pl_err:
                     logger.warning(f"  Could not get PL Support for {tf} grid filter @ {timestamp_utc}: {pl_err}. Using 0.")
                     price_floor = Decimal('0')

                 tf_support_zones = current_zones[tf]['support']
                 if not tf_support_zones.empty:
                     relevant_zones = tf_support_zones[
                         (tf_support_zones['zone_max_price'] < current_close) &
                         (tf_support_zones['zone_min_price'] >= price_floor) # Filter above PL floor
                     ].copy()

                     if not relevant_zones.empty:
                         # Sort closest first, take N, then sort deepest first for scaling calc
                         target_zones = relevant_zones.sort_values(by='zone_max_price', ascending=False).head(num_to_place).sort_values(by='zone_max_price', ascending=True)
                         target_zones.reset_index(inplace=True); num_actual_levels = len(target_zones)

                         if num_actual_levels > 0:
                             # Recalculate base target based on the *closest filtered* zone's target price
                             closest_filtered_zone_price_target = target_zones[TARGET_PRICE_IN_SUP_ZONE].iloc[-1]
                             min_value_from_qty_filtered = min_qty_bt * closest_filtered_zone_price_target
                             base_target_quote_value = max(min_value_from_qty_filtered, min_notional_bt) * MIN_QTY_VALUE_MULTIPLE_BT
                             logger.debug(f"  Recalculated base target value for {tf}: {base_target_quote_value:.4f}")

                             for i in range(num_actual_levels):
                                 zone_row = target_zones.iloc[i]; order_level_display = i + 1 # Level 1 = deepest
                                 raw_target_price = zone_row[TARGET_PRICE_IN_SUP_ZONE]
                                 adjusted_target_price = adjust_price_bt(raw_target_price, price_tick_size_bt)
                                 if adjusted_target_price and adjusted_target_price > 0:
                                     # Geometric scaling (deepest gets highest scale)
                                     scale_exponent = i; target_quote_value = base_target_quote_value * (QTY_SCALE_FACTOR_BT ** scale_exponent)
                                     raw_order_qty = target_quote_value / adjusted_target_price; adjusted_order_qty = adjust_qty_bt(raw_order_qty, min_qty_bt, qty_step_size_bt)
                                     if adjusted_order_qty > 0:
                                         notional_value = adjusted_target_price * adjusted_order_qty
                                         if notional_value >= min_notional_bt:
                                             # Check against dynamic TF budget
                                             if (tf_budget - temp_plan_cost) >= notional_value:
                                                 tf_planned_orders.append({"price": adjusted_target_price, "qty": adjusted_order_qty, "notional": notional_value, "level": order_level_display})
                                                 temp_plan_cost += notional_value
                                                 logger.debug(f"  Planned BUY ({tf} Lvl {order_level_display}): Qty {adjusted_order_qty:.8f} @ {adjusted_target_price:.4f}, Cost: {notional_value:.4f}")
                                             else:
                                                logger.debug(f"  Budget Exceeded for {tf} @ Lvl {order_level_display}. Stop planning for TF.")
                                                break # Stop planning for this TF if budget exceeded
                                         # else: logger.debug(f"  {tf} Lvl {order_level_display} Notional {notional_value:.4f} < Min {min_notional_bt}. Skip.")
                                     # else: logger.debug(f"  {tf} Lvl {order_level_display} Adjusted Qty is zero. Skip.")
                                 # else: logger.debug(f"  {tf} Lvl {order_level_display} Adjusted Price invalid. Skip.")
                             # Add planned orders for this TF to the main list
                             open_buy_orders[tf] = tf_planned_orders
                             logger.info(f"  Planned {len(tf_planned_orders)} BUY orders for {tf}. Total cost: {temp_plan_cost:.4f}/{tf_budget:.4f}")
                         # else: logger.debug(f"  No dynamic zones survived filtering for {tf} @ {timestamp_utc}.")
                     # else: logger.debug(f"  No relevant dynamic zones calculated or found below price for {tf} @ {timestamp_utc}.")
                 # else: logger.debug(f"  No dynamic support zones available for {tf} @ {timestamp_utc}.")


    # --- 4. Record Values ---\
    current_portfolio_value = quote_balance + (base_balance * current_close)
    portfolio_history.append({'timestamp': timestamp_utc, 'portfolio_value': current_portfolio_value, 'quote': quote_balance, 'base': base_balance})
    current_hodl_value = hodl_base_qty * current_close
    hodl_portfolio_history.append({'timestamp': timestamp_utc, 'hodl_value': current_hodl_value})

# --- Loop End ---\
logging.info(f"--- Simulation Loop Finished ---")

# --- Final Portfolio Calculation & Performance Metrics ---\
final_quote_balance = quote_balance; final_base_balance = base_balance
last_close_price = historical_data_test['Close'].iloc[-1] if not historical_data_test.empty else Decimal('0')
final_portfolio_value = final_quote_balance + (final_base_balance * last_close_price)
final_hodl_value = hodl_base_qty * last_close_price

print("\n--- Backtest Results (v9.0 - PL Filtered Dyn S/R Entry, Scaled PL% TP, Grid Abandon) ---")
print(f"Simulation Period (Adjusted): {historical_data_test.index.min()} to {historical_data_test.index.max()}")
print(f"S/R Zone Window: Last {ROLLING_WINDOW_FOR_SR} candles")
print(f"TF Settings: {TF_SETTINGS}")
print(f"Entry Logic: Dynamic S/R Zones filtered by PL Support Floor (buffer {BUFFER_BELOW_PL*100:.1f}%). Replan: { {tf: s['replan_interval'] for tf, s in TF_SETTINGS.items()} }\")")
print(f"Grid Abandonment: Enabled for 1h, 4h (Threshold: {ABANDON_ATR_MULT} ATR)\")")
print(f"Exit: Scaled PL Channel % Target (Initial: {TP_INITIAL_TARGET_PCT}, Fallback: {TP_FALLBACK_PERCENTAGES}, Min Profit: {TP_MIN_PROFIT_PERCENT*100}%)\")")
print(f"Fee Rate Applied: {FEE_RATE*100}%\\n")
print(f"Initial Portfolio Value: {STARTING_QUOTE_BALANCE:.2f} {QUOTE_ASSET}")
print(f"Final Portfolio Value (Strategy): {final_portfolio_value:.2f} {QUOTE_ASSET}")
total_profit_loss = final_portfolio_value - STARTING_QUOTE_BALANCE; total_profit_loss_percent = (total_profit_loss / STARTING_QUOTE_BALANCE) * 100 if STARTING_QUOTE_BALANCE > 0 else Decimal('0')
print(f"Total Profit/Loss (Strategy): {total_profit_loss:.2f} {QUOTE_ASSET} ({total_profit_loss_percent:.2f}%)\"")
print(f"Final Portfolio Value (HODL): {final_hodl_value:.2f} {QUOTE_ASSET}")
hodl_profit_loss = final_hodl_value - STARTING_QUOTE_BALANCE; hodl_profit_loss_percent = (hodl_profit_loss / STARTING_QUOTE_BALANCE) * 100 if STARTING_QUOTE_BALANCE > 0 else Decimal('0')
print(f"Total Profit/Loss (HODL): {hodl_profit_loss:.2f} {QUOTE_ASSET} ({hodl_profit_loss_percent:.2f}%)\"")

trades_df = pd.DataFrame(trade_log)
print(f"\nTotal Trades Executed (Strategy): {len(trades_df)}")
total_buys = 0; total_sells = 0
for tf_key in TF_SETTINGS.keys():
    buys = trades_df[trades_df['type'] == f'BUY_{tf_key}'] if not trades_df.empty else pd.DataFrame()
    sells = trades_df[trades_df['type'] == f'SELL_SCALED_PL_TP_{tf_key}'] if not trades_df.empty else pd.DataFrame()
    total_buys += len(buys); total_sells += len(sells)
    print(f"  {tf_key} Entry Trades: {len(buys)} Buys, {len(sells)} Sells")
    if not sells.empty and 'buy_fill_price' in sells.columns:
       try:
           # Ensure comparison is between numeric types
           wins = sells[sells['price'].astype(float) > sells['buy_fill_price'].astype(float)]
           win_rate = (len(wins) / len(sells)) * 100 if len(sells) > 0 else 0
           print(f"    {tf_key} Scaled PL % TP Win Rate: {win_rate:.2f}% ({len(wins)} wins / {len(sells)} exits)")
       except Exception as e:
           print(f"    Error calculating win rate for {tf_key}: {e}")

print(f"\n  Total Buys: {total_buys}")
print(f"  Total Sells: {total_sells}")
print(f"Total Fees Paid (Strategy): {total_fees_paid:.4f} {QUOTE_ASSET}")
print(f"Grid Abandon Counts: {abandon_counts}")

# --- Plotting (Strategy vs HODL) ---\
try:
    import matplotlib.pyplot as plt
    portfolio_df = pd.DataFrame(portfolio_history).set_index('timestamp')
    hodl_df = pd.DataFrame(hodl_portfolio_history).set_index('timestamp')
    fig, ax1 = plt.subplots(figsize=(12, 6))
    color = 'tab:blue'; ax1.set_xlabel('Date'); ax1.set_ylabel('Portfolio Value (USDT)', color=color)
    strat_line, = ax1.plot(portfolio_df.index, portfolio_df['portfolio_value'].astype(float), color=color, linewidth=1.5, label='Strategy Value (v9.0)') # Updated label
    hodl_color = 'darkgrey'; hodl_line, = ax1.plot(hodl_df.index, hodl_df['hodl_value'].astype(float), color=hodl_color, linestyle='--', linewidth=1.0, label='HODL Value')
    ax1.tick_params(axis='y', labelcolor=color);
    min_val_strat = portfolio_df['portfolio_value'].astype(float).min() if not portfolio_df.empty else float(STARTING_QUOTE_BALANCE)
    max_val_strat = portfolio_df['portfolio_value'].astype(float).max() if not portfolio_df.empty else float(STARTING_QUOTE_BALANCE)
    min_val_hodl = hodl_df['hodl_value'].astype(float).min() if not hodl_df.empty else float(STARTING_QUOTE_BALANCE)
    max_val_hodl = hodl_df['hodl_value'].astype(float).max() if not hodl_df.empty else float(STARTING_QUOTE_BALANCE)
    min_val = min(min_val_strat, min_val_hodl); max_val = max(max_val_strat, max_val_hodl)
    ax1.set_ylim(bottom=min_val * 0.95 if min_val > 0 else -100, top=max_val * 1.05 if max_val > 0 else 1100)
    freq_str = getattr(historical_data_test.index, 'freqstr', None) or "Hourly"
    fig.suptitle(f'Backtest v9.0: PL Filtered Dyn S/R Entry + Scaled PL% TP + Abandon - {SYMBOL} ({freq_str})') # Updated title
    handles = [strat_line, hodl_line]; labels = [strat_line.get_label(), hodl_line.get_label()]; ax1.legend(handles, labels, loc='upper left')
    fig.tight_layout(rect=[0, 0.03, 1, 0.95]); plt.show()
except ImportError: logging.warning("matplotlib not installed. Skipping plot generation. `pip install matplotlib`")
except Exception as plot_err: logging.error(f"Error during plotting: {plot_err}")

# End of Cell (Originally Cell 12, v9.0)


# In[ ]:




