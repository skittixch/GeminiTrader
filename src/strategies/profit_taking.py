# START OF FILE: src/strategies/profit_taking.py

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List  # Added List

# --- Add project root to sys.path ---
import os
import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
# --- End sys.path modification ---

# Import disabled for now until implemented in formatting.py
# try:
#     from src.utils.formatting import apply_filter_rules_to_price # For price adjustments
# except ImportError:
#      # Define dummy if needed for basic script structure, but real import is crucial
#     def apply_filter_rules_to_price(symbol: str, price: Decimal, exchange_info: Dict, filters_to_apply: List[str] = ['PRICE_FILTER'], operation: str = 'adjust') -> Optional[Decimal]:
#         print("WARNING: Dummy apply_filter_rules_to_price called!")
#         return price # Passthrough dummy

# --- Dummy function placeholder (remove when real import works) ---


def apply_filter_rules_to_price(symbol: str, price: Decimal, exchange_info: Dict, filters_to_apply: List[str] = ['PRICE_FILTER'], operation: str = 'adjust') -> Optional[Decimal]:
    logger.warning(
        "DUMMY apply_filter_rules_to_price called! Returning unadjusted price.")
    # Basic quantization as a fallback
    return price.quantize(Decimal('1e-8'), ROUND_HALF_UP)
# --- End Dummy ---


logger = logging.getLogger(__name__)

# --- Constants / Configuration Keys ---
TP_METHOD_KEY = 'tp_method'
TP_VALUE_KEY = 'tp_value'
CONFIDENCE_MULTIPLIER_LOW_KEY = 'confidence_multiplier_low'
CONFIDENCE_MULTIPLIER_MED_KEY = 'confidence_multiplier_medium'
CONFIDENCE_MULTIPLIER_HIGH_KEY = 'confidence_multiplier_high'

# --- Profit Taking Logic ---


def calculate_dynamic_tp_price(
    entry_price: Decimal,
    current_atr: Optional[Decimal],
    config: Dict[str, Any],
    # Still accept symbol_info, even if filters not applied yet
    symbol_info: Optional[Dict[str, Any]],
    confidence_score: Optional[float] = None
) -> Optional[Decimal]:
    """
    Calculates a dynamic take-profit price based on entry price, volatility (ATR),
    configuration settings, and optionally a confidence score.
    *** NOTE: Filter application is currently DISABLED (using dummy function). ***
    """
    # Input validation remains the same...
    if not isinstance(entry_price, Decimal) or entry_price <= Decimal('0'):
        logger.warning(f"Invalid entry_price provided: {entry_price}")
        return None

    tp_config = config.get('strategies', {}).get('profit_taking', {})
    if not tp_config:
        logger.error(
            "Missing 'profit_taking' configuration. Cannot calculate TP.")
        return None
    method = tp_config.get(TP_METHOD_KEY, 'percentage')
    value = tp_config.get(TP_VALUE_KEY)

    try:
        tp_value_decimal = Decimal(str(value)) if value is not None else None
    except Exception as e:
        logger.error(f"Invalid TP value format: '{value}'. Error: {e}")
        return None
    if tp_value_decimal is None:
        logger.error(f"Missing TP value for method '{method}'.")
        return None

    logger.debug(
        f"Calculating TP price. Entry: {entry_price:.4f}, Method: {method}, Value: {tp_value_decimal}, ATR: {current_atr}, Confidence: {confidence_score}")

    target_offset = Decimal('0.0')
    if method == 'percentage':
        if not (Decimal('0') < tp_value_decimal < Decimal('1')):
            logger.warning(
                f"TP Percentage '{tp_value_decimal}' outside expected range (0-1).")
        target_offset = entry_price * tp_value_decimal
    elif method == 'atr_multiple':
        if current_atr is None or not isinstance(current_atr, Decimal) or current_atr <= Decimal('0'):
            logger.warning(
                f"Invalid ATR '{current_atr}' for 'atr_multiple' TP.")
            return None
        target_offset = current_atr * tp_value_decimal
    elif method == 'fixed_amount':
        target_offset = tp_value_decimal
    else:
        logger.error(f"Unknown TP method: '{method}'")
        return None

    # --- Apply Confidence Modulation (remains the same) ---
    if confidence_score is not None:
        # Using tiered multipliers from config
        # Import to_decimal if available, otherwise use Decimal directly
        try:
            from src.utils.formatting import to_decimal
        except ImportError:
            to_decimal = Decimal

        conf_mult_low = to_decimal(tp_config.get(
            CONFIDENCE_MULTIPLIER_LOW_KEY, '0.8'))
        conf_mult_med = to_decimal(tp_config.get(
            CONFIDENCE_MULTIPLIER_MED_KEY, '1.0'))
        conf_mult_high = to_decimal(tp_config.get(
            CONFIDENCE_MULTIPLIER_HIGH_KEY, '1.2'))
        low_thresh, high_thresh = 0.4, 0.7
        confidence_multiplier = conf_mult_med
        try:
            score = float(confidence_score)
            if score < low_thresh:
                confidence_multiplier = conf_mult_low
            elif score >= high_thresh:
                confidence_multiplier = conf_mult_high
            original_offset = target_offset
            target_offset *= confidence_multiplier
            logger.debug(
                f"Applied confidence ({score:.2f}). Multiplier: {confidence_multiplier}. Offset: {original_offset:.4f} -> {target_offset:.4f}")
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Invalid confidence_score ({confidence_score}): {e}. Skipping modulation.")

    # --- Calculate Final Target Price ---
    target_price = entry_price + target_offset

    if target_price <= entry_price:
        logger.warning(
            f"Calculated TP price ({target_price:.4f}) <= entry price ({entry_price:.4f}).")
        return None

    # --- Apply Exchange Filters (DISABLED - USING DUMMY) ---
    symbol = symbol_info.get('symbol') if symbol_info else None
    final_price = apply_filter_rules_to_price(
        symbol=symbol if symbol else "UNKNOWN",  # Pass symbol if known
        price=target_price,
        # Pass required structure if info available
        exchange_info={'symbols': [symbol_info]} if symbol_info else {},
        operation='adjust'
    )
    if final_price is None:  # Dummy currently won't return None unless error
        logger.error(
            f"Dummy filter application failed for TP price {target_price:.4f}.")
        return None  # Should not happen with current dummy

    # Re-check after dummy adjustment (which might just quantize)
    if final_price <= entry_price:
        logger.warning(
            f"TP price ({target_price:.4f}) after dummy adjustment ({final_price:.4f}) is <= entry price ({entry_price:.4f}).")
        return None

    logger.info(
        f"Calculated TP price: {final_price:.4f} (Original: {target_price:.4f}, Entry: {entry_price:.4f}) *** Filter application is currently using a DUMMY ***")
    return final_price


