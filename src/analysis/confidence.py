# START OF FILE: src/analysis/confidence.py

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List
import pandas as pd # For Timestamp type hint if needed

# --- Add project root ---
# Import standard sys.path modification if needed for tests
import os
import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path: sys.path.insert(0, str(_project_root))
# --- End ---

try:
    from src.utils.formatting import to_decimal
except ImportError:
     # Define dummy if needed for basic script structure
    def to_decimal(v, default=None): return Decimal(v) if v is not None else default
    print("WARNING: Using dummy to_decimal in confidence.py")


logger = logging.getLogger(__name__)

# --- Confidence Calculation Constants ---
# Define weights or thresholds for different factors (can be moved to config later)
CONF_WEIGHT_RSI = Decimal('0.25')
CONF_WEIGHT_MACD = Decimal('0.35')
CONF_WEIGHT_TREND = Decimal('0.40')
# Add weights for S/R, Pivots later...

RSI_LOW_THRESH = Decimal('35') # Below this might increase buy confidence slightly (oversold relief)
RSI_HIGH_THRESH = Decimal('70') # Above this decreases buy confidence (overbought)
SMA_TREND_LOOKBACK = 5 # How many periods back to check if trend is consistent

def calculate_confidence_v1(
    indicators: Dict[str, Optional[Decimal]],
    # --- Optional inputs for future enhancement ---
    # current_price: Optional[Decimal] = None,
    # sr_zones: Optional[List[Dict[str, Any]]] = None,
    # pivot_levels: Optional[pd.Series] = None,
    # config: Optional[Dict] = None # If thresholds/weights become configurable
    ) -> float:
    """
    Calculates a basic confidence score (0.0 to 1.0) based on technical indicators.
    This version focuses on RSI, MACD, and basic SMA trend.
    Designed primarily to gauge confidence for potential BUY/LONG entries or holding.

    Args:
        indicators (Dict[str, Optional[Decimal]]): Dictionary containing the latest
                                                   indicator values (e.g., {'RSI_14': 55.2, 'MACD': ..., 'Signal': ...}).
                                                   Keys should match those stored in main_trader state.

    Returns:
        float: A confidence score between 0.0 and 1.0. Returns 0.5 on error or insufficient data.
    """
    if not indicators:
        logger.warning("Confidence: No indicators provided.")
        return 0.5 # Neutral confidence if no data

    total_score = Decimal('0.0')
    total_weight = Decimal('0.0')

    # --- 1. RSI Component ---
    # Prefers RSI not being overbought for buys. Some score if rising or exiting oversold.
    rsi_key = next((k for k in indicators if k.startswith('RSI_')), None) # Find first RSI key
    rsi_value = indicators.get(rsi_key) if rsi_key else None
    rsi_score = Decimal('0.5') # Default neutral
    if rsi_value is not None:
        try:
            if rsi_value > RSI_HIGH_THRESH:
                rsi_score = Decimal('0.1') # Low confidence if overbought
            elif rsi_value < RSI_LOW_THRESH:
                 rsi_score = Decimal('0.6') # Slightly higher confidence if oversold (potential bounce)
            else:
                 # Scale score linearly between thresholds (higher towards middle/lower end)
                 # Example: score = 1.0 - (value - low) / (high - low) # Higher score when closer to low
                 # Simpler: Higher score in the "middle ground"
                 rsi_score = Decimal('0.7') # Moderate confidence in non-extreme zone

            total_score += rsi_score * CONF_WEIGHT_RSI
            total_weight += CONF_WEIGHT_RSI
            logger.debug(f"Confidence - RSI: {rsi_value:.2f} -> Score: {rsi_score:.2f}")

        except Exception as e:
            logger.warning(f"Confidence: Error processing RSI value {rsi_value}: {e}")
            # Don't add weight if calculation failed

    # --- 2. MACD Component ---
    # Prefers MACD line above signal line and positive/rising histogram for buys.
    macd = indicators.get('MACD')
    signal = indicators.get('Signal')
    histogram = indicators.get('Histogram')
    macd_score = Decimal('0.5') # Default neutral
    if macd is not None and signal is not None and histogram is not None:
        try:
            is_bullish_cross = macd > signal
            is_histo_positive = histogram > Decimal('0.0')
            # is_histo_rising = ... # Requires previous histogram value - skip for v1

            if is_bullish_cross and is_histo_positive:
                macd_score = Decimal('0.9') # High confidence
            elif is_bullish_cross:
                macd_score = Decimal('0.7') # Moderate confidence (cross but negative histo)
            elif is_histo_positive: # Histo positive but no cross yet (divergence?)
                macd_score = Decimal('0.6') # Slightly positive confidence
            else: # Bearish cross and negative histo
                macd_score = Decimal('0.1') # Low confidence

            total_score += macd_score * CONF_WEIGHT_MACD
            total_weight += CONF_WEIGHT_MACD
            logger.debug(f"Confidence - MACD: M={macd:.2f}, S={signal:.2f}, H={histogram:.2f} -> Score: {macd_score:.2f}")

        except Exception as e:
             logger.warning(f"Confidence: Error processing MACD values: {e}")

    # --- 3. Trend Component (SMA Cross) ---
    # Prefers short-term SMA above long-term SMA for buys.
    sma_short_key = next((k for k in indicators if k.startswith('SMA_') and int(k.split('_')[1]) <= 20), None) # Find SMA_10 or similar
    sma_long_key = next((k for k in indicators if k.startswith('SMA_') and int(k.split('_')[1]) > 20), None) # Find SMA_50 or similar
    sma_short = indicators.get(sma_short_key) if sma_short_key else None
    sma_long = indicators.get(sma_long_key) if sma_long_key else None
    trend_score = Decimal('0.5') # Default neutral
    if sma_short is not None and sma_long is not None:
        try:
            if sma_short > sma_long:
                trend_score = Decimal('0.85') # Reasonably high confidence in uptrend
            else:
                trend_score = Decimal('0.15') # Low confidence in downtrend

            total_score += trend_score * CONF_WEIGHT_TREND
            total_weight += CONF_WEIGHT_TREND
            logger.debug(f"Confidence - Trend ({sma_short_key} vs {sma_long_key}): S={sma_short:.2f}, L={sma_long:.2f} -> Score: {trend_score:.2f}")

        except Exception as e:
             logger.warning(f"Confidence: Error processing SMA trend values: {e}")

    # --- Combine Scores ---
    if total_weight == Decimal('0.0'):
        logger.warning("Confidence: Could not calculate score from any indicator.")
        final_score = 0.5 # Return neutral if no indicators contributed
    else:
        # Weighted average
        final_score_decimal = total_score / total_weight
        # Clamp score between 0.0 and 1.0
        final_score_decimal = max(Decimal('0.0'), min(Decimal('1.0'), final_score_decimal))
        final_score = float(final_score_decimal) # Convert final score to float

    logger.info(f"Calculated Confidence Score V1: {final_score:.4f}")
    return final_score


# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Confidence Score Logic ---")

    # Test Case 1: Bullish conditions
    test_indicators_1 = {
        'RSI_14': Decimal('55.0'),
        'MACD': Decimal('15.5'),
        'Signal': Decimal('10.2'),
        'Histogram': Decimal('5.3'),
        'SMA_10': Decimal('105.0'),
        'SMA_50': Decimal('100.0'),
        'ATR_14': Decimal('2.5'), # ATR not used in V1 score
    }
    conf1 = calculate_confidence_v1(test_indicators_1)
    logger.info(f"Test 1 (Bullish): Score = {conf1:.4f}")

    # Test Case 2: Bearish conditions
    test_indicators_2 = {
        'RSI_14': Decimal('25.0'), # Oversold but potentially turning?
        'MACD': Decimal('-20.0'),
        'Signal': Decimal('-15.0'),
        'Histogram': Decimal('-5.0'),
        'SMA_10': Decimal('98.0'),
        'SMA_50': Decimal('100.0'),
        'ATR_14': Decimal('3.0'),
    }
    conf2 = calculate_confidence_v1(test_indicators_2)
    logger.info(f"Test 2 (Bearish/Oversold): Score = {conf2:.4f}")

    # Test Case 3: Mixed / Ranging conditions
    test_indicators_3 = {
        'RSI_14': Decimal('75.0'), # Overbought
        'MACD': Decimal('5.0'),
        'Signal': Decimal('4.5'), # Bullish cross
        'Histogram': Decimal('0.5'), # But small histo
        'SMA_10': Decimal('101.0'),
        'SMA_50': Decimal('100.0'), # Uptrend
        'ATR_14': Decimal('1.5'),
    }
    conf3 = calculate_confidence_v1(test_indicators_3)
    logger.info(f"Test 3 (Mixed/Overbought): Score = {conf3:.4f}")

    # Test Case 4: Missing indicators
    test_indicators_4 = {
        'RSI_14': Decimal('50.0'),
        'MACD': None, # Missing MACD components
        'Signal': None,
        'Histogram': None,
        'SMA_10': Decimal('100.0'),
        'SMA_50': Decimal('100.0'), # Flat trend
    }
    conf4 = calculate_confidence_v1(test_indicators_4)
    logger.info(f"Test 4 (Missing Indicators): Score = {conf4:.4f}")

    # Test Case 5: Empty indicators
    conf5 = calculate_confidence_v1({})
    logger.info(f"Test 5 (Empty Input): Score = {conf5:.4f}")

    logger.info("--- Confidence Score Test Complete ---")


# END OF FILE: src/analysis/confidence.py
