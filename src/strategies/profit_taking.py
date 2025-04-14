# START OF FILE: src/strategies/profit_taking.py

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List

# --- Add project root ---
import os
import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
# --- End ---

# --- Import REAL filter function ---
try:
    # Import real function and helper
    from src.utils.formatting import apply_filter_rules_to_price, to_decimal
except ImportError:
    # Attempt to set up logger early if possible, otherwise use basic print/logging
    try:
        logger = logging.getLogger(__name__)
        if not logger.hasHandlers():
            # Basic config if no handler
            logging.basicConfig(level=logging.ERROR)
    except NameError:  # If logging itself failed
        import logging
        logging.basicConfig(level=logging.ERROR)
        logger = logging.getLogger(__name__)

    logger.critical(
        "CRITICAL: Failed to import 'apply_filter_rules_to_price' or 'to_decimal' from src.utils.formatting.", exc_info=True)
    # Define dummy only if absolutely necessary to allow script import elsewhere, but it shouldn't run

    def apply_filter_rules_to_price(
        *args, **kwargs) -> Optional[Decimal]: return None
    def to_decimal(v, default=None): return Decimal(
        v) if v is not None else default
    # Consider raising an error immediately instead of dummies:
    # raise ImportError("CRITICAL: Failed to import formatting utilities required for profit_taking.")

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
    # --- UPDATED: Expect FULL exchange info ---
    exchange_info: Optional[Dict[str, Any]],  # Needed by filter function
    # --- Pass symbol explicitly ---
    symbol: str,
    confidence_score: Optional[float] = None
) -> Optional[Decimal]:
    """
    Calculates a dynamic take-profit price based on entry price, volatility (ATR),
    configuration settings, and optionally a confidence score. Applies exchange filters.

    Args:
        entry_price (Decimal): The price at which the position was entered.
        current_atr (Optional[Decimal]): The latest calculated ATR value.
        config (Dict[str, Any]): The main application configuration dictionary.
        exchange_info (Optional[Dict[str, Any]]): The FULL exchange info dictionary.
                                                 Required for applying filter rules.
        symbol (str): The trading symbol (e.g., 'BTCUSD').
        confidence_score (Optional[float]): A score (e.g., 0.0-1.0) indicating conviction.

    Returns:
        Optional[Decimal]: The calculated take-profit price, adjusted for filters,
                           or None if calculation/filtering fails.
    """
    if not isinstance(entry_price, Decimal) or entry_price <= Decimal('0'):
        logger.warning(f"Invalid entry_price: {entry_price}")
        return None
    if not exchange_info:
        logger.error(
            "Exchange info is required for TP calculation (for filters).")
        return None  # Make explicit
    if not symbol:
        logger.error("Symbol is required for TP calculation.")
        return None

    tp_config = config.get('strategies', {}).get('profit_taking', {})
    if not tp_config:
        logger.error("Missing 'profit_taking' config.")
        return None
    method = tp_config.get(TP_METHOD_KEY, 'percentage')
    value = tp_config.get(TP_VALUE_KEY)
    tp_value_decimal = to_decimal(value)  # Use helper
    if tp_value_decimal is None:
        logger.error(
            f"Invalid/Missing TP value '{value}' for method '{method}'.")
        return None

    logger.debug(
        f"Calculating TP price for {symbol}. Entry: {entry_price:.4f}, Method: {method}, Value: {tp_value_decimal}, ATR: {current_atr}, Confidence: {confidence_score}")

    target_offset = Decimal('0.0')
    if method == 'percentage':
        if not (Decimal('0') < tp_value_decimal < Decimal('1')):
            logger.warning(f"TP % '{tp_value_decimal}' outside range (0-1).")
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

    # Confidence Modulation
    if confidence_score is not None:
        # Use helper 'to_decimal' with defaults
        conf_mult_low = to_decimal(tp_config.get(
            CONFIDENCE_MULTIPLIER_LOW_KEY, '0.8'), Decimal('0.8'))
        conf_mult_med = to_decimal(tp_config.get(
            CONFIDENCE_MULTIPLIER_MED_KEY, '1.0'), Decimal('1.0'))
        conf_mult_high = to_decimal(tp_config.get(
            CONFIDENCE_MULTIPLIER_HIGH_KEY, '1.2'), Decimal('1.2'))
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
                f"Invalid confidence_score ({confidence_score}): {e}. Skip modulation.")

    # Calculate Target Price
    target_price = entry_price + target_offset
    if target_price <= entry_price:
        logger.warning(
            f"TP price ({target_price:.4f}) <= entry ({entry_price:.4f}).")
        return None

    # --- Apply Exchange Filters (Using REAL Function) ---
    # Operation choice for TP (limit sell above market): 'ceil' might be safer to guarantee the price is above
    # the unadjusted target if rounding occurs, increasing likelihood of fill if market touches it.
    # Let's try 'ceil'. 'adjust' rounds to nearest.
    tp_filter_operation = 'ceil'
    final_price = apply_filter_rules_to_price(
        symbol=symbol,
        price=target_price,
        exchange_info=exchange_info,  # Pass full exchange info
        operation=tp_filter_operation
    )

    if final_price is None:
        logger.error(
            f"Failed to apply price filter rules (Op: {tp_filter_operation}) for {symbol} to TP price {target_price:.4f}.")
        return None  # Filter application failed

    # Re-check if filter adjustment made price <= entry_price
    if final_price <= entry_price:
        logger.warning(
            f"TP price ({target_price:.4f}) after filter adjustment ({final_price:.4f}) is <= entry price ({entry_price:.4f}). Cannot place TP.")
        return None

    logger.info(
        f"Calculated TP price for {symbol}: {final_price:.4f} (Original: {target_price:.4f}, Entry: {entry_price:.4f})")
    return final_price


