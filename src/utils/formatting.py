# START OF FILE: src/utils/formatting.py

import logging
from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_CEILING, ROUND_FLOOR, getcontext, InvalidOperation
from typing import Dict, Optional, Any, List  # Added List

logger = logging.getLogger(__name__)

# --- Helper Function to Safely Convert to Decimal ---


def to_decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """Safely converts a value to Decimal, handling None, strings, floats."""
    if value is None:
        return default
    try:
        # Handle float conversion carefully
        if isinstance(value, float):
            value_str = f"{value:.16g}"  # Use 'g' for general format
        else:
            value_str = str(value)  # Convert others to string first
        return Decimal(value_str)
    except (TypeError, ValueError, InvalidOperation) as e:
        # Debug level might be better
        logger.debug(
            f"Could not convert value '{value}' (type: {type(value)}) to Decimal: {e}")
        return default

# --- Filter Extraction Helpers ---


def get_symbol_info_from_exchange_info(symbol: str, exchange_info: Dict) -> Optional[Dict]:
    """Extracts the specific symbol's dictionary from the full exchange info."""
    if not isinstance(exchange_info, dict) or 'symbols' not in exchange_info:
        logger.warning(
            "Invalid exchange_info structure: 'symbols' key missing or not a dict.")
        return None
    symbols_list = exchange_info['symbols']
    if not isinstance(symbols_list, list):
        logger.warning(
            "Invalid exchange_info structure: 'symbols' is not a list.")
        return None

    for symbol_data in symbols_list:
        if isinstance(symbol_data, dict) and symbol_data.get('symbol') == symbol:
            return symbol_data
    logger.warning(f"Symbol '{symbol}' not found in provided exchange info.")
    return None


def get_symbol_filter(symbol_info: Optional[Dict], filter_type: str) -> Optional[Dict]:
    """Extracts a specific filter dictionary from a symbol's info dictionary."""
    if not isinstance(symbol_info, dict) or 'filters' not in symbol_info:
        # Allow symbol_info to be None without logging warning here, handled by caller
        # logger.debug(f"Invalid symbol_info structure or missing 'filters' key.")
        return None
    filters_list = symbol_info['filters']
    if not isinstance(filters_list, list):
        logger.warning(
            f"Invalid symbol_info structure: 'filters' is not a list for symbol {symbol_info.get('symbol', 'N/A')}.")
        return None

    for f in filters_list:
        if isinstance(f, dict) and f.get('filterType') == filter_type:
            return f
    # Debug log if specific filter type not found for the symbol
    # logger.debug(f"Filter type '{filter_type}' not found for symbol '{symbol_info.get('symbol', 'N/A')}'.")
    return None

# --- Internal Value Adjustment Functions ---


def _adjust_value_by_step(value: Decimal, step_size: Decimal, operation: str = 'adjust') -> Optional[Decimal]:
    """
    Adjusts a value to be a multiple of step_size using different rounding methods.

    Args:
        value (Decimal): The value to adjust.
        step_size (Decimal): The step size (e.g., tickSize, stepSize). Must be > 0.
        operation (str): 'adjust' (nearest), 'floor' (down), 'ceil' (up).

    Returns:
        Optional[Decimal]: Adjusted value or None on error.
    """
    if step_size <= 0:
        logger.error(f"Step size must be positive, got {step_size}")
        return None
    if value is None:
        return None

    try:
        # Calculate remainder and adjust
        remainder = value % step_size
        if remainder == Decimal('0'):
            return value  # Already a multiple

        if operation == 'floor':
            adjusted = value - remainder
        elif operation == 'ceil':
            adjusted = value - remainder + step_size
        elif operation == 'adjust':  # adjust to nearest multiple
            if remainder >= step_size / Decimal('2'):
                adjusted = value - remainder + step_size  # Round up
            else:
                adjusted = value - remainder  # Round down
        else:
            logger.error(f"Unknown adjustment operation: {operation}")
            return None

        # Re-quantize to the step_size precision to avoid floating point issues
        return adjusted.quantize(step_size.normalize())

    except (TypeError, ValueError, InvalidOperation) as e:
        logger.error(
            f"Error adjusting value {value} with step_size {step_size}: {e}")
        return None


