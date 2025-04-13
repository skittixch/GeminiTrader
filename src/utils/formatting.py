# src/utils/formatting.py

import logging
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext, InvalidOperation
from typing import Dict, Optional, Any, List

logger = logging.getLogger(__name__)

# --- Helper Function to Safely Convert to Decimal ---


def to_decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    """Safely converts a value to Decimal, handling None, strings, floats."""
    if value is None:
        return default
    try:
        # Handle potential floating point inaccuracies if converting from float
        # Best practice is to receive strings or integers for Decimal conversion
        if isinstance(value, float):
            # Convert float to string first for exact representation
            value_str = f"{value:.16f}"  # Adjust precision as needed
            return Decimal(value_str)
        # Allow direct Decimal, int, or string conversion
        return Decimal(value)
    except (TypeError, ValueError, InvalidOperation) as e:
        logger.warning(
            f"Could not convert value '{value}' (type: {type(value)}) to Decimal: {e}")
        return default

# --- Filter Extraction Helper ---


def get_symbol_filter(exchange_filters: Dict, filter_type: str) -> Optional[Dict]:
    """
    Extracts a specific filter dictionary from the exchange info filter list.

    Args:
        exchange_filters (Dict): The dictionary for a specific symbol from exchange info,
                                 expected to contain a 'filters' key with a list of filter dicts.
                                 Example structure: {'symbol': 'BTCUSD', 'filters': [...]}
        filter_type (str): The 'filterType' to find (e.g., 'PRICE_FILTER', 'LOT_SIZE').

    Returns:
        Optional[Dict]: The dictionary for the matching filter, or None if not found.
    """
    if not isinstance(exchange_filters, dict) or 'filters' not in exchange_filters:
        logger.warning(
            f"Invalid exchange_filters structure passed to get_symbol_filter: {exchange_filters}")
        return None
    if not isinstance(exchange_filters['filters'], list):
        logger.warning(
            f"exchange_filters['filters'] is not a list: {exchange_filters['filters']}")
        return None

    for f in exchange_filters['filters']:
        if isinstance(f, dict) and f.get('filterType') == filter_type:
            return f
    logger.debug(
        f"Filter type '{filter_type}' not found in filters for symbol '{exchange_filters.get('symbol', 'N/A')}'.")
    return None

# --- Value Adjustment Functions ---


