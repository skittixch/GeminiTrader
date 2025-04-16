# START OF FILE: src/strategies/geometric_grid.py

import logging
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, InvalidOperation
from typing import Optional, Dict, Any, List

# --- Config Access Helper ---
try:
    from config.settings import get_config_value
except ImportError:
    def get_config_value(cfg, path, default=None): return default
    logging.warning("Using dummy get_config_value in geometric_grid.py")

# --- Formatting Utilities ---
try:
    from src.utils.formatting import (
        to_decimal, apply_filter_rules_to_price, apply_filter_rules_to_qty,
        validate_order_filters, get_symbol_info_from_exchange_info
    )
    # Type hint imports if needed
except ImportError:
    # ...(Dummies remain the same)...
    logger = logging.getLogger(__name__)
    if not logger.hasHandlers():
        logging.basicConfig(level=logging.ERROR)
    logger.critical(
        "CRITICAL: Failed imports in geometric_grid.py", exc_info=True)

    def to_decimal(v, default=None): return Decimal(
        v) if v is not None else default

    def apply_filter_rules_to_price(
        *args, **kwargs): return kwargs.get('price')
    def apply_filter_rules_to_qty(
        *args, **kwargs): return kwargs.get('quantity')

    def validate_order_filters(*args, **kwargs): return True
    def get_symbol_info_from_exchange_info(*args, **kwargs): return None

logger = logging.getLogger(__name__)

# --- Default Grid Parameters ---
DEFAULT_GRID_BASE_ORDER_SIZE_USD = Decimal('100.00')
DEFAULT_GRID_SPACING_ATR_MULTIPLIER = Decimal('0.5')
DEFAULT_GRID_SPACING_GEOMETRIC_FACTOR = Decimal('1.1')
DEFAULT_GRID_ORDER_SIZE_GEOMETRIC_FACTOR = Decimal('1.2')
DEFAULT_GRID_MAX_LEVELS = 5
DEFAULT_GRID_MAX_TOTAL_QTY_BASE = None
DEFAULT_ATR_PERIOD = 14

# --- Function Definition (Signature updated previously) ---