def _adjust_price_internal(price: Decimal, symbol_info: Dict, operation: str = 'adjust') -> Optional[Decimal]:
    """Internal: Adjusts price to meet PRICE_FILTER constraints (tickSize, min/max)."""
    price_filter = get_symbol_filter(symbol_info, 'PRICE_FILTER')
    if not price_filter:
        logger.warning(
            f"PRICE_FILTER not found for {symbol_info.get('symbol', 'N/A')}. Returning original price.")
        # Decide if this is an error or acceptable. For safety, maybe return None?
        # Let's return original for now, assuming maybe filter isn't strictly needed.
        # Consider adding a strict mode later.
        return price  # Or return None if filter *must* exist

    tick_size = to_decimal(price_filter.get('tickSize'))
    if tick_size is None or tick_size <= 0:
        logger.error(
            f"Invalid tickSize in PRICE_FILTER for {symbol_info.get('symbol', 'N/A')}")
        return None

    # Adjust to be multiple of tick_size
    adjusted_price = _adjust_value_by_step(price, tick_size, operation)
    if adjusted_price is None:
        return None  # Error during adjustment

    # Check min/max price
    min_price = to_decimal(price_filter.get('minPrice'))
    max_price = to_decimal(price_filter.get('maxPrice'))
    if min_price is not None and adjusted_price < min_price:
        logger.warning(f"Price {adjusted_price} below minPrice {min_price}")
        return None  # Fail if below min
    if max_price is not None and adjusted_price > max_price:
        logger.warning(f"Price {adjusted_price} above maxPrice {max_price}")
        return None  # Fail if above max

    return adjusted_price


def _adjust_qty_internal(quantity: Decimal, symbol_info: Dict, operation: str = 'adjust') -> Optional[Decimal]:
    """Internal: Adjusts quantity to meet LOT_SIZE constraints (stepSize, min/max)."""
    lot_size_filter = get_symbol_filter(symbol_info, 'LOT_SIZE')
    if not lot_size_filter:
        logger.warning(
            f"LOT_SIZE filter not found for {symbol_info.get('symbol', 'N/A')}. Returning original qty.")
        return quantity

    step_size = to_decimal(lot_size_filter.get('stepSize'))
    if step_size is None or step_size <= 0:
        logger.error(
            f"Invalid stepSize in LOT_SIZE for {symbol_info.get('symbol', 'N/A')}")
        return None

    # Adjust to be multiple of step_size (typically floor for orders)
    # Default internal adjust to floor for qty
    op = 'floor' if operation == 'adjust' else operation
    adjusted_qty = _adjust_value_by_step(quantity, step_size, op)
    if adjusted_qty is None:
        return None

    # Check min/max quantity
    min_qty = to_decimal(lot_size_filter.get('minQty'))
    max_qty = to_decimal(lot_size_filter.get('maxQty'))
    if min_qty is not None and adjusted_qty < min_qty:
        logger.warning(f"Qty {adjusted_qty} below minQty {min_qty}")
        return None  # Fail if below min
    if max_qty is not None and adjusted_qty > max_qty:
        logger.warning(f"Qty {adjusted_qty} above maxQty {max_qty}")
        return None  # Fail if above max

    return adjusted_qty


def _check_min_notional_internal(price: Decimal, quantity: Decimal, symbol_info: Dict) -> bool:
    """Internal: Checks if the order meets the MIN_NOTIONAL filter."""
    min_notional_filter = get_symbol_filter(symbol_info, 'MIN_NOTIONAL')
    if not min_notional_filter:
        return True  # Pass if filter doesn't exist

    min_notional = to_decimal(min_notional_filter.get('minNotional'))
    if min_notional is None or min_notional <= 0:
        logger.error(
            f"Invalid minNotional in MIN_NOTIONAL for {symbol_info.get('symbol', 'N/A')}")
        return False

    if price is None or quantity is None:
        logger.warning("Price/Qty None for min_notional check.")
        return False

    try:
        notional_value = price * quantity
        passes = notional_value >= min_notional
        if not passes:
            logger.debug(
                f"Order notional {notional_value:.8f} < MIN_NOTIONAL {min_notional:.8f}")
        # else: logger.debug(f"Order notional {notional_value:.8f} >= MIN_NOTIONAL {min_notional:.8f}")
        return passes
    except Exception as e:
        logger.error(
            f"Error calculating notional value (P:{price}, Q:{quantity}): {e}")
        return False

