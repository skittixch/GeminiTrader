# src/strategies/simple_tp.py

import logging
from decimal import Decimal, ROUND_UP, InvalidOperation
from typing import Dict, Optional, Union

# --- Add project root to sys.path FIRST (for testing block) ---
import os
import sys
_project_root_for_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root_for_path not in sys.path:
    sys.path.insert(0, _project_root_for_path)
# --- End sys.path modification ---

# --- Project Imports ---
try:
    # We might need filter adjustments for the calculated TP price
    from src.utils.formatting import adjust_price_to_filter, get_symbol_filter, to_decimal
    from src.utils.logging_setup import setup_logging  # For test block
except ImportError as e:
    print(f"ERROR: Could not import project modules. Error: {e}")
    print(f"Project Root (calculated for path): {_project_root_for_path}")
    print(f"System Path: {sys.path}")
    # Define dummy functions if running standalone for basic tests, but prefer failing

    def adjust_price_to_filter(price: Decimal, filters: Dict) -> Optional[Decimal]:
        print("WARNING: Using dummy adjust_price_to_filter")
        if price is None:
            return None
        tick_size = Decimal(filters.get('filters', [{}])[0].get(
            'tickSize', '0.01'))  # simplified dummy
        return (price / tick_size).to_integral_value(rounding=ROUND_UP) * tick_size

    def get_symbol_filter(filters: Dict, filter_type: str) -> Optional[Dict]:
        print("WARNING: Using dummy get_symbol_filter")
        if filter_type == 'PRICE_FILTER':
            return {'tickSize': '0.01'}
        return None

    def to_decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
        print("WARNING: Using dummy to_decimal")
        try:
            return Decimal(value)
        except:
            return default
    # Need setup_logging dummy only if the real one fails import
    # raise ImportError("Failed to import required project modules.") from e # Better to fail

# --- End Project Imports ---

logger = logging.getLogger(__name__)