def plan_buy_grid_v1(
    symbol: str,
    current_price: Decimal,
    current_atr: Optional[Decimal],
    available_quote_balance: Decimal,
    exchange_info: Dict,  # Needs full info for get_symbol_info_from_exchange_info
    config_dict: Dict,
    confidence_score: Optional[float] = 0.5,
) -> List[Dict[str, Any]]:
    """Plans geometric grid buys using config dictionary."""
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
        logger.error("Grid: Exchange info required.")
        return planned_orders

    # --- Get Grid Parameters using original paths ---
    base_order_usd = get_config_value(
        config_dict, ('strategies', 'geometric_grid', 'base_order_size_usd'), DEFAULT_GRID_BASE_ORDER_SIZE_USD)
    spacing_atr_mult = get_config_value(
        config_dict, ('strategies', 'geometric_grid', 'grid_spacing_atr_multiplier'), DEFAULT_GRID_SPACING_ATR_MULTIPLIER)
    spacing_geo_factor = get_config_value(
        config_dict, ('strategies', 'geometric_grid', 'grid_spacing_geometric_factor'), DEFAULT_GRID_SPACING_GEOMETRIC_FACTOR)
    size_geo_factor = get_config_value(config_dict, ('strategies', 'geometric_grid',
                                       'order_size_geometric_factor'), DEFAULT_GRID_ORDER_SIZE_GEOMETRIC_FACTOR)
    max_levels = get_config_value(
        config_dict, ('strategies', 'geometric_grid', 'max_grid_levels'), DEFAULT_GRID_MAX_LEVELS)
    max_total_qty = get_config_value(config_dict, ('strategies', 'geometric_grid',
                                     'max_total_grid_quantity_base'), DEFAULT_GRID_MAX_TOTAL_QTY_BASE)

    try:  # Convert and Validate Params
        base_order_usd_dec = to_decimal(base_order_usd)
        spacing_atr_mult_dec = to_decimal(spacing_atr_mult)
        spacing_geo_factor_dec = to_decimal(spacing_geo_factor)
        size_geo_factor_dec = to_decimal(size_geo_factor)
        max_levels_int = int(max_levels)
        max_total_qty_dec = to_decimal(
            max_total_qty) if max_total_qty is not None else None
        if not all([v is not None and v > 0 for v in [base_order_usd_dec, spacing_atr_mult_dec, spacing_geo_factor_dec, size_geo_factor_dec]]) or max_levels_int <= 0:
            raise ValueError("Core grid params invalid")
        if max_total_qty_dec is not None and max_total_qty_dec <= 0:
            raise ValueError("max_total_qty must be positive if set")
    except (ValueError, TypeError, InvalidOperation) as e:
        logger.error(
            f"Grid: Invalid params: {e}. Config: {get_config_value(config_dict, ('strategies', 'geometric_grid'), {})}", exc_info=True)
        return planned_orders

    # NOTE: Formatting functions expect the *full* exchange_info, not just filters
    # symbol_info = get_symbol_info_from_exchange_info(symbol, exchange_info) # This is done inside the filter funcs now
    # if not symbol_info: logger.error(f"Grid: Symbol '{symbol}' info missing."); return planned_orders
    # filters = symbol_info.get('filters', []) # No need to extract filters here

    clamped_conf = max(
        0.0, min(1.0, confidence_score if confidence_score is not None else 0.5))
    min_mult = Decimal('0.5')
    max_mult = Decimal('1.5')
    conf_size_mult = min_mult + \
        (max_mult - min_mult) * Decimal(str(clamped_conf))
    logger.debug(
        f"Grid: Conf={clamped_conf:.2f} -> SizeMult={conf_size_mult:.3f}")

    cum_cost = Decimal('0.0')
    cum_qty = Decimal('0.0')
    last_price = current_price
    qty_l1 = None

    for level in range(1, max_levels_int + 1):
        logger.debug(f"Grid: Planning Level {level}...")
        try:
            # 1. Price
            price_drop = spacing_geo_factor_dec ** (level - 1)
            target_price = last_price - \
                (current_atr * spacing_atr_mult_dec * price_drop)
            if target_price <= 0:
                logger.warning(f"Grid L{level}: Target price <= 0. Stop.")
                break

            # --- CORRECTED CALL to apply_filter_rules_to_price (using positional args) ---
            order_price = apply_filter_rules_to_price(
                symbol,          # Arg 1: symbol
                target_price,    # Arg 2: price
                exchange_info,   # Arg 3: full exchange_info dict
                operation='floor'  # Arg 4: operation
            )
            # --- END CORRECTION ---
            if order_price is None or order_price <= 0:
                logger.warning(
                    f"Grid L{level}: Price {target_price:.4f} invalid after filters: {order_price}. Skip.")
                continue

            # 2. Quantity
            if level == 1:
                qty_target = base_order_usd_dec / order_price
            elif qty_l1 is not None:
                qty_target = qty_l1 * (size_geo_factor_dec ** (level - 1))
            else:
                logger.error(f"Grid L{level}: Cannot get L1 qty. Stop.")
                break
            qty_target *= conf_size_mult

            # --- CORRECTED CALL to apply_filter_rules_to_qty (using positional args) ---
            order_qty = apply_filter_rules_to_qty(
                symbol,          # Arg 1: symbol
                qty_target,      # Arg 2: quantity
                exchange_info,   # Arg 3: full exchange_info dict
                # Arg 4: operation (is_base_asset handled internally if needed)
                operation='floor'
            )
            # --- END CORRECTION ---
            if order_qty is None or order_qty <= 0:
                logger.warning(
                    f"Grid L{level}: Qty {qty_target:.8f} invalid after filters: {order_qty}. Skip.")
                continue
            if level == 1:
                qty_l1 = order_qty

            # 3. Limits Check
            if max_total_qty_dec is not None and (cum_qty + order_qty) > max_total_qty_dec:
                logger.warning(
                    f"Grid L{level}: Qty {order_qty:.8f} exceeds max total {max_total_qty_dec:.8f}. Stop.")
                break
            order_cost = order_price * order_qty
            if (cum_cost + order_cost) > available_quote_balance:
                logger.warning(
                    f"Grid L{level}: Cost {order_cost:.2f} exceeds avail {available_quote_balance - cum_cost:.2f}. Stop.")
                break

            # --- CORRECTED CALL to validate_order_filters (using positional args) ---
            if not validate_order_filters(
                symbol,        # Arg 1
                order_price,   # Arg 2
                order_qty,     # Arg 3
                exchange_info  # Arg 4
            ):
                logger.warning(
                    f"Grid L{level}: Order (P:{order_price}, Q:{order_qty}) failed MIN_NOTIONAL/etc. Skip.")
                continue
            # --- END CORRECTION ---

            # 4. Add Order
            order = {'symbol': symbol, 'side': 'BUY', 'type': 'LIMIT', 'quantity': order_qty, 'price': order_price, 'metadata': {
                'grid_level': level, 'confidence_used': clamped_conf, 'size_multiplier_used': conf_size_mult}}
            planned_orders.append(order)
            cum_cost += order_cost
            cum_qty += order_qty
            last_price = order_price
            logger.info(
                f"Grid: Planned L{level} BUY @ {order_price:.2f}, Qty: {order_qty:.6f}, Cost: {order_cost:.2f}")
        except Exception as level_e:
            logger.error(
                f"Error planning grid level {level}: {level_e}", exc_info=True)
            continue

    quote_asset_name = get_config_value(
        config_dict, ('portfolio', 'quote_asset'), 'QUOTE')
    base_asset_name = symbol[:-len(quote_asset_name)
                             ] if symbol.endswith(quote_asset_name) else 'BASE'
    logger.info(
        f"Grid Plan Complete: {len(planned_orders)} orders. Cost:{cum_cost:.2f} {quote_asset_name}, Qty:{cum_qty:.8f} {base_asset_name}")
    return planned_orders


