# START OF FILE: src/analysis/confidence.py

import logging
from decimal import Decimal, InvalidOperation  # Added InvalidOperation
from typing import Optional, Dict, Any, List
import pandas as pd

# --- No longer need constants from indicators.py here ---
# --- No longer need project root path manipulation here ---

try:
    from src.utils.formatting import to_decimal
except ImportError:
    # Define dummy only if absolutely necessary for standalone testing
    def to_decimal(v, default=None):
        try:
            return Decimal(str(v)) if v is not None else default
        except (InvalidOperation, TypeError):
            return default
    print("WARNING: Using dummy to_decimal in confidence.py")


logger = logging.getLogger(__name__)

# --- Default Confidence Calculation Constants ---
DEFAULT_CONF_WEIGHT_RSI = Decimal('0.25')
DEFAULT_CONF_WEIGHT_MACD = Decimal('0.35')
DEFAULT_CONF_WEIGHT_TREND = Decimal('0.40')
DEFAULT_RSI_PERIOD = 14
DEFAULT_RSI_LOW_THRESH = Decimal('35')
DEFAULT_RSI_HIGH_THRESH = Decimal('70')
DEFAULT_MACD_FAST_PERIOD = 12
DEFAULT_MACD_SLOW_PERIOD = 26
DEFAULT_MACD_SIGNAL_PERIOD = 9
DEFAULT_SMA_FAST_PERIOD = 50
DEFAULT_SMA_SLOW_PERIOD = 200