def calculate_fixed_tp_price(
    entry_price: Decimal,
    method: str = 'percentage',  # 'percentage' or 'atr'
    # Percentage (e.g., 0.02 for 2%) or ATR multiple (e.g., 1.5)
    value: Decimal = Decimal('0.02'),
    atr: Optional[Decimal] = None,  # Required if method is 'atr'
    # Optional: For adjusting TP price to tick size
    exchange_filters: Optional[Dict] = None
) -> Optional[Decimal]:
    """
    Calculates a simple fixed Take Profit price based on entry price.

    Args:
        entry_price (Decimal): The execution price of the buy order.
        method (str): The calculation method ('percentage' or 'atr'). Default 'percentage'.
        value (Decimal): The value to use for the chosen method.
                         - For 'percentage': The desired profit percentage (e.g., 0.02 for 2%).
                         - For 'atr': The multiple of ATR to add (e.g., 1.5 for 1.5 * ATR).
        atr (Optional[Decimal]): The Average True Range value. Required if method is 'atr'.
        exchange_filters (Optional[Dict]): Exchange filter info for the symbol. If provided,
                                           the calculated TP price will be adjusted to the
                                           PRICE_FILTER tickSize (rounded up).

    Returns:
        Optional[Decimal]: The calculated Take Profit price, adjusted to filters if provided,
                           or None if inputs are invalid or calculation fails.
    """
    if entry_price <= 0:
        logger.error("Entry price must be positive.")
        return None
    if value <= 0:
        logger.error("Percentage or ATR multiple value must be positive.")
        return None

    calculated_tp = None

    if method == 'percentage':
        try:
            calculated_tp = entry_price * (Decimal('1.0') + value)
            logger.debug(
                f"Calculated TP (percentage): {entry_price} * (1 + {value}) = {calculated_tp}")
        except InvalidOperation as e:
            logger.error(f"Error calculating percentage TP: {e}")
            return None

    elif method == 'atr':
        if atr is None or atr <= 0:
            logger.error(
                "ATR value must be provided and positive for 'atr' method.")
            return None
        try:
            calculated_tp = entry_price + (atr * value)
            logger.debug(
                f"Calculated TP (ATR): {entry_price} + ({atr} * {value}) = {calculated_tp}")
        except InvalidOperation as e:
            logger.error(f"Error calculating ATR-based TP: {e}")
            return None

    else:
        logger.error(
            f"Invalid TP calculation method specified: {method}. Use 'percentage' or 'atr'.")
        return None

    if calculated_tp is None or calculated_tp <= entry_price:
        logger.warning(
            f"Calculated TP ({calculated_tp}) is not above entry price ({entry_price}). Cannot set TP.")
        return None  # TP must be above entry

    # --- Optional: Adjust TP to Exchange Filters ---
    if exchange_filters:
        logger.debug(
            f"Attempting to adjust TP price {calculated_tp} using filters.")
        # Note: For TP (SELL), we generally round UP to the nearest tick size
        # to ensure we get filled at or above the target.
        # We need to modify adjust_price_to_filter or create a variant for SELL rounding.
        # Let's assume adjust_price_to_filter handles rounding appropriately based on side later,
        # or we modify it now. For simplicity, let's use a simple ROUND_UP for now.

        price_filter = get_symbol_filter(exchange_filters, 'PRICE_FILTER')
        if price_filter:
            tick_size_str = price_filter.get('tickSize')
            tick_size = to_decimal(tick_size_str)
            if tick_size and tick_size > 0:
                try:
                    # Round UP to the nearest tick size
                    adjusted_tp = (
                        calculated_tp / tick_size).to_integral_value(rounding=ROUND_UP) * tick_size
                    # Re-quantize to the precision of the tick size
                    adjusted_tp = adjusted_tp.quantize(
                        tick_size.normalize(), rounding=ROUND_UP)

                    # Check min/max price from filter
                    min_price = to_decimal(price_filter.get('minPrice'))
                    max_price = to_decimal(price_filter.get('maxPrice'))
                    if min_price is not None and adjusted_tp < min_price:
                        logger.warning(
                            f"Adjusted TP {adjusted_tp} is below minPrice {min_price}. Cannot set TP.")
                        return None
                    if max_price is not None and adjusted_tp > max_price:
                        logger.warning(
                            f"Adjusted TP {adjusted_tp} is above maxPrice {max_price}. Cannot set TP.")
                        return None

                    if adjusted_tp > calculated_tp:  # Log if adjustment increased the TP
                        logger.debug(
                            f"Adjusted TP price rounded up from {calculated_tp} to {adjusted_tp} based on tickSize {tick_size}")
                    else:
                        logger.debug(
                            f"TP price {calculated_tp} already met tickSize {tick_size} or adjusted TP was not higher.")
                        adjusted_tp = calculated_tp  # Use original if adjustment didn't increase it

                    calculated_tp = adjusted_tp
                except (InvalidOperation, TypeError, ValueError) as e:
                    logger.error(
                        f"Error adjusting TP price {calculated_tp} to tick size {tick_size}: {e}")
                    # Return unadjusted TP or None? Let's return None if adjustment fails.
                    return None
            else:
                logger.warning(
                    f"Invalid tickSize '{tick_size_str}' found. Cannot adjust TP price.")
        else:
            logger.warning("PRICE_FILTER not found. Cannot adjust TP price.")

    # Log with precision
    logger.info(f"Final calculated TP price: {calculated_tp:.8f}")
    return calculated_tp