def adjust_price_to_filter(price: Decimal, filters: Dict) -> Optional[Decimal]:
    """Adjusts price to meet PRICE_FILTER constraints (tickSize)."""
    price_filter = get_symbol_filter(filters, 'PRICE_FILTER')
    if not price_filter:
        logger.warning(
            f"PRICE_FILTER not found for symbol {filters.get('symbol', 'N/A')}.")
        return None  # Cannot adjust without filter

    tick_size_str = price_filter.get('tickSize')
    if tick_size_str is None:
        logger.error(
            f"PRICE_FILTER found but 'tickSize' missing for symbol {filters.get('symbol', 'N/A')}")
        return None

    tick_size = to_decimal(tick_size_str)
    if tick_size is None or tick_size <= 0:
        logger.error(
            f"Invalid tickSize '{tick_size_str}' in PRICE_FILTER for {filters.get('symbol', 'N/A')}")
        return None

    # Ensure price is a multiple of tick_size, rounding down for BUY orders
    # For SELL orders, you might round up, but for grid planning (BUY), round down.
    if price is None:
        return None
    try:
        adjusted_price = (price // tick_size) * tick_size
        adjusted_price = adjusted_price.quantize(
            tick_size.normalize(), rounding=ROUND_DOWN)

        # Also check min/max price from the filter
        min_price = to_decimal(price_filter.get('minPrice'))
        max_price = to_decimal(price_filter.get('maxPrice'))

        if min_price is not None and adjusted_price < min_price:
            logger.debug(
                f"Adjusted price {adjusted_price} below minPrice {min_price}")
            return None  # Or adjust to min_price? For now, fail.
        if max_price is not None and adjusted_price > max_price:
            logger.debug(
                f"Adjusted price {adjusted_price} above maxPrice {max_price}")
            return None  # Price is too high

        return adjusted_price
    except (TypeError, ValueError, InvalidOperation) as e:
        logger.error(
            f"Error adjusting price {price} with tick_size {tick_size}: {e}")
        return None


def adjust_qty_to_filter(quantity: Decimal, filters: Dict) -> Optional[Decimal]:
    """Adjusts quantity to meet LOT_SIZE constraints (stepSize)."""
    lot_size_filter = get_symbol_filter(filters, 'LOT_SIZE')
    if not lot_size_filter:
        logger.warning(
            f"LOT_SIZE filter not found for symbol {filters.get('symbol', 'N/A')}.")
        return None

    step_size_str = lot_size_filter.get('stepSize')
    if step_size_str is None:
        logger.error(
            f"LOT_SIZE filter found but 'stepSize' missing for symbol {filters.get('symbol', 'N/A')}")
        return None

    step_size = to_decimal(step_size_str)
    if step_size is None or step_size <= 0:
        logger.error(
            f"Invalid stepSize '{step_size_str}' in LOT_SIZE filter for {filters.get('symbol', 'N/A')}")
        return None

    # Ensure quantity is a multiple of step_size, rounding down.
    if quantity is None:
        return None
    try:
        adjusted_qty = (quantity // step_size) * step_size
        adjusted_qty = adjusted_qty.quantize(
            step_size.normalize(), rounding=ROUND_DOWN)

        # Also check min/max quantity
        min_qty = to_decimal(lot_size_filter.get('minQty'))
        max_qty = to_decimal(lot_size_filter.get('maxQty'))

        if min_qty is not None and adjusted_qty < min_qty:
            logger.debug(
                f"Adjusted quantity {adjusted_qty} below minQty {min_qty}")
            # Adjust up to minQty IF possible without exceeding original intent significantly?
            # For now, let's return None if it falls below minQty after adjustment.
            return None
        if max_qty is not None and adjusted_qty > max_qty:
            logger.debug(
                f"Adjusted quantity {adjusted_qty} above maxQty {max_qty}")
            return None  # Exceeds max allowed quantity

        return adjusted_qty
    except (TypeError, ValueError, InvalidOperation) as e:
        logger.error(
            f"Error adjusting quantity {quantity} with step_size {step_size}: {e}")
        return None


def check_min_notional(price: Decimal, quantity: Decimal, filters: Dict) -> bool:
    """Checks if the order meets the MIN_NOTIONAL filter."""
    min_notional_filter = get_symbol_filter(filters, 'MIN_NOTIONAL')
    if not min_notional_filter:
        logger.warning(
            f"MIN_NOTIONAL filter not found for symbol {filters.get('symbol', 'N/A')}. Assuming check passes.")
        return True  # Pass if filter doesn't exist

    min_notional_str = min_notional_filter.get('minNotional')
    if min_notional_str is None:
        logger.error(
            f"MIN_NOTIONAL filter found but 'minNotional' value missing for {filters.get('symbol', 'N/A')}")
        return False  # Fail if filter exists but value is missing

    min_notional = to_decimal(min_notional_str)
    if min_notional is None or min_notional <= 0:
        logger.error(
            f"Invalid minNotional value '{min_notional_str}' for {filters.get('symbol', 'N/A')}")
        return False  # Fail on invalid value

    if price is None or quantity is None:
        logger.warning("Price or quantity is None, cannot check min notional.")
        return False

    try:
        notional_value = price * quantity
        if notional_value < min_notional:
            logger.debug(
                f"Order notional {notional_value:.8f} is less than MIN_NOTIONAL {min_notional:.8f}")
            return False
        else:
            logger.debug(
                f"Order notional {notional_value:.8f} meets MIN_NOTIONAL {min_notional:.8f}")
            return True
    except (TypeError, ValueError, InvalidOperation) as e:
        logger.error(
            f"Error calculating notional value (Price: {price}, Qty: {quantity}): {e}")
        return False


# --- Main Filter Application Function ---
def apply_filter_rules(
    order: Dict,
    exchange_filters: Dict,
    # Required for % price checks later
    current_price: Optional[Decimal] = None
) -> Optional[Dict]:
    """
    Applies exchange filter rules (PRICE_FILTER, LOT_SIZE, MIN_NOTIONAL)
    to a potential order dictionary.

    Modifies 'price' and 'quantity' in the order dictionary in place
    if adjustments are needed and possible.

    Args:
        order (Dict): The proposed order dictionary (must contain 'price', 'quantity').
                      Example: {'symbol': 'BTCUSD', 'side': 'BUY', 'type': 'LIMIT',
                                'quantity': Decimal('0.001'), 'price': Decimal('65000.1234'), ...}
        exchange_filters (Dict): The filter structure for the specific symbol,
                                 as retrieved from exchange info. Should contain 'filters' list.
        current_price (Optional[Decimal]): The current market price, needed for some
                                           filters like PERCENT_PRICE (not implemented yet).

    Returns:
        Optional[Dict]: The modified order dictionary if it passes all checks,
                        otherwise None if any filter fails validation.
    """
    if not all(k in order for k in ['price', 'quantity']):
        logger.error("Order dictionary missing 'price' or 'quantity'.")
        return None

    original_price = to_decimal(order.get('price'))
    original_quantity = to_decimal(order.get('quantity'))

    if original_price is None or original_quantity is None:
        logger.error(
            f"Invalid price or quantity in order: Price={order.get('price')}, Qty={order.get('quantity')}")
        return None

    # 1. Adjust Price
    adjusted_price = adjust_price_to_filter(original_price, exchange_filters)
    if adjusted_price is None:
        logger.warning(
            f"Order price {original_price} failed PRICE_FILTER adjustment or validation for {order.get('symbol')}.")
        return None
    if adjusted_price <= 0:
        logger.warning(f"Adjusted price {adjusted_price} is zero or negative.")
        return None

    # 2. Adjust Quantity (using the *adjusted* price for potential future checks if needed)
    adjusted_quantity = adjust_qty_to_filter(
        original_quantity, exchange_filters)
    if adjusted_quantity is None:
        logger.warning(
            f"Order quantity {original_quantity} failed LOT_SIZE adjustment or validation for {order.get('symbol')}.")
        return None
    if adjusted_quantity <= 0:
        logger.warning(
            f"Adjusted quantity {adjusted_quantity} is zero or negative.")
        return None

    # 3. Check MIN_NOTIONAL (using adjusted price and quantity)
    if not check_min_notional(adjusted_price, adjusted_quantity, exchange_filters):
        logger.warning(
            f"Order failed MIN_NOTIONAL check: Price={adjusted_price}, Qty={adjusted_quantity} for {order.get('symbol')}.")
        return None

    # --- TODO: Implement other filters as needed ---
    # Example: PERCENT_PRICE (requires current_price)
    # percent_price_filter = get_symbol_filter(exchange_filters, 'PERCENT_PRICE')
    # if percent_price_filter and current_price:
    #     multiplier_up = to_decimal(percent_price_filter.get('multiplierUp'))
    #     multiplier_down = to_decimal(percent_price_filter.get('multiplierDown'))
    #     avg_price_mins = int(percent_price_filter.get('avgPriceMins', 5)) # Need avg price logic if used
    #
    #     if multiplier_up and adjusted_price > current_price * multiplier_up:
    #         logger.warning(f"Order price {adjusted_price} exceeds PERCENT_PRICE upper limit.")
    #         return None
    #     if multiplier_down and adjusted_price < current_price * multiplier_down:
    #          logger.warning(f"Order price {adjusted_price} below PERCENT_PRICE lower limit.")
    #          return None

    # --- Update order dictionary ---
    order['price'] = adjusted_price
    order['quantity'] = adjusted_quantity
    logger.debug(
        f"Order passed filter validation: Price={adjusted_price}, Qty={adjusted_quantity}")

    return order


# File path: src/utils/formatting.py