# --- CORRECTED FUNCTION SIGNATURE AND LOGIC ---
def calculate_confidence_v1(
    indicators_df: pd.DataFrame,  # Changed: Expects DataFrame from calculate_indicators
    sr_zones: List[Dict[str, Any]],  # Added: Expects list of zone dicts
    config: Dict[str, Any]  # Added: Expects analysis_options sub-dictionary
) -> float:
    """
    Calculates a basic confidence score (0.0 to 1.0) based on technical indicators.
    V1 uses RSI, MACD (line vs signal, histogram), and SMA trend (short vs long).
    Higher score = higher confidence for potential BUY/LONG entries.

    Args:
        indicators_df (pd.DataFrame): DataFrame containing the latest calculated indicators.
                                     Index must be DatetimeIndex. Columns should match
                                     output from calculate_indicators (e.g., 'RSI_14', 'MACD', etc.).
        sr_zones (List[Dict[str, Any]]): List of calculated S/R zone dictionaries. (Not used in V1 yet)
        config (Dict[str, Any]): Analysis configuration dictionary (e.g., analysis_options section).
                                Used to retrieve periods and thresholds.

    Returns:
        float: A confidence score between 0.0 and 1.0. Returns 0.5 on error or insufficient data.
    """
    if not isinstance(indicators_df, pd.DataFrame) or indicators_df.empty:
        logger.warning(
            "Confidence: No indicators DataFrame provided or empty.")
        return 0.5

    # Get the latest row of indicators
    try:
        latest_indicators = indicators_df.iloc[-1]
    except IndexError:
        logger.warning("Confidence: Indicators DataFrame has no rows.")
        return 0.5

    # --- Extract config values or use defaults ---
    conf_weights = config.get('confidence_weights', {})  # Get weights sub-dict
    rsi_weight = to_decimal(conf_weights.get('rsi', DEFAULT_CONF_WEIGHT_RSI))
    macd_weight = to_decimal(conf_weights.get(
        'macd', DEFAULT_CONF_WEIGHT_MACD))
    trend_weight = to_decimal(conf_weights.get(
        'trend', DEFAULT_CONF_WEIGHT_TREND))

    rsi_period = config.get('rsi_period', DEFAULT_RSI_PERIOD)
    macd_fast = config.get('macd_fast_period', DEFAULT_MACD_FAST_PERIOD)
    macd_slow = config.get('macd_slow_period', DEFAULT_MACD_SLOW_PERIOD)
    macd_signal = config.get('macd_signal_period', DEFAULT_MACD_SIGNAL_PERIOD)
    sma_fast_period = config.get('sma_fast_period', DEFAULT_SMA_FAST_PERIOD)
    sma_slow_period = config.get('sma_slow_period', DEFAULT_SMA_SLOW_PERIOD)

    rsi_low_thresh = to_decimal(config.get(
        'confidence_rsi_low', DEFAULT_RSI_LOW_THRESH))
    rsi_high_thresh = to_decimal(config.get(
        'confidence_rsi_high', DEFAULT_RSI_HIGH_THRESH))
    # --- End Config Extraction ---

    # Construct expected column names based on config/defaults
    rsi_key = f'RSI_{rsi_period}'
    macd_key = 'MACD'  # Standardized name from calculate_macd
    signal_key = 'Signal'  # Standardized name
    histo_key = 'Histogram'  # Standardized name
    sma_short_key = f'SMA_{sma_fast_period}'
    sma_long_key = f'SMA_{sma_slow_period}'

    total_score = Decimal('0.0')
    total_weight = Decimal('0.0')
    calculation_possible = False

    # --- 1. RSI Component ---
    rsi_value_raw = latest_indicators.get(rsi_key)
    rsi_value = to_decimal(rsi_value_raw)  # Convert safely
    rsi_score = Decimal('0.5')  # Default neutral score
    if rsi_value is not None:
        try:
            if rsi_value > rsi_high_thresh:
                # Overbought = Low confidence for BUY
                rsi_score = Decimal('0.1')
            elif rsi_value < rsi_low_thresh:
                # Oversold = High confidence for BUY
                rsi_score = Decimal('0.9')
            else:
                # Neutral/Rising = Moderate confidence
                rsi_score = Decimal('0.7')
            total_score += rsi_score * rsi_weight
            total_weight += rsi_weight
            logger.debug(
                f"Conf RSI({rsi_period}): {rsi_value:.2f} (L:{rsi_low_thresh}, H:{rsi_high_thresh}) -> Score:{rsi_score:.2f} (W:{rsi_weight:.2f})")
            calculation_possible = True
        except Exception as e:
            logger.warning(
                f"Conf: Error processing {rsi_key} val {rsi_value_raw}: {e}")
    else:
        logger.debug(f"Conf: {rsi_key} missing/None.")

    # --- 2. MACD Component ---
    macd_raw = latest_indicators.get(macd_key)
    signal_raw = latest_indicators.get(signal_key)
    histo_raw = latest_indicators.get(histo_key)
    macd = to_decimal(macd_raw)
    signal = to_decimal(signal_raw)
    histogram = to_decimal(histo_raw)
    macd_score = Decimal('0.5')
    if macd is not None and signal is not None and histogram is not None:
        try:
            is_bullish_cross = macd > signal
            is_histo_positive = histogram > Decimal('0.0')
            # Refined scoring based on combo
            if is_bullish_cross and is_histo_positive:
                macd_score = Decimal('0.9')  # Strong bullish momentum
            elif is_bullish_cross and not is_histo_positive:
                macd_score = Decimal('0.6')  # Cross happened, losing momentum?
            elif not is_bullish_cross and is_histo_positive:
                # Below signal but rising momentum (divergence?)
                macd_score = Decimal('0.7')
            else:
                macd_score = Decimal('0.1')  # Bearish cross and momentum

            total_score += macd_score * macd_weight
            total_weight += macd_weight
            logger.debug(
                f"Conf MACD({macd_fast},{macd_slow},{macd_signal}): M={macd:.4f} S={signal:.4f} H={histogram:.4f} -> Score:{macd_score:.2f} (W:{macd_weight:.2f})")
            calculation_possible = True
        except Exception as e:
            logger.warning(
                f"Conf: Error processing MACD (M:{macd_raw}, S:{signal_raw}, H:{histo_raw}): {e}")
    else:
        logger.debug(
            f"Conf: MACD/Signal/Histo missing (M:{macd_raw is None}, S:{signal_raw is None}, H:{histo_raw is None}).")

    # --- 3. Trend Component (SMA Cross) ---
    sma_short_raw = latest_indicators.get(sma_short_key)
    sma_long_raw = latest_indicators.get(sma_long_key)
    sma_short = to_decimal(sma_short_raw)
    sma_long = to_decimal(sma_long_raw)
    trend_score = Decimal('0.5')
    if sma_short is not None and sma_long is not None:
        try:
            if sma_short > sma_long:
                trend_score = Decimal('0.85')  # Uptrend
            else:
                trend_score = Decimal('0.15')  # Downtrend
            total_score += trend_score * trend_weight
            total_weight += trend_weight
            logger.debug(
                f"Conf Trend (SMA {sma_fast_period}/{sma_slow_period}): S={sma_short:.2f} L={sma_long:.2f} -> Score:{trend_score:.2f} (W:{trend_weight:.2f})")
            calculation_possible = True
        except Exception as e:
            logger.warning(
                f"Conf: Error processing SMA trend (S:{sma_short_raw}, L:{sma_long_raw}): {e}")
    else:
        logger.debug(
            f"Conf: SMA Fast/Slow missing ({sma_short_key}:{sma_short_raw is None}, {sma_long_key}:{sma_long_raw is None}).")

    # --- 4. S/R Zone Component (Placeholder for V2) ---
    # Example: Check if price is near a strong support zone score > 0.7?
    # if sr_zones:
    #     current_price = to_decimal(latest_indicators.get('close')) # Need close price
    #     if current_price:
    #        strong_support_nearby = any(z['type'] == 'support' and z['composite_score'] > 0.7 and current_price >= z['min_price'] and current_price <= z['max_price'] * Decimal('1.005') for z in sr_zones)
    #        if strong_support_nearby:
    #             # Add small bonus? Needs careful weighting.
    #             pass
    # logger.debug("S/R Zone analysis not implemented in V1 confidence score.")

    # --- Combine Scores ---
    if total_weight <= Decimal('0.0') or not calculation_possible:
        logger.warning(
            "Confidence: Could not calculate score from any available indicator or total weight is zero.")
        final_score = 0.5  # Default neutral score
    else:
        final_score_decimal = total_score / total_weight
        final_score_decimal = max(Decimal('0.0'), min(
            Decimal('1.0'), final_score_decimal))  # Clamp between 0 and 1
        # Convert final score to float
        final_score = float(final_score_decimal)

    logger.info(f"Calculated Confidence Score V1: {final_score:.4f}")
    return final_score