# --- Example Usage / Testing Block ---
if __name__ == '__main__':
    from pathlib import Path

    # Setup basic logging for testing
    project_root = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    log_file_path = Path(project_root) / "data" / "logs" / "test_simple_tp.log"
    # Use the real setup_logging if available
    try:
        setup_logging(log_file=log_file_path,
                      console_logging=True, log_level=logging.DEBUG)
    except NameError:  # Fallback if import failed and dummy wasn't raised
        print("WARNING: Real setup_logging not found, using basic config.")
        logging.basicConfig(
            level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("--- Starting Simple TP Test ---")

    # Mock Inputs
    entry = Decimal('65000.50')
    percent_val = Decimal('0.015')  # 1.5%
    atr_val = Decimal('850.25')
    atr_mult = Decimal('1.2')

    # Mock Filters (similar structure to previous test)
    test_filters_tp = {
        'symbol': 'BTCUSD',
        'filters': [
            {'filterType': 'PRICE_FILTER', 'minPrice': '0.01',
                'maxPrice': '1000000.00', 'tickSize': '0.01'},
            # Other filters not directly used by this function but good practice to have
            {'filterType': 'LOT_SIZE', 'minQty': '0.00001',
             'maxQty': '100.0', 'stepSize': '0.00001'},
            {'filterType': 'MIN_NOTIONAL', 'minNotional': '10.0',
             'applyToMarket': True, 'avgPriceMins': 5}
        ]
    }

    # --- Test Cases ---
    logger.info("\n--- Test 1: Percentage TP (No Filters) ---")
    tp1 = calculate_fixed_tp_price(
        entry_price=entry, method='percentage', value=percent_val)
    logger.info(
        f"Entry: {entry}, Target: {percent_val*100}%, Calculated TP: {tp1}")

    logger.info("\n--- Test 2: ATR TP (No Filters) ---")
    tp2 = calculate_fixed_tp_price(
        entry_price=entry, method='atr', value=atr_mult, atr=atr_val)
    logger.info(
        f"Entry: {entry}, Target: {atr_mult} * ATR ({atr_val}), Calculated TP: {tp2}")

    logger.info("\n--- Test 3: Percentage TP (With Filters) ---")
    tp3 = calculate_fixed_tp_price(
        entry_price=entry, method='percentage', value=percent_val, exchange_filters=test_filters_tp)
    logger.info(
        f"Entry: {entry}, Target: {percent_val*100}%, Filters: Yes, Calculated TP: {tp3}")

    logger.info("\n--- Test 4: ATR TP (With Filters) ---")
    tp4 = calculate_fixed_tp_price(entry_price=entry, method='atr',
                                   value=atr_mult, atr=atr_val, exchange_filters=test_filters_tp)
    logger.info(
        f"Entry: {entry}, Target: {atr_mult} * ATR ({atr_val}), Filters: Yes, Calculated TP: {tp4}")

    logger.info("\n--- Test 5: Invalid Method ---")
    tp5 = calculate_fixed_tp_price(
        entry_price=entry, method='wrong', value=percent_val)
    logger.info(f"Entry: {entry}, Method: 'wrong', Calculated TP: {tp5}")

    logger.info("\n--- Test 6: Missing ATR for ATR method ---")
    tp6 = calculate_fixed_tp_price(
        entry_price=entry, method='atr', value=atr_mult)
    logger.info(
        f"Entry: {entry}, Method: 'atr', ATR: None, Calculated TP: {tp6}")

    logger.info(
        "\n--- Test 7: TP Below Entry (e.g., negative percentage - should fail) ---")
    tp7 = calculate_fixed_tp_price(
        entry_price=entry, method='percentage', value=Decimal('-0.01'))
    logger.info(f"Entry: {entry}, Target: -1%, Calculated TP: {tp7}")

    logger.info("\n--- Test 8: TP exactly at tick size ---")
    entry_exact = Decimal('65000.00')
    percent_exact = (Decimal('65000.01') / entry_exact) - \
        1  # Should result in 65000.01
    tp8 = calculate_fixed_tp_price(
        entry_price=entry_exact, method='percentage', value=percent_exact, exchange_filters=test_filters_tp)
    logger.info(
        f"Entry: {entry_exact}, Target: Small %, Filters: Yes, Calculated TP: {tp8}")

    logger.info("\n--- Simple TP Test Complete ---")

# File path: src/strategies/simple_tp.py
