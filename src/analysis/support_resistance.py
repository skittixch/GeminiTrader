# START OF FILE: src/analysis/support_resistance.py

import logging
import pandas as pd
import numpy as np
from decimal import Decimal
# --- Corrected import line ---
from typing import List, Tuple, Dict, Optional, Any  # Added Any

from collections import defaultdict

# --- Add project root ---
# Import standard sys.path modification if needed for tests
import os
import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
# --- End ---

logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_PIVOT_WINDOW = 10  # Look N bars left and right for pivot identification
# Pivots within 0.5% of each other might cluster
DEFAULT_ZONE_PROXIMITY_FACTOR = 0.005
DEFAULT_MIN_ZONE_TOUCHES = 2  # Minimum pivots needed to form a scored zone


def find_rolling_pivots(df: pd.DataFrame, window: int = DEFAULT_PIVOT_WINDOW) -> pd.DataFrame:
    """
    Identifies rolling pivot highs and lows within a DataFrame.

    A pivot high is a bar with 'high' greater than the 'high' of 'window' bars
    to the left and 'window' bars to the right.
    A pivot low is a bar with 'low' less than the 'low' of 'window' bars
    to the left and 'window' bars to the right.

    Args:
        df (pd.DataFrame): DataFrame with kline data. Must contain 'High' and 'Low'
                           columns (case-insensitive) with numeric/Decimal values.
        window (int): Number of bars to look left and right for pivot confirmation.

    Returns:
        pd.DataFrame: Original DataFrame with two new boolean columns:
                      'is_pivot_high' and 'is_pivot_low'.
                      Returns the original DataFrame if calculation fails.
    """
    if df is None or df.empty:
        logger.warning("SR: Input DataFrame empty, cannot find pivots.")
        return df
    if window <= 0:
        logger.error("SR: Pivot window must be positive.")
        return df

    # Find columns case-insensitively
    col_map = {col.lower(): col for col in df.columns}
    high_col = col_map.get('high')
    low_col = col_map.get('low')

    if not high_col or not low_col:
        logger.error("SR: DataFrame must contain 'High' and 'Low' columns.")
        return df

    # --- Convert H/L to numeric temporarily for rolling ops ---
    # Create a temporary DataFrame for calculations
    try:
        temp_df = pd.DataFrame(index=df.index)
        temp_df[high_col] = pd.to_numeric(df[high_col], errors='coerce')
        temp_df[low_col] = pd.to_numeric(df[low_col], errors='coerce')
        # Drop rows where conversion failed in essential columns
        temp_df.dropna(subset=[high_col, low_col], inplace=True)
        if temp_df.empty:
            logger.warning(
                "SR: No valid numeric High/Low data after cleaning.")
            # Add empty columns to original df if returning it
            df['is_pivot_high'] = False
            df['is_pivot_low'] = False
            return df
    except Exception as e:
        logger.error(
            f"SR: Error preparing High/Low columns for pivot calc: {e}")
        df['is_pivot_high'] = False  # Ensure columns exist even on error
        df['is_pivot_low'] = False
        return df

    df_copy = df.copy()  # Work on a copy of the original to add columns

    # --- Efficiently check using rolling max/min comparison on numeric data ---
    is_pivot_high_series = (
        temp_df[high_col] == temp_df[high_col].rolling(
            window * 2 + 1, center=True, min_periods=window+1).max()
    )
    is_pivot_low_series = (
        temp_df[low_col] == temp_df[low_col].rolling(
            window * 2 + 1, center=True, min_periods=window+1).min()
    )

    # --- Add results back to the original DataFrame copy ---
    df_copy['is_pivot_high'] = is_pivot_high_series.reindex(
        df_copy.index, fill_value=False)
    df_copy['is_pivot_low'] = is_pivot_low_series.reindex(
        df_copy.index, fill_value=False)

    # Optional: Refine - Ensure a pivot high isn't also marked as a low
    same_pivot_mask = df_copy['is_pivot_high'] & df_copy['is_pivot_low']
    if same_pivot_mask.any():
        logger.debug(
            f"Found {same_pivot_mask.sum()} bars marked as both high/low pivot. Resetting.")
        df_copy.loc[same_pivot_mask, ['is_pivot_high', 'is_pivot_low']] = False

    logger.debug(
        f"Identified {df_copy['is_pivot_high'].sum()} potential pivot highs and {df_copy['is_pivot_low'].sum()} potential pivot lows.")
    return df_copy