# --- Example Usage (Now uses REAL filters) ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Profit Taking Logic (with REAL filters) ---")

    # Mock Data
    mock_symbol = "BTCUSD"
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
    # Mock FULL exchange info structure
    mock_exchange_info = {
        "symbols": [
            {
                "symbol": "BTCUSD", "status": "TRADING",
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01",
                        "maxPrice": "1000000.00", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.00001",
                        "maxQty": "100.0", "stepSize": "0.00001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"}
                ]
            },
            {  # Add another symbol for completeness
                "symbol": "ETHUSD", "status": "TRADING",
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01",
                     "maxPrice": "100000.00", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.0001",
                     "maxQty": "1000.0", "stepSize": "0.0001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"}
                ]
            }
        ]
    }

    # Test Cases
    logger.info("\nTest 1: Basic ATR Multiple")
    tp1 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_exchange_info, mock_symbol)
    # Expect adjustment to tickSize 0.01 (using ceil)
    logger.info(f"Test 1 Result: {tp1}")

    logger.info("\nTest 2: ATR Multiple (Low Confidence)")
    tp2 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_exchange_info, mock_symbol, confidence_score=0.2)
    logger.info(f"Test 2 Result: {tp2}")

    logger.info("\nTest 3: ATR Multiple (High Confidence)")
    tp3 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_exchange_info, mock_symbol, confidence_score=0.85)
    logger.info(f"Test 3 Result: {tp3}")

    logger.info("\nTest 4: Percentage Method (2%)")
    mock_config['strategies']['profit_taking']['tp_method'] = 'percentage'
    mock_config['strategies']['profit_taking']['tp_value'] = '0.02'
    tp4 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_exchange_info, mock_symbol, confidence_score=0.6)
    logger.info(f"Test 4 Result: {tp4}")

    logger.info("\nTest 5: Missing ATR")
    mock_config['strategies']['profit_taking']['tp_method'] = 'atr_multiple'
    mock_config['strategies']['profit_taking']['tp_value'] = '1.0'
    tp5 = calculate_dynamic_tp_price(
        mock_entry_price, None, mock_config, mock_exchange_info, mock_symbol)
    logger.info(f"Test 5 Result: {tp5}")  # Should be None

    logger.info("\nTest 6: Invalid Method")
    mock_config['strategies']['profit_taking']['tp_method'] = 'magic'
    tp6 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_exchange_info, mock_symbol)
    logger.info(f"Test 6 Result: {tp6}")  # Should be None

    logger.info("\nTest 7: TP near entry (Low Confidence + filter)")
    mock_config['strategies']['profit_taking']['tp_method'] = 'atr_multiple'
    # Very small ATR multiple
    mock_config['strategies']['profit_taking']['tp_value'] = '0.0001'
    tp7 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, mock_exchange_info, mock_symbol, confidence_score=0.1)
    # Should be adjusted up slightly by ceil
    logger.info(f"Test 7 Result: {tp7}")

    logger.info("\nTest 8: Missing Exchange Info")
    tp8 = calculate_dynamic_tp_price(
        mock_entry_price, mock_atr, mock_config, None, mock_symbol)
    logger.info(f"Test 8 Result: {tp8}")  # Should be None

    logger.info("\n--- Profit Taking Logic Test Complete ---")

# END OF FILE: src/strategies/profit_taking.py
