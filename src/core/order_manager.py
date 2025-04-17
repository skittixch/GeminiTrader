# START OF FILE: src/core/order_manager.py (Corrected Validation Calls - FINAL v2 Merged)

import logging
import time
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Any

# Project Modules
from config.settings import get_config_value
from src.connectors.binance_us import BinanceUSConnector
# StateManager import removed
from src.utils.formatting import (
    to_decimal,
    apply_filter_rules_to_qty,
    apply_filter_rules_to_price,
    validate_order_filters
)

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Handles order placement, cancellation, tracking, and state updates.
    Requires the application state dictionary to be passed into relevant methods.
    """

    def __init__(self, config_dict: Dict, connector: BinanceUSConnector):
        self.config = config_dict
        self.connector = connector
        self.symbol = get_config_value(
            config_dict, ('trading', 'symbol'), 'BTCUSDT')
        self.quote_asset = get_config_value(
            config_dict, ('portfolio', 'quote_asset'), 'USDT')
        if self.symbol.endswith(self.quote_asset):
            self.base_asset = self.symbol[:-len(self.quote_asset)]
        else:
            # Attempt to infer base asset if quote doesn't match end
            common_bases = ['BTC', 'ETH']  # Extend as needed
            inferred = False
            for base in common_bases:
                if self.symbol.startswith(base):
                    self.base_asset = base
                    inferred = True
                    logger.info(f"Inferred base asset: {self.base_asset}")
                    break
            if not inferred:
                # Fallback or raise error if base asset cannot be determined
                self.base_asset = self.symbol.replace(
                    self.quote_asset, '')  # Basic replace as fallback
                logger.warning(
                    f"Base asset determination might be incorrect: Inferred as '{self.base_asset}' for symbol '{self.symbol}'. Verify correctness.")
                # Consider raising ValueError("Cannot determine base asset")

        self.simulation_mode = get_config_value(
            config_dict, ('trading', 'simulation_mode'), False)

        # Counters
        self.sim_order_id_counter = int(time.time() * 1000)
        self.sim_filled_buy_count = 0
        self.sim_filled_sell_count = 0

        # Fetch exchange info (Ensure exchange_info is stored)
        self.exchange_info = self.connector.get_exchange_info_cached()
        if not self.exchange_info:
            logger.warning(
                "Cached exchange info not found during OM init. Fetching fresh.")
            self.exchange_info = self.connector.get_exchange_info(
                force_refresh=True)
            if not self.exchange_info:
                # Use raise ValueError for critical init failures
                raise ValueError(
                    "OrderManager failed to initialize: Could not load Exchange Info.")
        logger.info("OrderManager initialized. Exchange Info loaded.")

    def _generate_client_order_id(self, prefix: str = "gt") -> str:
        """Generates a unique client order ID."""
        ts_part = int(time.time() * 1000)
        # Ensure length constraint (e.g., max 36 for Binance API)
        return f"{prefix}_{ts_part}"[-36:]

    # <<< MODIFIED: Accepts state dict >>>
    def _add_order_to_state(self, state: Dict, order_type: str, order_details: Dict) -> bool:
        """
        Adds order to the PASSED state dict. Returns True if added.
        NOTE: Saving the state is handled by the caller.
        """
        if not isinstance(state, dict):
            logger.error(
                "_add_order_to_state: Invalid state dictionary provided.")
            return False

        modified = False
        if order_type == 'grid':
            # Ensure key exists and is a list
            if not isinstance(state.get('active_grid_orders'), list):
                state['active_grid_orders'] = []
            # Prevent duplicates (optional but good practice)
            cid = order_details.get('clientOrderId')
            if cid and any(o.get('clientOrderId') == cid for o in state['active_grid_orders']):
                logger.warning(
                    f"Skipping duplicate grid order CID {cid} in _add_order_to_state.")
                # Return False as nothing was added, but log as warning not error
                return False
            else:
                state['active_grid_orders'].append(order_details)
                logger.debug(f"Added grid order {cid} to state dict.")
                modified = True
        elif order_type == 'tp':
            # Check if overwriting is intended
            existing_tp = state.get('active_tp_order')
            if existing_tp and isinstance(existing_tp, dict):
                logger.warning(
                    f"Overwriting existing active TP order {existing_tp.get('clientOrderId')} with new TP order {order_details.get('clientOrderId')}.")
            state['active_tp_order'] = order_details
            logger.debug(
                f"Added/Updated TP order {order_details.get('clientOrderId')} in state dict.")
            modified = True
        else:
            logger.error(
                f"Unknown order type '{order_type}' in _add_order_to_state.")
            return False

        return modified

    # <<< MODIFIED: Accepts state dict >>>
    def _remove_order_from_state(self, state: Dict, client_order_id: Optional[str] = None, order_id: Optional[str] = None) -> bool:
        """
        Removes order from the PASSED state dict based on ID. Returns True if removed.
        NOTE: Saving the state is handled by the caller.
        """
        if not isinstance(state, dict):
            logger.error(
                "_remove_order_from_state: Invalid state dictionary provided.")
            return False
        if not client_order_id and not order_id:
            logger.warning("_remove_order_from_state: No ID provided.")
            return False  # Indicate failure

        removed = False
        id_to_log = client_order_id or order_id  # Log whichever ID is available

        # Check Grid Orders
        active_grid = state.get('active_grid_orders', [])
        if isinstance(active_grid, list):
            initial_count = len(active_grid)
            # Filter out the matching order
            new_grid = [
                order for order in active_grid
                if not (
                    (client_order_id and order.get('clientOrderId') == client_order_id) or
                    # Ensure order_id comparison handles string/int mismatch if needed
                    (order_id and str(order.get('orderId')) == str(order_id))
                )
            ]
            if len(new_grid) < initial_count:
                state['active_grid_orders'] = new_grid  # Modify passed dict
                removed = True
                logger.debug(
                    f"Removed grid order {id_to_log} from state dict.")
            # else: Order not found, no change needed

        # Check TP Order
        active_tp = state.get('active_tp_order')
        if isinstance(active_tp, dict):  # Check if it's a dict before accessing keys
            match_tp = False
            if client_order_id and active_tp.get('clientOrderId') == client_order_id:
                match_tp = True
            elif order_id and str(active_tp.get('orderId')) == str(order_id):
                match_tp = True

            if match_tp:
                state['active_tp_order'] = None  # Set to None to remove
                removed = True
                logger.debug(
                    f"Removed TP order {id_to_log} from state dict.")

        if not removed:
            logger.debug(f"Order {id_to_log} not found in state for removal.")

        return removed

    # <<< MODIFIED: Accepts state dict >>>
    def check_orders(self, state: Dict, current_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """
        Checks the status of active orders in the PASSED state dictionary.
        Simulates fills if in simulation mode.
        Returns dictionary containing lists of filled orders.
        NOTE: Saving the state after processing fills is handled by the caller.
        """
        logger.info(
            "--- Entered check_orders ---")  # Keep INFO log for cycle demarcation
        if not isinstance(state, dict):
            logger.error("check_orders: Invalid state dict provided.")
            return {'grid_fills': [], 'tp_fill': None}

        active_grid = state.get('active_grid_orders', [])
        active_tp = state.get('active_tp_order')
        grid_fills = []
        tp_fill = None
        if not isinstance(active_grid, list):
            active_grid = []
        if not isinstance(active_tp, dict) and active_tp is not None:
            # Ensure active_tp is either a dict or None
            logger.warning(
                f"Correcting invalid active_tp_order state type: {type(active_tp)}")
            active_tp = None

        # --- Check Grid Orders ---
        remaining_grid_orders = []  # List to store orders that remain active
        for order in active_grid:
            # Basic type check for robustness
            if not isinstance(order, dict):
                logger.warning(
                    f"Skipping invalid item in active_grid_orders (not a dict): {order}")
                continue

            order_id = order.get('orderId')  # Can be None initially
            order_id_str = str(order_id) if order_id is not None else "N/A"
            # Should ideally always exist
            client_order_id = order.get('clientOrderId')
            order_price = to_decimal(order.get('price'))
            # Need original qty for sim fill
            order_qty = to_decimal(order.get('origQty'))
            order_processed = False  # Flag to check if order was handled this cycle

            if self.simulation_mode:
                if current_price is not None and order_price is not None and order_qty is not None:
                    # Grid BUY fills if market price drops to or below order price
                    is_fill = current_price <= order_price

                    # Keep DEBUG log for detailed sim checks
                    logger.debug(
                        f"Sim Check Grid: OrderPrice={order_price:.4f}, CurrentPrice={current_price:.4f}, IsFill?={is_fill} (ClientID: {client_order_id})")
                    if is_fill:
                        logger.info(
                            f"Sim: Grid order {client_order_id or order_id_str} (Price: {order_price}) filled at current price {current_price:.4f}")
                        # Construct fill details based on simulation logic
                        sim_fill_details = {
                            **order,  # Include original order details
                            'status': 'FILLED',
                            # Assume full fill in basic sim
                            'executedQty': str(order_qty),
                            # Use order price for sim
                            'cummulativeQuoteQty': str(order_price * order_qty),
                            # Simulate timestamp
                            'updateTime': int(time.time() * 1000)
                        }
                        grid_fills.append(sim_fill_details)
                        self.sim_filled_buy_count += 1
                        order_processed = True  # Mark as processed (filled)
                        # Order is NOT added to remaining_grid_orders if processed
                    # else: Order remains active, will be added to remaining list below if !order_processed
                else:
                    # Log if comparison can't happen
                    logger.warning(
                        f"Sim Check Grid: Cannot compare for {client_order_id or order_id_str}. OrderPrice={order_price}, CurrentPrice={current_price}, OrderQty={order_qty}")
                    # Keep order active if check failed (order_processed remains False)
            else:  # Live Mode
                if not order_id and not client_order_id:
                    logger.error(
                        f"Live Check Grid: Cannot check order status, missing both IDs: {order}")
                    # Treat as processed (cannot check) to remove from active checks? Or keep trying?
                    # Keep trying for now. order_processed remains False
                else:
                    logger.debug(
                        f"Live: Checking status for grid order {order_id_str} / {client_order_id}")
                    try:
                        # Use the connector method that handles ID priority
                        status_info = self.connector.get_order_status(
                            self.symbol, orderId=order_id, origClientOrderId=client_order_id)
                        if status_info:
                            status = status_info.get('status')
                            logger.debug(
                                f"Live: Order {order_id_str or client_order_id} Status: {status}")
                            if status == 'FILLED':
                                # Append full details
                                grid_fills.append(status_info)
                                order_processed = True
                            # Treat terminal states as processed
                            # Added UNKNOWN as a potential terminal state from some exchanges/conditions
                            elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'PENDING_CANCEL', 'UNKNOWN']:
                                logger.warning(
                                    f"Live: Grid order {order_id_str or client_order_id} found in terminal/unknown state: {status}. Removing from active list.")
                                order_processed = True
                            # else: NEW, PARTIALLY_FILLED etc. remain active (order_processed = False)
                        else:
                            # Status check failed or order not found
                            logger.warning(
                                f"Live: Failed to get status for grid order {order_id_str or client_order_id} or order not found. Assuming inactive.")
                            order_processed = True  # Treat failure to find as processed/inactive
                    except Exception as e:
                        logger.error(
                            f"Live: Error checking grid order {order_id_str or client_order_id}: {e}", exc_info=False)
                        # Keep checking on error (order_processed = False)

            # Only add order to remaining list if it WASN'T processed
            if not order_processed:
                remaining_grid_orders.append(order)

        # Modify passed state dict directly
        state['active_grid_orders'] = remaining_grid_orders

        # --- Check Take Profit Order ---
        tp_processed = False  # Flag for TP state update
        if active_tp:  # active_tp should be a dict or None here
            tp_order_id = active_tp.get('orderId')
            tp_order_id_str = str(
                tp_order_id) if tp_order_id is not None else "N/A"
            tp_client_order_id = active_tp.get('clientOrderId')
            tp_price = to_decimal(active_tp.get('price'))
            # Need original qty for sim fill
            tp_qty = to_decimal(active_tp.get('origQty'))

            if self.simulation_mode:
                if current_price is not None and tp_price is not None and tp_qty is not None:
                    # TP SELL fills if market price rises to or above order price
                    is_fill = current_price >= tp_price
                    # Keep DEBUG log for detailed sim checks
                    logger.debug(
                        f"Sim Check TP: OrderPrice={tp_price:.4f}, CurrentPrice={current_price:.4f}, IsFill?={is_fill} (ClientID: {tp_client_order_id})")
                    if is_fill:
                        logger.info(
                            f"Sim: TP order {tp_client_order_id or tp_order_id_str} (Price: {tp_price}) filled at current price {current_price:.4f}.")
                        sim_fill_details = {
                            **active_tp,  # Include original details
                            'status': 'FILLED',
                            'executedQty': str(tp_qty),  # Assume full fill
                            # Use order price for sim
                            'cummulativeQuoteQty': str(tp_price * tp_qty),
                            # Simulate timestamp
                            'updateTime': int(time.time() * 1000)
                        }
                        tp_fill = sim_fill_details
                        tp_processed = True  # Mark TP as processed
                        self.sim_filled_sell_count += 1
                    # else: TP remains active (tp_processed = False)
                else:
                    logger.warning(
                        f"Sim Check TP: Cannot compare for {tp_client_order_id or tp_order_id_str}. TP_Price={tp_price}, CurrentPrice={current_price}, TP_Qty={tp_qty}")
                    # Keep TP active if check failed (tp_processed = False)
            else:  # Live Mode
                if not tp_order_id and not tp_client_order_id:
                    logger.error(
                        f"Live Check TP: Cannot check status, missing both IDs: {active_tp}")
                    tp_processed = True  # Treat as processed/error state
                else:
                    logger.debug(
                        f"Live: Checking status for TP order {tp_order_id_str} / {tp_client_order_id}")
                    try:
                        status_info = self.connector.get_order_status(
                            self.symbol, orderId=tp_order_id, origClientOrderId=tp_client_order_id)
                        if status_info:
                            status = status_info.get('status')
                            logger.debug(
                                f"Live: Order {tp_order_id_str or tp_client_order_id} Status: {status}")
                            if status == 'FILLED':
                                tp_fill = status_info  # Store full details
                                tp_processed = True
                            # Added UNKNOWN
                            elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'PENDING_CANCEL', 'UNKNOWN']:
                                logger.warning(
                                    f"Live: TP order {tp_order_id_str or tp_client_order_id} found in terminal/unknown state: {status}. Removing from active list.")
                                tp_processed = True
                            # else: NEW, PARTIALLY_FILLED etc. remain active (tp_processed = False)
                        else:
                            logger.warning(
                                f"Live: Failed to get status for TP order {tp_order_id_str or tp_client_order_id} or order not found. Assuming inactive.")
                            tp_processed = True  # Treat failure to find as processed/inactive
                    except Exception as e:
                        logger.error(
                            f"Live: Error checking TP order {tp_order_id_str or tp_client_order_id}: {e}", exc_info=False)
                        # Keep checking on error (tp_processed = False)

            # Update passed state dict TP order *only* if it was processed
            if tp_processed:
                state['active_tp_order'] = None

        # NOTE: Do NOT save state here. Caller (main_trader) will save after processing fills.
        return {'grid_fills': grid_fills, 'tp_fill': tp_fill}

    # <<< MODIFIED: Accepts state dict >>>
    def reconcile_and_place_grid(self, state: Dict, planned_grid: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Compares planned grid with active orders in PASSED state dict.
        Cancels outdated orders and places new ones.
        Modifies the PASSED state dict directly for additions/removals.
        Returns dictionary summarizing actions.
        NOTE: Saving the state is handled by the caller.
        """
        if not isinstance(state, dict):
            logger.error("reconcile_and_place_grid: Invalid state dict.")
            return {'placed': [], 'cancelled': [], 'failed_cancel': [], 'failed_place': [], 'unchanged': []}

        # Get active orders from the PASSED state
        active_grid_orders = state.get('active_grid_orders', [])
        if not isinstance(active_grid_orders, list):
            active_grid_orders = []
        # Keep INFO log for overview
        logger.info(
            f"Reconciling Grid Orders: Planned={len(planned_grid)}, Currently Active State={len(active_grid_orders)}")

        # Build maps for comparison (logic remains the same)
        active_orders_map = {}
        for o in active_grid_orders:
            price = to_decimal(o.get('price'))
            if price is not None:
                active_orders_map[str(price)] = o
            else:
                logger.warning(
                    f"Active grid order missing price, cannot reconcile: {o}")

        planned_orders_map = {}
        for p in planned_grid:
            price = to_decimal(p.get('price'))
            if price is not None:
                planned_orders_map[str(price)] = p
            else:
                logger.warning(f"Planned grid order missing price: {p}")

        active_prices_str = set(active_orders_map.keys())
        planned_prices_str = set(planned_orders_map.keys())

        orders_to_cancel_prices_str = active_prices_str - planned_prices_str
        orders_to_place_prices_str = planned_prices_str - active_prices_str
        orders_unchanged_prices_str = active_prices_str.intersection(
            planned_prices_str)

        results: Dict[str, List[Any]] = {'placed': [], 'cancelled': [
        ], 'failed_cancel': [], 'failed_place': [], 'unchanged': []}

        # --- Cancel Outdated ---
        if orders_to_cancel_prices_str:
            # Use INFO log for cancellation intent
            logger.info(
                f"Cancelling {len(orders_to_cancel_prices_str)} outdated grid orders...")
            for price_str in orders_to_cancel_prices_str:
                order_to_cancel = active_orders_map[price_str]
                client_order_id = order_to_cancel.get('clientOrderId')
                order_id = order_to_cancel.get('orderId')
                # Pass state to cancel_order
                if self.cancel_order(state, client_order_id, order_id, reason="GridReconcile_Outdated"):
                    results['cancelled'].append(order_to_cancel)
                else:
                    results['failed_cancel'].append(
                        {**order_to_cancel, 'fail_reason': 'Cancellation failed'})

        # --- Place New ---
        if orders_to_place_prices_str:
            # Use INFO log for placement intent
            logger.info(
                f"Placing {len(orders_to_place_prices_str)} new grid orders...")
            for price_str in orders_to_place_prices_str:
                order_to_place = planned_orders_map[price_str]
                price = to_decimal(order_to_place.get(
                    'price'))  # Original planned price
                # Original planned quantity
                qty = to_decimal(order_to_place.get('quantity'))

                if price is None or qty is None or qty <= Decimal('0'):
                    logger.error(
                        f"Cannot place planned grid order, invalid original price/qty: P={price}, Q={qty}. Detail: {order_to_place}")
                    results['failed_place'].append(
                        {**order_to_place, 'fail_reason': 'Invalid original price/qty'})
                    continue

                # Apply filters before validation and placement
                adj_price = apply_filter_rules_to_price(
                    self.symbol, price, self.exchange_info, operation='adjust')
                adj_qty = apply_filter_rules_to_qty(
                    self.symbol, qty, self.exchange_info, operation='floor')  # Floor BUY qty

                if adj_price is None or adj_qty is None or adj_qty <= Decimal('0'):
                    logger.error(
                        f"Filter application failed for planned grid order: P={price}->{adj_price}, Q={qty}->{adj_qty}. Skipping.")
                    results['failed_place'].append(
                        {**order_to_place, 'fail_reason': 'Filter application failed'})
                    continue

                # <<< VERIFIED CORRECT VALIDATION CALL >>>
                if not validate_order_filters(symbol=self.symbol, quantity=adj_qty, price=adj_price, exchange_info=self.exchange_info):
                    logger.error(
                        f"Grid order (AdjQty:{adj_qty}, AdjPx:{adj_price}) failed filter validation. Skipping.")
                    results['failed_place'].append(
                        {**order_to_place, 'fail_reason': 'Filter validation failed'})
                    continue
                # <<< END VERIFIED CORRECTION >>>

                # Generate Client ID using internal method
                client_order_id = self._generate_client_order_id("grid")
                # Log adjusted values with INFO
                logger.info(
                    f"Placing new grid BUY order: Qty={adj_qty:.8f} @ Price={adj_price:.4f} (Client ID: {client_order_id})")

                if self.simulation_mode:
                    # Simulate placement using adjusted values
                    sim_order = {
                        'symbol': self.symbol,
                        'orderId': self.sim_order_id_counter,
                        'clientOrderId': client_order_id,
                        'transactTime': int(time.time() * 1000),
                        'price': str(adj_price),  # Use adjusted price
                        'origQty': str(adj_qty),  # Use adjusted quantity
                        'executedQty': '0',
                        'cummulativeQuoteQty': '0',
                        'status': 'NEW',
                        'timeInForce': 'GTC',
                        'type': 'LIMIT',
                        'side': 'BUY'
                    }
                    self.sim_order_id_counter += 1
                    # Pass state to _add_order_to_state
                    if self._add_order_to_state(state, 'grid', sim_order):
                        results['placed'].append(sim_order)
                    else:
                        results['failed_place'].append(
                            {**order_to_place, 'clientOrderId': client_order_id, 'fail_reason': 'Failed add sim order to state'})
                else:  # Live placement
                    try:
                        # Use adjusted price and quantity
                        api_response = self.connector.create_limit_buy(
                            symbol=self.symbol, quantity=adj_qty, price=adj_price, newClientOrderId=client_order_id)
                        if api_response:
                            logger.info(
                                f"Successfully placed live grid order: {api_response.get('orderId')} / {api_response.get('clientOrderId')}")
                            # Pass state to _add_order_to_state
                            if self._add_order_to_state(state, 'grid', api_response):
                                results['placed'].append(api_response)
                            else:
                                # This case is less likely but possible if state becomes invalid between checks
                                logger.error(
                                    f"Successfully placed live grid order {api_response.get('clientOrderId')} but FAILED TO ADD TO STATE DICT.")
                                results['failed_place'].append(
                                    {**order_to_place, 'clientOrderId': client_order_id, 'fail_reason': 'Placed live but failed add to state'})
                        else:
                            # Handle API rejection not caught by exception
                            logger.error(
                                f"Failed to place grid order (Client ID: {client_order_id}) - Connector returned None/False.")
                            results['failed_place'].append(
                                {**order_to_place, 'clientOrderId': client_order_id, 'fail_reason': 'API placement failed (connector returned None)'})
                    except Exception as e:
                        # Log full traceback for unexpected errors
                        logger.error(
                            f"Exception placing grid order (Client ID: {client_order_id}): {e}", exc_info=True)
                        results['failed_place'].append(
                            {**order_to_place, 'clientOrderId': client_order_id, 'fail_reason': f'API placement exception: {e}'})

        # --- Unchanged ---
        if orders_unchanged_prices_str:
            logger.debug(
                f"{len(orders_unchanged_prices_str)} grid orders remain unchanged.")
            results['unchanged'] = [active_orders_map[p]
                                    for p in orders_unchanged_prices_str]

        # Use INFO for the summary log, as it represents the outcome of the reconciliation step
        log_summary = (
            f"Grid Reconcile Summary: Placed={len(results['placed'])}, Cancelled={len(results['cancelled'])}, "
            f"FailedCancel={len(results['failed_cancel'])}, FailedPlace={len(results['failed_place'])}, Unchanged={len(results['unchanged'])}"
        )
        if results['failed_cancel'] or results['failed_place']:
            logger.warning(log_summary)
        else:
            logger.info(log_summary)

        return results

    # <<< MODIFIED: Accepts state dict >>>
    def place_or_update_tp_order(self, state: Dict, planned_tp_price: Optional[Decimal], position_size: Decimal) -> bool:
        """
        Places or updates the Take Profit LIMIT SELL order based on the PASSED state.
        Modifies the PASSED state dict directly.
        Returns True on success, False on failure.
        NOTE: Saving the state is handled by the caller.
        """
        if not isinstance(state, dict):
            logger.error("place_or_update_tp_order: Invalid state dict.")
            return False
        # Get active TP from the PASSED state
        active_tp_order = state.get('active_tp_order')
        # Validate type after loading
        if not isinstance(active_tp_order, dict) and active_tp_order is not None:
            logger.warning(
                f"Correcting invalid active_tp_order state: {active_tp_order}")
            active_tp_order = None

        # --- Scenario 1: Cancel/Ensure No TP ---
        # Condition: No position OR no valid TP price planned
        if position_size <= Decimal('0') or planned_tp_price is None or planned_tp_price <= Decimal('0'):
            if active_tp_order:
                reason = "TPUpdate_Clear (No Position)" if position_size <= Decimal(
                    '0') else "TPUpdate_Clear (No Valid Plan)"
                logger.info(
                    f"Attempting to cancel existing TP order. Reason: {reason}.")
                client_order_id = active_tp_order.get('clientOrderId')
                order_id = active_tp_order.get('orderId')
                # Pass state to cancel_order
                if self.cancel_order(state, client_order_id, order_id, reason=reason):
                    return True  # Successfully cancelled
                else:
                    logger.error(
                        "Failed to cancel existing TP order during clear operation.")
                    return False  # Failed to achieve desired state (no TP)
            else:
                # No position/plan, and no active TP -> Desired state already achieved
                logger.debug(
                    "No active TP order found and no TP placement required.")
                return True

        # --- Scenario 2: Have position AND Valid Planned TP ---
        # (planned_tp_price is not None and > 0, position_size > 0 here)

        # Apply Filters to planned TP
        # TP SELL order -> floor quantity
        adj_tp_qty = apply_filter_rules_to_qty(
            symbol=self.symbol, quantity=position_size, exchange_info=self.exchange_info, operation='floor')
        # TP SELL order -> adjust price (usually ceil preferred, but adjust is safer default)
        adj_tp_price = apply_filter_rules_to_price(
            symbol=self.symbol, price=planned_tp_price, exchange_info=self.exchange_info, operation='adjust')  # Consider 'ceil'

        if adj_tp_qty is None or adj_tp_qty <= Decimal('0') or adj_tp_price is None or adj_tp_price <= Decimal('0'):
            logger.error(
                f"TP order plan (Qty:{position_size}->{adj_tp_qty}, Px:{planned_tp_price}->{adj_tp_price}) invalid after filters.")
            # If filters make it invalid, should we cancel any existing TP? Yes, probably.
            if active_tp_order:
                logger.warning(
                    "Cancelling existing TP because new plan is invalid after filters.")
                # Pass state to cancel_order
                if self.cancel_order(state, active_tp_order.get('clientOrderId'), active_tp_order.get('orderId'), reason="TPUpdate_InvalidPlan"):
                    return True  # Treat cancel success as achieving best possible state
                else:
                    return False  # Failed to cancel
            else:
                return True  # No active TP, and cannot place new one -> desired state?

        # <<< VERIFIED CORRECT VALIDATION CALL >>>
        if not validate_order_filters(
            symbol=self.symbol,
            quantity=adj_tp_qty,
            price=adj_tp_price,
            exchange_info=self.exchange_info
        ):
            logger.error(
                f"Planned TP order (AdjQty:{adj_tp_qty}, AdjPx:{adj_tp_price}) failed validation. Cannot place/update.")
            if active_tp_order:
                logger.warning(
                    "Cancelling existing TP because new plan failed validation.")
                # Pass state to cancel_order
                return self.cancel_order(state, active_tp_order.get('clientOrderId'), active_tp_order.get('orderId'), reason="TPUpdate_InvalidPlanValidation")
            else:
                return True  # No active TP, cannot place new one -> desired state?
        # <<< END VERIFIED CORRECTION >>>
        logger.debug(
            f"Planned TP order passed validation. Adj Qty: {adj_tp_qty}, Adj Price: {adj_tp_price}")

        # --- Compare with Active TP ---
        needs_placement = True
        if active_tp_order:
            active_price = to_decimal(active_tp_order.get('price'))
            active_qty = to_decimal(active_tp_order.get('origQty'))

            # Check if active order sufficiently matches the adjusted plan
            # Use tolerances based on exchange filters for robust comparison
            price_tick_size = self.connector.get_filter_value(
                self.symbol, 'PRICE_FILTER', 'tickSize')
            price_tolerance = to_decimal(price_tick_size, Decimal(
                '0.00000001')) / Decimal('2')  # Half tick size
            qty_step_size = self.connector.get_filter_value(
                self.symbol, 'LOT_SIZE', 'stepSize')
            qty_tolerance = to_decimal(qty_step_size, Decimal(
                '0.00000001')) / Decimal('2')  # Half step size

            # Check if price and quantity are available for comparison
            if active_price is None or active_qty is None:
                logger.warning(
                    f"Active TP order {active_tp_order.get('clientOrderId')} missing price/qty for comparison. Replacing.")
                # Proceed to cancellation and placement below
            else:
                price_diff = abs(adj_tp_price - active_price)
                qty_diff = abs(adj_tp_qty - active_qty)

                # If price AND quantity are within tolerance, no update needed
                if price_diff <= price_tolerance and qty_diff <= qty_tolerance:
                    logger.debug(
                        f"Active TP order {active_tp_order.get('clientOrderId')} matches planned TP (PxDiff:{price_diff}, QtyDiff:{qty_diff}). No update needed.")
                    needs_placement = False
                else:
                    logger.info(  # Logged below if needs_placement is True
                        f"Active TP order {active_tp_order.get('clientOrderId')} differs from plan. Price Diff: {price_diff} (Tol: {price_tolerance}), Qty Diff: {qty_diff} (Tol: {qty_tolerance}). Replacing."
                    )
                    # Replacement needed (logged below if needs_placement is True)

            # If replacement is needed (either mismatch or missing data in active)
            if needs_placement:
                logger.info(
                    f"Active TP order {active_tp_order.get('clientOrderId')} differs from plan or has missing data. Replacing.")
                # Cancel the existing one first
                # Pass state to cancel_order
                if not self.cancel_order(state, active_tp_order.get('clientOrderId'), active_tp_order.get('orderId'), reason="TPUpdate_Replace"):
                    logger.error(
                        "Failed to cancel existing TP order during replacement. Aborting TP update.")
                    return False  # Critical failure, cannot guarantee desired state
                # else: Cancellation successful, proceed to placement below

        # --- Place New TP Order if needed ---
        if needs_placement:
            # Generate Client ID using internal method
            client_order_id = self._generate_client_order_id("tp")
            # Use INFO log for placement intent
            logger.info(
                f"Placing new TP SELL order: Qty={adj_tp_qty:.8f} @ Price={adj_tp_price:.4f} (Client ID: {client_order_id})")
            if self.simulation_mode:
                # Simulate placement
                sim_order = {
                    'symbol': self.symbol,
                    'orderId': self.sim_order_id_counter,
                    'clientOrderId': client_order_id,
                    'transactTime': int(time.time() * 1000),
                    'price': str(adj_tp_price),  # Use adjusted price
                    'origQty': str(adj_tp_qty),  # Use adjusted quantity
                    'executedQty': '0',
                    'cummulativeQuoteQty': '0',
                    'status': 'NEW',
                    'timeInForce': 'GTC',  # TP should be GTC
                    'type': 'LIMIT',
                    'side': 'SELL'
                }
                self.sim_order_id_counter += 1
                # Pass state to _add_order_to_state
                return self._add_order_to_state(state, 'tp', sim_order)
            else:  # Live placement
                try:
                    # Use adjusted price and quantity
                    api_response = self.connector.create_limit_sell(
                        symbol=self.symbol, quantity=adj_tp_qty, price=adj_tp_price, newClientOrderId=client_order_id)
                    if api_response:
                        logger.info(
                            f"Successfully placed live TP order: {api_response.get('orderId')} / {api_response.get('clientOrderId')}")
                        # Pass state to _add_order_to_state
                        return self._add_order_to_state(state, 'tp', api_response)
                    else:
                        logger.error(
                            f"Failed to place TP order (Client ID: {client_order_id}) - Connector returned None/False.")
                        return False
                except Exception as e:
                    # Log full traceback
                    logger.error(
                        f"Exception placing TP order (Client ID: {client_order_id}): {e}", exc_info=True)
                    return False

        # If needs_placement was False
        return True

    # <<< MODIFIED: Accepts state dict >>>
    def cancel_order(self, state: Dict, client_order_id: Optional[str], order_id: Optional[str], reason: str = "Unknown") -> bool:
        """
        Cancels an order via API or simulation.
        Removes order from the PASSED state dict on success.
        Returns True on successful cancellation/removal, False otherwise.
        NOTE: Saving the state is handled by the caller.
        """
        if not isinstance(state, dict):
            logger.error("cancel_order: Invalid state dict provided.")
            return False
        # Ensure order_id is string if provided
        order_id_str = str(order_id) if order_id is not None else None

        if not client_order_id and not order_id_str:
            logger.error(
                "Cannot cancel order: No clientOrderId or orderId provided.")
            return False

        id_to_log = order_id_str if order_id_str else client_order_id
        # Use INFO log for cancellation intent
        logger.info(
            f"Requesting cancellation for order {id_to_log} (Reason: {reason})")

        if self.simulation_mode:
            logger.info(f"Sim: Order {id_to_log} cancellation simulated.")
            # Pass state to _remove_order_from_state
            return self._remove_order_from_state(state, client_order_id, order_id_str)
        else:  # Live cancellation
            try:
                # Use connector which should handle None IDs gracefully
                success = self.connector.cancel_order(
                    symbol=self.symbol, orderId=order_id, origClientOrderId=client_order_id)
                if success:
                    logger.info(
                        f"Successfully cancelled order {id_to_log} via API.")
                    # Pass state to _remove_order_from_state *after* successful API confirmation
                    self._remove_order_from_state(
                        state, client_order_id, order_id_str)
                    return True
                else:
                    # API call returned False/None, indicating failure at exchange level
                    logger.error(
                        f"API call to cancel order {id_to_log} failed (connector returned False/None).")
                    # Check status - maybe it was already inactive?
                    try:
                        status_info = self.connector.get_order_status(
                            self.symbol, orderId=order_id, origClientOrderId=client_order_id)
                        # Added UNKNOWN
                        if status_info and status_info.get('status') in ['FILLED', 'CANCELED', 'EXPIRED', 'REJECTED', 'UNKNOWN']:
                            logger.warning(
                                f"Order {id_to_log} was already inactive ({status_info.get('status')}) after cancel attempt failed. Removing from state.")
                            # Pass state to remove
                            self._remove_order_from_state(
                                state, client_order_id, order_id_str)
                            return True  # Treat as success if already gone
                        else:
                            logger.warning(
                                f"Order {id_to_log} status after cancel fail: {status_info.get('status') if status_info else 'Unknown'}")
                    except Exception as status_err:
                        logger.error(
                            f"Error checking status after cancel fail for {id_to_log}: {status_err}")
                    return False  # Explicit API failure
            except Exception as e:
                # Log full traceback for unexpected errors during cancellation
                logger.error(
                    f"Exception cancelling order {id_to_log}: {e}", exc_info=True)
                return False

    # <<< MODIFIED: Accepts state dict >>>
    def execute_market_sell(self, state: Dict, quantity: Decimal, reason: str = "Unknown") -> Optional[Dict]:
        """
        Executes a market sell order.
        In simulation, updates the PASSED state dict immediately.
        Returns the order response/simulated details on success, None on failure.
        NOTE: Saving the state is handled by the caller.
        """
        if not isinstance(state, dict):
            logger.error(
                "execute_market_sell: Invalid state dictionary provided.")
            return None
        if quantity <= Decimal('0'):
            logger.error(
                f"Cannot execute market sell: Invalid quantity {quantity}")
            return None

        # Filter Qty first (floor sell qty might lose dust, but safer than exceeding holdings)
        adj_qty = apply_filter_rules_to_qty(
            symbol=self.symbol, quantity=quantity, exchange_info=self.exchange_info, operation='floor')
        if adj_qty is None or adj_qty <= Decimal('0'):
            logger.error(
                f"Market sell quantity {quantity} invalid ({adj_qty}) after LOT_SIZE filter.")
            return None

        # Validate MIN_NOTIONAL (requires estimated price)
        current_price = None
        ticker = None  # Initialize ticker
        try:
            # Use connector's ticker fetch
            ticker = self.connector.get_ticker(self.symbol)
            if ticker and ticker.get('lastPrice'):
                # Ensure ticker price is Decimal
                current_price = to_decimal(ticker['lastPrice'])
                if current_price is None:
                    logger.error(
                        "Failed to convert ticker price to Decimal for MIN_NOTIONAL check.")
                    return None  # Cannot validate
        except Exception as e:
            logger.warning(
                f"Could not fetch ticker price for MIN_NOTIONAL check: {e}")
            # Proceed without check? Or abort? Abort is safer.
            logger.error(
                "Aborting market sell due to inability to perform MIN_NOTIONAL check.")
            return None

        # Re-check current_price validity before using it
        if not current_price or current_price <= Decimal('0'):
            logger.error(
                f"Aborting market sell: Invalid estimated price ({current_price}) for MIN_NOTIONAL check.")
            return None

        # <<< VERIFIED CORRECT VALIDATION CALL >>>
        if not validate_order_filters(
            symbol=self.symbol,
            quantity=adj_qty,
            price=Decimal('0'),  # Indicate market order check
            exchange_info=self.exchange_info,
            estimated_price=current_price  # Pass the estimate
        ):
            logger.error(
                f"Estimated market sell (Qty:{adj_qty} @ EstPx:{current_price}) failed MIN_NOTIONAL filter validation. Aborting.")
            return None
        # <<< END VERIFIED CORRECTION >>>

        # --- Validation passed ---

        # Use WARNING log level for market sells as they are significant actions
        logger.warning(
            f"Executing MARKET SELL: Qty={adj_qty:.8f} {self.base_asset} (Reason: {reason})")

        if self.simulation_mode:
            logger.info("Sim: Market sell executed.")
            # Use the price fetched for validation as the simulated fill price
            fill_price = current_price
            # Re-check fill_price validity (already done, but safe)
            if fill_price is None or fill_price <= Decimal('0'):
                logger.error(
                    f"Sim: Invalid fill price ({fill_price}) for simulated market sell. Aborting state update.")
                return None

            # Generate Client ID using internal method
            client_order_id = self._generate_client_order_id("mkt_sell")
            sim_fill_details = {
                'symbol': self.symbol,
                'orderId': self.sim_order_id_counter,
                'clientOrderId': client_order_id,
                'transactTime': int(time.time() * 1000),
                'price': '0',  # Market orders have price 0
                # Original requested (adjusted) quantity
                'origQty': str(adj_qty),
                'executedQty': str(adj_qty),  # Assume full fill in simulation
                # Calculate quote value
                'cummulativeQuoteQty': str(fill_price * adj_qty),
                'status': 'FILLED',
                'timeInForce': 'GTC',  # Or IOC/FOK if applicable, GTC often default
                'type': 'MARKET',
                'side': 'SELL'
            }
            self.sim_order_id_counter += 1
            self.sim_filled_sell_count += 1

            # --- Immediate State Update for Sim (Operate on PASSED state dict) ---
            bal_q = to_decimal(state.get('balance_quote', '0'))
            bal_b = to_decimal(state.get('balance_base', '0'))
            proceeds = fill_price * adj_qty  # Use adjusted qty

            # Update state values in the PASSED dictionary
            state['position_size'] = Decimal('0')
            state['position_entry_price'] = Decimal('0')
            state['position_entry_timestamp'] = None
            state['balance_quote'] = bal_q + proceeds
            # Ensure base balance doesn't go negative due to precision issues
            state['balance_base'] = max(Decimal('0'), bal_b - adj_qty)
            # Clear active orders related to the position
            state['active_tp_order'] = None
            if state.get('active_grid_orders'):  # Check if key exists
                logger.info(
                    "Sim: Clearing active grid orders after market sell.")
                state['active_grid_orders'] = []

            # NOTE: Saving is handled by main_trader after this returns
            logger.info(
                "Sim: State dict updated immediately after market sell simulation.")
            # --- End Immediate State Update ---
            return sim_fill_details
        else:  # Live market sell
            try:
                # Use adjusted quantity
                api_response = self.connector.create_market_sell(
                    symbol=self.symbol, quantity=adj_qty)
                if api_response:
                    logger.info(
                        f"Successfully executed live market sell: {api_response.get('orderId')}")
                    # Live state update should happen via the main loop's check_orders and _process_fills
                    # based on the actual fill information received from the exchange.
                    return api_response
                else:
                    logger.error(
                        "Failed to execute market sell - Connector returned None/False.")
                    return None
            except Exception as e:
                # Log traceback
                logger.error(
                    f"Exception executing market sell: {e}", exc_info=True)
                return None

# END OF FILE: src/core/order_manager.py (Corrected Validation Calls - FINAL v2 Merged)