# --- Example Usage (remains the same, but uses dummy filter) ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Profit Taking Logic (with DUMMY filters) ---")
    mock_entry_price = Decimal('84500.1234')
    mock_atr = Decimal('450.56')
    mock_config = {
        'strategies': {
            'profit_taking': {
                'tp_method': 'atr_multiple', 'tp_value': '1.5',
                'confidence_multiplier_low': '0.7', 'confidence_multiplier_medium': '1.0', 'confidence_multiplier_high': '1.4'
            }
        }
    }
    mock_symbol_info = {  # Still needed for structure, even if filters are dummy
        'symbol': 'BTCUSD', 'status': 'TRADING',
        'filters': [{'filterType': 'PRICE_FILTER', 'tickSize': '0.01'}],
    }

    # Test cases (will log warnings about dummy filter)
    logger.info("\nTest 1: Basic ATR Multiple")
    tp1 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_symbol_info)
    logger.info(f"Test 1 Result: {tp1}")

    logger.info("\nTest 2: ATR Multiple (Low Confidence)")
    tp2 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_symbol_info, confidence_score=0.2)
    logger.info(f"Test 2 Result: {tp2}")

    logger.info("\nTest 3: ATR Multiple (High Confidence)")
    tp3 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_symbol_info, confidence_score=0.85)
    logger.info(f"Test 3 Result: {tp3}")

    logger.info("\nTest 4: Percentage Method (2%)")
    mock_config['strategies']['profit_taking']['tp_method'] = 'percentage'
    mock_config['strategies']['profit_taking']['tp_value'] = '0.02'
    tp4 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_symbol_info, confidence_score=0.6)
    logger.info(f"Test 4 Result: {tp4}")

    logger.info("\nTest 5: Missing ATR")
    mock_config['strategies']['profit_taking']['tp_method'] = 'atr_multiple'
    mock_config['strategies']['profit_taking']['tp_value'] = '1.0'
    tp5 = calculate_dynamic_tp_price(
        mock_entry_price, None, mock_config, mock_symbol_info)
    logger.info(f"Test 5 Result: {tp5}")

    logger.info("\nTest 6: Invalid Method")
    mock_config['strategies']['profit_taking']['tp_method'] = 'magic'
    tp6 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_symbol_info)
    logger.info(f"Test 6 Result: {tp6}")

    logger.info("\nTest 7: TP near entry (Low Confidence)")
    mock_config['strategies']['profit_taking']['tp_method'] = 'atr_multiple'
    mock_config['strategies']['profit_taking']['tp_value'] = '0.05'
    tp7 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_symbol_info, confidence_score=0.1)
    logger.info(f"Test 7 Result: {tp7}")

    logger.info("\n--- Profit Taking Logic Test Complete ---")

# END OF FILE: src/strategies/profit_taking.py
