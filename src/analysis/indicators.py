# START OF FILE: src/analysis/indicators.py

import pandas as pd
import pandas_ta as ta  # type: ignore # Use pandas-ta for common indicators
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import logging
from typing import Optional, Dict, Any  # Added Dict, Any

# --- Setup Logger ---
logger = logging.getLogger(__name__)

# --- Default Constants (can be overridden by config) ---
DEFAULT_ATR_PERIOD = 14
DEFAULT_SMA_FAST_PERIOD = 50  # Match config default if possible
DEFAULT_SMA_SLOW_PERIOD = 200  # Match config default if possible
DEFAULT_RSI_PERIOD = 14
DEFAULT_MACD_FAST_PERIOD = 12
DEFAULT_MACD_SLOW_PERIOD = 26
DEFAULT_MACD_SIGNAL_PERIOD = 9

# --- Helper for pandas-ta conversion ---


def _convert_to_float_df(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """Converts specified columns to float for pandas-ta compatibility."""
    try:
        float_df = df[cols].copy()
        for col in cols:
            float_df[col] = pd.to_numeric(float_df[col], errors='coerce')
            float_df[col] = float_df[col].astype('float64')
        if float_df.isnull().all().any():
            logger.warning(
                f"All values in one or more columns ({cols}) became NaN after conversion. Check input data.")
            # Return empty with original index
            return pd.DataFrame(index=df.index)
        return float_df
    except KeyError as e:
        logger.error(
            f"Required column missing for float conversion: {e}. Available columns: {list(df.columns)}")
        return pd.DataFrame(index=df.index)
    except Exception as e:
        logger.error(
            f"Error converting columns {cols} to float: {e}", exc_info=True)
        return pd.DataFrame(index=df.index)


def _convert_series_to_decimal(series: pd.Series, precision: str = '1e-8') -> pd.Series:
    """Converts a pandas Series (likely float) back to Decimal."""
    if series is None or series.empty:
        return pd.Series(dtype=object, index=series.index if series is not None else None)
    try:
        quantizer = Decimal(precision)
        decimal_series = series.apply(
            lambda x: Decimal(str(x)).quantize(
                quantizer, rounding=ROUND_HALF_UP)
            if pd.notna(x) and isinstance(x, (int, float, str))
            else (Decimal(x).quantize(quantizer, rounding=ROUND_HALF_UP) if isinstance(x, Decimal)
                  else None)
        )
        return decimal_series.astype(object)
    except (InvalidOperation, TypeError, ValueError) as e:
        # Reduce log noise
        logger.error(
            f"Error converting Series elements to Decimal: {e}", exc_info=False)
        # Log full trace to debug
        logger.debug(
            f"Full error converting Series to Decimal: {e}", exc_info=True)
        return pd.Series(dtype=object, index=series.index)
    except Exception as e:
        logger.error(
            f"Unexpected error converting Series to Decimal: {e}", exc_info=True)
        return pd.Series(dtype=object, index=series.index)

# --- Individual Indicator Functions (Mostly unchanged) ---


def calculate_atr(df: pd.DataFrame, length: int = DEFAULT_ATR_PERIOD) -> pd.Series:
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
        # Return empty with index
        return pd.Series(dtype=object, index=df.index)

    if length <= 0:
        logger.error("ATR length must be positive.")
        return pd.Series(dtype=object, index=df.index)
    if len(df) < length:
        logger.debug(f"ATR: Not enough data ({len(df)}<{length}).")
        return pd.Series(dtype=object, index=df.index)

    float_df = _convert_to_float_df(df, original_case_cols)
    if float_df.empty:
        logger.warning("ATR: Failed HLC float conversion.")
        return pd.Series(dtype=object, index=df.index)

    float_df.dropna(subset=original_case_cols, inplace=True)
    if len(float_df) < length:
        logger.debug(
            f"ATR: Not enough non-NaN data ({len(float_df)}<{length}).")
        return pd.Series(dtype=object, index=df.index)

    try:
        logger.debug(
            f"Calculating ATR with length {length} using pandas-ta...")
        float_df.columns = required_cols_case_insensitive  # Rename copy to lowercase

        atr_series_float = float_df.ta.atr(length=length, append=False)

        if atr_series_float is None or atr_series_float.empty:
            logger.warning(
                f"pandas_ta.atr returned None/empty for length {length}.")
            return pd.Series(dtype=object, index=df.index)

        atr_series_decimal = _convert_series_to_decimal(atr_series_float)
        atr_series_decimal.name = f'ATR_{length}'
        logger.debug(f"Successfully calculated ATR_{length}.")
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
        return pd.Series(dtype=object, index=df.index)
    if len(df) < period:
        logger.debug(f"SMA: Not enough data ({len(df)}<{period}).")
        return pd.Series(dtype=object, index=df.index)

    float_df = _convert_to_float_df(df, [original_price_col])
    if float_df.empty:
        logger.warning(f"SMA: Failed '{original_price_col}' float conversion.")
        return pd.Series(dtype=object, index=df.index)

    float_df.dropna(subset=[original_price_col], inplace=True)
    if len(float_df) < period:
        logger.debug(
            f"SMA: Not enough non-NaN data ({len(float_df)}<{period}).")
        return pd.Series(dtype=object, index=df.index)

    try:
        logger.debug(
            f"Calculating SMA with period {period} using pandas-ta...")
        # Use original case name for pandas_ta call if it exists
        sma_series_float = float_df.ta.sma(
            close=float_df[original_price_col], length=period, append=False)

        if sma_series_float is None or sma_series_float.empty:
            logger.warning(
                f"pandas_ta.sma returned None/empty for period {period}.")
            return pd.Series(dtype=object, index=df.index)

        sma_series_decimal = _convert_series_to_decimal(sma_series_float)
        sma_series_decimal.name = f'SMA_{period}'
        logger.debug(f"Successfully calculated SMA_{period}.")
        return sma_series_decimal.reindex(df.index)

    except AttributeError:
        logger.error("SMA: Check pandas-ta install/DataFrame.")
        return pd.Series(dtype=object, index=df.index)
    except Exception as e:
        logger.error(
            f"SMA Error (period={period}, col='{price_col}'): {e}", exc_info=True)
        return pd.Series(dtype=object, index=df.index)


def calculate_rsi(df: pd.DataFrame, period: int = DEFAULT_RSI_PERIOD, price_col: str = 'close') -> pd.Series:
    """Calculates RSI using pandas-ta."""
    if df is None or df.empty:
        logger.warning("RSI: Input DataFrame empty.")
        return pd.Series(dtype=object)

    price_col_lower = price_col.lower()
    col_map = {col.lower(): col for col in df.columns}
    original_price_col = col_map.get(price_col_lower)

    if not original_price_col:
        logger.warning(f"RSI: Price column '{price_col}' not found.")
        return pd.Series(dtype=object, index=df.index)
    if len(df) <= period:
        logger.debug(f"RSI: Not enough data ({len(df)}<={period}).")
        return pd.Series(dtype=object, index=df.index)

    float_df = _convert_to_float_df(df, [original_price_col])
    if float_df.empty:
        logger.warning(f"RSI: Failed '{original_price_col}' float conversion.")
        return pd.Series(dtype=object, index=df.index)

    float_df.dropna(subset=[original_price_col], inplace=True)
    if len(float_df) <= period:
        logger.debug(
            f"RSI: Not enough non-NaN data ({len(float_df)}<={period}).")
        return pd.Series(dtype=object, index=df.index)

    try:
        logger.debug(
            f"Calculating RSI with period {period} using pandas-ta...")
        rsi_series_float = float_df.ta.rsi(
            close=float_df[original_price_col], length=period, append=False)

        if rsi_series_float is None or rsi_series_float.empty:
            logger.warning(
                f"pandas_ta.rsi returned None/empty for period {period}.")
            return pd.Series(dtype=object, index=df.index)

        rsi_series_decimal = _convert_series_to_decimal(
            rsi_series_float, precision='0.01')
        rsi_series_decimal.name = f'RSI_{period}'
        logger.debug(f"Successfully calculated RSI_{period}.")
        return rsi_series_decimal.reindex(df.index)

    except AttributeError:
        logger.error("RSI: Check pandas-ta install/DataFrame.")
        return pd.Series(dtype=object, index=df.index)
    except Exception as e:
        logger.error(
            f"RSI Error (period={period}, col='{price_col}'): {e}", exc_info=True)
        return pd.Series(dtype=object, index=df.index)


def calculate_macd(df: pd.DataFrame,
                   fast_period: int = DEFAULT_MACD_FAST_PERIOD,
                   slow_period: int = DEFAULT_MACD_SLOW_PERIOD,
                   signal_period: int = DEFAULT_MACD_SIGNAL_PERIOD,
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
        return pd.DataFrame(dtype=object, index=df.index)
    min_len = slow_period + signal_period
    if len(df) < min_len:
        logger.debug(f"MACD: Not enough data ({len(df)}<{min_len}).")
        return pd.DataFrame(dtype=object, index=df.index)

    float_df = _convert_to_float_df(df, [original_price_col])
    if float_df.empty:
        logger.warning(
            f"MACD: Failed '{original_price_col}' float conversion.")
        return pd.DataFrame(dtype=object, index=df.index)

    float_df.dropna(subset=[original_price_col], inplace=True)
    if len(float_df) < min_len:
        logger.debug(
            f"MACD: Not enough non-NaN data ({len(float_df)}<{min_len}).")
        return pd.DataFrame(dtype=object, index=df.index)

    try:
        logger.debug(
            f"Calculating MACD ({fast_period},{slow_period},{signal_period}) using pandas-ta...")
        macd_df_float = float_df.ta.macd(
            close=float_df[original_price_col], fast=fast_period, slow=slow_period, signal=signal_period, append=False)

        if macd_df_float is None or macd_df_float.empty:
            logger.warning("pandas_ta.macd returned None/empty.")
            return pd.DataFrame(dtype=object, index=df.index)

        macd_df_decimal = pd.DataFrame(index=macd_df_float.index, dtype=object)
        # Standardized column names
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
                    dtype=object, index=macd_df_float.index)  # Empty series placeholder

        if cols_found == 0:
            logger.error("Failed to find any expected columns in MACD output.")
            return pd.DataFrame(dtype=object, index=df.index)

        logger.debug(f"Successfully calculated MACD.")
        return macd_df_decimal.reindex(df.index)

    except AttributeError:
        logger.error("MACD: Check pandas-ta install/DataFrame.")
        return pd.DataFrame(dtype=object, index=df.index)
    except Exception as e:
        logger.error(
            f"MACD Error (f={fast_period},s={slow_period},sig={signal_period},col='{price_col}'): {e}", exc_info=True)
        return pd.DataFrame(dtype=object, index=df.index)


def calculate_pivot_points(df_period: pd.DataFrame) -> Optional[pd.Series]:
    """Calculates standard Pivot Points (Manual calculation for a single prior period)."""
    required_cols = ['high', 'low', 'close']
    if df_period is None or len(df_period) != 1:
        logger.error(
            "Pivot: Input must be 1 row (representing the prior period).")
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
        quantizer = Decimal('1e-8')
        for key, value in pivot_levels.items():
            pivot_levels[key] = value.quantize(
                quantizer, rounding=ROUND_HALF_UP)
        return pd.Series(pivot_levels, dtype=object)
    except (ArithmeticError, InvalidOperation) as e:
        logger.error(f"Pivot: Arithmetic error: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Pivot: Calculation error: {e}", exc_info=True)
        return None


# --- Main Calculation Function (NEW) ---
def calculate_indicators(df: pd.DataFrame, config: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """
    Calculates all configured technical indicators and returns them in a single DataFrame.

    Args:
        df (pd.DataFrame): Input DataFrame with OHLCV data (index=timestamp).
        config (Optional[Dict[str, Any]], optional): Analysis configuration dictionary.
                                                     Defaults to None, using default periods.

    Returns:
        pd.DataFrame: DataFrame with calculated indicators, indexed like input df.
                      Returns an empty DataFrame if input is invalid or calculations fail.
    """
    if df is None or df.empty:
        logger.warning("calculate_indicators: Input DataFrame is empty.")
        return pd.DataFrame()

    if not isinstance(df.index, pd.DatetimeIndex):
        logger.error(
            "calculate_indicators: DataFrame index must be a DatetimeIndex.")
        return pd.DataFrame()

    if config is None:
        config = {}  # Use empty dict if no config provided, rely on defaults

    logger.info(f"Calculating indicators for DataFrame with {len(df)} rows...")

    # Initialize results DataFrame with the same index
    indicators_df = pd.DataFrame(index=df.index)

    # Get config values or use defaults
    atr_period = config.get('atr_period', DEFAULT_ATR_PERIOD)
    sma_fast_period = config.get('sma_fast_period', DEFAULT_SMA_FAST_PERIOD)
    sma_slow_period = config.get('sma_slow_period', DEFAULT_SMA_SLOW_PERIOD)
    rsi_period = config.get('rsi_period', DEFAULT_RSI_PERIOD)
    macd_fast = config.get('macd_fast_period', DEFAULT_MACD_FAST_PERIOD)
    macd_slow = config.get('macd_slow_period', DEFAULT_MACD_SLOW_PERIOD)
    macd_signal = config.get('macd_signal_period', DEFAULT_MACD_SIGNAL_PERIOD)
    # Configurable price column
    price_col = config.get('price_column_name', 'close')

    # --- Calculate Individual Indicators ---

    # ATR
    atr_series = calculate_atr(df, length=atr_period)
    if atr_series is not None and not atr_series.empty:
        indicators_df[atr_series.name] = atr_series
    else:
        logger.warning(f"Failed to calculate ATR_{atr_period}.")
        indicators_df[f'ATR_{atr_period}'] = pd.Series(
            dtype=object, index=df.index)  # Placeholder

    # SMA Fast
    sma_fast_series = calculate_sma(
        df, period=sma_fast_period, price_col=price_col)
    if sma_fast_series is not None and not sma_fast_series.empty:
        indicators_df[sma_fast_series.name] = sma_fast_series
    else:
        logger.warning(f"Failed to calculate SMA_{sma_fast_period}.")
        indicators_df[f'SMA_{sma_fast_period}'] = pd.Series(
            dtype=object, index=df.index)

    # SMA Slow
    sma_slow_series = calculate_sma(
        df, period=sma_slow_period, price_col=price_col)
    if sma_slow_series is not None and not sma_slow_series.empty:
        indicators_df[sma_slow_series.name] = sma_slow_series
    else:
        logger.warning(f"Failed to calculate SMA_{sma_slow_period}.")
        indicators_df[f'SMA_{sma_slow_period}'] = pd.Series(
            dtype=object, index=df.index)

    # RSI
    rsi_series = calculate_rsi(df, period=rsi_period, price_col=price_col)
    if rsi_series is not None and not rsi_series.empty:
        indicators_df[rsi_series.name] = rsi_series
    else:
        logger.warning(f"Failed to calculate RSI_{rsi_period}.")
        indicators_df[f'RSI_{rsi_period}'] = pd.Series(
            dtype=object, index=df.index)

    # MACD
    macd_df = calculate_macd(df,
                             fast_period=macd_fast,
                             slow_period=macd_slow,
                             signal_period=macd_signal,
                             price_col=price_col)
    if macd_df is not None and not macd_df.empty:
        # Check which columns actually got calculated before merging
        valid_macd_cols = [col for col in [
            'MACD', 'Histogram', 'Signal'] if col in macd_df and macd_df[col].notna().any()]
        if valid_macd_cols:
            # Use merge to align by index, prevents potential issues with concat if indices differ slightly
            indicators_df = pd.merge(
                indicators_df, macd_df[valid_macd_cols], left_index=True, right_index=True, how='left')
        else:
            logger.warning(
                "MACD calculation returned DataFrame but no valid columns found.")
            # Add placeholders if MACD failed validation
            for col in ['MACD', 'Histogram', 'Signal']:
                indicators_df[col] = pd.Series(dtype=object, index=df.index)
    else:
        logger.warning("Failed to calculate MACD.")
        # Add placeholders if MACD failed entirely
        for col in ['MACD', 'Histogram', 'Signal']:
            indicators_df[col] = pd.Series(dtype=object, index=df.index)

    # Pivot Points (Note: This calculates pivots based on the *previous* candle for each row, which is not typical daily/weekly pivots)
    # For standard daily pivots, you'd resample the data first.
    # This rolling calculation might be useful for short-term S/R but isn't standard pivots.
    # We might want to remove this or make it optional / clarify its purpose later.
    # For now, let's comment it out from the main combined function to avoid confusion.
    # logger.debug("Skipping rolling pivot point calculation in combined function for now.")
    # indicators_df['PP'] = df.rolling(window=2).apply(lambda x: calculate_pivot_points(x.iloc[[0]])['PP'] if len(x) == 2 else None, raw=False).shift(1)
    # ... (similarly for R1, S1 etc.)

    logger.info(
        f"Finished calculating indicators. Result shape: {indicators_df.shape}")
    # logger.debug(f"Indicator DataFrame tail:\n{indicators_df.tail()}") # Optional: Log tail for verification

    # Ensure all columns have object dtype if they contain Decimals or None
    for col in indicators_df.columns:
        if indicators_df[col].apply(lambda x: isinstance(x, Decimal)).any():
            indicators_df[col] = indicators_df[col].astype(object)

    return indicators_df


# --- Example Usage (Updated to use the main function) ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info(
        "Starting indicator calculation example using main calculate_indicators function...")

    # Sample Data (same as before)
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
    # Convert to Decimal (using original case names from data dict)
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

    # --- Call the main function ---
    # Example config dict (could be loaded from YAML)
    analysis_config = {
        'atr_period': 14,
        'sma_fast_period': 10,  # Using different periods for testing
        'sma_slow_period': 20,
        'rsi_period': 14,
        'macd_fast_period': 12,
        'macd_slow_period': 26,
        'macd_signal_period': 9,
        # Specify the column name (case-sensitive matches input df)
        'price_column_name': 'Close'
    }
    logger.info(
        f"\n--- Calculating all indicators with config: {analysis_config} ---")
    indicators_result_df = calculate_indicators(df, analysis_config)

    # --- Display results ---
    if indicators_result_df is not None and not indicators_result_df.empty:
        logger.info("\n--- Calculated Indicators DataFrame Tail ---")
        print(indicators_result_df.tail().to_markdown(
            numalign="left", stralign="left"))
        logger.info("\nCalculated Indicators DataFrame Info:")
        indicators_result_df.info()
    else:
        logger.warning(
            "calculate_indicators returned None or an empty DataFrame.")

    logger.info("Indicator calculation example finished.")

# END OF FILE: src/analysis/indicators.py