# --- Public Filter Application Functions ---


def apply_filter_rules_to_price(
    symbol: str,
    price: Decimal,
    exchange_info: Dict,
    operation: str = 'adjust'
) -> Optional[Decimal]:
    """
    Applies PRICE_FILTER rules (tickSize, minPrice, maxPrice) to a given price.

    Args:
        symbol (str): The trading symbol (e.g., 'BTCUSD').
        price (Decimal): The price to adjust.
        exchange_info (Dict): The FULL exchange info dictionary containing data for all symbols.
        operation (str): How to adjust to tickSize: 'adjust' (nearest), 'floor', 'ceil'.

    Returns:
        Optional[Decimal]: The adjusted price if valid according to filters, otherwise None.
    """
    symbol_info = get_symbol_info_from_exchange_info(symbol, exchange_info)
    if not symbol_info:
        logger.error(
            f"Cannot apply price filters: Symbol '{symbol}' not found in exchange info.")
        return None  # Cannot proceed without symbol info

    if price is None:
        logger.warning("Input price is None, cannot apply filters.")
        return None

    return _adjust_price_internal(price, symbol_info, operation)


def apply_filter_rules_to_qty(
    symbol: str,
    quantity: Decimal,
    exchange_info: Dict,
    operation: str = 'floor'  # Default to floor for quantity adjustment
) -> Optional[Decimal]:
    """
    Applies LOT_SIZE filter rules (stepSize, minQty, maxQty) to a given quantity.

    Args:
        symbol (str): The trading symbol (e.g., 'BTCUSD').
        quantity (Decimal): The quantity to adjust.
        exchange_info (Dict): The FULL exchange info dictionary containing data for all symbols.
        operation (str): How to adjust to stepSize: 'adjust' (nearest), 'floor', 'ceil'.
                         Defaults to 'floor' as typically required for orders.

    Returns:
        Optional[Decimal]: The adjusted quantity if valid according to filters, otherwise None.
    """
    symbol_info = get_symbol_info_from_exchange_info(symbol, exchange_info)
    if not symbol_info:
        logger.error(
            f"Cannot apply quantity filters: Symbol '{symbol}' not found in exchange info.")
        return None

    if quantity is None:
        logger.warning("Input quantity is None, cannot apply filters.")
        return None

    return _adjust_qty_internal(quantity, symbol_info, operation)


def validate_order_filters(
    symbol: str,
    price: Decimal,
    quantity: Decimal,
    exchange_info: Dict
) -> bool:
    """
    Validates if a given price and quantity combination satisfies MIN_NOTIONAL filter.
    (Assumes price and quantity have already been adjusted for tick/step size if necessary).

    Args:
        symbol (str): The trading symbol (e.g., 'BTCUSD').
        price (Decimal): The proposed order price (should ideally be pre-adjusted).
        quantity (Decimal): The proposed order quantity (should ideally be pre-adjusted).
        exchange_info (Dict): The FULL exchange info dictionary.

    Returns:
        bool: True if the order meets MIN_NOTIONAL (or if filter doesn't exist), False otherwise.
    """
    symbol_info = get_symbol_info_from_exchange_info(symbol, exchange_info)
    if not symbol_info:
        logger.error(
            f"Cannot validate MIN_NOTIONAL: Symbol '{symbol}' not found in exchange info.")
        return False  # Fail if symbol info not found

    return _check_min_notional_internal(price, quantity, symbol_info)


# --- Deprecated? Keep for compatibility? Decide later ---
# def apply_filter_rules( ... ): <-- The old function working on dict
# This function might still be useful internally but the new functions are more granular.
# Let's keep it for now but perhaps mark as potentially deprecated or for internal use.


# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Formatting Utilities ---")

    # Mock exchange info structure
    mock_exchange_info = {
        "symbols": [
            {
                "symbol": "BTCUSD",
                "status": "TRADING",
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01",
                        "maxPrice": "1000000.00", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.00001",
                        "maxQty": "100.0", "stepSize": "0.00001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"}
                ]
            },
            {
                "symbol": "ETHUSD",
                "status": "TRADING",
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.01",
                        "maxPrice": "100000.00", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.0001",
                        "maxQty": "1000.0", "stepSize": "0.0001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"}
                ]
            }
        ]
        # Add other exchange info keys if needed by other functions
    }

    # Test Price Adjustment
    logger.info("\n--- Testing Price Adjustment ---")
    raw_price = Decimal('84123.4567')
    adjusted_price = apply_filter_rules_to_price(
        "BTCUSD", raw_price, mock_exchange_info, operation='adjust')
    floored_price = apply_filter_rules_to_price(
        "BTCUSD", raw_price, mock_exchange_info, operation='floor')
    ceiled_price = apply_filter_rules_to_price(
        "BTCUSD", raw_price, mock_exchange_info, operation='ceil')
    logger.info(f"Raw Price: {raw_price}")
    logger.info(f"Adjusted Price (adjust): {adjusted_price}")
    logger.info(f"Adjusted Price (floor): {floored_price}")
    logger.info(f"Adjusted Price (ceil): {ceiled_price}")
    invalid_price = apply_filter_rules_to_price(
        "BTCUSD", Decimal('0.001'), mock_exchange_info)  # Below minPrice
    logger.info(f"Invalid Low Price Result: {invalid_price}")
    invalid_price_symbol = apply_filter_rules_to_price(
        "XYZUSD", raw_price, mock_exchange_info)
    logger.info(f"Invalid Symbol Price Result: {invalid_price_symbol}")

    # Test Quantity Adjustment
    logger.info("\n--- Testing Quantity Adjustment ---")
    raw_qty = Decimal('0.12345678')
    adjusted_qty_floor = apply_filter_rules_to_qty(
        "BTCUSD", raw_qty, mock_exchange_info, operation='floor')
    adjusted_qty_ceil = apply_filter_rules_to_qty(
        "BTCUSD", raw_qty, mock_exchange_info, operation='ceil')
    adjusted_qty_adjust = apply_filter_rules_to_qty(
        # Should default to floor internally
        "BTCUSD", raw_qty, mock_exchange_info, operation='adjust')
    logger.info(f"Raw Qty: {raw_qty}")
    logger.info(f"Adjusted Qty (floor): {adjusted_qty_floor}")
    logger.info(f"Adjusted Qty (ceil): {adjusted_qty_ceil}")
    # Should be same as floor
    logger.info(f"Adjusted Qty (adjust): {adjusted_qty_adjust}")
    invalid_qty = apply_filter_rules_to_qty("BTCUSD", Decimal(
        '0.000001'), mock_exchange_info)  # Below minQty
    logger.info(f"Invalid Low Qty Result: {invalid_qty}")
    invalid_qty_symbol = apply_filter_rules_to_qty(
        "XYZUSD", raw_qty, mock_exchange_info)
    logger.info(f"Invalid Symbol Qty Result: {invalid_qty_symbol}")

    # Test Min Notional Validation
    logger.info("\n--- Testing Min Notional ---")
    valid_order_p = Decimal('84000.00')
    valid_order_q = Decimal('0.0002')  # 84000 * 0.0002 = 16.8 ( > 10)
    invalid_order_q = Decimal('0.0001')  # 84000 * 0.0001 = 8.4 ( < 10)
    check1 = validate_order_filters(
        "BTCUSD", valid_order_p, valid_order_q, mock_exchange_info)
    logger.info(
        f"Min Notional Check (Valid: {valid_order_p} * {valid_order_q}): {check1}")
    check2 = validate_order_filters(
        "BTCUSD", valid_order_p, invalid_order_q, mock_exchange_info)
    logger.info(
        f"Min Notional Check (Invalid: {valid_order_p} * {invalid_order_q}): {check2}")
    check3 = validate_order_filters(
        "NOSYMBOL", valid_order_p, valid_order_q, mock_exchange_info)
    logger.info(f"Min Notional Check (Invalid Symbol): {check3}")

    logger.info("\n--- Formatting Utilities Test Complete ---")


# END OF FILE: src/utils/formatting.py
