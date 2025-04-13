# src/utils/formatting.py

import logging
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation

# Get a logger instance specific to this module
log = logging.getLogger(__name__)

# Set high precision context for critical calculations if needed, though Decimal default is usually sufficient
# from decimal import getcontext
# getcontext().prec = 28 # Example: Set precision to 28 decimal places


def adjust_price_to_tick_size(price: Decimal, tick_size: Decimal, side: str = 'BUY') -> Decimal:
    """
    Adjusts a price to be a valid multiple of the tick_size.
    For limit BUY orders, it's generally safer to round DOWN to the nearest tick.
    For limit SELL orders, it's generally safer to round UP to the nearest tick.
    However, rounding down generally increases likelihood of fill for both,
    so we default to ROUND_DOWN unless specified otherwise for specific strategies.

    Args:
        price (Decimal): The desired price.
        tick_size (Decimal): The minimum price increment allowed by the exchange filter.
        side (str): Optional, 'BUY' or 'SELL'. Currently influences rounding direction if implemented.
                    (Default behaviour rounds down for safety/fill probability).

    Returns:
        Decimal: The adjusted price conforming to the tick_size.
    """
    if not isinstance(price, Decimal):
        log.warning(
            f"adjust_price_to_tick_size received non-Decimal price: {price} (Type: {type(price)}). Attempting conversion.")
        try:
            price = Decimal(str(price))
        except InvalidOperation:
            log.error(f"Invalid price value for Decimal conversion: {price}")
            raise ValueError(
                f"Invalid price value for Decimal conversion: {price}")

    if not isinstance(tick_size, Decimal) or tick_size <= Decimal('0'):
        log.error(
            f"Invalid tick_size: {tick_size}. Must be a positive Decimal.")
        # Decide handling: raise error or return original price? Raising is safer.
        raise ValueError(f"Invalid tick_size: {tick_size}")

    try:
        # Perform the adjustment using quantization (rounding to a specific exponent)
        # We want to round down to the nearest multiple of tick_size.
        # Decimal.quantize requires an exponent, not just the step size directly.
        # For tick_size like 0.01, exponent is Decimal('0.01')
        # For tick_size like 10, exponent is Decimal('1')
        # We want to round down to the nearest multiple of tick_size.
        # E.g., price=10.123, tick_size=0.01 -> (10.123 / 0.01) = 1012.3 -> floor(1012.3) = 1012 -> 1012 * 0.01 = 10.12

        factor = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
        adjusted_price = factor * tick_size

        # Alternative rounding based on side - currently defaults to ROUND_DOWN
        # rounding_mode = ROUND_DOWN if side.upper() == 'BUY' else ROUND_UP # Example if different rounding needed
        # adjusted_price = price.quantize(tick_size, rounding=rounding_mode) # Simpler if tick_size is 10^n

        log.debug(
            f"Adjusted price {price} to {adjusted_price} using tick_size {tick_size}")
        return adjusted_price
    except (InvalidOperation, TypeError) as e:
        log.error(
            f"Error adjusting price {price} with tick_size {tick_size}: {e}", exc_info=True)
        # Decide handling: raise error or return original price? Raising is safer.
        raise ValueError(
            f"Could not adjust price {price} with tick_size {tick_size}")


def adjust_qty_to_step_size(quantity: Decimal, step_size: Decimal) -> Decimal:
    """
    Adjusts a quantity to be a valid multiple of the step_size.
    Always rounds DOWN to the nearest step to avoid exceeding available balance or position size limits.

    Args:
        quantity (Decimal): The desired quantity.
        step_size (Decimal): The minimum quantity increment allowed by the exchange filter.

    Returns:
        Decimal: The adjusted quantity conforming to the step_size.
    """
    if not isinstance(quantity, Decimal):
        log.warning(
            f"adjust_qty_to_step_size received non-Decimal quantity: {quantity} (Type: {type(quantity)}). Attempting conversion.")
        try:
            quantity = Decimal(str(quantity))
        except InvalidOperation:
            log.error(
                f"Invalid quantity value for Decimal conversion: {quantity}")
            raise ValueError(
                f"Invalid quantity value for Decimal conversion: {quantity}")

    if not isinstance(step_size, Decimal) or step_size <= Decimal('0'):
        log.error(
            f"Invalid step_size: {step_size}. Must be a positive Decimal.")
        raise ValueError(f"Invalid step_size: {step_size}")

    try:
        # Similar logic to price adjustment, but always rounding down.
        factor = (quantity / step_size).to_integral_value(rounding=ROUND_DOWN)
        adjusted_quantity = factor * step_size

        log.debug(
            f"Adjusted quantity {quantity} to {adjusted_quantity} using step_size {step_size}")
        return adjusted_quantity
    except (InvalidOperation, TypeError) as e:
        log.error(
            f"Error adjusting quantity {quantity} with step_size {step_size}: {e}", exc_info=True)
        raise ValueError(
            f"Could not adjust quantity {quantity} with step_size {step_size}")


