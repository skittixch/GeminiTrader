# START OF FILE: src/analysis/support_resistance.py

import pandas as pd
import numpy as np
from decimal import Decimal, ROUND_HALF_UP
from sklearn.cluster import DBSCAN
import logging
from typing import List, Dict, Any, Tuple, Optional

# --- Setup Logger ---
logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_PIVOT_WINDOW = 10
DEFAULT_ZONE_PROXIMITY_FACTOR = Decimal('0.005')
DEFAULT_MIN_ZONE_TOUCHES = 2
# Scoring Weights (adjustable later via config)
RECENCY_WEIGHT = Decimal('0.4')
TOUCH_COUNT_WEIGHT = Decimal('0.6')

# --- Helper Functions ---


def find_rolling_pivots(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """ Finds rolling High/Low pivots. """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'])
    if not all(col in df.columns for col in ['High', 'Low']):
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'])
    if not window > 0:
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'])
    if len(df) < window:
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'], index=df.index)
    try:
        highs = pd.to_numeric(df['High'], errors='coerce')
        lows = pd.to_numeric(df['Low'], errors='coerce')
        def get_pivot_idx(x): return x.argmax() if len(x) >= window else np.nan
        rolling_high_argmax_pos = highs.rolling(
            window=window, min_periods=window).apply(get_pivot_idx, raw=True)
        rolling_low_argmin_pos = lows.rolling(window=window, min_periods=window).apply(
            lambda x: x.argmin() if len(x) >= window else np.nan, raw=True)
        shifted_high_argmax_pos = rolling_high_argmax_pos.shift(1)
        shifted_low_argmin_pos = rolling_low_argmin_pos.shift(1)
        pivot_df = pd.DataFrame(index=df.index, dtype=object)
        pivot_df['PivotHigh'] = None
        pivot_df['PivotLow'] = None
        for i in range(window - 1 + 1, len(df)):
            idx_label = df.index[i]
            argmax_pos = shifted_high_argmax_pos.loc[idx_label]
            if pd.notna(argmax_pos):
                pivot_integer_location = i - window + int(argmax_pos)
                if pivot_integer_location == i - 1:
                    pivot_df.loc[idx_label, 'PivotHigh'] = df['High'].iloc[i-1]
            argmin_pos = shifted_low_argmin_pos.loc[idx_label]
            if pd.notna(argmin_pos):
                pivot_integer_location = i - window + int(argmin_pos)
                if pivot_integer_location == i - 1:
                    pivot_df.loc[idx_label, 'PivotLow'] = df['Low'].iloc[i-1]
        logger.debug(
            f"Pivots: Found {pivot_df['PivotHigh'].notna().sum()} highs, {pivot_df['PivotLow'].notna().sum()} lows.")
        return pivot_df
    except Exception as e:
        logger.exception(f"Error finding rolling pivots: {e}")
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'], index=df.index)


def cluster_pivots_to_zones(pivots: pd.Series, proximity_factor: Decimal = DEFAULT_ZONE_PROXIMITY_FACTOR) -> List[Tuple[Decimal, Decimal]]:
    """ Clusters pivot prices into zones using DBSCAN. """
    valid_pivots = pivots.dropna()
    if valid_pivots.empty or len(valid_pivots) < 2:
        return []
    try:
        prices_numeric = pd.to_numeric(
            valid_pivots, errors='coerce').dropna().values.reshape(-1, 1)
        if len(prices_numeric) < 2:
            return []
        median_price = Decimal(str(np.median(prices_numeric)))
        eps_val = float(
            median_price * proximity_factor) if median_price > 0 and proximity_factor > 0 else 1e-8
        min_samples = 1
        logger.debug(
            f"Running DBSCAN: MedianPrice={median_price:.4f}, Epsilon={eps_val:.4f}, MinSamples={min_samples}")
        db = DBSCAN(eps=eps_val, min_samples=min_samples).fit(prices_numeric)
        labels = db.labels_
        clusters = {}
        for label, price in zip(labels, prices_numeric.flatten()):
            if label != -1:
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(Decimal(str(price)))
        zones = []
        quantizer = Decimal('1e-8')
        for label, prices_in_cluster in clusters.items():
            if prices_in_cluster:
                min_p = min(prices_in_cluster).quantize(
                    quantizer, rounding=ROUND_HALF_UP)
                max_p = max(prices_in_cluster).quantize(
                    quantizer, rounding=ROUND_HALF_UP)
                if min_p == max_p:
                    logger.debug(
                        f"Cluster {label}: Zero-width zone at {min_p}")
                zones.append((min_p, max_p))
                logger.debug(f"Cluster {label}: Zone {min_p} - {max_p}")
        zones.sort(key=lambda x: x[0])
        return zones
    except Exception as e:
        logger.exception(f"Error clustering pivots: {e}")
        return []

# --- UPDATED score_zones FUNCTION ---


def score_zones(
    zones: List[Tuple[Decimal, Decimal]],
    df: pd.DataFrame,
    min_touches: int
) -> List[Dict[str, Any]]:
    """
    Validates zones based on interactions (touches), determines type (S/R/Range),
    and calculates simple recency and composite scores.

    Args:
        zones (List[Tuple[Decimal, Decimal]]): List of potential zone tuples (min_price, max_price).
        df (pd.DataFrame): DataFrame with 'High', 'Low', 'Close' columns (expects Decimal) and DatetimeIndex.
        min_touches (int): Minimum number of touches required for a zone to be kept.

    Returns:
        List[Dict[str, Any]]: List of scored zone dictionaries.
    """
    validated_zones_list = []
    required_cols = ['High', 'Low', 'Close']
    if not zones:
        logger.debug("score_zones: No zones provided.")
        return []
    if df.empty or not all(col in df.columns for col in required_cols) or not isinstance(df.index, pd.DatetimeIndex):
        logger.error(
            "score_zones: DataFrame invalid (empty, missing cols, or not DatetimeIndex).")
        return []

    try:
        # Convert columns once
        highs_num = pd.to_numeric(df['High'], errors='coerce')
        lows_num = pd.to_numeric(df['Low'], errors='coerce')
        closes_num = pd.to_numeric(df['Close'], errors='coerce')
        last_close_num = closes_num.iloc[-1] if not closes_num.empty and pd.notna(
            closes_num.iloc[-1]) else None
        if last_close_num is None:
            logger.warning("score_zones: Could not get last close price.")

        # For recency: get total number of bars in the dataframe
        total_bars = len(df)

        for z_min, z_max in zones:
            try:
                z_min_float = float(z_min)
                z_max_float = float(z_max)
                if z_min_float > z_max_float:
                    logger.warning(
                        f"score_zones: Skipping invalid zone tuple min > max")
                    continue

                # 1. Calculate Touches
                touch_mask = (highs_num >= z_min_float) & (
                    lows_num <= z_max_float)
                touches = int(touch_mask.sum())

                # Filter by minimum touches
                if touches >= min_touches:
                    # 2. Determine Zone Type
                    zone_type = "range"
                    if last_close_num is not None:
                        if last_close_num > z_max_float:
                            zone_type = "support"
                        elif last_close_num < z_min_float:
                            zone_type = "resistance"

                    # 3. Calculate Recency Score
                    recency_score = 0.0  # Default if no touches somehow
                    # Get integer indices where mask is True
                    touch_indices = np.where(touch_mask)[0]
                    if len(touch_indices) > 0:
                        # Get the index of the most recent touch
                        last_touch_index = touch_indices[-1]
                        # Simple linear recency: score = (index_of_last_touch / total_bars)
                        # Closer to 1.0 means more recent touch
                        # Add 1 because index is 0-based
                        recency_score = float(
                            last_touch_index + 1) / total_bars
                        # Round for cleanliness
                        recency_score = round(recency_score, 4)

                    # 4. Calculate Composite Score (Simple Example)
                    # Normalize touches (e.g., assume max possible touches is total_bars) - crude, but simple
                    # A better approach might cap touch score contribution (e.g., score levels off after 10 touches)
                    # Cap score at 10 touches for normalization
                    touch_score_normalized = min(1.0, float(touches) / 10.0)
                    composite_score_decimal = (Decimal(str(
                        touch_score_normalized)) * TOUCH_COUNT_WEIGHT) + (Decimal(str(recency_score)) * RECENCY_WEIGHT)
                    composite_score = round(float(composite_score_decimal), 4)

                    validated_zones_list.append({
                        "min_price": z_min,
                        "max_price": z_max,
                        "touches": touches,
                        "type": zone_type,
                        "recency_score": recency_score,
                        "composite_score": composite_score,
                    })
                    logger.debug(
                        f"Zone {z_min}-{z_max} validated: T={touches}, Type={zone_type}, Rec={recency_score:.3f}, Comp={composite_score:.3f}")
                else:
                    logger.debug(
                        f"Zone {z_min}-{z_max} discarded: Touches ({touches}) < Min Touches ({min_touches})")
            except Exception as e:
                logger.error(f"Error scoring zone {z_min}-{z_max}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during zone scoring: {e}")
        return []

    # Sort final zones by composite score (highest first) for potential prioritization
    validated_zones_list.sort(key=lambda x: x['composite_score'], reverse=True)

    return validated_zones_list
# --- END OF UPDATED FUNCTION ---


def calculate_dynamic_zones(
    df: pd.DataFrame,
    pivot_window: int = DEFAULT_PIVOT_WINDOW,
    proximity_factor: Decimal = DEFAULT_ZONE_PROXIMITY_FACTOR,
    min_touches: int = DEFAULT_MIN_ZONE_TOUCHES
) -> List[Dict[str, Any]]:
    """ Calculates dynamic Support/Resistance zones based on rolling pivots and clustering. """
    logger.info(
        # Shorter INFO
        f"Calculating dynamic S/R zones (Win={pivot_window}, Prox={proximity_factor:.2%}, Touch={min_touches}).")
    if not isinstance(df, pd.DataFrame) or df.empty:
        logger.error("S/R Zones: Input DataFrame empty.")
        return []
    pivot_df = find_rolling_pivots(df, window=pivot_window)
    if pivot_df is None or pivot_df.empty:
        logger.warning("S/R Zones: No pivots found or error.")
        return []
    valid_high_pivots = pivot_df['PivotHigh'].dropna()
    valid_low_pivots = pivot_df['PivotLow'].dropna()
    logger.debug(
        f"Pivots Found: High={len(valid_high_pivots)}, Low={len(valid_low_pivots)}.")
    high_zones_raw = cluster_pivots_to_zones(
        valid_high_pivots, proximity_factor)
    low_zones_raw = cluster_pivots_to_zones(valid_low_pivots, proximity_factor)
    logger.debug(
        f"Raw Zones Clustered: High={len(high_zones_raw)}, Low={len(low_zones_raw)}.")
    all_raw_zones = sorted(high_zones_raw + low_zones_raw, key=lambda x: x[0])
    validated_zones = score_zones(all_raw_zones, df, min_touches)
    for zone in validated_zones:  # Add readable string AFTER validation
        zone['zone_str'] = f"{zone['type']} (S:{zone['composite_score']:.2f} T:{zone['touches']}): {zone['min_price']:.2f}-{zone['max_price']:.2f}"
    if validated_zones:
        # INFO summary
        logger.info(
            f"S/R Zones Found: {len(validated_zones)} validated zones.")
        preview = [z['zone_str'] for z in validated_zones[:3]]
        logger.debug(f"Zone Preview: {preview}")
    else:
        logger.info("S/R Zones: No valid zones found after filtering.")
    return validated_zones


# Example Usage
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    data = {
        'open_time': pd.to_datetime(['2023-01-01 00:00:00', '2023-01-01 01:00:00', '2023-01-01 02:00:00', '2023-01-01 03:00:00', '2023-01-01 04:00:00', '2023-01-01 05:00:00', '2023-01-01 06:00:00', '2023-01-01 07:00:00', '2023-01-01 08:00:00', '2023-01-01 09:00:00', '2023-01-01 10:00:00', '2023-01-01 11:00:00', '2023-01-01 12:00:00', '2023-01-01 13:00:00', '2023-01-01 14:00:00', '2023-01-01 15:00:00', '2023-01-01 16:00:00', '2023-01-01 17:00:00', '2023-01-01 18:00:00', '2023-01-01 19:00:00', '2023-01-01 20:00:00', '2023-01-01 21:00:00', '2023-01-01 22:00:00', '2023-01-01 23:00:00', '2023-01-02 00:00:00', '2023-01-02 01:00:00', '2023-01-02 02:00:00'], utc=True),
        'High': ['16515.2', '16525.0', '16530.1', '16515.5', '16505.8', '16535.0', '16560.0', '16570.3', '16565.5', '16575.1', '16590.0', '16605.3', '16610.0', '16600.0', '16595.9', '16630.5', '16640.1', '16650.0', '16645.0', '16665.3', '16675.0', '16660.1', '16680.0', '16695.0', '16715.3', '16705.0', '16720.0'],
        'Low': ['16495.0', '16505.1', '16500.5', '16488.9', '16485.0', '16495.5', '16520.0', '16535.8', '16530.2', '16550.0', '16565.0', '16575.0', '16585.0', '16578.8', '16570.0', '16590.0', '16615.0', '16620.5', '16625.8', '16640.0', '16650.0', '16640.5', '16660.0', '16675.5', '16680.0', '16685.1', '16695.2'],
        'Close': ['16510.5', '16520.3', '16505.0', '16490.7', '16500.0', '16530.8', '16555.2', '16540.1', '16560.9', '16570.0', '16585.5', '16600.2', '16590.7', '16580.3', '16610.0', '16625.5', '16640.0', '16635.1', '16648.2', '16655.9', '16642.1', '16668.8', '16680.5', '16698.3', '16688.8', '16705.6', '16715.0'],
    }
    df_test = pd.DataFrame(data)
    df_test = df_test.set_index('open_time')
    decimal_cols = ['High', 'Low', 'Close']
    for col in decimal_cols:
        if col in df_test.columns:
            df_test[col] = df_test[col].apply(lambda x: Decimal(
                str(x)) if pd.notna(x) else None).astype(object)
    logger.info("--- Testing Dynamic Zone Calculation ---")
    zones_result = calculate_dynamic_zones(
        df_test, pivot_window=5, min_touches=2)
    logger.info(f"Found {len(zones_result)} validated zones:")
    for zone in zones_result:
        print(f"  - {zone.get('zone_str', 'N/A')}")
    logger.info("--- S/R Zone Test Complete ---")

# END OF FILE: src/analysis/support_resistance.py