# Example Usage (Updated to pass DataFrame and config)
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Confidence Score Logic ---")

    # Create a dummy DataFrame similar to what calculate_indicators would return
    dummy_index = pd.to_datetime(
        ['2023-01-01 10:00', '2023-01-01 11:00', '2023-01-01 12:00'])
    dummy_indicators_df_1 = pd.DataFrame({  # Bullish
        f'RSI_{DEFAULT_RSI_PERIOD}': [Decimal('50'), Decimal('55'), Decimal('60')],
        'MACD': [Decimal('10.1'), Decimal('15.5'), Decimal('20.0')],
        'Signal': [Decimal('8.0'), Decimal('10.2'), Decimal('12.0')],
        'Histogram': [Decimal('2.1'), Decimal('5.3'), Decimal('8.0')],
        f'SMA_{DEFAULT_SMA_FAST_PERIOD}': [Decimal('102.0'), Decimal('105.0'), Decimal('108.0')],
        f'SMA_{DEFAULT_SMA_SLOW_PERIOD}': [Decimal('98.0'), Decimal('100.0'), Decimal('101.0')],
    }, index=dummy_index)
    dummy_indicators_df_1 = dummy_indicators_df_1.astype(
        object)  # Ensure object dtype

    dummy_zones = []  # Not used in V1
    dummy_config = {  # Example config
        'rsi_period': DEFAULT_RSI_PERIOD,
        'macd_fast_period': DEFAULT_MACD_FAST_PERIOD,
        # ... other periods ...
        'confidence_rsi_low': 35,  # Test reading from config
        'confidence_rsi_high': 70,
        'confidence_weights': {'rsi': 0.25, 'macd': 0.40, 'trend': 0.35}
    }

    conf1 = calculate_confidence_v1(
        dummy_indicators_df_1, dummy_zones, dummy_config)
    logger.info(f"Test 1 (Bullish): Score = {conf1:.4f}")

    # Test 2 (Bearish/Oversold)
    dummy_indicators_df_2 = pd.DataFrame({
        f'RSI_{DEFAULT_RSI_PERIOD}': [Decimal('30'), Decimal('25'), Decimal('28')],
        'MACD': [Decimal('-18.0'), Decimal('-20.0'), Decimal('-19.0')],
        'Signal': [Decimal('-14.0'), Decimal('-15.0'), Decimal('-16.0')],
        'Histogram': [Decimal('-4.0'), Decimal('-5.0'), Decimal('-3.0')],
        f'SMA_{DEFAULT_SMA_FAST_PERIOD}': [Decimal('99.0'), Decimal('98.0'), Decimal('97.0')],
        f'SMA_{DEFAULT_SMA_SLOW_PERIOD}': [Decimal('101.0'), Decimal('100.0'), Decimal('99.5')],
    }, index=dummy_index)
    dummy_indicators_df_2 = dummy_indicators_df_2.astype(object)
    conf2 = calculate_confidence_v1(
        dummy_indicators_df_2, dummy_zones, dummy_config)
    logger.info(f"Test 2 (Bearish/Oversold): Score = {conf2:.4f}")

    # Test 3 (Missing Data)
    dummy_indicators_df_3 = pd.DataFrame({
        # Missing RSI
        f'RSI_{DEFAULT_RSI_PERIOD}': [Decimal('50'), Decimal('50'), None],
        'MACD': [Decimal('10.1'), Decimal('15.5'), Decimal('20.0')],
        'Signal': [Decimal('8.0'), Decimal('10.2'), Decimal('12.0')],
        'Histogram': [Decimal('2.1'), Decimal('5.3'), Decimal('8.0')],
        # Missing SMA
        f'SMA_{DEFAULT_SMA_FAST_PERIOD}': [Decimal('102.0'), None, Decimal('108.0')],
        f'SMA_{DEFAULT_SMA_SLOW_PERIOD}': [Decimal('98.0'), Decimal('100.0'), Decimal('101.0')],
    }, index=dummy_index)
    dummy_indicators_df_3 = dummy_indicators_df_3.astype(object)
    conf3 = calculate_confidence_v1(
        dummy_indicators_df_3, dummy_zones, dummy_config)
    logger.info(f"Test 3 (Missing Indicators): Score = {conf3:.4f}")

    logger.info("--- Confidence Score Test Complete ---")


# END OF FILE: src/analysis/confidence.py
