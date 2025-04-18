# START OF FILE: src/core/order_manager.py (Corrected: Original Logic + Test Block)

import logging
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN  # Added ROUND_DOWN
from typing import Dict, List, Optional, Any

# Project Modules
# --- Fix Imports for Standalone Execution within __main__ block ---
if __name__ == '__main__':
    import sys
    from pathlib import Path
    import pprint  # For pretty printing results
    # Adjust if directory structure changes
    _project_root = Path(__file__).resolve().parent.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))
        print(f"Temporarily added project root to sys.path: {_project_root}")
    # Import project modules *after* path modification
    # Added load_config for test
    from config.settings import get_config_value, load_config
    from src.connectors.binance_us import BinanceUSConnector
    from src.utils.formatting import (  # Import specific utils needed by OM and test
        to_decimal,
        apply_filter_rules_to_qty,
        apply_filter_rules_to_price,
        validate_order_filters,
        _adjust_value_by_step
    )
else:
    # Regular imports when run as part of the application
    from config.settings import get_config_value
    from src.connectors.binance_us import BinanceUSConnector
    # StateManager import removed
    from src.utils.formatting import (
        to_decimal,
        apply_filter_rules_to_qty,
        apply_filter_rules_to_price,
        validate_order_filters,
        _adjust_value_by_step  # Import the internal function for price calc
    )