# --- IMPLEMENTED CLUSTERING FUNCTION ---
def cluster_pivots_to_zones(
    df_with_pivots: pd.DataFrame,
    proximity_factor: float = DEFAULT_ZONE_PROXIMITY_FACTOR
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Clusters identified pivot points into potential Support and Resistance zones
    based on price proximity.

    Args:
        df_with_pivots (pd.DataFrame): DataFrame containing kline data and boolean
                                       'is_pivot_high', 'is_pivot_low' columns.
                                       Must also contain 'High' and 'Low' columns.
        proximity_factor (float): Percentage factor (e.g., 0.005 for 0.5%) to
                                  group pivots. Two pivots are clustered if one
                                  is within proximity_factor % of the other.

    Returns:
        Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]: A tuple containing two lists:
            - List of resistance zone dictionaries.
            - List of support zone dictionaries.
        Each zone dict contains: {'price_low': Decimal, 'price_high': Decimal,
                                 'pivot_timestamps': List[Timestamp], 'num_touches': int}
    """
    logger.debug(
        f"Clustering pivots with proximity factor: {proximity_factor*100:.2f}%")
    resistance_zones = []
    support_zones = []

    # Find columns case-insensitively
    col_map = {col.lower(): col for col in df_with_pivots.columns}
    high_col = col_map.get('high')
    low_col = col_map.get('low')
    if not high_col or not low_col:
        logger.error("SR Cluster: DataFrame missing 'High' or 'Low' column.")
        return [], []
    if 'is_pivot_high' not in df_with_pivots.columns or 'is_pivot_low' not in df_with_pivots.columns:
        logger.error("SR Cluster: DataFrame missing pivot boolean columns.")
        return [], []

    # --- Process Resistance Pivots (Highs) ---
    pivot_highs = df_with_pivots[df_with_pivots['is_pivot_high']]
    try:  # Convert high prices to Decimal, drop Nones/NaNs
        pivot_high_prices = pivot_highs[high_col].apply(
            lambda x: Decimal(str(x)) if pd.notna(x) else None).dropna()
    except Exception as e:
        logger.error(
            f"SR Cluster: Error converting pivot high prices to Decimal: {e}")
        pivot_high_prices = pd.Series(dtype=Decimal)

    # Sort pivots by price descending
    sorted_highs = pivot_high_prices.sort_values(ascending=False)
    clustered_high_indices = set()

    for timestamp, price in sorted_highs.items():
        if timestamp in clustered_high_indices:
            continue
        current_zone_pivots = {timestamp: price}
        min_price_in_zone = price
        max_price_in_zone = price
        # Check subsequent pivots for proximity
        # Avoid self-comparison
        for other_ts, other_price in sorted_highs.drop(timestamp).items():
            if other_ts in clustered_high_indices:
                continue
            # Check proximity: if the other price is within % of the current max (which is the starting price)
            if abs(other_price - max_price_in_zone) <= max_price_in_zone * Decimal(str(proximity_factor)):
                current_zone_pivots[other_ts] = other_price
                min_price_in_zone = min(min_price_in_zone, other_price)
                # Don't update clustered_high_indices here yet, do it after the inner loop

        # Finalize zone and mark pivots as clustered
        if current_zone_pivots:
            resistance_zones.append({
                # Quantize zone bounds
                'price_low': min_price_in_zone.quantize(Decimal('1e-8')),
                'price_high': max_price_in_zone.quantize(Decimal('1e-8')),
                # Store sorted timestamps
                'pivot_timestamps': sorted(list(current_zone_pivots.keys())),
                'num_touches': len(current_zone_pivots)
            })
            clustered_high_indices.update(current_zone_pivots.keys())

    logger.debug(f"Formed {len(resistance_zones)} initial resistance zones.")

    # --- Process Support Pivots (Lows) ---
    pivot_lows = df_with_pivots[df_with_pivots['is_pivot_low']]
    try:  # Convert low prices to Decimal, drop Nones/NaNs
        pivot_low_prices = pivot_lows[low_col].apply(
            lambda x: Decimal(str(x)) if pd.notna(x) else None).dropna()
    except Exception as e:
        logger.error(
            f"SR Cluster: Error converting pivot low prices to Decimal: {e}")
        pivot_low_prices = pd.Series(dtype=Decimal)

    # Sort pivots by price ascending
    sorted_lows = pivot_low_prices.sort_values(ascending=True)
    clustered_low_indices = set()

    for timestamp, price in sorted_lows.items():
        if timestamp in clustered_low_indices:
            continue
        current_zone_pivots = {timestamp: price}
        min_price_in_zone = price
        max_price_in_zone = price
        # Check subsequent pivots for proximity
        # Avoid self-comparison
        for other_ts, other_price in sorted_lows.drop(timestamp).items():
            if other_ts in clustered_low_indices:
                continue
            # Check proximity: if the other price is within % of the current min (starting price)
            if abs(other_price - min_price_in_zone) <= min_price_in_zone * Decimal(str(proximity_factor)):
                current_zone_pivots[other_ts] = other_price
                max_price_in_zone = max(max_price_in_zone, other_price)

        # Finalize zone and mark pivots as clustered
        if current_zone_pivots:
            support_zones.append({
                'price_low': min_price_in_zone.quantize(Decimal('1e-8')),
                'price_high': max_price_in_zone.quantize(Decimal('1e-8')),
                'pivot_timestamps': sorted(list(current_zone_pivots.keys())),
                'num_touches': len(current_zone_pivots)
            })
            clustered_low_indices.update(current_zone_pivots.keys())

    logger.debug(f"Formed {len(support_zones)} initial support zones.")

    return resistance_zones, support_zones


# --- Placeholder scoring function ---
def score_zones(zones: List[Dict[str, Any]], df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Scores the identified S/R zones based on factors like touches, recency, volume.
    (Implementation TBD)
    """
    logger.warning("score_zones is not implemented yet.")
    # TODO: Implement scoring logic
    for zone in zones:
        zone['score'] = 0.0  # Dummy score
    return zones


