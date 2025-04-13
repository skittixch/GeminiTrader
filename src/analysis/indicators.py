# src/analysis/indicators.py

import pandas as pd
import pandas_ta as ta  # Import pandas-ta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def calculate_atr(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """
    Calculates the Average True Range (ATR) for the given kline data.

    Args:
        df (pd.DataFrame): DataFrame with kline data. Must contain
                           'High', 'Low', and 'Close' columns with
                           numeric (preferably Decimal) values.
        length (int): The period length for ATR calculation. Default is 14.

    Returns:
        pd.DataFrame: The original DataFrame with an added 'ATR_{length}' column
                      containing the calculated ATR values as Decimals, or the
                      original DataFrame if calculation fails.
    """
    if df is None or df.empty:
        logger.warning("Input DataFrame is empty, cannot calculate ATR.")
        return df
    if not all(col in df.columns for col in ['High', 'Low', 'Close']):
        logger.error(
            "DataFrame must contain 'High', 'Low', and 'Close' columns for ATR.")
        return df
    if length <= 0:
        logger.error("ATR length must be positive.")
        return df

    # Ensure columns are numeric for pandas_ta, converting Decimal if needed
    # pandas_ta might work better with floats, let's convert temporarily
    try:
        df_float = df[['High', 'Low', 'Close']].astype(float)

        logger.debug(f"Calculating ATR with length {length}...")
        # Calculate ATR using pandas_ta
        # Use append=False to get just the series
        atr_series = df_float.ta.atr(length=length, append=False)

        if atr_series is None or atr_series.empty:
            logger.warning(
                f"pandas_ta.atr returned None or empty series for length {length}.")
            return df  # Return original df if ATR calculation failed

        # Add the calculated ATR series back to the original DataFrame
        # Convert the float results back to Decimal for consistency
        atr_col_name = f'ATR_{length}'
        df[atr_col_name] = atr_series.apply(
            lambda x: Decimal(str(x)) if pd.notna(x) else None)
        logger.debug(
            f"Successfully calculated and added '{atr_col_name}' column.")

    except Exception as e:
        logger.exception(f"Error calculating ATR: {e}")
        # Return the original dataframe without the ATR column in case of error
        return df

    return df

# --- Example Usage (for testing purposes) ---
# if __name__ == '__main__':
#     from src.utils.logging_setup import setup_logging
#     import os
#
#     # Setup basic logging for testing
#     project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
#     log_file = os.path.join(project_root, "data", "logs", "test_indicators.log")
#     os.makedirs(os.path.dirname(log_file), exist_ok=True)
#     setup_logging(log_file=log_file, console_logging=True)
#
#     # Create a sample DataFrame (replace with actual fetched data)
#     data = {
#         'Open': [Decimal('100'), Decimal('102'), Decimal('101'), Decimal('103'), Decimal('105')],
#         'High': [Decimal('103'), Decimal('104'), Decimal('103'), Decimal('106'), Decimal('107')],
#         'Low': [Decimal('99'), Decimal('101'), Decimal('100'), Decimal('102'), Decimal('104')],
#         'Close': [Decimal('102'), Decimal('103'), Decimal('102'), Decimal('105'), Decimal('106')],
#         'Volume': [Decimal('1000'), Decimal('1200'), Decimal('1100'), Decimal('1500'), Decimal('1600')]
#     }
#     sample_df = pd.DataFrame(data)
#     sample_df.index = pd.to_datetime(['2023-01-01 10:00', '2023-01-01 11:00', '2023-01-01 12:00', '2023-01-01 13:00', '2023-01-01 14:00'], utc=True)
#
#     logger.info("Calculating ATR for sample data...")
#     df_with_atr = calculate_atr(sample_df.copy(), length=3) # Use a smaller length for the small sample
#
#     if f'ATR_3' in df_with_atr.columns:
#         logger.info("ATR Calculation Result:")
#         print(df_with_atr[['High', 'Low', 'Close', 'ATR_3']].to_markdown(numalign="right", stralign="right"))
#     else:
#         logger.error("ATR calculation failed.")

# --- End Example Usage ---

# File path: src/analysis/indicators.py
