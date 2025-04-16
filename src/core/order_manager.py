# START OF FILE: src/core/order_manager.py

import logging
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from typing import List, Dict, Optional, TYPE_CHECKING, Any
import pandas as pd
import time

if TYPE_CHECKING:
    from src.connectors.binance_us import BinanceUSConnector
    from src.core.state_manager import StateManager

try:
    from config.settings import get_config_value
except ImportError:
    # Dummy function for potential standalone testing or type checking issues
    def get_config_value(cfg, path, default=None): return default
    _logger_om = logging.getLogger(__name__)
    if not _logger_om.hasHandlers():
        logging.basicConfig(level=logging.WARNING)
    _logger_om.warning("Using dummy get_config_value in order_manager.py")

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages order placement, tracking, and reconciliation.
    Separates order logic from the main trading loop.
    """

    def __init__(self, config_dict: Dict[str, Any], connector: 'BinanceUSConnector', state_manager: 'StateManager'):
        self.config_dict = config_dict
        self.connector = connector
        self.state_manager = state_manager

        # Get simulation_mode and symbol/assets from the top-level 'trading' section
        # as used in main_trader.py for consistency
        self.simulation_mode = get_config_value(
            self.config_dict, ('trading', 'simulation_mode'), False)
        self.symbol = get_config_value(
            self.config_dict, ('trading', 'symbol'), 'BTCUSDT')
        self.quote_asset = get_config_value(
            self.config_dict, ('portfolio', 'quote_asset'), 'USDT')

        # Infer base asset (same logic as main_trader.py)
        if self.symbol.endswith(self.quote_asset):
            self.base_asset = self.symbol[:-len(self.quote_asset)]
        else:
            common_bases = ['BTC', 'ETH']
            inferred = False
            for base in common_bases:
                if self.symbol.startswith(base):
                    self.base_asset = base
                    inferred = True
                    break
            if not inferred:
                self.base_asset = 'UNKNOWN_BASE'
                logger.error(
                    f"OrderManager could not infer base asset for symbol '{self.symbol}' and quote '{self.quote_asset}'. Defaulting to {self.base_asset}.")

        # Simulation counters (initialize here)
        self.sim_order_id_counter = 1
        self.place_attempts = 0  # Added for tracking
        self.place_failures = 0  # Added for tracking
        self.cancel_attempts = 0  # Added for tracking
        self.cancel_failures = 0  # Added for tracking
        self.sim_market_sell_counter = 0
        self.sim_tp_fill_counter = 0
        self.sim_grid_fill_counter = 0

        # Load initial state to initialize active orders (important!)
        self._load_order_state()

    def _load_order_state(self):
        """Loads active grid and TP orders from the state manager."""
        state = self.state_manager.load_state()
        state = state if state else {}
        self.active_grid_orders = state.get('active_grid_orders', [])
        self.active_tp_order = state.get('active_tp_order', None)
        logger.debug(
            f"OrderManager state loaded: Grid={len(self.active_grid_orders)}, TP={self.active_tp_order is not None}")

    def _save_order_state(self):
        """Saves the current active orders back to the state manager."""
        # It's often better practice for OrderManager *not* to save state directly,
        # but rather have the main loop save the entire state after calling OM methods.
        # However, if immediate persistence after OM actions is needed:
        state = self.state_manager.load_state()
        state = state if state else {}
        state['active_grid_orders'] = self.active_grid_orders
        state['active_tp_order'] = self.active_tp_order
        self.state_manager.save_state(state)
        logger.debug("OrderManager state saved.")

    def _get_next_sim_order_id(self) -> str:
        # Simple counter for simulation order IDs
        order_id = f"sim_{int(time.time() * 1000)}_{self.sim_order_id_counter}"
        self.sim_order_id_counter += 1
        return order_id

    def _simulate_fill(self, order: Dict, current_price: Decimal) -> bool:
        """Simulates if a limit order would fill based on the current price."""
        try:
            order_price = Decimal(order.get('price', '0'))
        except (InvalidOperation, TypeError):
            logger.warning(
                f"SimFill: Invalid price '{order.get('price')}' in order {order.get('clientOrderId', order.get('orderId'))}. Cannot simulate fill.")
            return False

        order_side = order.get('side')
        order_type = order.get('type')

        # Only simulate fills for LIMIT orders
        if order_type != 'LIMIT':
            return False

        cid = order.get('clientOrderId', order.get('orderId', 'N/A'))

        # Buy order fills if current price drops to or below order price
        if order_side == 'BUY' and current_price <= order_price:
            logger.debug(
                f"[SIM] Buy fill condition met for {cid} @ {order_price} (Current Price: {current_price})")
            self.sim_grid_fill_counter += 1
            return True
        # Sell order (TP) fills if current price rises to or above order price
        elif order_side == 'SELL' and current_price >= order_price:
            logger.debug(
                f"[SIM] Sell fill condition met for {cid} @ {order_price} (Current Price: {current_price})")
            self.sim_tp_fill_counter += 1
            return True

        # No fill condition met
        return False

    def check_orders(self, current_price: Decimal) -> Dict[str, Any]:
        """
        Checks status of active grid and TP orders.
        In simulation, checks against current_price.
        In live mode, queries the exchange API (read-only).
        Returns a dictionary containing lists of filled orders.
        Modifies internal state (active_grid_orders, active_tp_order).
        """
        # Load the latest order state before checking
        self._load_order_state()

        filled_grid_orders, filled_tp_order = [], None
        logger.debug(
            f"Checking Orders: Active Grid={len(self.active_grid_orders)}, Active TP={self.active_tp_order is not None}")

        if self.simulation_mode:
            remaining_grid = []
            for order in self.active_grid_orders:
                if self._simulate_fill(order, current_price):
                    # Simulate the fill response structure
                    filled_order_data = {
                        **order,  # Keep original order data
                        # Assume full fill
                        'executedQty': order.get('origQty', '0.0'),
                        'cummulativeQuoteQty': str(Decimal(order.get('price', '0')) * Decimal(order.get('origQty', '0'))),
                        'status': 'FILLED',
                        'updateTime': int(time.time() * 1000)
                    }
                    filled_grid_orders.append(filled_order_data)
                    logger.info(
                        f"[SIM] Grid order filled: {order.get('clientOrderId', order.get('orderId'))}")
                else:
                    remaining_grid.append(order)  # Keep order if not filled
            self.active_grid_orders = remaining_grid  # Update internal state

            if self.active_tp_order and self._simulate_fill(self.active_tp_order, current_price):
                filled_tp_data = {
                    **self.active_tp_order,
                    'executedQty': self.active_tp_order.get('origQty', '0.0'),
                    'cummulativeQuoteQty': str(Decimal(self.active_tp_order.get('price', '0')) * Decimal(self.active_tp_order.get('origQty', '0'))),
                    'status': 'FILLED',
                    'updateTime': int(time.time() * 1000)
                }
                filled_tp_order = filled_tp_data
                logger.info(
                    f"[SIM] TP order filled: {self.active_tp_order.get('clientOrderId', self.active_tp_order.get('orderId'))}")
                self.active_tp_order = None  # Update internal state
            # No need to explicitly save state here, let main loop handle it after getting results

        else:  # Live Mode (Read-only calls to check status)
            indices_to_remove = set()
            for i, order in enumerate(self.active_grid_orders):
                order_id = order.get('orderId')
                client_order_id = order.get('clientOrderId')
                display_id = client_order_id or order_id or f"Index_{i}"

                if not order_id and not client_order_id:
                    logger.warning(
                        f"Skipping grid order check: Missing both orderId and clientOrderId in order data: {order}")
                    continue

                try:
                    # Use the connector's status check
                    status_data = self.connector.get_order_status(
                        symbol=self.symbol,
                        orderId=order_id,
                        origClientOrderId=client_order_id
                    )

                    if status_data is None:
                        # Error logged within connector, skip processing this order
                        logger.warning(
                            f"Could not get status for grid order {display_id}. Assuming still active.")
                        continue

                    status = status_data.get(
                        'status', 'ERROR').upper()  # Normalize status
                    logger.debug(
                        f"Checked live grid order {display_id}: Status={status}")

                    if status == 'FILLED':
                        logger.info(f"Live grid order FILLED: {display_id}")
                        # Merge original metadata with potentially updated status data
                        filled_order_data = {**order, **status_data}
                        filled_grid_orders.append(filled_order_data)
                        indices_to_remove.add(i)
                    elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'PENDING_CANCEL']:
                        logger.info(
                            f"Live grid order {display_id} is inactive (Status: {status}). Removing from active list.")
                        indices_to_remove.add(i)
                    elif status in ['NEW', 'PARTIALLY_FILLED']:
                        # Still active, do nothing, keep in list
                        logger.debug(
                            f"Live grid order {display_id} is active (Status: {status}).")
                        # Optionally update the state with the latest partial fill info if needed
                        # self.active_grid_orders[i] = {**order, **status_data}
                    else:  # UNKNOWN or ERROR status
                        logger.warning(
                            f"Live grid order {display_id} has unexpected status: {status}. Keeping for now.")

                except Exception as e:
                    logger.error(
                        f"Error checking status for grid order {display_id}: {e}", exc_info=False)
                    logger.debug(
                        "Traceback for grid order check error:", exc_info=True)

            # Update active grid orders list based on checks
            if indices_to_remove:
                self.active_grid_orders = [o for i, o in enumerate(
                    self.active_grid_orders) if i not in indices_to_remove]

            # Check Take Profit Order
            if self.active_tp_order:
                order_id = self.active_tp_order.get('orderId')
                client_order_id = self.active_tp_order.get('clientOrderId')
                display_id = client_order_id or order_id or "Unknown_TP_ID"

                if not order_id and not client_order_id:
                    logger.error(
                        f"Active TP order is missing required IDs: {self.active_tp_order}. Removing.")
                    self.active_tp_order = None
                else:
                    try:
                        status_data = self.connector.get_order_status(
                            symbol=self.symbol,
                            orderId=order_id,
                            origClientOrderId=client_order_id
                        )

                        if status_data is None:
                            logger.warning(
                                f"Could not get status for TP order {display_id}. Assuming still active.")
                        else:
                            status = status_data.get('status', 'ERROR').upper()
                            logger.debug(
                                f"Checked live TP order {display_id}: Status={status}")

                            if status == 'FILLED':
                                logger.info(
                                    f"Live TP order FILLED: {display_id}")
                                filled_tp_order = {
                                    **self.active_tp_order, **status_data}
                                self.active_tp_order = None  # Remove from active state
                            elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'PENDING_CANCEL']:
                                logger.info(
                                    f"Live TP order {display_id} is inactive (Status: {status}). Removing from active list.")
                                self.active_tp_order = None
                            elif status in ['NEW', 'PARTIALLY_FILLED']:
                                logger.debug(
                                    f"Live TP order {display_id} is active (Status: {status}).")
                                # Optionally update state with latest info
                                # self.active_tp_order = {**self.active_tp_order, **status_data}
                            else:
                                logger.warning(
                                    f"Live TP order {display_id} has unexpected status: {status}. Keeping for now.")

                    except Exception as e:
                        logger.error(
                            f"Error checking status for TP order {display_id}: {e}", exc_info=False)
                        logger.debug(
                            "Traceback for TP order check error:", exc_info=True)

        # Save the updated active orders back to the state manager after checks
        self._save_order_state()

        # Return the fills detected during this check cycle
        return {'grid_fills': filled_grid_orders, 'tp_fill': filled_tp_order}

    def reconcile_and_place_grid(self, planned_grid: List[Dict]) -> Dict[str, List]:
        """
        Compares planned grid orders with active orders, cancels outdated ones,
        and places new ones.
        Returns a dictionary summarizing actions taken.
        Modifies internal state (active_grid_orders).
        """
        self._load_order_state()  # Load current active orders

        result = {"placed": [], "cancelled": [], "failed": [], "unchanged": []}
        current_ts_float = time.time()

        logger.info(
            f"Reconciling Grid Orders: Planned={len(planned_grid)}, Currently Active={len(self.active_grid_orders)}")

        # --- Create sets for efficient comparison ---
        # Use a consistent precision for price comparison
        # Example precision, adjust if needed
        price_precision = Decimal('1e-8')

        # Planned orders: {price: plan_dict}
        planned_orders_map = {}
        for plan in planned_grid:
            try:
                price = Decimal(plan['price']).quantize(price_precision)
                planned_orders_map[price] = plan
            except (InvalidOperation, TypeError):
                logger.warning(
                    f"Invalid price in planned grid order, skipping: {plan.get('price')}")
                result['failed'].append(
                    {**plan, 'reason': 'Invalid price format'})

        # Active orders: {price: order_dict}
        active_orders_map = {}
        valid_active_grid = []
        for order in self.active_grid_orders:
            try:
                price = Decimal(order['price']).quantize(price_precision)
                # Store the first active order found at a given price level
                if price not in active_orders_map:
                    active_orders_map[price] = order
                valid_active_grid.append(order)  # Keep track of valid orders
            except (InvalidOperation, TypeError):
                logger.warning(
                    f"Invalid price in active grid order state, ignoring: {order.get('price')}, ID: {order.get('clientOrderId')}")
        self.active_grid_orders = valid_active_grid  # Update state with only valid ones

        planned_prices = set(planned_orders_map.keys())
        active_prices = set(active_orders_map.keys())

        # --- Identify Orders to Cancel ---
        prices_to_cancel = active_prices - planned_prices
        orders_to_cancel = [active_orders_map[price]
                            for price in prices_to_cancel]

        # --- Identify Orders to Place ---
        prices_to_place = planned_prices - active_prices
        orders_to_place = [planned_orders_map[price]
                           for price in prices_to_place]

        # --- Identify Unchanged Orders ---
        prices_unchanged = active_prices.intersection(planned_prices)
        orders_unchanged = [active_orders_map[price]
                            for price in prices_unchanged]
        # Add unchanged orders to result
        result['unchanged'] = orders_unchanged

        logger.debug(
            f"Grid Reconcile: Place={len(orders_to_place)}, Cancel={len(orders_to_cancel)}, Unchanged={len(orders_unchanged)}")

        # --- Execute Cancellations ---
        remaining_active_after_cancel = list(
            orders_unchanged)  # Start with unchanged ones
        for order in orders_to_cancel:
            cid = order.get('clientOrderId')
            oid = order.get('orderId')
            price = order.get('price')
            logger.debug(
                f"Attempting to cancel outdated grid order at price {price} (ID: {cid or oid})")
            # Use the dedicated cancel method which handles sim/live
            cancel_success_id = self.cancel_order(cid, oid, "Grid (Reconcile)")
            if cancel_success_id is not None:
                # Log the ID that was targeted
                result['cancelled'].append(cid or oid or f"Price_{price}")
            else:
                logger.error(
                    f"Failed to cancel grid order at price {price} (ID: {cid or oid}). It might remain active.")
                # Decide if we should keep it in the active list despite failed cancel
                remaining_active_after_cancel.append(order)  # Keep it for now

        # --- Execute Placements ---
        newly_placed_orders = []
        for plan in orders_to_place:
            # Generate a unique client order ID
            grid_level = plan.get('metadata', {}).get('grid_level', 'N')
            cid = f"gt_grid_{int(current_ts_float * 1000)}_{grid_level}"
            # Use original string price from plan for logging/API
            plan_price = plan['price']
            plan_quantity = plan['quantity']  # Use correct key

            try:
                if self.simulation_mode:
                    logger.debug(
                        # !!! CORRECTED KEY HERE !!!
                        f"Attempting place SIM grid: {cid} for {plan_quantity} @ {plan_price}")
                    sim_order = {
                        'symbol': plan['symbol'],
                        'orderId': self._get_next_sim_order_id(),  # Generate sim ID
                        'clientOrderId': cid,
                        'price': str(plan_price),  # Store as string like API
                        'origQty': str(plan_quantity),  # Store as string
                        'executedQty': '0.00000000',
                        'cummulativeQuoteQty': '0.00000000',
                        'status': 'NEW',
                        'timeInForce': 'GTC',  # Assuming GTC for limit orders
                        'type': plan['type'],
                        'side': plan['side'],
                        'isWorking': True,  # Assume working when placed in sim
                        'time': int(time.time() * 1000),
                        'updateTime': int(time.time() * 1000),
                        # Include metadata
                        'metadata': plan.get('metadata', {})
                    }
                    newly_placed_orders.append(sim_order)
                    # Use the generated sim order data
                    result['placed'].append(sim_order)
                    self.place_attempts += 1
                    logger.info(f"Simulated grid order placed: {cid}")
                else:
                    # Place live order using connector
                    logger.info(  # Use INFO for live placement attempts
                        # !!! CORRECTED KEY HERE !!!
                        f"Attempting place LIVE grid order: {cid} for {plan_quantity} @ {plan_price}")
                    order_response = self.connector.create_limit_buy(
                        symbol=plan['symbol'],
                        quantity=plan_quantity,  # Use Decimal quantity
                        price=Decimal(plan_price),  # Use Decimal price
                        newClientOrderId=cid
                    )
                    if order_response and isinstance(order_response, dict):
                        logger.info(
                            f"LIVE Grid order placement successful: {order_response.get('clientOrderId')} (ID: {order_response.get('orderId')}), Status: {order_response.get('status')}")
                        # Add necessary metadata back if not included in response
                        order_response_with_meta = {
                            **order_response, 'metadata': plan.get('metadata', {})}
                        newly_placed_orders.append(order_response_with_meta)
                        result['placed'].append(
                            order_response_with_meta)  # Use API response
                        self.place_attempts += 1
                    else:
                        logger.error(
                            f"LIVE Grid order placement failed for plan: Price={plan_price}, Qty={plan_quantity}. Response: {order_response}")
                        result['failed'].append(
                            {**plan, 'reason': 'API placement failed', 'response': order_response})
                        self.place_failures += 1
            except Exception as e:
                logger.error(
                    f"Exception occurred placing {'live' if not self.simulation_mode else 'simulated'} grid order for plan {plan}: {e}", exc_info=True)
                result['failed'].append(
                    {**plan, 'reason': f'Exception during placement: {e}'})
                self.place_failures += 1

        # Update the internal state with the final list of active orders
        self.active_grid_orders = remaining_active_after_cancel + newly_placed_orders

        # Save the updated state
        self._save_order_state()

        return result

    def place_or_update_tp_order(self, tp_price: Optional[Decimal], position_size: Decimal) -> Optional[Dict]:
        """
        Places a new Take Profit order or updates/cancels the existing one.
        Returns the active TP order dict if successful/unchanged, None otherwise.
        Modifies internal state (active_tp_order).
        """
        self._load_order_state()  # Load current TP order state

        # If position is closed or TP price is None, ensure any active TP is cancelled
        if position_size <= Decimal('0') or tp_price is None:
            if self.active_tp_order:
                logger.info(
                    f"Position closed or no TP planned. Cancelling active TP order: {self.active_tp_order.get('clientOrderId')}")
                self.cancel_order(
                    self.active_tp_order.get('clientOrderId'),
                    self.active_tp_order.get('orderId'),
                    "TP (Position Closed/No Plan)"
                )
                self.active_tp_order = None  # Clear internal state
                self._save_order_state()  # Save cleared state
            else:
                logger.debug(
                    "No position or no TP planned, and no active TP order found.")
            return None  # No TP should be active

        # --- Validate TP Quantity against filters ---
        try:
            # Ensure connector has filters loaded
            filters = self.connector.get_filters(self.symbol)
            if not filters:
                logger.error(
                    f"Cannot place/update TP order for {self.symbol}: Exchange filters not available.")
                return None

            # Import formatting utils locally if needed (or ensure available via imports)
            from src.utils.formatting import apply_filter_rules_to_qty, apply_filter_rules_to_price, validate_min_notional

            # Adjust quantity based on LOT_SIZE filter
            tp_qty_adjusted = apply_filter_rules_to_qty(
                position_size, filters, is_base_asset=True, symbol=self.symbol)
            if tp_qty_adjusted is None or tp_qty_adjusted <= Decimal('0'):
                logger.warning(
                    f"Take Profit quantity {position_size} is invalid or zero after applying LOT_SIZE filter for {self.symbol}. Cannot place/update TP.")
                # Cancel existing TP if qty becomes invalid
                if self.active_tp_order:
                    logger.info(
                        "Cancelling existing TP due to invalid quantity.")
                    self.cancel_order(self.active_tp_order.get(
                        'clientOrderId'), self.active_tp_order.get('orderId'), "TP (Invalid Qty)")
                    self.active_tp_order = None
                    self._save_order_state()
                return None

            # Adjust price based on PRICE_FILTER and PERCENT_PRICE filters
            tp_price_adjusted = apply_filter_rules_to_price(
                tp_price, filters, symbol=self.symbol)
            if tp_price_adjusted is None or tp_price_adjusted <= Decimal('0'):
                logger.warning(
                    f"Take Profit price {tp_price} is invalid after applying price filters for {self.symbol}. Cannot place/update TP.")
                if self.active_tp_order:
                    logger.info("Cancelling existing TP due to invalid price.")
                    self.cancel_order(self.active_tp_order.get(
                        'clientOrderId'), self.active_tp_order.get('orderId'), "TP (Invalid Price)")
                    self.active_tp_order = None
                    self._save_order_state()
                return None

            # Validate MIN_NOTIONAL
            if not validate_min_notional(tp_price_adjusted, tp_qty_adjusted, filters, symbol=self.symbol):
                logger.warning(
                    f"Take Profit order ({tp_qty_adjusted} @ {tp_price_adjusted}) does not meet MIN_NOTIONAL filter for {self.symbol}. Cannot place/update TP.")
                if self.active_tp_order:
                    logger.info(
                        "Cancelling existing TP due to MIN_NOTIONAL failure.")
                    self.cancel_order(self.active_tp_order.get(
                        'clientOrderId'), self.active_tp_order.get('orderId'), "TP (Min Notional Fail)")
                    self.active_tp_order = None
                    self._save_order_state()
                return None

            logger.debug(
                f"Validated TP parameters: Qty={tp_qty_adjusted}, Price={tp_price_adjusted}")
            target_tp_qty = tp_qty_adjusted
            target_tp_price = tp_price_adjusted

        except Exception as e:
            logger.error(
                f"Error applying filters to TP order (Qty:{position_size}, Price:{tp_price}): {e}", exc_info=True)
            return None  # Cannot proceed without valid filtered parameters

        # --- Compare with active TP order ---
        needs_update = False
        if self.active_tp_order:
            try:
                # Use consistent precision for comparison
                price_precision = Decimal('1e-8')  # Match reconcile logic
                # Match reconcile logic (adjust based on actual asset precision if needed)
                qty_precision = Decimal('1e-8')

                active_price = Decimal(self.active_tp_order.get(
                    'price', '0')).quantize(price_precision)
                active_qty = Decimal(self.active_tp_order.get(
                    'origQty', '0')).quantize(qty_precision)
                target_price_q = target_tp_price.quantize(price_precision)
                target_qty_q = target_tp_qty.quantize(qty_precision)

                price_differs = active_price != target_price_q
                qty_differs = active_qty != target_qty_q

                if price_differs or qty_differs:
                    logger.info(
                        f"Take Profit order needs update. Active: {active_qty} @ {active_price}, Target: {target_qty_q} @ {target_price_q}")
                    needs_update = True
                    # Cancel the existing order before placing a new one
                    logger.debug(
                        f"Cancelling existing TP order {self.active_tp_order.get('clientOrderId')} before update.")
                    cancel_success_id = self.cancel_order(
                        self.active_tp_order.get('clientOrderId'),
                        self.active_tp_order.get('orderId'),
                        "TP (Update)"
                    )
                    if cancel_success_id is not None:
                        logger.info(
                            f"Successfully cancelled existing TP order {cancel_success_id} for update.")
                        self.active_tp_order = None  # Clear internal state after successful cancel
                    else:
                        logger.error(
                            "Failed to cancel existing TP order. Cannot place updated TP.")
                        self._save_order_state()  # Save state even if cancel failed
                        return None  # Abort update if cancellation fails
                else:
                    logger.debug(
                        f"Active TP order already matches target ({target_tp_qty} @ {target_tp_price}). No update needed.")
                    # No need to save state if nothing changed
                    return self.active_tp_order  # Return the existing order

            except (InvalidOperation, TypeError) as parse_err:
                logger.warning(
                    f"Could not parse active TP order details for comparison: {parse_err}. Will attempt to cancel and replace. Active TP: {self.active_tp_order}")
                needs_update = True
                cancel_success_id = self.cancel_order(
                    self.active_tp_order.get('clientOrderId'),
                    self.active_tp_order.get('orderId'),
                    "TP (Parse Error)"
                )
                if cancel_success_id is not None:
                    self.active_tp_order = None
                else:
                    logger.error("Failed cancel TP after parse error.")
                    return None

        # --- Place New TP Order (if no active one or if update needed) ---
        if self.active_tp_order is None:  # Place if no active order or if cancelled for update
            client_order_id = f"gt_tp_{self.symbol}_{int(time.time() * 1000)}"
            new_tp_order_data = None

            if self.simulation_mode:
                sim_order_id = self._get_next_sim_order_id()
                new_tp_order_data = {
                    'symbol': self.symbol,
                    'orderId': sim_order_id,
                    'clientOrderId': client_order_id,
                    'price': str(target_tp_price),  # Use validated price
                    'origQty': str(target_tp_qty),  # Use validated quantity
                    'executedQty': '0.00000000',
                    'cummulativeQuoteQty': '0.00000000',
                    'status': 'NEW',
                    'timeInForce': 'GTC',  # Assuming GTC
                    'type': 'LIMIT',
                    'side': 'SELL',
                    'isWorking': True,
                    'time': int(time.time() * 1000),
                    'updateTime': int(time.time() * 1000)
                }
                logger.info(
                    f"[SIM] Placing new Take Profit order: {client_order_id} for {target_tp_qty} @ {target_tp_price}")
                self.place_attempts += 1
            else:  # Live Mode
                try:
                    logger.info(
                        f"Attempting to place LIVE Take Profit order: {client_order_id} for {target_tp_qty} @ {target_tp_price}")
                    order_response = self.connector.create_limit_sell(
                        symbol=self.symbol,
                        quantity=target_tp_qty,  # Use validated Decimal qty
                        price=target_tp_price,  # Use validated Decimal price
                        newClientOrderId=client_order_id
                    )
                    if order_response and isinstance(order_response, dict):
                        logger.info(
                            f"LIVE Take Profit order placement successful: {order_response.get('clientOrderId')} (ID: {order_response.get('orderId')}), Status: {order_response.get('status')}")
                        new_tp_order_data = order_response
                        self.place_attempts += 1
                    else:
                        logger.error(
                            f"LIVE Take Profit order placement failed. Qty={target_tp_qty}, Price={target_tp_price}. Response: {order_response}")
                        self.place_failures += 1
                except Exception as e:
                    logger.error(
                        f"Exception occurred placing live Take Profit order (Qty:{target_tp_qty}, Price:{target_tp_price}): {e}", exc_info=True)
                    self.place_failures += 1

            # Update internal state and save if placement (sim or live) was successful
            if new_tp_order_data:
                self.active_tp_order = new_tp_order_data
                self._save_order_state()
                return self.active_tp_order
            else:
                # Placement failed, ensure active_tp_order remains None
                self.active_tp_order = None
                self._save_order_state()
                return None
        else:
            # This case should only be reached if the existing order matched the target and no update was needed
            return self.active_tp_order

    def cancel_order(self, client_order_id: Optional[str], order_id: Optional[str], order_type_label: str) -> Optional[str]:
        """
        Attempts to cancel an order using clientOrderId or orderId.
        Handles simulation vs live mode.
        Returns the ID used for cancellation if successful or handled, None otherwise.
        """
        if not client_order_id and not order_id:
            logger.warning(
                f"Cannot cancel {order_type_label} order: No clientOrderId or orderId provided.")
            return None

        # Prefer clientOrderId if available, fallback to orderId
        target_id = client_order_id or order_id
        id_type = "ClientOrderId" if client_order_id else "OrderId"
        self.cancel_attempts += 1

        if self.simulation_mode:
            # In simulation, simply log the cancellation attempt and assume success
            logger.info(
                f"[SIM] Cancelling {order_type_label} order ({id_type}={target_id})")
            # Remove the order from internal state if found (match by either ID)
            original_grid_count = len(self.active_grid_orders)
            self.active_grid_orders = [o for o in self.active_grid_orders if not (
                (client_order_id and o.get('clientOrderId') == client_order_id) or
                (order_id and o.get('orderId') == order_id)
            )]
            if len(self.active_grid_orders) < original_grid_count:
                logger.debug(
                    f"[SIM] Removed cancelled grid order {target_id} from state.")

            if self.active_tp_order and (
                (client_order_id and self.active_tp_order.get('clientOrderId') == client_order_id) or
                    (order_id and self.active_tp_order.get('orderId') == order_id)):
                logger.debug(
                    f"[SIM] Removed cancelled TP order {target_id} from state.")
                self.active_tp_order = None

            self._save_order_state()  # Save updated state after simulated cancel
            return target_id  # Indicate handled

        else:  # Live Mode
            try:
                logger.info(
                    f"Attempting to cancel LIVE {order_type_label} order ({id_type}={target_id})")
                # Use the connector's cancel method
                result = self.connector.cancel_order(
                    symbol=self.symbol,
                    orderId=order_id,  # Pass None if not available
                    origClientOrderId=client_order_id  # Pass None if not available
                )

                # Check the result from the connector
                if result and isinstance(result, dict):
                    # Binance API often returns the cancelled order details
                    status = result.get('status', 'UNKNOWN').upper()
                    final_id = result.get('clientOrderId') or result.get(
                        'orderId') or target_id
                    if status in ['CANCELED', 'EXPIRED']:  # Definite success
                        logger.info(
                            f"Successfully cancelled LIVE {order_type_label} order {final_id}. Final Status: {status}")
                        # Remove from internal state immediately on confirmation
                        self.active_grid_orders = [o for o in self.active_grid_orders if not (
                            (client_order_id and o.get('clientOrderId') == client_order_id) or
                            (order_id and o.get('orderId') == order_id)
                        )]
                        if self.active_tp_order and (
                            (client_order_id and self.active_tp_order.get('clientOrderId') == client_order_id) or
                                (order_id and self.active_tp_order.get('orderId') == order_id)):
                            self.active_tp_order = None
                        self._save_order_state()
                        return final_id
                    elif status in ['PENDING_CANCEL']:
                        logger.info(
                            f"LIVE {order_type_label} order {final_id} cancellation pending. Status: {status}. Assuming success for now.")
                        # Remove from internal state optimistically
                        self.active_grid_orders = [o for o in self.active_grid_orders if not (
                            (client_order_id and o.get('clientOrderId') == client_order_id) or
                            (order_id and o.get('orderId') == order_id)
                        )]
                        if self.active_tp_order and (
                           (client_order_id and self.active_tp_order.get('clientOrderId') == client_order_id) or
                           (order_id and self.active_tp_order.get('orderId') == order_id)):
                            self.active_tp_order = None
                        self._save_order_state()
                        return final_id  # Indicate handled
                    else:
                        # This might happen if the order was already FILLED or REJECTED
                        logger.warning(
                            f"Cancel request for LIVE {order_type_label} order {final_id} returned status '{status}'. Order might not have been open.")
                        # Check if it was already filled - check_orders should handle this, but maybe remove here too
                        if status not in ['NEW', 'PARTIALLY_FILLED']:
                            self.active_grid_orders = [o for o in self.active_grid_orders if not (
                                (client_order_id and o.get('clientOrderId') == client_order_id) or
                                (order_id and o.get('orderId') == order_id)
                            )]
                            if self.active_tp_order and (
                                (client_order_id and self.active_tp_order.get('clientOrderId') == client_order_id) or
                                    (order_id and self.active_tp_order.get('orderId') == order_id)):
                                self.active_tp_order = None
                            self._save_order_state()
                        # Indicate handled (even if not actually cancelled now)
                        return target_id
                # Handle cases where the connector might return a simple boolean or None
                # Adjust based on your connector's specific cancel_order implementation
                elif result is True:  # Simple success indicator
                    logger.info(
                        f"Cancel request for LIVE {order_type_label} order {target_id} successful (Boolean response).")
                    # Remove from state
                    self.active_grid_orders = [o for o in self.active_grid_orders if not (
                        (client_order_id and o.get('clientOrderId') == client_order_id) or
                        (order_id and o.get('orderId') == order_id)
                    )]
                    if self.active_tp_order and (
                       (client_order_id and self.active_tp_order.get('clientOrderId') == client_order_id) or
                       (order_id and self.active_tp_order.get('orderId') == order_id)):
                        self.active_tp_order = None
                    self._save_order_state()
                    return target_id
                else:  # Result is None, False, or unexpected type
                    logger.error(
                        f"Cancel request for LIVE {order_type_label} order {target_id} failed or returned unexpected result: {result}")
                    self.cancel_failures += 1
                    return None

            except Exception as e:
                # Specific handling for "Order does not exist" could go here if the connector raises distinct exceptions
                # Example: if isinstance(e, OrderNotFoundException): logger.info(...) return target_id
                logger.error(
                    f"Exception occurred cancelling LIVE {order_type_label} order {target_id}: {e}", exc_info=True)
                self.cancel_failures += 1
                # Decide if an "Order does not exist" error should be treated as success for removal purposes
                # For now, treat all exceptions as failure to cancel.
                return None

    def execute_market_sell(self, quantity: Decimal, reason: str) -> Optional[Dict]:
        """Executes an immediate market sell order for the specified quantity."""
        self._load_order_state()  # Load state to access current kline for sim price

        if quantity <= Decimal('0'):
            logger.warning(
                f"Market sell ({reason}) requested with invalid quantity: {quantity}. Skipping.")
            return None

        # --- Validate Quantity against filters ---
        try:
            filters = self.connector.get_filters(self.symbol)
            if not filters:
                logger.error(
                    f"Cannot execute market sell ({reason}): Exchange filters not available for {self.symbol}.")
                return None

            from src.utils.formatting import apply_filter_rules_to_qty, validate_notional_market

            # Apply LOT_SIZE filter
            sell_qty_adjusted = apply_filter_rules_to_qty(
                quantity, filters, is_base_asset=True, symbol=self.symbol)
            if sell_qty_adjusted is None or sell_qty_adjusted <= Decimal('0'):
                logger.error(
                    f"Market sell ({reason}) quantity {quantity} is invalid or zero after applying LOT_SIZE filter for {self.symbol}.")
                return None

            # Apply MARKET_LOT_SIZE filter if present (often same as LOT_SIZE)
            # Re-apply using the potentially adjusted quantity
            sell_qty_adjusted = apply_filter_rules_to_qty(
                sell_qty_adjusted, filters, is_base_asset=True, symbol=self.symbol, filter_type='MARKET_LOT_SIZE')
            if sell_qty_adjusted is None or sell_qty_adjusted <= Decimal('0'):
                logger.error(
                    f"Market sell ({reason}) quantity {quantity} is invalid or zero after applying MARKET_LOT_SIZE filter for {self.symbol}.")
                return None

            # Validate NOTIONAL (Market) - requires estimated price
            # Get current price for estimation (use last close price from state)
            current_kline_data = self.state_manager.load_state().get('current_kline', {})
            est_price = to_decimal(current_kline_data.get('close'))
            if est_price is None or est_price <= 0:
                logger.warning(
                    f"Market sell ({reason}): Cannot estimate price for NOTIONAL check. Proceeding with caution.")
                # Optionally fail here if NOTIONAL check is critical
            elif not validate_notional_market(est_price, sell_qty_adjusted, filters, symbol=self.symbol):
                logger.error(
                    f"Market sell ({reason}) order ({sell_qty_adjusted} @ ~{est_price}) does not meet NOTIONAL (Market) filter for {self.symbol}.")
                return None

            logger.debug(
                f"Validated market sell quantity ({reason}): {sell_qty_adjusted}")
            target_sell_qty = sell_qty_adjusted

        except Exception as e:
            logger.error(
                f"Error applying filters to market sell ({reason}) order (Qty:{quantity}): {e}", exc_info=True)
            return None

        # --- Execute Order ---
        client_order_id = f"gt_mkt_sell_{self.symbol}_{reason}_{int(time.time() * 1000)}"

        if self.simulation_mode:
            self.sim_market_sell_counter += 1
            # Estimate fill price (e.g., use current close or open price)
            current_kline = self.state.get('current_kline', {})
            # Use close if available, otherwise open, default to 1 to avoid zero division
            sim_fill_price = to_decimal(current_kline.get('close')) or to_decimal(
                current_kline.get('open')) or Decimal('1')

            sim_quote_proceeds = target_sell_qty * sim_fill_price

            # Simulate the response structure
            sim_response = {
                'symbol': self.symbol,
                'orderId': f"sim_mkt_{self.sim_market_sell_counter}",
                'clientOrderId': client_order_id,
                'transactTime': int(time.time() * 1000),
                'price': '0',  # Market orders have price 0
                'origQty': str(target_sell_qty),
                'executedQty': str(target_sell_qty),  # Assume full fill in sim
                'cummulativeQuoteQty': str(sim_quote_proceeds),
                'status': 'FILLED',
                'type': 'MARKET',
                'side': 'SELL',
                # Simulate a single fill entry
                'fills': [{
                    'price': str(sim_fill_price),
                    'qty': str(target_sell_qty),
                    'commission': '0',  # Simulating zero fees for now
                    'commissionAsset': self.quote_asset,
                    'tradeId': self.sim_market_sell_counter  # Simple sim trade ID
                }]
            }
            logger.info(
                f"[SIM] Executing Market Sell ({reason}): {client_order_id} for {target_sell_qty} @ ~{sim_fill_price}")

            # Manually update simulated balances immediately
            # Need to load current state to update balances
            current_state = self.state_manager.load_state()
            current_state['balance_quote'] = current_state.get(
                'balance_quote', Decimal('0')) + sim_quote_proceeds
            current_state['balance_base'] = max(Decimal('0'), current_state.get(
                'balance_base', Decimal('0')) - target_sell_qty)
            # Also clear position info immediately after market sell execution in sim
            current_state['position_size'] = Decimal('0')
            current_state['position_entry_price'] = Decimal('0')
            current_state['position_entry_timestamp'] = None
            # Cancel any active TP order immediately
            if current_state.get('active_tp_order'):
                logger.info(
                    "[SIM] Clearing active TP order due to market sell.")
                current_state['active_tp_order'] = None
            self.state_manager.save_state(current_state)  # Save updated state

            return sim_response

        else:  # Live Mode
            try:
                logger.info(
                    f"Attempting to execute LIVE Market Sell ({reason}): {client_order_id} for {target_sell_qty}")
                # Use the connector's market sell method
                order_response = self.connector.create_market_sell(
                    symbol=self.symbol,
                    quantity=target_sell_qty,  # Use validated Decimal qty
                    newClientOrderId=client_order_id
                )

                if order_response and isinstance(order_response, dict):
                    # Market orders usually return FILLED status immediately if successful
                    logger.info(
                        f"LIVE Market Sell ({reason}) submitted/executed: {order_response.get('clientOrderId')} (ID: {order_response.get('orderId')}), Status: {order_response.get('status')}")
                    # NOTE: Actual balance update happens when _process_fills sees this based on check_orders or webhook
                    # We *don't* modify main state here for live, just return the response.
                    # However, we *should* immediately cancel any active TP order in our state
                    self._load_order_state()
                    if self.active_tp_order:
                        logger.info(
                            f"Market sell placed. Cancelling tracked active TP order {self.active_tp_order.get('clientOrderId')} preventatively.")
                        self.cancel_order(self.active_tp_order.get(
                            'clientOrderId'), self.active_tp_order.get('orderId'), "TP (Post Market Sell)")
                        self.active_tp_order = None
                        self._save_order_state()

                else:
                    logger.error(
                        f"LIVE Market Sell ({reason}) failed for quantity {target_sell_qty}. Response: {order_response}")

                # Return API response (or None if initial call failed)
                return order_response

            except Exception as e:
                logger.error(
                    f"Exception occurred executing live market sell ({reason}) for quantity {target_sell_qty}: {e}", exc_info=True)
                return None


# EOF: src/core/order_manager.py