# Example Usage (remains the same)
if __name__ == '__main__':
    # ...(Same example usage as message #53)...
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Geometric Grid Logic ---")
    mock_symbol = "BTCUSD"
    mock_current_price = Decimal('84500.00')
    mock_atr = Decimal('450.00')
    mock_balance = Decimal('1000.00')
    mock_confidence = 0.65
    mock_config = {'portfolio': {'quote_asset': 'USD'}, 'strategies': {'geometric_grid': {'base_order_size_usd': '50.00', 'grid_spacing_atr_multiplier': '0.4',
                                                                                          'grid_spacing_geometric_factor': '1.15', 'order_size_geometric_factor': '1.3', 'max_grid_levels': 7, 'max_total_grid_quantity_base': '0.05', 'atr_period': 14}}}
    mock_exchange_info = {"symbols": [{"symbol": "BTCUSD", "status": "TRADING", "filters": [{"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000.00", "tickSize": "0.01"}, {
        "filterType": "LOT_SIZE", "minQty": "0.00001", "maxQty": "100.0", "stepSize": "0.00001"}, {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"}]}]}
    logger.info(
        f"Test Conditions: Price={mock_current_price}, ATR={mock_atr}, Balance={mock_balance}, Confidence={mock_confidence}")
    planned_grid = plan_buy_grid_v1(symbol=mock_symbol, current_price=mock_current_price, current_atr=mock_atr, available_quote_balance=mock_balance,
                                    # Pass config_dict
                                    exchange_info=mock_exchange_info, config_dict=mock_config, confidence_score=mock_confidence)
    logger.info(f"\n--- Planned Grid Orders ({len(planned_grid)}) ---")
    if planned_grid:
        for i, order in enumerate(planned_grid):
            print(
                f"Order {i+1} (L{order['metadata']['grid_level']}): P:{order['price']:.2f} Q:{order['quantity']:.8f} Cost:{(order['price']*order['quantity']):.2f}")
    else:
        print("No orders planned.")
    logger.info("\n--- Geometric Grid Logic Test Complete ---")

# END OF FILE: src/strategies/geometric_grid.py