# --- UPDATED Orchestration Function ---
def calculate_dynamic_zones(
    df: pd.DataFrame,
    pivot_window: int = DEFAULT_PIVOT_WINDOW,
    proximity_factor: float = DEFAULT_ZONE_PROXIMITY_FACTOR,
    min_touches: int = DEFAULT_MIN_ZONE_TOUCHES
) -> List[Dict[str, Any]]:
    """
    Orchestrates the process of finding pivots, clustering them, and scoring zones.

    Args:
        df (pd.DataFrame): Kline data with 'High' and 'Low' columns.
        pivot_window (int): Lookback/lookforward window for identifying pivots.
        proximity_factor (float): Percentage factor for clustering pivots by price.
        min_touches (int): Minimum number of pivots required to form a valid zone after clustering.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each representing a scored S/R zone
                              (score added later). Returns empty list on error or if no
                              zones meet criteria.
    """
    logger.info(
        f"Calculating dynamic S/R zones (Window: {pivot_window}, Proximity: {proximity_factor*100:.2f}%, Min Touch: {min_touches}).")

    # Step 1: Find rolling pivots
    df_with_pivots = find_rolling_pivots(df, window=pivot_window)
    if 'is_pivot_high' not in df_with_pivots.columns:
        logger.error("SR Zones: Failed to identify pivot points.")
        return []

    # Step 2: Cluster pivots into zones
    resistance_zones, support_zones = cluster_pivots_to_zones(
        df_with_pivots,
        proximity_factor=proximity_factor
    )

    # Combine zones and filter by minimum touches
    initial_zones = []
    for r_zone in resistance_zones:
        if r_zone['num_touches'] >= min_touches:
            r_zone['zone_type'] = 'resistance'
            initial_zones.append(r_zone)
    for s_zone in support_zones:
        if s_zone['num_touches'] >= min_touches:
            s_zone['zone_type'] = 'support'
            initial_zones.append(s_zone)

    if not initial_zones:
        logger.info(
            f"No S/R zones found meeting minimum touches ({min_touches}).")
        return []

    logger.info(
        f"Found {len(initial_zones)} potential S/R zones after clustering & min_touch filter.")

    # Step 3: Score zones (Not Implemented Yet - placeholder)
    scored_zones = score_zones(initial_zones, df_with_pivots)

    # Step 4: Further Filter zones (Optional - e.g., by score)
    # final_zones = [zone for zone in scored_zones if zone.get('score', 0) > some_threshold]
    final_zones = scored_zones  # No score filtering yet

    # Log final zones found (example: print first few)
    if final_zones:
        log_preview = [
            f"{z['zone_type']} ({z['num_touches']} touches): {z['price_low']:.2f}-{z['price_high']:.2f}" for z in final_zones[:3]]
        logger.info(
            f"Dynamic S/R Zone calculation complete. Found {len(final_zones)} zones. Preview: {log_preview}")
    else:
        logger.info(
            "Dynamic S/R Zone calculation complete. No zones passed final filters (scoring TBD).")

    return final_zones


# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing S/R Zone Logic ---")

    # Create more extensive sample data
    data = {
        'open_time': pd.to_datetime(['2023-01-01 00:00:00', '2023-01-01 01:00:00', '2023-01-01 02:00:00', '2023-01-01 03:00:00', '2023-01-01 04:00:00', '2023-01-01 05:00:00', '2023-01-01 06:00:00', '2023-01-01 07:00:00', '2023-01-01 08:00:00', '2023-01-01 09:00:00', '2023-01-01 10:00:00', '2023-01-01 11:00:00', '2023-01-01 12:00:00', '2023-01-01 13:00:00', '2023-01-01 14:00:00', '2023-01-01 15:00:00', '2023-01-01 16:00:00', '2023-01-01 17:00:00', '2023-01-01 18:00:00', '2023-01-01 19:00:00', '2023-01-01 20:00:00', '2023-01-01 21:00:00', '2023-01-01 22:00:00', '2023-01-01 23:00:00', '2023-01-02 00:00:00', '2023-01-02 01:00:00', '2023-01-02 02:00:00'], utc=True),
        'Open': [Decimal(o) for o in ['16500.1', '16510.5', '16520.3', '16505.0', '16490.7', '16500.0', '16530.8', '16555.2', '16540.1', '16560.9', '16570.0', '16585.5', '16600.2', '16590.7', '16580.3', '16610.0', '16625.5', '16640.0', '16635.1', '16650.0', '16660.5', '16645.8', '16670.2', '16685.9', '16700.0', '16690.5', '16710.8']],
        'High': [Decimal(h) for h in ['16515.2', '16525.0', '16530.1', '16515.5', '16505.8', '16535.0', '16560.0', '16570.3', '16565.5', '16575.1', '16590.0', '16605.3', '16610.0', '16600.0', '16595.9', '16630.5', '16640.1', '16650.0', '16645.0', '16665.3', '16675.0', '16660.1', '16680.0', '16695.0', '16715.3', '16705.0', '16720.0']],
        'Low': [Decimal(l) for l in ['16495.0', '16505.1', '16500.5', '16488.9', '16485.0', '16495.5', '16520.0', '16535.8', '16530.2', '16550.0', '16565.0', '16575.0', '16585.0', '16578.8', '16570.0', '16590.0', '16615.0', '16620.5', '16625.8', '16640.0', '16650.0', '16640.5', '16660.0', '16675.5', '16680.0', '16685.1', '16695.2']],
        'Close': [Decimal(c) for c in ['16510.5', '16520.3', '16505.0', '16490.7', '16500.0', '16530.8', '16555.2', '16540.1', '16560.9', '16570.0', '16585.5', '16600.2', '16590.7', '16580.3', '16610.0', '16625.5', '16640.0', '16635.1', '16648.2', '16655.9', '16642.1', '16668.8', '16680.5', '16698.3', '16688.8', '16705.6', '16715.0']],
        'Volume': [Decimal(v) for v in ['100.5', '110.2', '95.8', '120.1', '88.5', '105.3', '130.0', '115.7', '125.4', '108.9', '112.1', '118.6', '102.3', '99.8', '122.0', '135.2', '140.0', '128.8', '119.5', '123.7', '111.4', '133.3', '129.1', '141.0', '136.5', '125.0', '130.8']],
    }
    df_sample = pd.DataFrame(data)
    df_sample = df_sample.set_index('open_time')

    # Test finding pivots
    logger.info("\n--- Testing Pivot Finding ---")
    pivot_window_test = 3  # Use a smaller window for smaller dataset
    df_pivots_found = find_rolling_pivots(df_sample, window=pivot_window_test)
    pivot_rows = df_pivots_found[df_pivots_found['is_pivot_high']
                                 | df_pivots_found['is_pivot_low']]
    if not pivot_rows.empty:
        print("\nDataFrame rows with potential pivots identified:")
        print(pivot_rows[['High', 'is_pivot_high',
              'Low', 'is_pivot_low']].to_markdown())
    else:
        print("\nNo pivots identified with current window size on sample data.")

    # Test the orchestration function (includes clustering now)
    logger.info("\n--- Testing Full Zone Calculation (Pivots + Clustering) ---")
    # Use min_touches=1 to see initial zones formed
    zones = calculate_dynamic_zones(
        df_sample, pivot_window=pivot_window_test, min_touches=1)
    logger.info(
        f"Found {len(zones)} zones initially (min_touches=1, scoring TBD).")
    # Print details of found zones for verification
    for i, zone in enumerate(zones):
        print(
            f"Zone {i+1}: Type='{zone['zone_type']}', Touches={zone['num_touches']}, Range=[{zone['price_low']:.2f} - {zone['price_high']:.2f}]")

    logger.info("\n--- S/R Zone Logic Test Complete ---")


# END OF FILE: src/analysis/support_resistance.py
