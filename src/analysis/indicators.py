# START OF FILE: src/analysis/indicators.py

import pandas as pd
import pandas_ta as ta  # Use pandas-ta for common indicators
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import logging
from typing import Optional  # Added for type hinting

# --- Setup Logger ---
logger = logging.getLogger(__name__)

# --- Constants ---
ATR_PERIOD = 14
SMA_SHORT_PERIOD = 10
SMA_LONG_PERIOD = 50
RSI_PERIOD = 14
MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9

# --- Helper for pandas-ta conversion ---


def _convert_to_float_df(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Converts specified columns to float for pandas-ta compatibility."""
    try:
        float_df = df[cols].copy()
        for col in cols:
            # Convert to numeric, coercing errors to NaN
            float_df[col] = pd.to_numeric(float_df[col], errors='coerce')
            # *** ADDED: Explicitly set dtype to float64 ***
            float_df[col] = float_df[col].astype('float64')
        # Check if all values in any required column became NaN after conversion
        if float_df.isnull().all().any():
            logger.warning(
                f"All values in one or more columns ({cols}) became NaN after conversion. Check input data.")
            # Return empty, as calculation is impossible
            return pd.DataFrame()
        return float_df
    except KeyError as e:
        logger.error(
            f"Required column missing for float conversion: {e}. Available columns: {list(df.columns)}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(
            f"Error converting columns {cols} to float: {e}", exc_info=True)
        return pd.DataFrame()


def _convert_series_to_decimal(series: pd.Series, precision: str = '1e-8') -> pd.Series:
    """Converts a pandas Series (likely float) back to Decimal."""
    if series is None or series.empty:
        return pd.Series(dtype=object, index=series.index if series is not None else None)
    try:
        quantizer = Decimal(precision)
        # Apply conversion, robustly handling None/NaN
        decimal_series = series.apply(
            lambda x: Decimal(str(x)).quantize(
                quantizer, rounding=ROUND_HALF_UP)
            if pd.notna(x) and isinstance(x, (int, float, str))
            else (Decimal(x).quantize(quantizer, rounding=ROUND_HALF_UP) if isinstance(x, Decimal)
                  else None)  # None for Decimal NaN
        )
        return decimal_series.astype(object)
    except (InvalidOperation, TypeError, ValueError) as e:
        logger.error(
            f"Error converting Series elements to Decimal: {e}", exc_info=True)
        return pd.Series(dtype=object, index=series.index)
    except Exception as e:
        logger.error(
            f"Unexpected error converting Series to Decimal: {e}", exc_info=True)
        return pd.Series(dtype=object, index=series.index)

# --- Indicator Functions ---


def calculate_atr(df: pd.DataFrame, length: int = ATR_PERIOD) -> pd.Series:
    """Calculates ATR using pandas-ta."""
    required_cols_case_insensitive = ['high', 'low', 'close']
    if df is None or df.empty:
        logger.warning("Input DataFrame is empty, cannot calculate ATR.")
        return pd.Series(dtype=object)

    col_map = {col.lower(): col for col in df.columns}
    original_case_cols = [col_map.get(req_col)
                          for req_col in required_cols_case_insensitive]

    if not all(original_case_cols):
        missing = [req for req, orig in zip(
            required_cols_case_insensitive, original_case_cols) if not orig]
        logger.error(
            f"DataFrame must contain {missing} columns (case-insensitive) for ATR.")
        return pd.Series(dtype=object)

    if length <= 0:
        logger.error("ATR length must be positive.")
        return pd.Series(dtype=object)
    if len(df) < length:
        logger.debug(f"ATR: Not enough data ({len(df)}<{length}).")
        return pd.Series(dtype=object, index=df.index)

    float_df = _convert_to_float_df(df, original_case_cols)
    if float_df.empty:
        logger.warning("ATR: Failed HLC float conversion.")
        return pd.Series(dtype=object, index=df.index)

    # *** ADDED: Drop rows with NaNs in necessary columns BEFORE calculating ***
    float_df.dropna(subset=original_case_cols, inplace=True)
    if len(float_df) < length:
        logger.debug(
            f"ATR: Not enough non-NaN data ({len(float_df)}<{length}).")
        return pd.Series(dtype=object, index=df.index)

    try:
        logger.debug(
            f"Calculating ATR with length {length} using pandas-ta...")
        # RENAME columns in the float copy to lowercase for pandas-ta
        # Assign standard lowercase names
        float_df.columns = required_cols_case_insensitive

        atr_series_float = float_df.ta.atr(length=length, append=False)

        if atr_series_float is None or atr_series_float.empty:
            logger.warning(
                f"pandas_ta.atr returned None/empty for length {length}.")
            return pd.Series(dtype=object, index=df.index)

        atr_series_decimal = _convert_series_to_decimal(atr_series_float)
        atr_series_decimal.name = f'ATR_{length}'
        logger.debug(f"Successfully calculated ATR_{length}.")
        # Reindex to the original DataFrame's index to include NaNs where calculation wasn't possible
        return atr_series_decimal.reindex(df.index)

    except AttributeError:
        logger.error("ATR: Check pandas-ta install/DataFrame.")
        return pd.Series(dtype=object, index=df.index)
    except Exception as e:
        logger.exception(f"ATR Error: {e}")
        return pd.Series(dtype=object, index=df.index)


def calculate_sma(df: pd.DataFrame, period: int, price_col: str = 'close') -> pd.Series:
    """Calculates SMA using pandas-ta."""
    if df is None or df.empty:
        logger.warning("SMA: Input DataFrame empty.")
        return pd.Series(dtype=object)

    price_col_lower = price_col.lower()
    col_map = {col.lower(): col for col in df.columns}
    original_price_col = col_map.get(price_col_lower)

    if not original_price_col:
        logger.warning(f"SMA: Price column '{price_col}' not found.")
        return pd.Series(dtype=object)
    if len(df) < period:
        logger.debug(f"SMA: Not enough data ({len(df)}<{period}).")
        return pd.Series(dtype=object, index=df.index)

    float_df = _convert_to_float_df(df, [original_price_col])
    if float_df.empty:
        logger.warning(f"SMA: Failed '{original_price_col}' float conversion.")
        return pd.Series(dtype=object, index=df.index)

    # *** ADDED: Drop NaNs from the specific price column BEFORE calculating ***
    float_df.dropna(subset=[original_price_col], inplace=True)
    if len(float_df) < period:
        logger.debug(
            f"SMA: Not enough non-NaN data ({len(float_df)}<{period}).")
        return pd.Series(dtype=object, index=df.index)

    try:
        logger.debug(
            f"Calculating SMA with period {period} using pandas-ta...")
        sma_series_float = float_df.ta.sma(
            close=original_price_col, length=period, append=False)

        if sma_series_float is None or sma_series_float.empty:
            logger.warning(
                f"pandas_ta.sma returned None/empty for period {period}.")
            return pd.Series(dtype=object, index=df.index)

        sma_series_decimal = _convert_series_to_decimal(sma_series_float)
        sma_series_decimal.name = f'SMA_{period}'
        logger.debug(f"Successfully calculated SMA_{period}.")
        return sma_series_decimal.reindex(df.index)  # Reindex to original

    except AttributeError:
        logger.error("SMA: Check pandas-ta install/DataFrame.")
        return pd.Series(dtype=object, index=df.index)
    except Exception as e:
        logger.error(
            f"SMA Error (period={period}, col='{price_col}'): {e}", exc_info=True)
        return pd.Series(dtype=object, index=df.index)


def calculate_rsi(df: pd.DataFrame, period: int = RSI_PERIOD, price_col: str = 'close') -> pd.Series:
    """Calculates RSI using pandas-ta."""
    if df is None or df.empty:
        logger.warning("RSI: Input DataFrame empty.")
        return pd.Series(dtype=object)

    price_col_lower = price_col.lower()
    col_map = {col.lower(): col for col in df.columns}
    original_price_col = col_map.get(price_col_lower)

    if not original_price_col:
        logger.warning(f"RSI: Price column '{price_col}' not found.")
        return pd.Series(dtype=object)
    if len(df) <= period:
        logger.debug(f"RSI: Not enough data ({len(df)}<={period}).")
        return pd.Series(dtype=object, index=df.index)

    float_df = _convert_to_float_df(df, [original_price_col])
    if float_df.empty:
        logger.warning(f"RSI: Failed '{original_price_col}' float conversion.")
        return pd.Series(dtype=object, index=df.index)

    # *** ADDED: Drop NaNs from the specific price column BEFORE calculating ***
    float_df.dropna(subset=[original_price_col], inplace=True)
    if len(float_df) <= period:
        logger.debug(
            f"RSI: Not enough non-NaN data ({len(float_df)}<={period}).")
        return pd.Series(dtype=object, index=df.index)

    try:
        logger.debug(
            f"Calculating RSI with period {period} using pandas-ta...")
        rsi_series_float = float_df.ta.rsi(
            close=original_price_col, length=period, append=False)

        if rsi_series_float is None or rsi_series_float.empty:
            logger.warning(
                f"pandas_ta.rsi returned None/empty for period {period}.")
            return pd.Series(dtype=object, index=df.index)

        rsi_series_decimal = _convert_series_to_decimal(
            rsi_series_float, precision='0.01')
        rsi_series_decimal.name = f'RSI_{period}'
        logger.debug(f"Successfully calculated RSI_{period}.")
        return rsi_series_decimal.reindex(df.index)  # Reindex to original

    except AttributeError:
        logger.error("RSI: Check pandas-ta install/DataFrame.")
        return pd.Series(dtype=object, index=df.index)
    except Exception as e:
        logger.error(
            f"RSI Error (period={period}, col='{price_col}'): {e}", exc_info=True)
        return pd.Series(dtype=object, index=df.index)


def calculate_macd(df: pd.DataFrame,
                   fast_period: int = MACD_FAST_PERIOD,
                   slow_period: int = MACD_SLOW_PERIOD,
                   signal_period: int = MACD_SIGNAL_PERIOD,
                   price_col: str = 'close') -> pd.DataFrame:
    """Calculates MACD using pandas-ta."""
    if df is None or df.empty:
        logger.warning("MACD: Input DataFrame empty.")
        return pd.DataFrame(dtype=object)

    price_col_lower = price_col.lower()
    col_map = {col.lower(): col for col in df.columns}
    original_price_col = col_map.get(price_col_lower)

    if not original_price_col:
        logger.warning(f"MACD: Price column '{price_col}' not found.")
        return pd.DataFrame(dtype=object)
    # MACD calculation (specifically EMA) technically only needs slow_period, but more helps convergence
    # A slightly safer minimum length estimate
    min_len = slow_period + signal_period
    if len(df) < min_len:
        logger.debug(f"MACD: Not enough data ({len(df)}<{min_len}).")
        return pd.DataFrame(dtype=object, index=df.index)

    float_df = _convert_to_float_df(df, [original_price_col])
    if float_df.empty:
        logger.warning(
            f"MACD: Failed '{original_price_col}' float conversion.")
        return pd.DataFrame(dtype=object, index=df.index)

    # *** ADDED: Drop NaNs from the specific price column BEFORE calculating ***
    float_df.dropna(subset=[original_price_col], inplace=True)
    if len(float_df) < min_len:
        logger.debug(
            f"MACD: Not enough non-NaN data ({len(float_df)}<{min_len}).")
        return pd.DataFrame(dtype=object, index=df.index)

    try:
        logger.debug(
            f"Calculating MACD ({fast_period},{slow_period},{signal_period}) using pandas-ta...")
        macd_df_float = float_df.ta.macd(
            close=original_price_col, fast=fast_period, slow=slow_period, signal=signal_period, append=False)

        if macd_df_float is None or macd_df_float.empty:
            logger.warning("pandas_ta.macd returned None/empty.")
            return pd.DataFrame(dtype=object, index=df.index)

        macd_df_decimal = pd.DataFrame(index=macd_df_float.index, dtype=object)
        expected_ta_cols = {
            f'MACD_{fast_period}_{slow_period}_{signal_period}': 'MACD',
            f'MACDh_{fast_period}_{slow_period}_{signal_period}': 'Histogram',
            f'MACDs_{fast_period}_{slow_period}_{signal_period}': 'Signal'
        }
        cols_found = 0
        for col_ta, col_std in expected_ta_cols.items():
            if col_ta in macd_df_float.columns:
                macd_df_decimal[col_std] = _convert_series_to_decimal(
                    macd_df_float[col_ta])
                cols_found += 1
            else:
                if cols_found == 0:
                    logger.warning(
                        f"Expected MACD columns like '{col_ta}' not found.")
                macd_df_decimal[col_std] = pd.Series(
                    dtype=object, index=macd_df_float.index)

        if cols_found == 0:
            logger.error("Failed to find any expected columns in MACD output.")
            return pd.DataFrame(dtype=object, index=df.index)

        logger.debug(f"Successfully calculated MACD.")
        # Reindex to original DataFrame's index
        return macd_df_decimal.reindex(df.index)

    except AttributeError:
        logger.error("MACD: Check pandas-ta install/DataFrame.")
        return pd.DataFrame(dtype=object, index=df.index)
    except Exception as e:
        logger.error(
            f"MACD Error (f={fast_period},s={slow_period},sig={signal_period},col='{price_col}'): {e}", exc_info=True)
        return pd.DataFrame(dtype=object, index=df.index)


def calculate_pivot_points(df_period: pd.DataFrame) -> Optional[pd.Series]:
    """Calculates standard Pivot Points (Manual calculation)."""
    required_cols = ['high', 'low', 'close']
    if df_period is None or len(df_period) != 1:
        logger.error("Pivot: Input must be 1 row.")
        return None

    col_map = {col.lower(): col for col in df_period.columns}
    original_case_cols = [col_map.get(req_col) for req_col in required_cols]

    if not all(original_case_cols):
        missing = [req for req, orig in zip(
            required_cols, original_case_cols) if not orig]
        logger.error(f"Pivot: Missing {missing} columns.")
        return None

    try:
        prev_high_val = df_period[original_case_cols[0]].iloc[0]
        prev_low_val = df_period[original_case_cols[1]].iloc[0]
        prev_close_val = df_period[original_case_cols[2]].iloc[0]

        prev_high = Decimal(str(prev_high_val)) if pd.notna(
            prev_high_val) else None
        prev_low = Decimal(str(prev_low_val)) if pd.notna(
            prev_low_val) else None
        prev_close = Decimal(str(prev_close_val)) if pd.notna(
            prev_close_val) else None

        if None in [prev_high, prev_low, prev_close]:
            logger.error("Pivot: HLC missing/invalid.")
            return None

    except (InvalidOperation, TypeError, ValueError) as e:
        logger.error(
            f"Pivot: HLC Decimal conversion error: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Pivot: HLC extraction error: {e}", exc_info=True)
        return None

    try:
        three, two = Decimal('3.0'), Decimal('2.0')
        pp = (prev_high + prev_low + prev_close) / three
        range_hl = prev_high - prev_low

        r1, s1 = (two * pp) - prev_low, (two * pp) - prev_high
        r2, s2 = pp + range_hl, pp - range_hl
        r3, s3 = prev_high + (two * (pp - prev_low)
                              ), prev_low - (two * (prev_high - pp))

        pivot_levels = {'PP': pp, 'R1': r1, 'S1': s1,
                        'R2': r2, 'S2': s2, 'R3': r3, 'S3': s3}
        quantizer = Decimal('1e-8')  # Adjust precision as needed
        for key, value in pivot_levels.items():
            pivot_levels[key] = value.quantize(
                quantizer, rounding=ROUND_HALF_UP)

        # Return object dtype Series
        return pd.Series(pivot_levels, dtype=object)

    except (ArithmeticError, InvalidOperation) as e:
        logger.error(f"Pivot: Arithmetic error: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Pivot: Calculation error: {e}", exc_info=True)
        return None


# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Starting indicator calculation example using pandas-ta...")

    # Data remains the same...
    data = {
        'open_time': pd.to_datetime(['2023-01-01 00:00:00', '2023-01-01 01:00:00', '2023-01-01 02:00:00', '2023-01-01 03:00:00', '2023-01-01 04:00:00', '2023-01-01 05:00:00', '2023-01-01 06:00:00', '2023-01-01 07:00:00', '2023-01-01 08:00:00', '2023-01-01 09:00:00', '2023-01-01 10:00:00', '2023-01-01 11:00:00', '2023-01-01 12:00:00', '2023-01-01 13:00:00', '2023-01-01 14:00:00', '2023-01-01 15:00:00', '2023-01-01 16:00:00', '2023-01-01 17:00:00', '2023-01-01 18:00:00', '2023-01-01 19:00:00', '2023-01-01 20:00:00', '2023-01-01 21:00:00', '2023-01-01 22:00:00', '2023-01-01 23:00:00', '2023-01-02 00:00:00', '2023-01-02 01:00:00', '2023-01-02 02:00:00'], utc=True),
        'Open': ['16500.1', '16510.5', '16520.3', '16505.0', '16490.7', '16500.0', '16530.8', '16555.2', '16540.1', '16560.9', '16570.0', '16585.5', '16600.2', '16590.7', '16580.3', '16610.0', '16625.5', '16640.0', '16635.1', '16650.0', '16660.5', '16645.8', '16670.2', '16685.9', '16700.0', '16690.5', '16710.8'],
        'High': ['16515.2', '16525.0', '16530.1', '16515.5', '16505.8', '16535.0', '16560.0', '16570.3', '16565.5', '16575.1', '16590.0', '16605.3', '16610.0', '16600.0', '16595.9', '16630.5', '16640.1', '16650.0', '16645.0', '16665.3', '16675.0', '16660.1', '16680.0', '16695.0', '16715.3', '16705.0', '16720.0'],
        'Low': ['16495.0', '16505.1', '16500.5', '16488.9', '16485.0', '16495.5', '16520.0', '16535.8', '16530.2', '16550.0', '16565.0', '16575.0', '16585.0', '16578.8', '16570.0', '16590.0', '16615.0', '16620.5', '16625.8', '16640.0', '16650.0', '16640.5', '16660.0', '16675.5', '16680.0', '16685.1', '16695.2'],
        'Close': ['16510.5', '16520.3', '16505.0', '16490.7', '16500.0', '16530.8', '16555.2', '16540.1', '16560.9', '16570.0', '16585.5', '16600.2', '16590.7', '16580.3', '16610.0', '16625.5', '16640.0', '16635.1', '16648.2', '16655.9', '16642.1', '16668.8', '16680.5', '16698.3', '16688.8', '16705.6', '16715.0'],
        'Volume': ['100.5', '110.2', '95.8', '120.1', '88.5', '105.3', '130.0', '115.7', '125.4', '108.9', '112.1', '118.6', '102.3', '99.8', '122.0', '135.2', '140.0', '128.8', '119.5', '123.7', '111.4', '133.3', '129.1', '141.0', '136.5', '125.0', '130.8'],
    }
    df = pd.DataFrame(data)
    df = df.set_index('open_time')
    decimal_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in decimal_cols:
        try:
            df[col] = df[col].apply(lambda x: Decimal(
                str(x)) if pd.notna(x) else None).astype(object)
        except KeyError:
            logger.warning(f"Column '{col}' not found in example data.")

    logger.info("--- Sample DataFrame (first 5 rows) ---")
    print(df.head().to_markdown(numalign="left", stralign="left"))
    logger.info("\nDataFrame Info:")
    df.info()

    results_df = df[['Close']].copy()

    # --- Calculate and Add Indicators ---
    indicator_funcs = {
        f'ATR_{ATR_PERIOD}': lambda d: calculate_atr(d, length=ATR_PERIOD),
        f'SMA_{SMA_SHORT_PERIOD}': lambda d: calculate_sma(d, period=SMA_SHORT_PERIOD, price_col='Close'),
        # Keep trying SMA 50
        f'SMA_{SMA_LONG_PERIOD}': lambda d: calculate_sma(d, period=SMA_LONG_PERIOD, price_col='Close'),
        f'RSI_{RSI_PERIOD}': lambda d: calculate_rsi(d, period=RSI_PERIOD, price_col='Close'),
    }

    for name, func in indicator_funcs.items():
        logger.info(f"\n--- Calculating {name} ---")
        series = func(df)
        # *** FIX: Check if series is valid before adding ***
        if series is not None and not series.empty and series.notna().any():
            results_df[name] = series
            print(results_df[[name]].tail().to_markdown(
                numalign="left", stralign="left"))
        else:
            logger.warning(
                f"{name} calculation returned None or empty/all-NaN series.")
            # Add empty column if failed
            results_df[name] = pd.Series(dtype=object, index=df.index)

    logger.info("\n--- Calculating MACD ---")
    macd_df = calculate_macd(df, price_col='Close')
    if macd_df is not None and not macd_df.empty:
        # *** FIX: Check if columns exist and have data before concat ***
        valid_macd_cols = [col for col in [
            'MACD', 'Signal', 'Histogram'] if col in macd_df and macd_df[col].notna().any()]
        if valid_macd_cols:
            results_df = pd.concat(
                [results_df, macd_df[valid_macd_cols]], axis=1)
            print(results_df[valid_macd_cols].tail().to_markdown(
                numalign="left", stralign="left"))
        else:
            logger.warning(
                "MACD DataFrame was returned but contained no valid data columns.")
    else:
        logger.warning("MACD calculation returned None or empty DataFrame.")
        # Add empty columns if MACD failed entirely
        for col in ['MACD', 'Signal', 'Histogram']:
            if col not in results_df:
                results_df[col] = pd.Series(dtype=object, index=df.index)

    logger.info("\n--- Calculating Pivot Points ---")
    previous_period_data = df.iloc[[-1]]
    logger.debug(
        f"Using this data for Pivot Point calculation:\n{previous_period_data.to_markdown(numalign='left', stralign='left')}")
    pivot_levels = calculate_pivot_points(previous_period_data)
    if pivot_levels is not None and not pivot_levels.empty:
        print("Pivot Levels calculated:")
        print(pivot_levels.to_markdown(numalign="left", stralign="left"))
    else:
        logger.warning("Could not calculate pivot points.")

    logger.info("\n--- Final Results DataFrame Tail ---")
    print(results_df.tail().to_markdown(numalign="left", stralign="left"))
    logger.info("\nFinal Results DataFrame Info:")
    # Replace potential None columns created on failure with object dtype for info()
    for col in results_df.columns:
        if results_df[col].isnull().all():
            results_df[col] = pd.Series(dtype=object, index=results_df.index)
    results_df.info()

    logger.info("Indicator calculation example finished.")

# END OF FILE: src/analysis/indicators.py