def check_min_notional(quantity: Decimal, price: Decimal, min_notional: Decimal) -> bool:
    """
    Checks if the calculated notional value (quantity * price) meets the minimum required.

    Args:
        quantity (Decimal): The order quantity (MUST be adjusted for step_size first).
        price (Decimal): The order price (MUST be adjusted for tick_size first).
        min_notional (Decimal): The minimum notional value required by the exchange filter.

    Returns:
        bool: True if quantity * price >= min_notional, False otherwise.
    """
    if not all(isinstance(v, Decimal) for v in [quantity, price, min_notional]):
        log.error(
            f"Non-Decimal input to check_min_notional: qty={type(quantity)}, price={type(price)}, min_not={type(min_notional)}")
        # Attempt conversion? Safer to raise error if inputs aren't already Decimal.
        raise TypeError(
            "Inputs quantity, price, and min_notional must be Decimal for check_min_notional.")

    if quantity < Decimal('0') or price < Decimal('0') or min_notional < Decimal('0'):
        log.error(
            f"Inputs must be non-negative for check_min_notional: qty={quantity}, price={price}, min_not={min_notional}")
        # Depending on context, a zero quantity/price might be valid but won't meet min_notional > 0
        return False  # Or raise error? Returning False seems reasonable.

    try:
        notional_value = quantity * price
        is_valid = notional_value >= min_notional
        log.debug(
            f"Check Min Notional: Qty={quantity}, Price={price}, Notional={notional_value:.8f}, MinRequired={min_notional}, Valid={is_valid}")
        return is_valid
    except (InvalidOperation, TypeError) as e:
        log.error(
            f"Error calculating notional value for qty={quantity}, price={price}: {e}", exc_info=True)
        return False  # Treat calculation errors as failure


# --- Example Usage (for testing when run directly via python -m src.utils.formatting) ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log.info("--- Testing Formatting Utilities ---")

    # Price Adjustment Tests
    log.info("\n--- Price Adjustment Tests ---")
    price1 = Decimal('65432.12345')
    tick1 = Decimal('0.01')  # Standard price tick
    adj_price1 = adjust_price_to_tick_size(price1, tick1)
    log.info(
        f"Price: {price1}, Tick: {tick1} -> Adjusted: {adj_price1} (Expected: 65432.12)")

    price2 = Decimal('65432.1')
    tick2 = Decimal('10')  # Large price tick
    adj_price2 = adjust_price_to_tick_size(price2, tick2)
    log.info(
        f"Price: {price2}, Tick: {tick2} -> Adjusted: {adj_price2} (Expected: 65430)")

    price3 = Decimal('0.123456789')
    tick3 = Decimal('0.00000001')  # Small tick size
    adj_price3 = adjust_price_to_tick_size(price3, tick3)
    log.info(
        f"Price: {price3}, Tick: {tick3} -> Adjusted: {adj_price3} (Expected: 0.12345678)")

    # Quantity Adjustment Tests
    log.info("\n--- Quantity Adjustment Tests ---")
    qty1 = Decimal('0.123456789')
    step1 = Decimal('0.001')  # Common step size
    adj_qty1 = adjust_qty_to_step_size(qty1, step1)
    log.info(
        f"Qty: {qty1}, Step: {step1} -> Adjusted: {adj_qty1} (Expected: 0.123)")

    qty2 = Decimal('15.6')
    step2 = Decimal('1')  # Step size of 1
    adj_qty2 = adjust_qty_to_step_size(qty2, step2)
    log.info(
        f"Qty: {qty2}, Step: {step2} -> Adjusted: {adj_qty2} (Expected: 15)")

    qty3 = Decimal('0.00001234')
    step3 = Decimal('0.00001')  # Small step size
    adj_qty3 = adjust_qty_to_step_size(qty3, step3)
    log.info(
        f"Qty: {qty3}, Step: {step3} -> Adjusted: {adj_qty3} (Expected: 0.00001)")

    # Min Notional Tests
    log.info("\n--- Minimum Notional Tests ---")
    # Use adjusted values from previous tests where appropriate
    min_notional_req = Decimal('10.0')  # Example: $10 minimum

    valid1 = check_min_notional(adj_qty1, adj_price1, min_notional_req)
    log.info(f"Qty: {adj_qty1}, Price: {adj_price1}, MinNot: {min_notional_req} -> Valid: {valid1} (Expected: True, as {adj_qty1*adj_price1:.2f} > 10)")

    # Test case designed to fail
    qty_fail = Decimal('0.0001')
    price_fail = Decimal('65000')  # Notional = 6.5
    valid_fail = check_min_notional(qty_fail, price_fail, min_notional_req)
    log.info(
        f"Qty: {qty_fail}, Price: {price_fail}, MinNot: {min_notional_req} -> Valid: {valid_fail} (Expected: False)")

    # Test case near the boundary
    qty_boundary = Decimal('0.00015385')  # Approx 10.00025 notional at 65000
    price_boundary = Decimal('65000')
    valid_boundary = check_min_notional(
        qty_boundary, price_boundary, min_notional_req)
    log.info(
        f"Qty: {qty_boundary}, Price: {price_boundary}, MinNot: {min_notional_req} -> Valid: {valid_boundary} (Expected: True)")

    # Approx 9.9996 notional at 65000
    qty_boundary_fail = Decimal('0.00015384')
    valid_boundary_fail = check_min_notional(
        qty_boundary_fail, price_boundary, min_notional_req)
    log.info(f"Qty: {qty_boundary_fail}, Price: {price_boundary}, MinNot: {min_notional_req} -> Valid: {valid_boundary_fail} (Expected: False)")