# --- End Import Handling ---


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
        # Initialize with current time to make somewhat unique across restarts
        self.sim_order_id_counter = int(time.time() * 1000)
        self._client_id_counter = 0
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
        self._client_id_counter += 1  # Increment counter
        # Combine prefix, timestamp, and counter
        # Ensure length constraint (e.g., max 36 for Binance API)
        return f"{prefix}_{ts_part}_{self._client_id_counter}"[-36:]

    # <<< MODIFIED: Accepts state dict & Handles 'cascade' type >>>
    def _add_order_to_state(self, state: Dict, order_type: str, order_details: Dict) -> bool:
        """
        Adds order to the PASSED state dict. Returns True if added.
        NOTE: Saving the state is handled by the caller.
        """
        if not isinstance(state, dict):
            logger.error(
                "_add_order_to_state: Invalid state dictionary provided.")
            return False
        if not isinstance(order_details, dict):
            logger.error(
                f"_add_order_to_state: Invalid order_details (not dict): {order_details}")
            return False

        modified = False
        cid = order_details.get('clientOrderId')
        oid = order_details.get('orderId')
        id_to_log = cid or oid or "N/A"

        if order_type == 'grid':
            if not isinstance(state.get('active_grid_orders'), list):
                state['active_grid_orders'] = []
            # Prevent duplicates
            if cid and any(o.get('clientOrderId') == cid for o in state['active_grid_orders']):
                logger.warning(
                    f"Skipping duplicate grid order CID {cid} in _add_order_to_state.")
                return False
            elif oid and any(str(o.get('orderId')) == str(oid) for o in state['active_grid_orders']):
                logger.warning(
                    f"Skipping duplicate grid order OID {oid} in _add_order_to_state.")
                return False
            else:
                state['active_grid_orders'].append(order_details)
                logger.debug(f"Added grid order {id_to_log} to state dict.")
                modified = True
        elif order_type == 'tp':
            existing_tp = state.get('active_tp_order')
            if existing_tp and isinstance(existing_tp, dict):
                logger.warning(
                    f"Overwriting existing active TP order {existing_tp.get('clientOrderId')} with new TP order {cid}.")
            state['active_tp_order'] = order_details
            logger.debug(f"Added/Updated TP order {cid} in state dict.")
            modified = True
        # --- START CASCADE ADDITION ---
        elif order_type == 'cascade':
            existing_cascade = state.get('ts_exit_active_order_details')
            if existing_cascade and isinstance(existing_cascade, dict):
                logger.warning(
                    f"Overwriting existing active cascade exit order {existing_cascade.get('clientOrderId')} with new cascade order {cid}.")
            state['ts_exit_active_order_details'] = order_details
            # Also update the separate ID field for quick reference
            state['ts_exit_active_order_id'] = cid or str(oid) if oid else None
            logger.debug(
                f"Added/Updated Cascade Exit order {id_to_log} in state dict.")
            modified = True
        # --- END CASCADE ADDITION ---
        else:
            logger.error(
                f"Unknown order type '{order_type}' in _add_order_to_state.")
            return False

        return modified
    # <<< END MODIFICATION >>>

    # <<< MODIFIED: Accepts state dict & Handles 'cascade' type >>>
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
        # Ensure ID is string for comparison
        id_str = str(order_id) if order_id else None
        id_to_log = client_order_id or id_str  # Log whichever ID is available

        # Check Grid Orders
        active_grid = state.get('active_grid_orders', [])
        if isinstance(active_grid, list):
            initial_count = len(active_grid)
            new_grid = [
                order for order in active_grid
                if not (
                    (client_order_id and order.get('clientOrderId') == client_order_id) or
                    (id_str and str(order.get('orderId')) == id_str)
                )
            ]
            if len(new_grid) < initial_count:
                state['active_grid_orders'] = new_grid  # Modify passed dict
                removed = True
                logger.debug(
                    f"Removed grid order {id_to_log} from state dict.")

        # Check TP Order
        active_tp = state.get('active_tp_order')
        if isinstance(active_tp, dict):
            match_tp = False
            if client_order_id and active_tp.get('clientOrderId') == client_order_id:
                match_tp = True
            elif id_str and str(active_tp.get('orderId')) == id_str:
                match_tp = True

            if match_tp:
                state['active_tp_order'] = None  # Set to None to remove
                removed = True
                logger.debug(
                    f"Removed TP order {id_to_log} from state dict.")

        # --- START CASCADE ADDITION ---
        # Check Cascade Exit Order
        active_cascade_order = state.get('ts_exit_active_order_details')
        if isinstance(active_cascade_order, dict):
            match_cascade = False
            if client_order_id and active_cascade_order.get('clientOrderId') == client_order_id:
                match_cascade = True
            elif id_str and str(active_cascade_order.get('orderId')) == id_str:
                match_cascade = True

            if match_cascade:
                # Set to None to remove
                state['ts_exit_active_order_details'] = None
                # Clear the ID field too
                state['ts_exit_active_order_id'] = None
                removed = True
                logger.debug(
                    f"Removed Cascade Exit order {id_to_log} from state dict.")
        # --- END CASCADE ADDITION ---

        if not removed:
            logger.debug(f"Order {id_to_log} not found in state for removal.")

        return removed
    # <<< END MODIFICATION >>>

    # <<< MODIFIED: Needs to check cascade order status too >>>
    def check_orders(self, state: Dict, current_price: Optional[Decimal] = None) -> Dict[str, Any]:
        """
        Checks the status of active orders (Grid, TP, Cascade Exit) in the PASSED state dictionary.
        Simulates fills if in simulation mode.
        Returns dictionary containing lists of filled orders.
        NOTE: Saving the state after processing fills is handled by the caller.
        """
        logger.info("--- Entered check_orders ---")
        if not isinstance(state, dict):
            logger.error("check_orders: Invalid state dict provided.")
            # Added cascade_fill
            return {'grid_fills': [], 'tp_fill': None, 'cascade_fill': None}

        active_grid = state.get('active_grid_orders', [])
        active_tp = state.get('active_tp_order')
        # Get cascade order details
        active_cascade = state.get('ts_exit_active_order_details')

        grid_fills = []
        tp_fill = None
        cascade_fill = None  # Initialize cascade fill

        # Type safety checks
        if not isinstance(active_grid, list):
            active_grid = []
        if not isinstance(active_tp, dict) and active_tp is not None:
            active_tp = None
        if not isinstance(active_cascade, dict) and active_cascade is not None:
            active_cascade = None

        # --- Check Grid Orders (Logic unchanged) ---
        remaining_grid_orders = []
        for order in active_grid:
            if not isinstance(order, dict):
                continue  # Skip invalid items

            # *** THESE LINES MUST BE INDENTED HERE, UNDER THE `for order` LOOP ***
            order_id = order.get('orderId')
            order_id_str = str(order_id) if order_id else "N/A"
            client_order_id = order.get('clientOrderId')
            order_price = to_decimal(order.get('price'))
            order_qty = to_decimal(order.get('origQty'))
            order_processed = False
            # *** END OF LINES THAT NEEDED CORRECT INDENTATION ***

            if self.simulation_mode:
                if current_price and order_price and order_qty and current_price <= order_price:
                    logger.info(
                        f"Sim: Grid order {client_order_id or order_id_str} filled at {current_price:.4f}")
                    sim_fill_details = {**order, 'status': 'FILLED', 'executedQty': str(
                        order_qty), 'cummulativeQuoteQty': str(order_price * order_qty), 'updateTime': int(time.time() * 1000)}
                    grid_fills.append(sim_fill_details)
                    self.sim_filled_buy_count += 1
                    order_processed = True
                # else: logger.debug(...) or warning if cannot compare
            else:  # Live Mode
                if order_id or client_order_id:
                    # logger.debug(...)
                    try:
                        status_info = self.connector.get_order_status(
                            self.symbol, orderId=order_id, origClientOrderId=client_order_id)
                        if status_info:
                            # *** STATUS ASSIGNMENT WAS MISSING IN BROKEN VERSION ***
                            status = status_info.get('status')
                            # logger.debug(...)
                            if status == 'FILLED':
                                grid_fills.append(status_info)
                                order_processed = True
                            elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'PENDING_CANCEL', 'UNKNOWN']:
                                logger.warning(
                                    f"Live: Grid order {order_id_str or client_order_id} inactive: {status}. Removing.")
                                order_processed = True
                            # If NEW, PARTIALLY_FILLED, etc., it remains active (order_processed stays False)
                        else:  # Status check failed or order not found
                            logger.warning(
                                f"Live: Status check failed for grid order {order_id_str or client_order_id}. Assuming inactive.")
                            order_processed = True  # Treat as processed/inactive
                    except Exception as e:
                        logger.error(
                            f"Live: Error checking grid order {order_id_str or client_order_id}: {e}", exc_info=False)
                        # Keep order in list to retry check later, order_processed remains False
                else:
                    logger.error(f"Live Check Grid: Missing IDs: {order}")
                    order_processed = True  # Cannot check, treat as processed/inactive

            if not order_processed:
                remaining_grid_orders.append(order)  # Keep active orders

        # Update state with only the remaining active orders
        state['active_grid_orders'] = remaining_grid_orders

        # --- Check Take Profit Order (Logic unchanged, but corrected API check) ---
        tp_processed = False
        if active_tp:
            tp_order_id = active_tp.get('orderId')
            tp_order_id_str = str(tp_order_id) if tp_order_id else "N/A"
            tp_client_order_id = active_tp.get('clientOrderId')
            tp_price = to_decimal(active_tp.get('price'))
            tp_qty = to_decimal(active_tp.get('origQty'))

            if self.simulation_mode:
                if current_price and tp_price and tp_qty and current_price >= tp_price:
                    logger.info(
                        f"Sim: TP order {tp_client_order_id or tp_order_id_str} filled at {current_price:.4f}.")
                    sim_fill_details = {**active_tp, 'status': 'FILLED', 'executedQty': str(
                        tp_qty), 'cummulativeQuoteQty': str(tp_price * tp_qty), 'updateTime': int(time.time() * 1000)}
                    tp_fill = sim_fill_details
                    tp_processed = True
                    self.sim_filled_sell_count += 1
                # else: logger.debug(...) or warning
            else:  # Live Mode
                if tp_order_id or tp_client_order_id:
                    # logger.debug(...)
                    try:
                        status_info = self.connector.get_order_status(
                            self.symbol, orderId=tp_order_id, origClientOrderId=tp_client_order_id)
                        if status_info:
                            # *** STATUS ASSIGNMENT WAS MISSING IN BROKEN VERSION ***
                            status = status_info.get('status')
                            # logger.debug(...)
                            if status == 'FILLED':
                                tp_fill = status_info
                                tp_processed = True
                            elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'PENDING_CANCEL', 'UNKNOWN']:
                                logger.warning(
                                    f"Live: TP order {tp_order_id_str or tp_client_order_id} inactive: {status}. Removing.")
                                tp_processed = True
                            # If NEW, PARTIALLY_FILLED, etc., it remains active
                        else:  # Status check failed or order not found
                            logger.warning(
                                f"Live: Status check failed for TP order {tp_order_id_str or tp_client_order_id}. Assuming inactive.")
                            tp_processed = True  # Treat as processed/inactive
                    except Exception as e:
                        logger.error(
                            f"Live: Error checking TP order {tp_order_id_str or tp_client_order_id}: {e}", exc_info=False)
                        # Keep order active to retry check later
                else:
                    logger.error(f"Live Check TP: Missing IDs: {active_tp}")
                    tp_processed = True  # Cannot check, treat as processed/inactive

            if tp_processed:
                # Remove from state only if processed
                state['active_tp_order'] = None

        # --- START CASCADE CHECK ---
        # Check Cascade Exit Order (similar logic to TP check, corrected API check)
        cascade_processed = False
        if active_cascade:  # active_cascade should be a dict or None here
            cas_order_id = active_cascade.get('orderId')
            cas_order_id_str = str(cas_order_id) if cas_order_id else "N/A"
            cas_client_order_id = active_cascade.get('clientOrderId')
            cas_price = to_decimal(active_cascade.get('price'))
            cas_qty = to_decimal(active_cascade.get('origQty'))

            if self.simulation_mode:
                if current_price is not None and cas_price is not None and cas_qty is not None:
                    # Cascade SELL fills if market price rises to or above order price
                    is_fill = current_price >= cas_price
                    logger.debug(
                        f"Sim Check Cascade: OrderPrice={cas_price:.4f}, CurrentPrice={current_price:.4f}, IsFill?={is_fill} (ClientID: {cas_client_order_id})")
                    if is_fill:
                        logger.info(
                            f"Sim: Cascade Exit order {cas_client_order_id or cas_order_id_str} (Price: {cas_price}) filled at current price {current_price:.4f}.")
                        sim_fill_details = {
                            **active_cascade,  # Include original details
                            'status': 'FILLED',
                            'executedQty': str(cas_qty),  # Assume full fill
                            # Use order price for sim
                            'cummulativeQuoteQty': str(cas_price * cas_qty),
                            # Simulate timestamp
                            'updateTime': int(time.time() * 1000)
                        }
                        cascade_fill = sim_fill_details  # Store fill
                        cascade_processed = True  # Mark cascade as processed
                        self.sim_filled_sell_count += 1  # Count as a sell
                    # else: Cascade remains active
                else:
                    logger.warning(
                        f"Sim Check Cascade: Cannot compare for {cas_client_order_id or cas_order_id_str}. Price={cas_price}, CurrentPrice={current_price}, Qty={cas_qty}")
                    # Keep Cascade active if check failed
            else:  # Live Mode
                if not cas_order_id and not cas_client_order_id:
                    logger.error(
                        f"Live Check Cascade: Cannot check status, missing both IDs: {active_cascade}")
                    cascade_processed = True  # Treat as processed/error state
                else:
                    logger.debug(
                        f"Live: Checking status for Cascade Exit order {cas_order_id_str} / {cas_client_order_id}")
                    try:
                        status_info = self.connector.get_order_status(
                            self.symbol, orderId=cas_order_id, origClientOrderId=cas_client_order_id)
                        if status_info:
                            # *** STATUS ASSIGNMENT WAS MISSING IN BROKEN VERSION ***
                            status = status_info.get('status')
                            logger.debug(
                                f"Live: Order {cas_order_id_str or cas_client_order_id} Status: {status}")
                            if status == 'FILLED':
                                cascade_fill = status_info  # Store full details
                                cascade_processed = True
                            elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'PENDING_CANCEL', 'UNKNOWN']:
                                logger.warning(
                                    f"Live: Cascade Exit order {cas_order_id_str or cas_client_order_id} found in inactive state: {status}. Removing from active list.")
                                cascade_processed = True
                            # else: NEW, PARTIALLY_FILLED etc. remain active
                        else:  # Status check failed or order not found
                            logger.warning(
                                f"Live: Failed to get status for Cascade Exit order {cas_order_id_str or cas_client_order_id} or order not found. Assuming inactive.")
                            cascade_processed = True  # Treat failure to find as processed/inactive
                    except Exception as e:
                        logger.error(
                            f"Live: Error checking Cascade Exit order {cas_order_id_str or cas_client_order_id}: {e}", exc_info=False)
                        # Keep checking on error, cascade_processed remains False

            # Update passed state dict cascade order *only* if it was processed
            if cascade_processed:
                state['ts_exit_active_order_details'] = None
                state['ts_exit_active_order_id'] = None
        # --- END CASCADE CHECK ---

        # Return cascade fill
        return {'grid_fills': grid_fills, 'tp_fill': tp_fill, 'cascade_fill': cascade_fill}

    # --- NEW Cascade Helper Methods ---

    def _calculate_cascade_limit_price(self, order_type: str, book_ticker: Dict, config_cascade: Dict) -> Optional[Decimal]:
        """
        Calculates the target price for a cascade limit sell order.
        """
        logger.debug(f"Calculating cascade limit price for type: {order_type}")
        if not book_ticker or not isinstance(book_ticker, dict):
            logger.error(
                "Cannot calculate cascade price: Invalid book_ticker provided.")
            return None
        if not config_cascade or not isinstance(config_cascade, dict):
            logger.error(
                "Cannot calculate cascade price: Invalid config_cascade provided.")
            return None

        # Already Decimal from connector method
        best_bid = book_ticker.get('bidPrice')
        # Already Decimal from connector method
        best_ask = book_ticker.get('askPrice')

        if best_bid is None or best_ask is None or not isinstance(best_bid, Decimal) or not isinstance(best_ask, Decimal):
            logger.error(
                f"Cannot calculate cascade price: Missing or invalid bid/ask prices in book_ticker. Bid={best_bid}, Ask={best_ask}")
            return None

        # Fetch tickSize for price adjustments
        tick_size_str = self.connector.get_filter_value(
            self.symbol, 'PRICE_FILTER', 'tickSize')
        tick_size = to_decimal(tick_size_str)
        if tick_size is None or tick_size <= Decimal('0'):
            logger.error(
                f"Cannot calculate cascade price: Invalid or missing tickSize ({tick_size_str}).")
            return None

        calculated_price = None
        if order_type == 'MAKER' or order_type == 'OFFSET':  # Treat OFFSET same as MAKER for now
            offset_ticks = int(config_cascade.get(
                'initial_maker_offset_ticks', 1))
            # Place *above* best bid to act as maker sell
            calculated_price = best_bid + (offset_ticks * tick_size)
            logger.debug(
                f"Cascade MAKER price calc: BestBid={best_bid} + ({offset_ticks} * {tick_size}) = {calculated_price}")
        elif order_type == 'TAKER':
            offset_ticks = int(config_cascade.get(
                'aggressive_taker_offset_ticks', 1))
            # Place *below* best bid to act as aggressive taker sell
            calculated_price = best_bid - (offset_ticks * tick_size)
            logger.debug(
                f"Cascade TAKER price calc: BestBid={best_bid} - ({offset_ticks} * {tick_size}) = {calculated_price}")
        else:
            logger.error(f"Unknown cascade order_type: {order_type}")
            return None

        # Ensure calculated price is not negative or zero
        if calculated_price <= Decimal('0'):
            logger.error(
                f"Calculated cascade price is zero or negative ({calculated_price}). Cannot place order.")
            return None

        # Adjust the final calculated price to be a multiple of tick_size, rounding DOWN
        # We round down for SELL limits to ensure the price is valid and not accidentally rounded up
        # Use the internal _adjust_value_by_step for this
        final_price = _adjust_value_by_step(
            calculated_price, tick_size, operation='floor')

        if final_price is None:
            logger.error(
                f"Failed to adjust calculated cascade price {calculated_price} using tick size {tick_size}")
            return None

        logger.debug(
            f"Final calculated cascade price ({order_type}): {final_price}")
        return final_price

    def place_ts_exit_limit_order(self, state: Dict, quantity: Decimal, cascade_step_type: str) -> Optional[Dict]:
        """
        Places a specific limit sell order as part of the Time Stop cascade.
        Handles fetching book ticker, calculating price based on type, applying filters,
        and placing the order via API or simulation. Updates state.
        Returns the order details dict on success, None on failure.
        """
        logger.info(
            f"--- Placing Time Stop Cascade Limit Order ({cascade_step_type}) ---")
        if not isinstance(state, dict):
            logger.error(
                "place_ts_exit_limit_order: Invalid state dictionary provided.")
            return None
        if quantity <= Decimal('0'):
            logger.error(
                f"Cannot place TS exit order: Invalid quantity {quantity}")
            return None

        # 1. Fetch Cascade Config
        config_cascade = self.config.get('risk_controls', {}).get(
            'time_stop', {}).get('cascade', {})
        if not config_cascade or not config_cascade.get('enabled', False):
            logger.error(
                "Cannot place TS exit order: Cascade configuration missing or disabled.")
            return None

        # 2. Fetch Book Ticker (Corrected Try/Except)
        book_ticker = None  # Initialize
        try:
            book_ticker = self.connector.get_symbol_book_ticker(self.symbol)
            if not book_ticker:  # Check should be inside try
                logger.error(
                    "Failed to fetch book ticker for cascade price calculation.")
                return None
        except Exception as e:
            logger.error(f"Exception fetching book ticker: {e}", exc_info=True)
            return None
        # book_ticker is now guaranteed to be a Dict or None (if exception occurred)

        # 3. Determine Order Type & Calculate Price
        order_type = None
        if cascade_step_type == 'initial':
            order_type = config_cascade.get('initial_order_type', 'MAKER')
        elif cascade_step_type == 'aggressive':
            order_type = 'TAKER'  # Aggressive step is always TAKER type
        else:
            logger.error(f"Unknown cascade_step_type: {cascade_step_type}")
            return None

        calculated_price = self._calculate_cascade_limit_price(
            order_type, book_ticker, config_cascade)
        if calculated_price is None:
            logger.error("Failed to calculate cascade limit price.")
            return None

        # 4. Apply Filters and Validate
        adj_qty = apply_filter_rules_to_qty(
            self.symbol, quantity, self.exchange_info, operation='floor')
        # Use 'adjust' which quantizes correctly for price
        adj_price = apply_filter_rules_to_price(
            self.symbol, calculated_price, self.exchange_info, operation='adjust')

        if adj_qty is None or adj_qty <= Decimal('0') or adj_price is None or adj_price <= Decimal('0'):
            logger.error(
                f"TS Exit order plan (Qty:{quantity}->{adj_qty}, Px:{calculated_price}->{adj_price}) invalid after filters.")
            return None

        # Use the validation function
        if not validate_order_filters(symbol=self.symbol, quantity=adj_qty, price=adj_price, exchange_info=self.exchange_info):
            logger.error(
                f"TS Exit order (AdjQty:{adj_qty}, AdjPx:{adj_price}) failed filter validation. Skipping.")
            return None

        logger.debug(
            f"TS Exit order passed validation. Adj Qty: {adj_qty}, Adj Price: {adj_price}")

        # 5. Generate Client Order ID
        # Use more descriptive prefix based on step AND type
        prefix = f"ts_{cascade_step_type}_{order_type.lower()}"
        client_order_id = self._generate_client_order_id(prefix=prefix)

        # 6. Place Order (Sim or Live)
        logger.info(
            f"Placing Cascade [{order_type}] SELL order: Qty={adj_qty:.8f} @ Price={adj_price:.4f} (Client ID: {client_order_id})")

        if self.simulation_mode:
            sim_order = {
                'symbol': self.symbol,
                'orderId': self.sim_order_id_counter,
                'clientOrderId': client_order_id,
                'transactTime': int(time.time() * 1000),
                'price': str(adj_price),
                'origQty': str(adj_qty),
                'executedQty': '0',
                'cummulativeQuoteQty': '0',
                'status': 'NEW',
                'timeInForce': 'GTC',  # Limit orders should be GTC
                'type': 'LIMIT',
                'side': 'SELL'
            }
            self.sim_order_id_counter += 1
            # Add to state using the new 'cascade' type
            if self._add_order_to_state(state, 'cascade', sim_order):
                logger.info(
                    f"Sim: Cascade exit order {client_order_id} added to state.")
                # No need to update state['ts_exit_active_order_id'] here, _add_order does it.
                return sim_order
            else:
                logger.error(
                    f"Sim: Failed to add cascade order {client_order_id} to state (Duplicate CID?).")
                return None
        else:  # Live placement
            try:
                api_response = self.connector.create_limit_sell(
                    symbol=self.symbol, quantity=adj_qty, price=adj_price, newClientOrderId=client_order_id)
                if api_response:  # Correctly indented check
                    logger.info(
                        f"Successfully placed live Cascade [{order_type}] order: {api_response.get('orderId')} / {client_order_id}")
                    # Add to state using the new 'cascade' type
                    if self._add_order_to_state(state, 'cascade', api_response):
                        # No need to update state['ts_exit_active_order_id'] here.
                        return api_response
                    else:
                        logger.error(
                            f"Successfully placed live cascade order {client_order_id} but FAILED TO ADD TO STATE DICT.")
                        # Attempt to cancel the order we just placed but couldn't track?
                        self.cancel_order(state, client_order_id=client_order_id, order_id=api_response.get(
                            'orderId'), reason="StateAddFail")
                        return None
                else:  # Correctly indented else
                    logger.error(
                        f"Failed to place Cascade [{order_type}] order (Client ID: {client_order_id}) - Connector returned None/False.")
                    return None
            except Exception as e:
                logger.error(
                    f"Exception placing Cascade [{order_type}] order (Client ID: {client_order_id}): {e}", exc_info=True)
                return None

    # --- End NEW Cascade Helper Methods ---

    # --- Existing Methods (reconcile_and_place_grid, place_or_update_tp_order, cancel_order, execute_market_sell) ---
    # These remain largely unchanged structurally, but ensure they use the modified
    # _add_order_to_state and _remove_order_from_state correctly.
    # Review confirms they already pass the state dict correctly.

    def reconcile_and_place_grid(self, state: Dict, planned_grid: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Reconciles internal state with fetched open orders, then compares the
        reconciled state against the planned grid.
        Cancels outdated orders and places new ones.
        Modifies the PASSED state dict directly for additions/removals.
        Returns dictionary summarizing actions.
        NOTE: Saving the state is handled by the caller.
        """
        logger.info("--- Entered reconcile_and_place_grid ---")
        if not isinstance(state, dict):
            logger.error("reconcile_and_place_grid: Invalid state dict.")
            return {'placed': [], 'cancelled': [], 'failed_cancel': [], 'failed_place': [], 'unchanged': []}

        # --- Stage 1: Fetch / Simulate Fetching Open Orders ---
        fetched_orders: Optional[List[Dict]] = None
        if self.simulation_mode:
            logger.debug("Sim Mode: Using current state as 'fetched' orders.")
            sim_fetched_grid = state.get('active_grid_orders', [])
            sim_fetched_tp = state.get('active_tp_order')
            sim_fetched_cascade = state.get(
                'ts_exit_active_order_details')  # Include cascade
            if not isinstance(sim_fetched_grid, list):
                sim_fetched_grid = []
            # *** CORRECTED logic in broken version: copy list ***
            fetched_orders = list(sim_fetched_grid)
            if isinstance(sim_fetched_tp, dict):
                fetched_orders.append(sim_fetched_tp)
            if isinstance(sim_fetched_cascade, dict):
                fetched_orders.append(sim_fetched_cascade)  # Add cascade
        else:  # Live Mode
            logger.info("Live Mode: Fetching open orders from exchange...")
            try:  # Corrected Try/Except
                fetched_orders = self.connector.get_open_orders(self.symbol)
                # Check needs to be inside try
                if fetched_orders is None:
                    logger.error(
                        "Failed to fetch open orders from exchange. Aborting reconcile.")
                    # Return early if fetch failed critically
                    return {'placed': [], 'cancelled': [], 'failed_cancel': [], 'failed_place': [], 'unchanged': []}
                logger.info(
                    f"Fetched {len(fetched_orders)} open orders from exchange.")
            except Exception as e:
                logger.error(
                    f"Exception fetching open orders: {e}. Aborting reconcile.", exc_info=True)
                return {'placed': [], 'cancelled': [], 'failed_cancel': [], 'failed_place': [], 'unchanged': []}

        # Ensure fetched_orders is a list even if simulation/API returned None somehow (though handled above)
        if fetched_orders is None:
            fetched_orders = []

        # --- Stage 2: Reconcile Fetched Orders with Internal State ---
        logger.debug("Reconciling fetched orders with internal state...")
        state_grid_orders = state.get('active_grid_orders', [])
        state_tp_order = state.get('active_tp_order')
        state_cascade_order = state.get(
            'ts_exit_active_order_details')  # Include cascade
        if not isinstance(state_grid_orders, list):
            state_grid_orders = []
        if not isinstance(state_tp_order, dict) and state_tp_order is not None:
            state_tp_order = None
        if not isinstance(state_cascade_order, dict) and state_cascade_order is not None:
            state_cascade_order = None

        state_cids = set()
        if state_grid_orders:
            state_cids.update(o.get('clientOrderId')
                              for o in state_grid_orders if o.get('clientOrderId'))
        if state_tp_order and state_tp_order.get('clientOrderId'):
            state_cids.add(state_tp_order.get('clientOrderId'))
        if state_cascade_order and state_cascade_order.get('clientOrderId'):
            state_cids.add(state_cascade_order.get(
                'clientOrderId'))  # Add cascade

        fetched_cids = set(o.get('clientOrderId')
                           for o in fetched_orders if o.get('clientOrderId'))
        state_only_cids = state_cids - fetched_cids
        fetched_only_cids = fetched_cids - state_cids
        recon_removed_count = 0

        if state_only_cids:
            logger.warning(
                f"Reconciliation: Found {len(state_only_cids)} orders in state but not fetched: {state_only_cids}. Removing from state.")
            # *** CORRECTED loop in broken version ***
            for cid_to_remove in state_only_cids:
                if self._remove_order_from_state(state, client_order_id=cid_to_remove):
                    recon_removed_count += 1
        if fetched_only_cids:
            logger.warning(
                f"Reconciliation: Found {len(fetched_only_cids)} orders fetched but not in state: {fetched_only_cids}. Check state consistency.")

        if recon_removed_count > 0:
            logger.info(
                f"Reconciliation: Removed {recon_removed_count} orders from state.")
        else:
            # *** CORRECTED else alignment in broken version ***
            logger.debug(
                "Reconciliation: State matches fetched open orders (based on CIDs).")

        # --- Stage 3: Compare Reconciled State with Planned Grid ---
        reconciled_active_grid_orders = state.get('active_grid_orders', [])
        if not isinstance(reconciled_active_grid_orders, list):
            reconciled_active_grid_orders = []
            # *** CORRECTED log indentation in broken version ***
        logger.info(
            f"Planning Comparison: Planned={len(planned_grid)}, Active after reconcile={len(reconciled_active_grid_orders)}")

        active_orders_map = {str(p): o for o in reconciled_active_grid_orders if (
            p := to_decimal(o.get('price')))}
        planned_orders_map = {str(p): pl for pl in planned_grid if (
            p := to_decimal(pl.get('price')))}
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
            logger.info(
                f"Cancelling {len(orders_to_cancel_prices_str)} outdated grid orders...")
            # *** CORRECTED loop in broken version ***
            for price_str in orders_to_cancel_prices_str:
                order_to_cancel = active_orders_map[price_str]
                if self.cancel_order(state, order_to_cancel.get('clientOrderId'), order_to_cancel.get('orderId'), reason="GridReconcile_OutdatedPrice"):
                    results['cancelled'].append(order_to_cancel)
                else:
                    results['failed_cancel'].append(
                        {**order_to_cancel, 'fail_reason': 'Cancellation failed'})

        # --- Place New ---
        if orders_to_place_prices_str:
            logger.info(
                f"Placing {len(orders_to_place_prices_str)} new grid orders...")
            # *** CORRECTED loop in broken version ***
            for price_str in orders_to_place_prices_str:
                order_to_place = planned_orders_map[price_str]
                price = to_decimal(order_to_place.get('price'))
                qty = to_decimal(order_to_place.get('quantity'))
                if price is None or qty is None or qty <= Decimal('0'):
                    logger.error(
                        f"Invalid planned grid order: P={price}, Q={qty}. Skipping.")
                    results['failed_place'].append(
                        {**order_to_place, 'fail_reason': 'Invalid original price/qty'})
                    continue
                adj_price = apply_filter_rules_to_price(
                    self.symbol, price, self.exchange_info, operation='adjust')
                adj_qty = apply_filter_rules_to_qty(
                    self.symbol, qty, self.exchange_info, operation='floor')
                if adj_price is None or adj_qty is None or adj_qty <= Decimal('0'):
                    logger.error(
                        f"Filter application failed for grid order: P={price}->{adj_price}, Q={qty}->{adj_qty}. Skipping.")
                    results['failed_place'].append(
                        {**order_to_place, 'fail_reason': 'Filter application failed'})
                    continue
                if not validate_order_filters(symbol=self.symbol, quantity=adj_qty, price=adj_price, exchange_info=self.exchange_info):
                    logger.error(
                        f"Grid order (AdjQty:{adj_qty}, AdjPx:{adj_price}) failed validation. Skipping.")
                    results['failed_place'].append(
                        {**order_to_place, 'fail_reason': 'Filter validation failed'})
                    continue

                client_order_id = self._generate_client_order_id("grid")
                logger.info(
                    f"Placing new grid BUY order: Qty={adj_qty:.8f} @ Price={adj_price:.4f} (Client ID: {client_order_id})")
                if self.simulation_mode:
                    sim_order = {'symbol': self.symbol, 'orderId': self.sim_order_id_counter, 'clientOrderId': client_order_id, 'transactTime': int(time.time() * 1000), 'price': str(
                        adj_price), 'origQty': str(adj_qty), 'executedQty': '0', 'cummulativeQuoteQty': '0', 'status': 'NEW', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'BUY'}
                    self.sim_order_id_counter += 1
                    # *** CORRECTED logic/indentation in broken version ***
                    if self._add_order_to_state(state, 'grid', sim_order):
                        results['placed'].append(sim_order)
                    else:
                        results['failed_place'].append(
                            {**order_to_place, 'clientOrderId': client_order_id, 'fail_reason': 'Failed add sim order to state'})
                else:  # Live placement
                    try:  # Corrected Try/Except structure
                        api_response = self.connector.create_limit_buy(
                            symbol=self.symbol, quantity=adj_qty, price=adj_price, newClientOrderId=client_order_id)
                        if api_response:  # Correctly indented check
                            logger.info(
                                f"Live grid order placed: {api_response.get('orderId')} / {client_order_id}")
                            if self._add_order_to_state(state, 'grid', api_response):
                                results['placed'].append(api_response)
                            else:
                                logger.error(
                                    f"Placed live grid order {client_order_id} but FAILED TO ADD TO STATE.")
                                results['failed_place'].append(
                                    {**order_to_place, 'clientOrderId': client_order_id, 'fail_reason': 'Placed live but failed add to state'})
                        else:  # Correctly indented else
                            logger.error(
                                f"Failed to place grid order (CID: {client_order_id}) - Connector None.")
                            results['failed_place'].append(
                                {**order_to_place, 'clientOrderId': client_order_id, 'fail_reason': 'API placement failed (connector None)'})
                    except Exception as e:
                        logger.error(
                            f"Exception placing grid order (CID: {client_order_id}): {e}", exc_info=True)
                        results['failed_place'].append(
                            {**order_to_place, 'clientOrderId': client_order_id, 'fail_reason': f'API exception: {e}'})

        # --- Unchanged ---
        if orders_unchanged_prices_str:
            logger.debug(
                f"{len(orders_unchanged_prices_str)} grid orders remain unchanged by price.")
            results['unchanged'] = [active_orders_map[p]
                                    for p in orders_unchanged_prices_str]

        # --- Final Summary ---
        log_summary = (
            f"Grid Reconcile Summary: Placed={len(results['placed'])}, Cancelled={len(results['cancelled'])}, " f"FailedCancel={len(results['failed_cancel'])}, FailedPlace={len(results['failed_place'])}, Unchanged={len(results['unchanged'])}")
        if results['failed_cancel'] or results['failed_place']:
            logger.warning(log_summary)
        else:
            # *** CORRECTED else alignment in broken version ***
            logger.info(log_summary)

        return results

    def place_or_update_tp_order(self, state: Dict, planned_tp_price: Optional[Decimal], position_size: Decimal) -> bool:
        """
        Places or updates the Take Profit LIMIT SELL order based on the PASSED state.
        Modifies the PASSED state dict directly. Returns True on success.
        """
        # --- Function body unchanged logic, corrected indentation/structure ---
        if not isinstance(state, dict):
            logger.error("place_or_update_tp_order: Invalid state dict.")
            return False
        active_tp_order = state.get('active_tp_order')
        if not isinstance(active_tp_order, dict) and active_tp_order is not None:
            logger.warning(
                f"Correcting invalid active_tp_order state: {active_tp_order}")
            active_tp_order = None

        # Condition to check if TP needs to be cleared
        if position_size <= Decimal('0') or planned_tp_price is None or planned_tp_price <= Decimal('0'):
            if active_tp_order:
                reason = "TPUpdate_Clear (No Position)" if position_size <= Decimal(
                    '0') else "TPUpdate_Clear (No Valid Plan)"
                logger.info(
                    f"Attempting to cancel existing TP order. Reason: {reason}.")
                # *** CORRECTED logic in broken version ***
                if self.cancel_order(state, active_tp_order.get('clientOrderId'), active_tp_order.get('orderId'), reason=reason):
                    return True
                else:
                    logger.error(
                        "Failed to cancel existing TP order during clear operation.")
                    return False
            else:  # No active TP and no need to place one
                logger.debug(
                    "No active TP order found and no TP placement required.")
                return True  # Successfully did nothing (which was the goal)

        # We have a position and a planned price, proceed with validation/placement
        adj_tp_qty = apply_filter_rules_to_qty(
            symbol=self.symbol, quantity=position_size, exchange_info=self.exchange_info, operation='floor')
        adj_tp_price = apply_filter_rules_to_price(
            symbol=self.symbol, price=planned_tp_price, exchange_info=self.exchange_info, operation='adjust')

        if adj_tp_qty is None or adj_tp_qty <= Decimal('0') or adj_tp_price is None or adj_tp_price <= Decimal('0'):
            logger.error(
                f"TP order plan (Qty:{position_size}->{adj_tp_qty}, Px:{planned_tp_price}->{adj_tp_price}) invalid after filters.")
            # *** CORRECTED logic block in broken version ***
            if active_tp_order:
                logger.warning(
                    "Cancelling existing TP because new plan is invalid after filters.")
                return self.cancel_order(state, active_tp_order.get('clientOrderId'), active_tp_order.get('orderId'), reason="TPUpdate_InvalidPlan")
            else:
                # No active TP, and the plan is invalid, so nothing to do.
                return True  # Successfully did nothing

        if not validate_order_filters(symbol=self.symbol, quantity=adj_tp_qty, price=adj_tp_price, exchange_info=self.exchange_info):
            logger.error(
                f"Planned TP order (AdjQty:{adj_tp_qty}, AdjPx:{adj_tp_price}) failed validation. Cannot place/update.")
            # *** CORRECTED logic block in broken version ***
            if active_tp_order:
                logger.warning(
                    "Cancelling existing TP because new plan failed validation.")
                return self.cancel_order(state, active_tp_order.get('clientOrderId'), active_tp_order.get('orderId'), reason="TPUpdate_InvalidPlanValidation")
            else:
                # No active TP, and the plan is invalid, so nothing to do.
                return True  # Successfully did nothing

        logger.debug(
            f"Planned TP order passed validation. Adj Qty: {adj_tp_qty}, Adj Price: {adj_tp_price}")

        # Check if existing TP needs update
        needs_placement = True
        if active_tp_order:
            active_price = to_decimal(active_tp_order.get('price'))
            active_qty = to_decimal(active_tp_order.get('origQty'))
            # *** CORRECTED logic block in broken version ***
            if active_price is None or active_qty is None:
                logger.warning(
                    f"Active TP order {active_tp_order.get('clientOrderId')} missing data. Replacing.")
                # needs_placement remains True
            else:
                # Calculate tolerances based on filters
                price_tick_size = self.connector.get_filter_value(
                    self.symbol, 'PRICE_FILTER', 'tickSize')
                price_tolerance = to_decimal(
                    price_tick_size, Decimal('1E-8')) / Decimal('2')
                qty_step_size = self.connector.get_filter_value(
                    self.symbol, 'LOT_SIZE', 'stepSize')
                qty_tolerance = to_decimal(
                    qty_step_size, Decimal('1E-8')) / Decimal('2')
                price_diff = abs(adj_tp_price - active_price)
                qty_diff = abs(adj_tp_qty - active_qty)

                # Check if differences are within tolerance
                if price_diff <= price_tolerance and qty_diff <= qty_tolerance:
                    logger.debug(
                        f"Active TP {active_tp_order.get('clientOrderId')} matches plan. No update.")
                    needs_placement = False  # No need to place new one

            # If needs_placement is still True (either missing data or plan differs)
            if needs_placement:
                logger.info(
                    f"Active TP order {active_tp_order.get('clientOrderId')} differs from plan. Replacing.")
                # *** CORRECTED logic block in broken version ***
                if not self.cancel_order(state, active_tp_order.get('clientOrderId'), active_tp_order.get('orderId'), reason="TPUpdate_Replace"):
                    logger.error(
                        "Failed cancel existing TP during replacement.")
                    return False  # Failed to cancel, cannot proceed

        # Place new TP order if needed
        if needs_placement:
            client_order_id = self._generate_client_order_id("tp")
            logger.info(
                f"Placing new TP SELL order: Qty={adj_tp_qty:.8f} @ Price={adj_tp_price:.4f} (Client ID: {client_order_id})")
            # *** CORRECTED logic block in broken version ***
            if self.simulation_mode:
                sim_order = {'symbol': self.symbol, 'orderId': self.sim_order_id_counter, 'clientOrderId': client_order_id, 'transactTime': int(time.time() * 1000), 'price': str(
                    adj_tp_price), 'origQty': str(adj_tp_qty), 'executedQty': '0', 'cummulativeQuoteQty': '0', 'status': 'NEW', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'SELL'}
                self.sim_order_id_counter += 1
                # Add to state and return success/failure of adding
                return self._add_order_to_state(state, 'tp', sim_order)
            else:  # Live placement
                try:  # Corrected Try/Except structure
                    api_response = self.connector.create_limit_sell(
                        symbol=self.symbol, quantity=adj_tp_qty, price=adj_tp_price, newClientOrderId=client_order_id)
                    if api_response:  # Correctly indented check
                        logger.info(
                            f"Live TP placed: {api_response.get('orderId')} / {client_order_id}")
                        return self._add_order_to_state(state, 'tp', api_response)
                    else:  # Correctly indented else
                        logger.error(
                            f"Failed to place TP order (CID: {client_order_id}) - Connector None.")
                        return False
                except Exception as e:
                    logger.error(
                        f"Exception placing TP order (CID: {client_order_id}): {e}", exc_info=True)
                    return False

        # If we reached here, it means needs_placement was False
        return True  # TP order was up-to-date

    def cancel_order(self, state: Dict, client_order_id: Optional[str], order_id: Optional[str], reason: str = "Unknown") -> bool:
        """
        Cancels an order via API or simulation. Removes from state on success.
        """
        # --- Function body unchanged logic, corrected indentation/structure ---
        if not isinstance(state, dict):
            logger.error("cancel_order: Invalid state dict.")
            return False
        order_id_str = str(order_id) if order_id is not None else None
        if not client_order_id and not order_id_str:
            logger.error("Cannot cancel order: No ID provided.")
            return False
        id_to_log = order_id_str or client_order_id
        logger.info(
            f"Requesting cancellation for order {id_to_log} (Reason: {reason})")
        if self.simulation_mode:
            logger.info(f"Sim: Order {id_to_log} cancellation simulated.")
            return self._remove_order_from_state(state, client_order_id, order_id_str)
        else:  # Live cancellation
            try:  # Corrected Try/Except structure
                success = self.connector.cancel_order(
                    symbol=self.symbol, orderId=order_id, origClientOrderId=client_order_id)
                if success:  # Correctly indented check
                    logger.info(
                        f"Successfully cancelled order {id_to_log} via API.")
                    self._remove_order_from_state(
                        state, client_order_id, order_id_str)
                    return True
                else:  # Correctly indented else (API call returned False)
                    logger.error(
                        f"API call to cancel order {id_to_log} failed.")
                    # Check if order is already inactive after failed cancellation attempt
                    try:  # Nested try for status check
                        status_info = self.connector.get_order_status(
                            self.symbol, orderId=order_id, origClientOrderId=client_order_id)
                        if status_info and status_info.get('status') in ['FILLED', 'CANCELED', 'EXPIRED', 'REJECTED', 'UNKNOWN']:
                            logger.warning(
                                f"Order {id_to_log} was already inactive ({status_info.get('status')}). Removing from state.")
                            self._remove_order_from_state(
                                state, client_order_id, order_id_str)
                            return True  # Treat as success because it's inactive
                        else:  # Correctly indented else
                            logger.warning(
                                f"Order {id_to_log} status after cancel fail: {status_info.get('status') if status_info else 'Unknown'}")
                            # Fall through to return False as cancellation failed and order might still be active
                    except Exception as status_err:
                        logger.error(
                            f"Error checking status after cancel fail for {id_to_log}: {status_err}")
                        # Fall through to return False as we couldn't confirm status
                    return False  # Return False because API cancel failed and status check didn't confirm inactivity
            except Exception as e:  # Catch exception during the cancel API call itself
                logger.error(
                    f"Exception cancelling order {id_to_log}: {e}", exc_info=True)
                return False

    def execute_market_sell(self, state: Dict, quantity: Decimal, reason: str = "Unknown") -> Optional[Dict]:
        """
        Executes a market sell order. Updates state in sim. Returns order details.
        """
        # --- Function body unchanged logic, corrected indentation/structure ---
        if not isinstance(state, dict):
            logger.error("execute_market_sell: Invalid state.")
            return None
        if quantity <= Decimal('0'):
            logger.error(f"Cannot execute market sell: Invalid qty {quantity}")
            return None

        adj_qty = apply_filter_rules_to_qty(
            symbol=self.symbol, quantity=quantity, exchange_info=self.exchange_info, operation='floor')
        if adj_qty is None or adj_qty <= Decimal('0'):
            logger.error(
                f"Market sell qty {quantity} invalid ({adj_qty}) after LOT_SIZE.")
            return None

        # Check MIN_NOTIONAL using estimated price
        current_price = None
        book_ticker = None
        try:  # Corrected Try/Except structure
            book_ticker = self.connector.get_symbol_book_ticker(self.symbol)
            # Checks need to be inside try
            if book_ticker and book_ticker.get('lastPrice'):
                current_price = book_ticker['lastPrice']
            if current_price is None:
                logger.error(
                    "Failed to get last price for MIN_NOTIONAL check.")
                return None  # Cannot proceed without price estimate
        except Exception as e:
            logger.warning(
                f"Could not fetch ticker price for MIN_NOTIONAL check: {e}")
            logger.error("Aborting market sell.")
            return None

        # Check price validity
        if not current_price or current_price <= Decimal('0'):
            logger.error(
                f"Aborting market sell: Invalid est price ({current_price})")
            return None

        # Validate filters including MIN_NOTIONAL
        if not validate_order_filters(symbol=self.symbol, quantity=adj_qty, price=Decimal('0'), exchange_info=self.exchange_info, estimated_price=current_price):
            logger.error(
                f"Est market sell (Qty:{adj_qty} @ EstPx:{current_price}) failed validation (likely MIN_NOTIONAL). Aborting.")
            return None

        logger.warning(
            f"Executing MARKET SELL: Qty={adj_qty:.8f} {self.base_asset} (Reason: {reason})")

        if self.simulation_mode:
            logger.info("Sim: Market sell executed.")
            # Use the fetched price for simulation fill price
            fill_price = current_price
            # *** CORRECTED logic block in broken version ***
            # Redundant check, but safe
            if fill_price is None or fill_price <= Decimal('0'):
                logger.error(
                    f"Sim: Invalid fill price ({fill_price}). Aborting state update.")
                return None

            client_order_id = self._generate_client_order_id("mkt_sell")
            sim_fill_details = {'symbol': self.symbol, 'orderId': self.sim_order_id_counter, 'clientOrderId': client_order_id, 'transactTime': int(time.time() * 1000), 'price': '0', 'origQty': str(
                adj_qty), 'executedQty': str(adj_qty), 'cummulativeQuoteQty': str(fill_price * adj_qty), 'status': 'FILLED', 'timeInForce': 'GTC', 'type': 'MARKET', 'side': 'SELL'}
            self.sim_order_id_counter += 1
            self.sim_filled_sell_count += 1

            # --- Immediate State Update for Sim ---
            bal_q = to_decimal(state.get('balance_quote', '0'))
            bal_b = to_decimal(state.get('balance_base', '0'))
            proceeds = fill_price * adj_qty
            state['position_size'] = Decimal('0')
            state['position_entry_price'] = Decimal('0')
            state['position_entry_timestamp'] = None
            state['balance_quote'] = bal_q + proceeds
            state['balance_base'] = max(Decimal('0'), bal_b - adj_qty)
            state['active_tp_order'] = None
            state['ts_exit_active_order_details'] = None
            state['ts_exit_active_order_id'] = None  # Clear cascade state too
            if state.get('active_grid_orders'):
                logger.info(
                    "Sim: Clearing active grid orders after market sell.")
                state['active_grid_orders'] = []
            logger.info(
                "Sim: State dict updated immediately after market sell simulation.")
            return sim_fill_details
        else:  # Live market sell
            try:  # Corrected Try/Except structure
                api_response = self.connector.create_market_sell(
                    symbol=self.symbol, quantity=adj_qty)
                if api_response:  # Correctly indented check
                    logger.info(
                        f"Live market sell placed: {api_response.get('orderId')}")
                    return api_response
                else:  # Correctly indented else
                    logger.error(
                        "Failed to execute market sell - Connector None.")
                    return None
            except Exception as e:
                logger.error(
                    f"Exception executing market sell: {e}", exc_info=True)
                return None


# --- Test Block (Appended from 'updated' code, structure verified) ---
if __name__ == '__main__':
    # Basic logging for test block
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger_om = logging.getLogger(__name__)  # Use the module's logger
    logger_om.info("--- Running OrderManager Test Block ---")

    try:
        config = load_config()  # Load combined config (YAML + Env Vars)
        if not config:
            logger_om.critical(
                "Failed to load config. Ensure config/config.yaml and .env exist.")
            sys.exit(1)

        # Get API keys from the loaded config
        api_key = get_config_value(config, ('binance_us', 'api_key'))
        api_secret = get_config_value(config, ('binance_us', 'api_secret'))

        if not api_key or not api_secret:
            logger_om.critical(
                "BINANCE_US_API_KEY/SECRET missing in config/env.")
            sys.exit(1)

        # --- Instantiate Connector and OrderManager ---
        try:
            # Pass config dict to connector as well
            connector = BinanceUSConnector(
                api_key, api_secret, config, tld='us')
            om = OrderManager(config, connector)
        except (ConnectionError, ValueError) as e:
            logger_om.critical(f"Failed to initialize connector/manager: {e}")
            sys.exit(1)
        except Exception as e_init:  # Catch other potential init errors
            logger_om.critical(
                f"Unexpected error initializing connector/manager: {e_init}", exc_info=True)
            sys.exit(1)

        # --- Test Setup ---
        test_symbol = om.symbol  # Use symbol from OM
        # Sample quantity to sell (ensure it passes filters)
        test_qty = Decimal('0.0002')  # User defined
        config_cascade = config.get('risk_controls', {}).get(
            'time_stop', {}).get('cascade', {})

        # Ensure required cascade config exists for testing
        if not config_cascade or not config_cascade.get('enabled'):
            logger_om.warning(
                "Cascade config missing or disabled in config.yaml. Tests might fail or be limited.")
            # Add default values if missing for test run? Or just warn.
            config_cascade = config_cascade or {}  # Ensure it's a dict
            # Treat as disabled if totally missing
            config_cascade.setdefault('enabled', False)
            config_cascade.setdefault('initial_maker_offset_ticks', 1)
            config_cascade.setdefault('aggressive_taker_offset_ticks', 1)

        test_state = {
            'balance_quote': Decimal('1000'),
            # Simulate having enough base asset
            'balance_base': test_qty * Decimal('1.5'),
            'position_size': test_qty,  # Simulate being in position
            'position_entry_price': Decimal('60000'),
            'position_entry_timestamp': time.time() - 3600,  # 1 hour ago
            'active_grid_orders': [],
            'active_tp_order': None,
            'ts_exit_active': False,
            'ts_exit_step': 0,
            'ts_exit_timer_start': None,
            'ts_exit_trigger_price': None,
            'ts_exit_active_order_id': None,
            'ts_exit_active_order_details': None  # Add the new key
        }
        pp = pprint.PrettyPrinter(indent=2)
        logger_om.info(f"Using Symbol: {test_symbol}, Test Qty: {test_qty}")
        logger_om.info(f"Initial Test State:\n{pp.pformat(test_state)}")
        logger_om.info(f"Cascade Config:\n{pp.pformat(config_cascade)}")

        # --- Test: _calculate_cascade_limit_price ---
        logger_om.info("\n--- Testing Price Calculation ---")
        try:
            book_ticker = connector.get_symbol_book_ticker(test_symbol)
            if book_ticker:
                logger_om.info(
                    f"Fetched Book Ticker:\n{pp.pformat(book_ticker)}")
                price_maker = om._calculate_cascade_limit_price(
                    'MAKER', book_ticker, config_cascade)
                price_taker = om._calculate_cascade_limit_price(
                    'TAKER', book_ticker, config_cascade)
                logger_om.info(f"Calculated MAKER price: {price_maker}")
                logger_om.info(f"Calculated TAKER price: {price_taker}")
            else:
                logger_om.warning(
                    "Could not fetch book ticker for price calculation test.")
        except Exception as e_ticker:
            logger_om.error(
                f"Error fetching book ticker during test: {e_ticker}", exc_info=True)

        # --- Test: place_ts_exit_limit_order (Simulation Mode) ---
        logger_om.info(
            "\n--- Testing Cascade Order Placement (Simulation Mode) ---")
        om.simulation_mode = True  # Ensure simulation mode for safety
        logger_om.info(f"OrderManager simulation_mode: {om.simulation_mode}")

        # Test Initial Step (e.g., MAKER or type from config)
        initial_step_type = 'initial'
        initial_result = None
        # Only test placement if cascade is enabled
        if config_cascade.get('enabled'):
            try:
                initial_result = om.place_ts_exit_limit_order(
                    test_state, test_qty, initial_step_type)
                logger_om.info(
                    f"\nResult of placing '{initial_step_type}' cascade order:\n{pp.pformat(initial_result)}")
                logger_om.info(
                    f"State after '{initial_step_type}' placement:\n{pp.pformat(test_state)}")
            except Exception as e_place_initial:
                logger_om.error(
                    f"Error during initial cascade placement test: {e_place_initial}", exc_info=True)
        else:
            logger_om.info(
                "Skipping cascade placement test as cascade is disabled in config.")

        # Test Aggressive Step (TAKER) - Simulate cancelling previous one first
        aggressive_step_type = 'aggressive'
        aggressive_result = None
        # Only if initial step succeeded
        if config_cascade.get('enabled') and initial_result:
            # Remove the previous order to simulate cancellation before placing next
            removed_ok = om._remove_order_from_state(
                test_state, client_order_id=initial_result.get('clientOrderId'))
            if removed_ok:
                logger_om.info("\nSimulated removal of 'initial' order.")
                logger_om.info(
                    f"State before '{aggressive_step_type}' placement:\n{pp.pformat(test_state)}")

                try:
                    aggressive_result = om.place_ts_exit_limit_order(
                        test_state, test_qty, aggressive_step_type)
                    logger_om.info(
                        f"\nResult of placing '{aggressive_step_type}' cascade order:\n{pp.pformat(aggressive_result)}")
                    logger_om.info(
                        f"State after '{aggressive_step_type}' placement:\n{pp.pformat(test_state)}")
                except Exception as e_place_agg:
                    logger_om.error(
                        f"Error during aggressive cascade placement test: {e_place_agg}", exc_info=True)

            else:
                logger_om.warning(
                    "Could not remove 'initial' order from state, skipping 'aggressive' test.")

        elif config_cascade.get('enabled'):
            logger_om.warning(
                "Skipping 'aggressive' step test as 'initial' order placement failed or was skipped.")

        # --- (Optional/Risky) Test: place_ts_exit_limit_order (Live Mode) ---
        # logger_om.warning("\n--- TESTING LIVE MODE - PLACES REAL ORDERS ---")
        # logger_om.warning("--- ENSURE TEST QTY IS VERY SMALL ---")
        # om.simulation_mode = False
        # logger_om.info(f"OrderManager simulation_mode: {om.simulation_mode}")
        # live_qty = Decimal('0.0001') # <<< USE A TINY AMOUNT FOR LIVE TEST >>>
        # test_state['ts_exit_active_order_details'] = None # Reset state
        # test_state['ts_exit_active_order_id'] = None
        # live_result = om.place_ts_exit_limit_order(test_state, live_qty, 'initial')
        # logger_om.info(f"\nResult of placing LIVE 'initial' cascade order:\n{pp.pformat(live_result)}")
        # logger_om.info(f"State after LIVE 'initial' placement:\n{pp.pformat(test_state)}")
        # if live_result:
        #      logger_om.warning(f"!!! IMPORTANT: MANUALLY CANCEL LIVE ORDER {live_result.get('clientOrderId')} ({live_result.get('orderId')}) ON BINANCE !!!")
        #      # You might want to add an automatic cancellation here for safety in the test block
        #      # time.sleep(5) # Give time for order to appear
        #      # cancel_success = om.cancel_order(test_state, client_order_id=live_result.get('clientOrderId'), order_id=live_result.get('orderId'), reason="TestCleanup")
        #      # logger_om.info(f"Attempted cleanup cancellation: {cancel_success}")
        # logger_om.warning("--- END LIVE MODE TEST ---")

    except Exception as e:
        logger_om.critical(
            f"An error occurred in the test block: {e}", exc_info=True)

    logger_om.info("\n--- OrderManager Test Block Finished ---")

# END OF FILE: src/core/order_manager.py (Corrected: Original Logic + Test Block)
