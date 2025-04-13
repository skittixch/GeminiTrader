# src/strategies/geometric_grid.py

# --- Add project root to sys.path FIRST ---
from pathlib import Path  # Ensure Path is imported
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext
import logging
import os
import sys
# Define project_root for sys.path modification
_project_root_for_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root_for_path not in sys.path:
    sys.path.insert(0, _project_root_for_path)
# --- End sys.path modification ---

# --- Now other imports ---

# --- Project Imports ---
try:
    # Import necessary functions from utils
    from src.utils.formatting import apply_filter_rules, get_symbol_filter
    # We also need the logging setup for the __main__ block later
    from src.utils.logging_setup import setup_logging
except ImportError as e:
    # If imports fail even after path modification, log details and raise
    print(f"ERROR: Could not import project modules. Error: {e}")
    print(f"Project Root (calculated for path): {_project_root_for_path}")
    print(f"System Path: {sys.path}")
    raise ImportError(
        "Failed to import required project modules. Check paths and structure.") from e

# Set Decimal precision context if needed (can be done here or globally)
# getcontext().prec = 28 # Example precision setting

logger = logging.getLogger(__name__)  # Initialize logger after imports


# --- Core Grid Planning Function ---
def plan_buy_grid_v1(
    symbol: str,
    current_price: Decimal,
    available_balance: Decimal,
    atr: Decimal,
    exchange_filters: Dict,
    strategy_config: Dict,
    confidence_multiplier: Decimal = Decimal(
        '1.0')  # Basic adaptive sizing input
) -> List[Dict]:
    """
    Plans a geometric buy grid based on volatility (ATR), configuration,
    and a confidence multiplier.

    Args:
        symbol (str): The trading symbol (e.g., 'BTCUSD').
        current_price (Decimal): The current market price.
        available_balance (Decimal): The available quote currency balance for orders.
        atr (Decimal): The current Average True Range value for the interval.
        exchange_filters (Dict): Parsed exchange filter information for the symbol.
                                 Expected structure: {'symbol': 'BTCUSD', 'filters': [...]}
        strategy_config (Dict): Configuration parameters for the grid strategy:
            - base_order_size_usd (Decimal): Base size of the first order in quote currency.
            - grid_spacing_atr_multiplier (Decimal): Multiplier for ATR to determine spacing.
            - grid_spacing_geometric_factor (Decimal): Geometric factor for spacing increase.
            - order_size_geometric_factor (Decimal): Geometric factor for order size increase.
            - max_grid_levels (int): Maximum number of buy orders to place.
            - max_total_grid_quantity_base (Decimal): Max total base asset allowed in the grid.
        confidence_multiplier (Decimal): Factor to adjust base order size (adaptive sizing).
                                          Defaults to 1.0 (no adjustment).

    Returns:
        List[Dict]: A list of feasible buy limit order dictionaries, ready for placement,
                    or an empty list if no orders can be planned. Each dict contains:
                    {'symbol': str, 'side': 'BUY', 'type': 'LIMIT',
                     'quantity': Decimal, 'price': Decimal, 'timeInForce': 'GTC'}
    """
    planned_orders = []
    total_quantity_planned = Decimal('0.0')
    total_cost_planned = Decimal('0.0')

    # --- Input Validation ---
    if current_price <= 0 or available_balance <= 0 or atr <= 0:
        logger.warning(
            f"[{symbol}] Invalid input for planning grid: Price={current_price}, Balance={available_balance}, ATR={atr}")
        return []
    if not exchange_filters or not isinstance(exchange_filters.get('filters'), list):
        logger.error(
            f"[{symbol}] Invalid or missing exchange filters structure.")
        return []
    if not strategy_config:
        logger.error(f"[{symbol}] Missing strategy configuration.")
        return []

    # --- Extract Config Parameters ---
    try:
        base_order_usd = Decimal(str(strategy_config['base_order_size_usd']))
        spacing_atr_mult = Decimal(
            str(strategy_config['grid_spacing_atr_multiplier']))
        spacing_geom_factor = Decimal(
            str(strategy_config['grid_spacing_geometric_factor']))
        size_geom_factor = Decimal(
            str(strategy_config['order_size_geometric_factor']))
        max_levels = int(strategy_config['max_grid_levels'])
        # Use base asset symbol dynamically later if needed
        max_total_qty_base = Decimal(
            str(strategy_config['max_total_grid_quantity_base']))
    except KeyError as e:
        logger.error(f"[{symbol}] Missing key in strategy_config: {e}")
        return []
    except (TypeError, ValueError) as e:
        logger.error(f"[{symbol}] Invalid value type in strategy_config: {e}")
        return []

    # --- Apply Confidence Multiplier (Adaptive Sizing) ---
    adjusted_base_order_usd = base_order_usd * confidence_multiplier
    logger.info(f"[{symbol}] Base Order USD: {base_order_usd}, Confidence Multiplier: {confidence_multiplier}, Adjusted Base USD: {adjusted_base_order_usd}")

    # --- Calculate Grid Levels ---
    # Use current price as the starting point for level 1 drop
    last_price_level_start = current_price
    # Start with adjusted base size for the first level calculation
    current_geometric_base_size_usd = adjusted_base_order_usd

    for level in range(1, max_levels + 1):
        logger.debug(f"[{symbol}] Planning level {level}...")

        # Calculate Price Drop for this level relative to initial price
        # Level 1 drop: ATR * mult * factor^0
        # Level 2 drop: ATR * mult * factor^1 (cumulative drop from start)
        price_drop_factor = (spacing_atr_mult) * \
            (spacing_geom_factor ** (level - 1))
        price_drop = atr * price_drop_factor
        # Calculate target price from the *initial* price
        order_price = last_price_level_start - price_drop
        logger.debug(
            f"[{symbol}] Level {level}: Drop Factor={price_drop_factor:.4f}, Price Drop={price_drop:.8f}, Target Price={order_price:.8f}")

        if order_price <= 0:
            logger.warning(
                f"[{symbol}] Calculated order price is zero or negative at level {level}. Stopping grid planning.")
            break

        # Calculate Order Size for this level (increases geometrically from adjusted base)
        # Level 1 size: adjusted_base_usd * size_factor^0
        # Level 2 size: adjusted_base_usd * size_factor^1
        order_size_usd = current_geometric_base_size_usd * \
            (size_geom_factor ** (level - 1))

        # Prevent division by zero if order_price is somehow zero after checks
        if order_price == 0:
            logger.error(
                f"[{symbol}] Order price is zero before quantity calculation at level {level}. Stopping.")
            break
        order_quantity_base = order_size_usd / \
            order_price  # Estimate quantity in base asset
        logger.debug(
            f"[{symbol}] Level {level}: Target Size USD={order_size_usd:.2f}, Estimated Qty={order_quantity_base:.8f}")

        # --- Prepare Order Dictionary ---
        order = {
            'symbol': symbol,
            'side': 'BUY',
            'type': 'LIMIT',
            'quantity': order_quantity_base,  # Will be adjusted by filters
            'price': order_price,           # Will be adjusted by filters
            'timeInForce': 'GTC'            # Good Till Cancelled
        }

        # --- Apply Exchange Filters (CRITICAL STEP) ---
        # Pass the specific symbol's filter structure
        adjusted_order = apply_filter_rules(
            order.copy(), exchange_filters, current_price)

        if adjusted_order is None:
            logger.warning(
                f"[{symbol}] Level {level}: Order failed filter validation (Raw Price: {order_price:.8f}, Raw Qty: {order_quantity_base:.8f}). Stopping grid planning for this level and below.")
            break  # Stop adding levels if one fails filters

        adjusted_price = adjusted_order['price']
        adjusted_quantity = adjusted_order['quantity']

        # Recalculate cost AFTER filter adjustments
        if adjusted_price is None or adjusted_quantity is None or adjusted_price <= 0 or adjusted_quantity <= 0:
            logger.error(
                f"[{symbol}] Level {level}: Invalid adjusted price/quantity after filters. Price={adjusted_price}, Qty={adjusted_quantity}. Stopping.")
            break

        adjusted_cost = adjusted_price * adjusted_quantity
        logger.debug(
            f"[{symbol}] Level {level}: Adjusted Order - Price: {adjusted_price:.8f}, Qty: {adjusted_quantity:.8f}, Cost: {adjusted_cost:.2f}")

        # --- Check Limits ---
        # 1. Max Total Base Quantity Limit
        if (total_quantity_planned + adjusted_quantity) > max_total_qty_base:
            logger.warning(
                f"[{symbol}] Level {level}: Exceeds max total grid quantity ({max_total_qty_base}). Adjusted Qty={adjusted_quantity}, Current Total={total_quantity_planned}. Stopping grid planning.")
            break

        # 2. Available Balance Limit
        if (total_cost_planned + adjusted_cost) > available_balance:
            logger.warning(
                f"[{symbol}] Level {level}: Exceeds available balance ({available_balance}). Order Cost={adjusted_cost}, Current Total Cost={total_cost_planned}. Stopping grid planning.")
            break

        # --- Add Validated Order ---
        planned_orders.append(adjusted_order)
        total_quantity_planned += adjusted_quantity
        total_cost_planned += adjusted_cost
        logger.info(f"[{symbol}] Added Level {level}: Price={adjusted_price:.8f}, Qty={adjusted_quantity:.8f}, Cost={adjusted_cost:.2f}, Cumul Cost={total_cost_planned:.2f}, Cumul Qty={total_quantity_planned:.8f}")

        # Note: Price calculation for next level continues based on original price + geometrically increasing drop factor.

    logger.info(f"[{symbol}] Planned {len(planned_orders)} grid buy orders. Total Cost: {total_cost_planned:.2f}, Total Qty: {total_quantity_planned:.8f}")
    return planned_orders


