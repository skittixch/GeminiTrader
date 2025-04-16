# START OF FILE: src/analysis/support_resistance.py

import pandas as pd
import numpy as np
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from sklearn.cluster import DBSCAN
import logging
from typing import List, Dict, Any, Tuple, Optional

# Import get_config_value for config access
try:
    from config.settings import get_config_value
except ImportError:
    # Dummy for standalone testing
    def get_config_value(cfg, path, default=None): return default
    logging.warning("Using dummy get_config_value in support_resistance.py")

logger = logging.getLogger(__name__)

# --- Defaults ---
DEFAULT_PIVOT_WINDOW = 10
DEFAULT_ZONE_PROXIMITY_FACTOR = Decimal('0.005')
DEFAULT_MIN_ZONE_TOUCHES = 2
DEFAULT_RECENCY_WEIGHT = Decimal('0.4')
DEFAULT_TOUCH_COUNT_WEIGHT = Decimal('0.6')

# --- Helper Functions ---

# --- UPDATED find_rolling_pivots ---


def find_rolling_pivots(df: pd.DataFrame, window: int) -> pd.DataFrame:
    """ Finds rolling High/Low pivots using rolling max/min comparison. """
    required_cols = [
        'High', 'Low']  # Expect TitleCase matching simulation data
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'])
    if not all(col in df.columns for col in required_cols):
        logger.error(f"Pivot requires columns: {required_cols}")
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'])
    if not window > 0:
        logger.error("Pivot window must be > 0")
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'])
    # Ensure window is realistic for data length
    window = min(window, len(df))
    if len(df) < window:
        logger.debug(
            f"Not enough data ({len(df)}) for pivot window ({window})")
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'], index=df.index)

    try:
        # Ensure High and Low are numeric, coercing errors
        highs = pd.to_numeric(df['High'], errors='coerce')
        lows = pd.to_numeric(df['Low'], errors='coerce')

        # Calculate rolling max/min
        # Add 1 to window because we look back N periods *excluding* the current one
        # Shift(1) makes the window end *before* the current candle
        rolling_high = highs.rolling(
            window=window, closed='left').max()  # Look back N periods
        rolling_low = lows.rolling(
            window=window, closed='left').min()   # Look back N periods

        # Identify pivots: Current High > rolling max of previous N OR Current Low < rolling min of previous N
        # We compare the current bar's high/low to the max/min of the preceding window.
        # Using shift(1) effectively makes rolling window end at i-1
        # A high pivot occurs if High[i] is the highest in window [i-N+1 .. i]
        # A low pivot occurs if Low[i] is the lowest in window [i-N+1 .. i]
        # Alternative: Find where current High == rolling(window).max()

        # Simpler approach: Find where the current high is the max of the window ending *at* the current bar
        # And also higher than the high of the previous bar (basic confirmation)
        rolling_max_high = highs.rolling(window=window).max()
        rolling_min_low = lows.rolling(window=window).min()

        # Pivot high if current high is the max of the window AND higher than previous high (optional check)
        # Pivot low if current low is the min of the window AND lower than previous low (optional check)
        # & (highs > highs.shift(1)) # Optional stricter check
        is_pivot_high = (highs == rolling_max_high)
        # & (lows < lows.shift(1))   # Optional stricter check
        is_pivot_low = (lows == rolling_min_low)

        pivot_df = pd.DataFrame(index=df.index, dtype=object)
        # Assign the original Decimal value where pivot condition is met
        pivot_df['PivotHigh'] = df['High'].where(is_pivot_high)
        pivot_df['PivotLow'] = df['Low'].where(is_pivot_low)

        # Ensure Decimal or None
        pivot_df['PivotHigh'] = pivot_df['PivotHigh'].apply(
            lambda x: Decimal(str(x)) if pd.notna(x) else None)
        pivot_df['PivotLow'] = pivot_df['PivotLow'].apply(
            lambda x: Decimal(str(x)) if pd.notna(x) else None)

        logger.debug(
            f"Pivots (Rolling Max/Min): Found {pivot_df['PivotHigh'].notna().sum()} highs, {pivot_df['PivotLow'].notna().sum()} lows using window {window}.")
        return pivot_df

    except Exception as e:
        logger.exception(f"Error finding rolling pivots: {e}")
        return pd.DataFrame(columns=['PivotHigh', 'PivotLow'], index=df.index)
