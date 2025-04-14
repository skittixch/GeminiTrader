# START OF FILE: src/strategies/geometric_grid.py

import logging
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from typing import Optional, Dict, Any, List

# --- Add project root ---
import os
import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
# --- End ---

try:
    from src.utils.formatting import (
        to_decimal,
        apply_filter_rules_to_price,
        apply_filter_rules_to_qty,
        validate_order_filters,
        get_symbol_info_from_exchange_info  # Helper to get symbol specific filters
    )
except ImportError:
    logger = logging.getLogger(__name__)  # Need logger if import fails early
    if not logger.hasHandlers():
        logging.basicConfig(level=logging.ERROR)
    logger.critical(
        "CRITICAL: Failed imports from src.utils.formatting in geometric_grid.py", exc_info=True)
    # Define dummies or raise error

    def to_decimal(v, default=None): return Decimal(
        v) if v is not None else default

    def apply_filter_rules_to_price(
        *args, **kwargs): return kwargs.get('price')
    def apply_filter_rules_to_qty(
        *args, **kwargs): return kwargs.get('quantity')

    def validate_order_filters(*args, **kwargs): return True
    def get_symbol_info_from_exchange_info(*args, **kwargs): return None
    # raise ImportError("CRITICAL: Missing formatting utilities.")


logger = logging.getLogger(__name__)

# --- Default Grid Parameters (used if not found in config) ---
DEFAULT_GRID_BASE_ORDER_SIZE_USD = Decimal('100.00')
DEFAULT_GRID_SPACING_ATR_MULTIPLIER = Decimal('0.5')
DEFAULT_GRID_SPACING_GEOMETRIC_FACTOR = Decimal('1.1')
DEFAULT_GRID_ORDER_SIZE_GEOMETRIC_FACTOR = Decimal('1.2')
DEFAULT_GRID_MAX_LEVELS = 5
DEFAULT_GRID_MAX_TOTAL_QTY_BASE = None  # No limit by default unless specified