# --- Example Usage / Testing Block ---
if __name__ == '__main__':
    # Setup basic logging for testing
    # setup_logging was imported above

    # --- Define project_root *within* this block for clarity/robustness ---
    project_root = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))

    # Define the full log file path using Path and the locally defined project_root
    log_file_path = Path(project_root) / "data" / \
        "logs" / "test_geometric_grid.log"

    # Correctly call setup_logging using the 'log_file' argument
    setup_logging(
        log_file=log_file_path,  # Pass the full Path object
        console_logging=True,
        log_level=logging.DEBUG  # Use DEBUG for detailed output
    )

    logger.info("--- Starting Geometric Grid Test ---")

    # --- Mock Inputs ---
    test_symbol = 'BTCUSD'
    test_current_price = Decimal('65000.00')
    # Enough balance for several levels
    test_available_balance = Decimal('5000.00')
    test_atr = Decimal('850.00')  # Example ATR value
    # Example: 20% more confident than baseline
    test_confidence = Decimal('1.2')

    # Simplified Mock Exchange Filters (Adjust according to actual Binance.US filters)
    # Ensure your actual apply_filter_rules can handle this structure
    test_filters = {
        'symbol': test_symbol,  # Often filters are nested under symbol
        'filters': [  # Binance often returns filters as a list of dicts
            {'filterType': 'PRICE_FILTER', 'minPrice': '0.01',
                'maxPrice': '1000000.00', 'tickSize': '0.01'},
            {'filterType': 'LOT_SIZE', 'minQty': '0.00001',
             'maxQty': '100.0', 'stepSize': '0.00001'},
            {'filterType': 'MIN_NOTIONAL', 'minNotional': '10.0',
             'applyToMarket': True, 'avgPriceMins': 5}
            # Add other relevant filter types if your apply_filter_rules uses them
        ]
    }

    # Mock Strategy Configuration from config.yaml
    test_strategy_config = {
        'base_order_size_usd': '50.00',                 # Start with a $50 order
        # Space levels 0.5 * ATR apart initially
        'grid_spacing_atr_multiplier': '0.5',
        # Increase spacing factor by 20% each level
        'grid_spacing_geometric_factor': '1.2',
        # Increase order size by 50% each level
        'order_size_geometric_factor': '1.5',
        'max_grid_levels': 7,                           # Max 7 buy orders
        'max_total_grid_quantity_base': '0.15'          # Max 0.15 BTC total in the grid
    }

    logger.info(f"Test Inputs:")
    logger.info(f"  Symbol: {test_symbol}")
    logger.info(f"  Current Price: {test_current_price}")
    logger.info(f"  Available Balance: {test_available_balance}")
    logger.info(f"  ATR: {test_atr}")
    logger.info(f"  Confidence Multiplier: {test_confidence}")
    logger.info(f"  Filters structure (example): {test_filters}")
    logger.info(f"  Strategy Config: {test_strategy_config}")

    # --- Call the Function ---
    # Make sure apply_filter_rules expects the structure of test_filters
    planned_buy_orders = plan_buy_grid_v1(
        symbol=test_symbol,
        current_price=test_current_price,
        available_balance=test_available_balance,
        atr=test_atr,
        exchange_filters=test_filters,  # Pass the whole structure
        strategy_config=test_strategy_config,
        confidence_multiplier=test_confidence
    )

    # --- Print Results ---
    logger.info("\n--- Planned Buy Grid Orders ---")
    if planned_buy_orders:
        total_cost = sum(o['price'] * o['quantity']
                         for o in planned_buy_orders)
        total_qty = sum(o['quantity'] for o in planned_buy_orders)
        logger.info(f"Total Orders: {len(planned_buy_orders)}")
        logger.info(f"Total Cost: {total_cost:.2f} USD")
        logger.info(f"Total Quantity: {total_qty:.8f} BTC")  # Assuming BTC
        for i, order in enumerate(planned_buy_orders):
            cost = order['price'] * order['quantity']
            logger.info(
                f"  Level {i+1}: Price={order['price']:.2f}, Qty={order['quantity']:.8f}, Cost={cost:.2f}")
    else:
        logger.info("No orders were planned.")

    logger.info("--- Geometric Grid Test Complete ---")


# File path: src/strategies/geometric_grid.py