# --- END UPDATED find_rolling_pivots ---


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
            f"Running DBSCAN: Pivots={len(prices_numeric)}, Median={median_price:.4f}, Eps={eps_val:.4f}, MinSamples={min_samples}")
        db = DBSCAN(eps=eps_val, min_samples=min_samples).fit(prices_numeric)
        labels = db.labels_
        clusters = {}
        for label, price in zip(labels, prices_numeric.flatten()):
            if label != -1:
                if label not in clusters:
                    clusters[label] = []
                try:
                    clusters[label].append(Decimal(str(price)))
                except InvalidOperation:
                    logger.warning(
                        f"Could not convert clustered price {price} to Decimal.")
        zones = []
        quantizer = Decimal('1e-8')
        for label, prices_in_cluster in clusters.items():
            if prices_in_cluster:
                min_p = min(prices_in_cluster).quantize(
                    quantizer, rounding=ROUND_HALF_UP)
                max_p = max(prices_in_cluster).quantize(
                    quantizer, rounding=ROUND_HALF_UP)
                zones.append((min_p, max_p))
                logger.debug(f"Cluster {label}: Zone {min_p} - {max_p}")
        zones.sort(key=lambda x: x[0])
        return zones
    except Exception as e:
        logger.exception(f"Error clustering pivots: {e}")
        return []


def score_zones(zones: List[Tuple[Decimal, Decimal]], df: pd.DataFrame, min_touches: int, recency_weight: Decimal, touch_weight: Decimal) -> List[Dict[str, Any]]:
    """Validates zones, determines type, calculates scores."""
    validated_zones = []
    required_cols = ['High', 'Low', 'Close']  # Expect TitleCase
    if not zones:
        logger.debug("score_zones: No zones.")
        return []
    if df.empty or not all(col in df.columns for col in required_cols) or not isinstance(df.index, pd.DatetimeIndex):
        logger.error("score_zones: DataFrame invalid.")
        return []
    try:
        highs = pd.to_numeric(df['High'], errors='coerce')
        lows = pd.to_numeric(df['Low'], errors='coerce')
        closes = pd.to_numeric(df['Close'], errors='coerce')
        last_close_val = closes.iloc[-1] if not closes.empty else None
        last_close = float(last_close_val) if pd.notna(
            last_close_val) else None
        if last_close is None:
            logger.warning("score_zones: Could not get numeric last close.")
        total_bars = len(df)
        if total_bars == 0:
            logger.error("score_zones: DF has zero length.")
            return []

        for z_min, z_max in zones:
            try:
                z_min_f = float(z_min)
                z_max_f = float(z_max)
                if z_min_f > z_max_f:
                    continue
                touch_mask = (lows <= z_max_f) & (highs >= z_min_f)
                touches = int(touch_mask.sum())
                if touches >= min_touches:
                    zone_type = "range"
                    if last_close is not None:
                        zone_type = "support" if last_close > z_max_f else (
                            "resistance" if last_close < z_min_f else "range")
                    recency_score = 0.0
                    touch_indices = np.where(touch_mask)[0]
                    if len(touch_indices) > 0:
                        last_touch_idx = touch_indices[-1]
                        recency_score = round(
                            float(last_touch_idx + 1) / total_bars, 4)
                    touch_norm = min(1.0, float(touches) / 10.0)
                    comp_score_dec = (Decimal(
                        str(touch_norm)) * touch_weight) + (Decimal(str(recency_score)) * recency_weight)
                    comp_score = round(float(comp_score_dec), 4)
                    validated_zones.append({"min_price": z_min, "max_price": z_max, "touches": touches,
                                           "type": zone_type, "recency_score": recency_score, "composite_score": comp_score})
                    logger.debug(
                        f"Zone {z_min}-{z_max} valid: T={touches}, Type={zone_type}, Rec={recency_score:.3f}, Comp={comp_score:.3f}")
                else:
                    logger.debug(
                        f"Zone {z_min}-{z_max} discard: Touches ({touches}) < Min ({min_touches})")
            except Exception as e:
                logger.error(f"Error scoring zone {z_min}-{z_max}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error during zone scoring: {e}")
        return []
    validated_zones.sort(key=lambda x: x['composite_score'], reverse=True)
    return validated_zones