def plan_buy_grid_v1(
    symbol: str,
    current_price: Decimal,
    current_atr: Optional[Decimal],
    available_quote_balance: Decimal,
    exchange_info: Dict,  # Full exchange info needed for filters
    config: Dict,
    # Default to neutral confidence if not provided
    confidence_score: Optional[float] = 0.5
) -> List[Dict[str, Any]]:
    """
    Plans a series of geometric limit buy orders below the current price,
    adjusted by volatility (ATR) and confidence.

    Args:
        symbol (str): The trading symbol.
        current_price (Decimal): The current market price (used as reference).
        current_atr (Optional[Decimal]): The latest ATR value. Required for spacing calc.
        available_quote_balance (Decimal): Available balance in quote currency (e.g., USD).
        exchange_info (Dict): Full exchange info containing filters.
        config (Dict): Main application configuration dictionary.
        confidence_score (Optional[float]): Confidence score (0.0-1.0) to modulate sizing.

    Returns:
        List[Dict[str, Any]]: A list of order dictionaries suitable for placement,
                              e.g., [{'symbol': 'BTCUSD', 'side': 'BUY', 'type': 'LIMIT',
                                     'quantity': Decimal('...'), 'price': Decimal('...')}, ...]
                              Returns empty list on error or if no valid orders can be planned.
    """
    planned_orders = []
    if current_price <= 0:
        logger.warning("Grid: Invalid current_price.")
        return planned_orders
    if current_atr is None or current_atr <= 0:
        logger.warning("Grid: Invalid current_atr.")
        return planned_orders
    if available_quote_balance <= 0:
        logger.warning("Grid: Insufficient quote balance.")
        return planned_orders
    if not exchange_info:
        logger.error("Grid: Exchange info required for filters.")
        return planned_orders

    # --- Get Grid Parameters ---
    grid_config = config.get('strategies', {}).get('geometric_grid', {})
    base_order_size_usd = to_decimal(grid_config.get(
        'base_order_size_usd'), DEFAULT_GRID_BASE_ORDER_SIZE_USD)
    spacing_atr_mult = to_decimal(grid_config.get(
        'grid_spacing_atr_multiplier'), DEFAULT_GRID_SPACING_ATR_MULTIPLIER)
    spacing_geo_factor = to_decimal(grid_config.get(
        'grid_spacing_geometric_factor'), DEFAULT_GRID_SPACING_GEOMETRIC_FACTOR)
    size_geo_factor = to_decimal(grid_config.get(
        'order_size_geometric_factor'), DEFAULT_GRID_ORDER_SIZE_GEOMETRIC_FACTOR)
    max_levels = int(grid_config.get(
        'max_grid_levels', DEFAULT_GRID_MAX_LEVELS))
    max_total_qty = to_decimal(grid_config.get(
        'max_total_grid_quantity_base'), DEFAULT_GRID_MAX_TOTAL_QTY_BASE)

    if not all([v is not None and v > 0 for v in [base_order_size_usd, spacing_atr_mult, spacing_geo_factor, size_geo_factor, max_levels]]):
        logger.error(f"Grid: Invalid grid parameters in config: {grid_config}")
        return planned_orders

    # --- Get Symbol Specific Filters ---
    symbol_info = get_symbol_info_from_exchange_info(symbol, exchange_info)
    if not symbol_info:
        logger.error(f"Grid: Symbol '{symbol}' not found in exchange info.")
        return planned_orders

    # --- Confidence Sizing Multiplier ---
    # Example: Scale linearly from 0.5x at 0.0 confidence to 1.5x at 1.0 confidence
    # (Can be made more complex or configurable later)
    # Clamp confidence score first
    clamped_confidence = max(
        0.0, min(1.0, confidence_score if confidence_score is not None else 0.5))
    # Linear scale: min_mult + (max_mult - min_mult) * score
    min_size_mult = Decimal('0.5')  # Size multiplier at 0.0 confidence
    max_size_mult = Decimal('1.5')  # Size multiplier at 1.0 confidence
    confidence_size_multiplier = min_size_mult + \
        (max_size_mult - min_size_mult) * Decimal(str(clamped_confidence))
    logger.debug(
        f"Grid: Confidence={clamped_confidence:.2f} -> Size Multiplier={confidence_size_multiplier:.3f}")

    # --- Iterate and Plan Levels ---
    cumulative_quote_cost = Decimal('0.0')
    cumulative_base_qty = Decimal('0.0')
    last_level_price = current_price  # Start reference for spacing

    for level in range(1, max_levels + 1):
        logger.debug(f"Grid: Planning Level {level}...")

        # 1. Calculate Price Spacing & Target Price
        # Price drops more significantly at lower levels due to geometric factor
        price_drop_factor = spacing_geo_factor ** (level - 1)
        target_price_level = last_level_price - \
            (current_atr * spacing_atr_mult * price_drop_factor)
        # Alternative: Drop from current price each time?
        # target_price_level = current_price - (current_atr * spacing_atr_mult * price_drop_factor)
        # Let's use drop from last level price for potentially wider spacing further down

        if target_price_level <= 0:
            logger.warning(
                f"Grid: Level {level} target price <= 0. Stopping grid plan.")
            break

        # Apply price filter (floor for buy limit below market)
        order_price = apply_filter_rules_to_price(
            symbol, target_price_level, exchange_info, operation='floor')
        if order_price is None or order_price <= 0:
            logger.warning(
                f"Grid: Level {level} price {target_price_level:.4f} failed filter adjustment or is <= 0. Adjusted: {order_price}. Skipping level.")
            continue  # Skip this level if price is invalid after filtering

        # 2. Calculate Order Size (Base + Geometric + Confidence)
        # Base size calculation (using USD amount) - approximate using filtered price
        # Use actual L1 qty if available
        base_qty_level_1 = (
            base_order_size_usd / order_price) if level == 1 else planned_orders[0]['quantity']
        target_quantity = base_qty_level_1 * (size_geo_factor ** (level - 1))

        # Apply confidence sizing
        target_quantity *= confidence_size_multiplier

        # Apply quantity filter (floor)
        order_quantity = apply_filter_rules_to_qty(
            symbol, target_quantity, exchange_info, operation='floor')
        if order_quantity is None or order_quantity <= 0:
            logger.warning(
                f"Grid: Level {level} quantity {target_quantity:.8f} failed filter adjustment or is <= 0. Adjusted: {order_quantity}. Skipping level.")
            continue

        # 3. Check Cumulative Quantity Limit
        if max_total_qty is not None and (cumulative_base_qty + order_quantity) > max_total_qty:
            logger.warning(
                f"Grid: Level {level} order quantity {order_quantity:.8f} would exceed max total base qty {max_total_qty:.8f}. Stopping grid plan.")
            break  # Stop placing orders

        # 4. Check Available Balance
        order_cost = order_price * order_quantity
        if (cumulative_quote_cost + order_cost) > available_quote_balance:
            logger.warning(
                f"Grid: Level {level} order cost {order_cost:.2f} would exceed available balance {available_quote_balance - cumulative_quote_cost:.2f}. Stopping grid plan.")
            break  # Stop placing orders

        # 5. Check Minimum Notional
        if not validate_order_filters(symbol, order_price, order_quantity, exchange_info):
            logger.warning(
                f"Grid: Level {level} order (P:{order_price}, Q:{order_quantity}) failed MIN_NOTIONAL check. Skipping level.")
            continue  # Skip this specific order

        # --- Order is valid, add to list and update cumulative values ---
        order_details = {
            'symbol': symbol,
            'side': 'BUY',
            'type': 'LIMIT',
            'quantity': order_quantity,
            'price': order_price,
            'metadata': {  # Optional metadata for tracking
                'grid_level': level,
                'confidence_used': clamped_confidence,
                'size_multiplier_used': confidence_size_multiplier
            }
        }
        planned_orders.append(order_details)
        cumulative_quote_cost += order_cost
        cumulative_base_qty += order_quantity
        # Update reference for next level's spacing calculation
        last_level_price = order_price

        logger.info(
            f"Grid: Planned Level {level} BUY @ {order_price:.2f}, Qty: {order_quantity:.6f}, Cost: {order_cost:.2f}")

    # Attempt to get base asset name
    logger.info(
        f"Grid Plan Complete: Planned {len(planned_orders)} orders. Total Cost: {cumulative_quote_cost:.2f} {config.get('portfolio', {}).get('quote_asset', 'QUOTE')}, Total Qty: {cumulative_base_qty:.8f} {symbol[:-len(config.get('portfolio', {}).get('quote_asset', ''))]}")

    return planned_orders


# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Geometric Grid Logic ---")

    # Mock Data
    mock_symbol = "BTCUSD"
    mock_current_price = Decimal('84500.00')
    mock_atr = Decimal('450.00')
    mock_balance = Decimal('1000.00')  # Available USD
    mock_confidence = 0.65  # Example confidence

    # Mock Config (using defaults where possible, overriding some)
    mock_config = {
        'portfolio': {'quote_asset': 'USD'},
        'strategies': {
            'geometric_grid': {
                'base_order_size_usd': '50.00',  # Smaller base order for testing
                'grid_spacing_atr_multiplier': '0.4',
                'grid_spacing_geometric_factor': '1.15',  # Slightly faster spacing increase
                'order_size_geometric_factor': '1.3',  # Faster size increase
                'max_grid_levels': 7,
                'max_total_grid_quantity_base': '0.05'  # Max 0.05 BTC total
            }
            # Add profit_taking etc. if needed by dependencies? No.
        }
    }
    # Mock Exchange Info (same as formatting test)
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
            }
        ]
    }

    # --- Run Test ---
    logger.info(
        f"Test Conditions: Price={mock_current_price}, ATR={mock_atr}, Balance={mock_balance}, Confidence={mock_confidence}")
    planned_grid = plan_buy_grid_v1(
        symbol=mock_symbol,
        current_price=mock_current_price,
        current_atr=mock_atr,
        available_quote_balance=mock_balance,
        exchange_info=mock_exchange_info,
        config=mock_config,
        confidence_score=mock_confidence
    )

    logger.info(f"\n--- Planned Grid Orders ({len(planned_grid)}) ---")
    if planned_grid:
        for i, order in enumerate(planned_grid):
            print(f"Order {i+1} (Level {order['metadata']['grid_level']}):")
            print(f"  Price: {order['price']:.2f}")
            print(f"  Qty:   {order['quantity']:.8f}")
            print(f"  Cost:  {(order['price'] * order['quantity']):.2f}")
            print("-" * 10)
    else:
        print("No orders planned.")

    logger.info("\n--- Geometric Grid Logic Test Complete ---")


# END OF FILE: src/strategies/geometric_grid.py