# --- Main Calculation Function (Accepts whole config) ---


def calculate_dynamic_zones(df: pd.DataFrame, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """ Calculates dynamic S/R zones using config dict. """
    # --- Extract params using ORIGINAL config paths ---
    # Assume S/R params might be under strategies -> geometric_grid or a dedicated analysis section
    # Let's try accessing via potential paths, using defaults
    pivot_window = get_config_value(
        # Example path
        config, ('strategies', 'geometric_grid', 'pivot_window'), DEFAULT_PIVOT_WINDOW)
    prox_factor_raw = get_config_value(config, ('strategies', 'geometric_grid',
                                       'zone_proximity_factor'), DEFAULT_ZONE_PROXIMITY_FACTOR)  # Example path
    min_touches = get_config_value(config, ('strategies', 'geometric_grid',
                                   'min_zone_touches'), DEFAULT_MIN_ZONE_TOUCHES)  # Example path
    # Scoring weights might be defined elsewhere or use defaults
    recency_weight = get_config_value(
        # Example path
        config, ('analysis', 'scoring', 'recency_weight'), DEFAULT_RECENCY_WEIGHT)
    touch_weight = get_config_value(
        # Example path
        config, ('analysis', 'scoring', 'touch_weight'), DEFAULT_TOUCH_COUNT_WEIGHT)
    # --- End Config Extraction ---

    try:  # Ensure proximity factor is Decimal
        proximity_factor = Decimal(str(prox_factor_raw))
        if proximity_factor <= 0:
            raise ValueError("Proximity factor must be positive")
    except (InvalidOperation, TypeError, ValueError) as e:
        logger.warning(
            f"Invalid proximity_factor '{prox_factor_raw}', using default {DEFAULT_ZONE_PROXIMITY_FACTOR}. Err: {e}")
        proximity_factor = DEFAULT_ZONE_PROXIMITY_FACTOR

    logger.info(
        f"Calculating dynamic S/R zones (Win={pivot_window}, Prox={float(proximity_factor):.2%}, Touch={min_touches}).")
    if not isinstance(df, pd.DataFrame) or df.empty:
        logger.error("S/R Zones: Input DataFrame empty.")
        return []

    pivot_df = find_rolling_pivots(df, window=pivot_window)
    if pivot_df is None or pivot_df.empty:
        logger.warning("S/R Zones: No pivots found.")
        return []
    valid_high = pivot_df['PivotHigh'].dropna()
    valid_low = pivot_df['PivotLow'].dropna()
    logger.debug(
        f"Pivots Found: High={len(valid_high)}, Low={len(valid_low)}.")
    high_zones = cluster_pivots_to_zones(valid_high, proximity_factor)
    low_zones = cluster_pivots_to_zones(valid_low, proximity_factor)
    logger.debug(
        f"Raw Zones Clustered: High={len(high_zones)}, Low={len(low_zones)}.")
    all_zones = sorted(high_zones + low_zones, key=lambda x: x[0])
    validated = score_zones(all_zones, df, min_touches,
                            recency_weight, touch_weight)

    for zone in validated:  # Add readable string
        min_p, max_p = zone['min_price'], zone['max_price']
        zone['zone_str'] = f"{zone['type']} (S:{zone['composite_score']:.2f} T:{zone['touches']}): {min_p:.4f}-{max_p:.4f}"

    logger.info(f"S/R Zones Found: {len(validated)} validated zones.")
    if validated:
        logger.debug(f"Zone Preview: {[z['zone_str'] for z in validated[:3]]}")
    else:
        logger.info("S/R Zones: No valid zones found after filtering.")
    return validated


# Example Usage (Passes whole dummy config)
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # ... (Sample data remains the same) ...
    data = {'open_time': pd.to_datetime(['2023-01-01 00:00:00', '2023-01-01 01:00:00', '2023-01-01 02:00:00', '2023-01-01 03:00:00', '2023-01-01 04:00:00', '2023-01-01 05:00:00', '2023-01-01 06:00:00', '2023-01-01 07:00:00', '2023-01-01 08:00:00', '2023-01-01 09:00:00', '2023-01-01 10:00:00', '2023-01-01 11:00:00', '2023-01-01 12:00:00', '2023-01-01 13:00:00', '2023-01-01 14:00:00', '2023-01-01 15:00:00', '2023-01-01 16:00:00', '2023-01-01 17:00:00', '2023-01-01 18:00:00', '2023-01-01 19:00:00', '2023-01-01 20:00:00', '2023-01-01 21:00:00', '2023-01-01 22:00:00', '2023-01-01 23:00:00', '2023-01-02 00:00:00', '2023-01-02 01:00:00', '2023-01-02 02:00:00'], utc=True),
            'High': ['16515.2', '16525.0', '16530.1', '16515.5', '16505.8', '16535.0', '16560.0', '16570.3', '16565.5', '16575.1', '16590.0', '16605.3', '16610.0', '16600.0', '16595.9', '16630.5', '16640.1', '16650.0', '16645.0', '16665.3', '16675.0', '16660.1', '16680.0', '16695.0', '16715.3', '16705.0', '16720.0'],
            'Low': ['16495.0', '16505.1', '16500.5', '16488.9', '16485.0', '16495.5', '16520.0', '16535.8', '16530.2', '16550.0', '16565.0', '16575.0', '16585.0', '16578.8', '16570.0', '16590.0', '16615.0', '16620.5', '16625.8', '16640.0', '16650.0', '16640.5', '16660.0', '16675.5', '16680.0', '16685.1', '16695.2'],
            'Close': ['16510.5', '16520.3', '16505.0', '16490.7', '16500.0', '16530.8', '16555.2', '16540.1', '16560.9', '16570.0', '16585.5', '16600.2', '16590.7', '16580.3', '16610.0', '16625.5', '16640.0', '16635.1', '16648.2', '16655.9', '16642.1', '16668.8', '16680.5', '16698.3', '16688.8', '16705.6', '16715.0'], }
    df_test = pd.DataFrame(data)
    df_test = df_test.set_index('open_time')
    for col in ['High', 'Low', 'Close']:
        df_test[col] = df_test[col].apply(lambda x: Decimal(
            str(x)) if pd.notna(x) else None).astype(object)

    # Example dummy config matching original structure
    dummy_config = {
        'strategies': {
            'geometric_grid': {
                'pivot_window': 5,  # Override default
                'zone_proximity_factor': '0.003',
                'min_zone_touches': 2
            }
        },
        'analysis': {  # Example analysis section for weights
            'scoring': {
                'recency_weight': 0.3,
                'touch_weight': 0.7
            }
        }
        # Other sections omitted for brevity
    }

    logger.info("--- Testing Dynamic Zone Calculation with Config Dict ---")
    zones_result = calculate_dynamic_zones(
        df_test, config=dummy_config)  # Pass whole dict
    logger.info(f"Found {len(zones_result)} validated zones:")
    for zone in zones_result:
        print(f"  - {zone.get('zone_str', 'N/A')}")
    logger.info("--- S/R Zone Test Complete ---")


# END OF FILE: src/analysis/support_resistance.py
