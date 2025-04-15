# START OF FILE: src/core/order_manager.py

import logging
import time
import random
from decimal import Decimal
from typing import Optional, Dict, Any, List, Set

import pandas as pd  # Used for type hints and Timestamp

# Project Imports (relative paths assuming main_trader.py runs from root)
try:
    from config.settings import get_config_value
    from src.connectors.binance_us import BinanceUSConnector
    from src.utils.formatting import to_decimal, apply_filter_rules_to_qty
except ImportError as e:
    # Provide fallbacks for standalone testing or if imports fail initially
    logging.basicConfig(level=logging.ERROR)
    logging.critical(f"OrderManager Import Error: {e}. Using dummy functions.")
    def get_config_value(config, key, default=None): return default
    def to_decimal(v, default=None): return Decimal(
        str(v)) if v is not None else default

    def apply_filter_rules_to_qty(symbol, qty, info, op='floor'): return qty

    class BinanceUSConnector:
        pass  # Dummy class

logger = logging.getLogger(__name__)  # Logger for this module


class OrderManager:
    """
    Manages order checking, placement, cancellation, and reconciliation logic.
    Interacts with the connector and updates the shared application state.
    """

    def __init__(self, connector: BinanceUSConnector, state: Dict[str, Any], config: Dict[str, Any]):
        """
        Initializes the OrderManager.

        Args:
            connector: Instance of BinanceUSConnector.
            state: The shared application state dictionary (will be modified directly).
            config: The application configuration dictionary.
        """
        if connector is None:
            raise ValueError(
                "OrderManager requires a valid connector instance.")
        if state is None:
            raise ValueError(
                "OrderManager requires a valid state dictionary instance.")
        if config is None:
            raise ValueError(
                "OrderManager requires a valid config dictionary instance.")

        self.connector = connector
        self.state = state  # Reference to the main state dictionary
        self.config = config
        # Determine simulation mode from the main state if available, else default
        # Default to True if not set in state yet
        self.SIMULATION_MODE = self.state.get('simulation_mode', True)
        self.SIM_PLACEMENT_SUCCESS_RATE = self.state.get(
            'sim_placement_success_rate', 0.99)  # Get from state or default

        # Initialize state keys if they don't exist (more robust)
        self.state.setdefault('active_grid_orders', [])
        self.state.setdefault('active_tp_order', None)
        self.state.setdefault('position', None)
        self.state.setdefault('sim_grid_fills', 0)
        self.state.setdefault('sim_tp_fills', 0)
        self.state.setdefault('sim_market_sells', 0)
        self.state.setdefault('sim_grid_place_fail', 0)
        self.state.setdefault('sim_tp_place_fail', 0)
        self.state.setdefault('sim_grid_cancel_fail', 0)
        self.state.setdefault('sim_tp_cancel_fail', 0)

        logger.info(
            f"OrderManager initialized (SIM_MODE: {self.SIMULATION_MODE})")

    def _get_trading_param(self, key: str, default=None):
        return get_config_value(self.config, ('trading', key), default)

    # ==========================================================================
    # ORDER CHECKING LOGIC (Moved from main_trader.py)
    # ==========================================================================
    def check_orders(self):
        """
        Checks status of active orders via API (or SIMULATES based on price),
        updates internal state (position, active orders).
        """
        if not self.connector:
            logger.error("OrderManager: Connector not available.")
            return
        symbol = self._get_trading_param('symbol', 'BTCUSDT')
        # Use LIVE prefix if not SIM
        log_prefix = "(SIM)" if self.SIMULATION_MODE else "(LIVE)"
        logger.debug(f"OrderManager checking status {log_prefix}...")
        made_state_changes = False
        current_price_for_sim, current_low_for_sim, current_high_for_sim = None, None, None

        # Get current price from shared state for simulation
        if self.SIMULATION_MODE and 'klines' in self.state and not self.state['klines'].empty:
            latest_kline = self.state['klines'].iloc[-1]
            current_price_for_sim = latest_kline.get('Close')
            current_low_for_sim = latest_kline.get('Low')
            current_high_for_sim = latest_kline.get('High')
            logger.debug(
                f"OrderManager Sim Price Check: L={current_low_for_sim}, H={current_high_for_sim}, C={current_price_for_sim}")

        # --- Check Grid Orders ---
        orders_to_remove_indices = []
        grid_orders_copy = list(self.state['active_grid_orders'])
        for i, order_data in enumerate(grid_orders_copy):
            if not isinstance(order_data, dict):
                orders_to_remove_indices.append(i)
                continue
            order_id = order_data.get('orderId')
            if not order_id:
                orders_to_remove_indices.append(i)
                continue
            logger.debug(f"Checking grid order ID: {order_id}...")
            status_info = None
            sim_status = 'NEW'
            if self.SIMULATION_MODE:
                # --- Simulation fill logic ---
                order_price = to_decimal(order_data.get('price'))
                check_price = current_low_for_sim if current_low_for_sim is not None else current_price_for_sim
                if order_price and check_price and check_price <= order_price:
                    if random.random() < 0.95:
                        sim_status = 'FILLED'
                        logger.debug(
                            f"{log_prefix} Price ({check_price}) <= Order Price ({order_price}). Simulating FILL for {order_id}.")
                    else:
                        logger.debug(
                            f"{log_prefix} Price ({check_price}) <= Order Price ({order_price}) but simulating NEW for {order_id}.")
                        sim_status = 'NEW'
                if sim_status == 'NEW':
                    if random.random() < 0.005:
                        sim_status = random.choice(
                            ['CANCELED', 'REJECTED', 'UNKNOWN'])
                        logger.warning(
                            f"{log_prefix} Simulating random failure ({sim_status}) for {order_id}.")
                if sim_status != 'NEW':
                    status_info = {'symbol': symbol, 'orderId': order_id, 'status': sim_status, 'price': str(order_data.get('price', '0')), 'origQty': str(order_data.get(
                        'origQty', '0')), 'executedQty': str(order_data.get('origQty', '0')) if sim_status == 'FILLED' else '0', 'updateTime': int(time.time()*1000)}
            else:  # Live mode
                try:
                    # --- UNCOMMENTED READ-ONLY API CALL ---
                    status_info = self.connector.get_order_status(
                        symbol, str(order_id))
                    logger.debug(
                        f"API check grid order {order_id}: Status={status_info.get('status') if status_info else 'Error'}")
                except Exception as e:
                    logger.error(
                        f"API Error checking order {order_id}: {e}", exc_info=True)
                    status_info = None

            # --- Process Status Update ---
            if status_info:
                status = status_info.get('status')
                if status == 'FILLED':
                    logger.info(
                        f"{log_prefix} *** GRID BUY FILLED ***: OrderID={order_id}, Qty={status_info.get('executedQty')}, Px={status_info.get('price')}")
                    entry_price = to_decimal(status_info.get('price'))
                    filled_qty = to_decimal(status_info.get('executedQty'))
                    if entry_price and filled_qty and self.state['position'] is None:
                        self.state['position'] = {'symbol': symbol, 'entry_price': entry_price, 'quantity': filled_qty, 'entry_time': pd.Timestamp(
                            status_info.get('updateTime'), unit='ms', tz='UTC')}
                        logger.info(
                            f"+++ Position CREATED {log_prefix} +++: Entry={entry_price:.4f}, Qty={filled_qty}")
                        if self.SIMULATION_MODE:
                            self.state['sim_grid_fills'] += 1
                        logger.warning(
                            f"{log_prefix}: Fill detected, marking remaining grid orders for removal state update...")
                        orders_to_remove_indices.extend(
                            j for j in range(len(grid_orders_copy)) if j != i)
                        made_state_changes = True
                        break
                    elif self.state['position'] is not None:
                        logger.warning(
                            f"{log_prefix} fill {order_id}, but pos exists. Marking removal.")
                        orders_to_remove_indices.append(i)
                    else:
                        logger.error(
                            f"Could not parse fill {order_id}. Info: {status_info}. Marking removal.")
                        orders_to_remove_indices.append(i)
                elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'UNKNOWN', 'PENDING_CANCEL']:
                    logger.warning(
                        f"Grid order {order_id} inactive (Status: {status}). Marking removal.")
                    orders_to_remove_indices.append(i)
                    made_state_changes = True
                elif status not in ['NEW', 'PARTIALLY_FILLED']:
                    logger.warning(
                        f"Unhandled order status '{status}' for grid order {order_id}. Marking removal.")
                    orders_to_remove_indices.append(i)
                    made_state_changes = True
            else:
                if self.SIMULATION_MODE and sim_status == 'NEW':
                    logger.debug(f"Grid order {order_id} status: NEW.")
                else:
                    logger.error(
                        f"Failed get status grid order {order_id}. Marking removal.")
                    orders_to_remove_indices.append(i)
                    made_state_changes = True
            if not self.SIMULATION_MODE:
                time.sleep(0.1)
            else:
                time.sleep(0.01)

        # --- Update state by removing marked grid orders ---
        unique_indices_to_remove = sorted(
            list(set(orders_to_remove_indices)), reverse=True)
        if unique_indices_to_remove:
            logger.debug(
                f"OrderManager removing indices {unique_indices_to_remove} from active_grid_orders state")
            indices_set = set(unique_indices_to_remove)
            self.state['active_grid_orders'] = [o for i, o in enumerate(
                self.state['active_grid_orders']) if i not in indices_set]
            logger.debug(
                f"OrderManager removed {len(unique_indices_to_remove)} grid orders from state. New count: {len(self.state['active_grid_orders'])}.")
            made_state_changes = True

        # --- Check TP Order ---
        tp_order = self.state.get('active_tp_order')
        if tp_order and isinstance(tp_order, dict) and tp_order.get('orderId'):
            order_id = tp_order['orderId']
            logger.debug(f"Checking TP order ID: {order_id}...")
            status_info_tp = None
            sim_status_tp = 'NEW'
            if self.SIMULATION_MODE:
                order_price_tp = to_decimal(tp_order.get('price'))
                check_price_tp = current_high_for_sim if current_high_for_sim is not None else current_price_for_sim
                if order_price_tp and check_price_tp and check_price_tp >= order_price_tp:
                    if random.random() < 0.95:
                        sim_status_tp = 'FILLED'
                        logger.debug(
                            f"{log_prefix} Price ({check_price_tp}) >= TP Price ({order_price_tp}). Simulating FILL for {order_id}.")
                    else:
                        logger.debug(
                            f"{log_prefix} Price ({check_price_tp}) >= TP Price ({order_price_tp}) but simulating NEW for {order_id}.")
                        sim_status_tp = 'NEW'
                if sim_status_tp == 'NEW':
                    if random.random() < 0.005:
                        sim_status_tp = random.choice(
                            ['CANCELED', 'REJECTED', 'UNKNOWN'])
                        logger.warning(
                            f"{log_prefix} Simulating random failure ({sim_status_tp}) for TP order {order_id}.")
                if sim_status_tp != 'NEW':
                    status_info_tp = {'symbol': symbol, 'orderId': order_id, 'status': sim_status_tp, 'price': str(tp_order.get('price', '0')), 'executedQty': str(
                        self.state['position'].get('quantity', '0')) if sim_status_tp == 'FILLED' and self.state['position'] else '0', 'updateTime': int(time.time()*1000)}
            else:  # Live mode
                try:
                    # --- UNCOMMENTED READ-ONLY API CALL ---
                    status_info_tp = self.connector.get_order_status(
                        symbol, str(order_id))
                    logger.debug(
                        f"API check TP order {order_id}: Status={status_info_tp.get('status') if status_info_tp else 'Error'}")
                except Exception as e:
                    logger.error(
                        f"API Error checking TP order {order_id}: {e}", exc_info=True)
                    status_info_tp = None

            # --- Process Status Update ---
            if status_info_tp:
                status = status_info_tp.get('status')
                if status == 'FILLED':
                    logger.info(
                        f"{log_prefix} *** TAKE PROFIT FILLED ***: OrderID={order_id}, Qty={status_info_tp.get('executedQty')}, Px={status_info_tp.get('price')}")
                    if self.SIMULATION_MODE:
                        self.state['sim_tp_fills'] += 1
                    self.state['position'] = None
                    self.state['active_tp_order'] = None
                    logger.info(f"--- Position CLEARED {log_prefix} ---")
                    made_state_changes = True
                elif status in ['CANCELED', 'EXPIRED', 'REJECTED', 'UNKNOWN', 'PENDING_CANCEL']:
                    logger.warning(
                        f"TP order {order_id} inactive (Status: {status}). Clearing state.")
                    self.state['active_tp_order'] = None
                    made_state_changes = True
                elif status not in ['NEW', 'PARTIALLY_FILLED']:
                    logger.warning(
                        f"Unhandled order status '{status}' for TP order {order_id}. Clearing state.")
                    self.state['active_tp_order'] = None
                    made_state_changes = True
            else:
                if self.SIMULATION_MODE and sim_status_tp == 'NEW':
                    logger.debug(f"TP order {order_id} status: NEW.")
                else:
                    logger.error(
                        f"Failed get status TP order {order_id}. Clearing state.")
                    self.state['active_tp_order'] = None
                    made_state_changes = True

        if not made_state_changes:
            logger.debug(
                "Order check complete: No relevant state changes detected.")

    def reconcile_and_place_grid(self, planned_orders: List[Dict]):
        """ Fetches open orders, reconciles with state, cancels discrepancies/old orders, places new ones. """
        if not self.connector:
            logger.error("OrderManager: Connector NA.")
            return
        symbol = self._get_trading_param('symbol', 'BTCUSDT')
        log_prefix = "(SIM)" if self.SIMULATION_MODE else "(LIVE)"
        logger.info(
            f"--- OrderManager: Starting Grid Reconciliation & Placement {log_prefix} ---")
        exchange_open_orders: List[Dict] = []
        try:
            if self.SIMULATION_MODE:
                logger.debug(
                    f"Simulating fetch open orders based on state: {len(self.state['active_grid_orders'])} orders")
                for order_in_state in self.state['active_grid_orders']:
                    if random.random() > 0.1:
                        exchange_open_orders.append(order_in_state.copy())
                logger.info(
                    f"{log_prefix} Recon: Simulated {len(exchange_open_orders)} open orders based on current state.")
            else:  # Live Mode
                # --- UNCOMMENTED READ-ONLY API CALL ---
                logger.info(
                    f"Attempting to fetch REAL open orders for {symbol}...")
                fetched_orders = self.connector.get_open_orders(symbol)
                if fetched_orders is None:
                    logger.error(
                        "API Error fetching open orders. Cannot reconcile.")
                    return
                exchange_open_orders = fetched_orders
                logger.info(
                    f"{log_prefix} Recon: Found {len(exchange_open_orders)} open orders on exchange for {symbol}.")
        except Exception as e:
            logger.exception(f"Error fetching open orders {log_prefix}")
            return

        # --- Reconciliation Logic (remains the same) ---
        state_order_ids: Set[int] = {
            int(o['orderId']) for o in self.state['active_grid_orders'] if o.get('orderId')}
        exchange_order_ids: Set[int] = {
            int(o['orderId']) for o in exchange_open_orders if o.get('orderId')}
        orders_in_state_only = state_order_ids - exchange_order_ids
        orders_on_exchange_only = exchange_order_ids - state_order_ids
        orders_match = state_order_ids.intersection(exchange_order_ids)
        if orders_in_state_only:
            logger.warning(
                f"{log_prefix} Recon: Orders in state but NOT on exchange: {orders_in_state_only}")
            self.state['active_grid_orders'] = [o for o in self.state['active_grid_orders'] if int(
                o.get('orderId', -1)) not in orders_in_state_only]
        if orders_on_exchange_only:
            logger.warning(
                f"{log_prefix} Recon: Orders ON exchange but NOT in state (rogue?): {orders_on_exchange_only}")
        logger.info(
            f"{log_prefix} Recon: Matching orders in state & on exchange: {len(orders_match)}")
        orders_to_cancel_ids = list(orders_match)
        successfully_cancelled_ids = []

        # --- Cancel matching orders ---
        if orders_to_cancel_ids:
            logger.info(
                f"{log_prefix} Cancelling {len(orders_to_cancel_ids)} matching grid orders...")
            for order_id_to_cancel in orders_to_cancel_ids:
                logger.debug(
                    f"{log_prefix} Attempting cancel order {order_id_to_cancel}...")
                cancel_result = None
                if self.SIMULATION_MODE:  # Simulate cancel
                    if random.random() < self.SIM_PLACEMENT_SUCCESS_RATE:
                        cancel_result = {
                            'orderId': order_id_to_cancel, 'status': 'CANCELED'}
                        logger.debug(
                            f"{log_prefix} Sim CANCEL success for {order_id_to_cancel}")
                    else:
                        logger.error(
                            f"{log_prefix} Sim CANCEL failure for {order_id_to_cancel}")
                        self.state['sim_grid_cancel_fail'] += 1
                else:  # Live mode - CANCEL REMAINS COMMENTED FOR SAFETY
                    logger.warning(
                        f"LIVE MODE: Skipping actual cancel for order {order_id_to_cancel}")
                    # Assume cancel would work
                    cancel_result = {
                        'orderId': order_id_to_cancel, 'status': 'CANCELED'}
                    # --- KEEP CANCEL COMMENTED ---
                    # try: cancel_result = self.connector.cancel_order(symbol, order_id=str(order_id_to_cancel))
                    # except Exception as e: logger.error(f"API Error cancelling order {order_id_to_cancel}: {e}", exc_info=True); cancel_result = None
                    # --- END KEEP CANCEL COMMENTED ---
                if cancel_result and (cancel_result.get('status') == 'CANCELED' or cancel_result.get('status') == 'UNKNOWN'):
                    successfully_cancelled_ids.append(order_id_to_cancel)
                else:
                    logger.error(
                        f"{log_prefix} Cancel FAILED for {order_id_to_cancel}. Result: {cancel_result}")
                    if not self.SIMULATION_MODE:
                        self.state['sim_grid_cancel_fail'] += 1
                time.sleep(0.01 if self.SIMULATION_MODE else 0.2)
        # Update state post-cancel/stale
        cancelled_or_stale_ids = set(
            successfully_cancelled_ids) | orders_in_state_only
        if cancelled_or_stale_ids:
            self.state['active_grid_orders'] = [o for o in self.state['active_grid_orders'] if int(
                o.get('orderId', -1)) not in cancelled_or_stale_ids]
        if orders_to_cancel_ids and self.state['active_grid_orders']:
            logger.warning(
                f"State has orders after cancel: {self.state['active_grid_orders']}. Clearing.")
            self.state['active_grid_orders'] = []

        # --- Place new orders ---
        placed_orders_state_update = []
        success_count = 0
        failure_count = 0
        if planned_orders:
            logger.info(
                f"{log_prefix} Placing {len(planned_orders)} new grid orders...")
            for order_to_place in planned_orders:
                price = order_to_place.get('price')
                quantity = order_to_place.get('quantity')
                if price is None or quantity is None:
                    logger.error(
                        f"Skipping invalid planned order: {order_to_place}")
                    failure_count += 1
                    continue
                logger.debug(
                    f"{log_prefix} Placing new grid order: {quantity}@{price}")
                result = None
                if self.SIMULATION_MODE:  # Simulate placement
                    if random.random() < self.SIM_PLACEMENT_SUCCESS_RATE:
                        sim_order_id = random.randint(10000000, 99999999)
                        result = {'symbol': symbol, 'orderId': sim_order_id, 'clientOrderId': f"sim_{sim_order_id}", 'transactTime': int(time.time() * 1000), 'price': str(
                            price), 'origQty': str(quantity), 'executedQty': '0.0', 'cummulativeQuoteQty': '0.0', 'status': 'NEW', 'timeInForce': 'GTC', 'type': 'LIMIT', 'side': 'BUY'}
                        logger.debug(
                            f"{log_prefix} Sim placement success. ID: {sim_order_id}")
                    else:
                        logger.error(
                            f"{log_prefix} Sim placement failure for order at {price}.")
                else:  # Live mode - PLACEMENT REMAINS COMMENTED
                    logger.warning(
                        f"LIVE MODE: Skipping actual placement for grid order at {price}")
                    sim_order_id = random.randint(10000000, 99999999)
                    result = {'symbol': symbol, 'orderId': sim_order_id, 'status': 'NEW', 'price': str(
                        price), 'origQty': str(quantity)}  # Fake result
                    # --- KEEP PLACE COMMENTED ---
                    # try: result = self.connector.create_limit_buy(symbol=symbol, quantity=quantity, price=price)
                    # except Exception as e: logger.error(f"API Error placing grid order at {price}: {e}", exc_info=True); result = None
                    # --- END KEEP PLACE COMMENTED ---
                if result and result.get('orderId'):
                    placed_orders_state_update.append(result)
                    success_count += 1
                else:
                    logger.error(
                        f"{log_prefix} Placement FAILED grid order at {price}.")
                    failure_count += 1
                    if self.SIMULATION_MODE:
                        self.state['sim_grid_place_fail'] += 1
                time.sleep(0.01 if self.SIMULATION_MODE else 0.3)
            logger.info(
                f"{log_prefix} Grid Placement Summary: {success_count} succeeded, {failure_count} failed.")
        else:
            logger.info(f"{log_prefix} No new grid orders were planned.")
        self.state['active_grid_orders'] = placed_orders_state_update
        logger.info(
            f"--- OrderManager: Grid Recon & Placement Complete {log_prefix}. Final Active Grid Orders: {len(self.state['active_grid_orders'])} ---")

    def place_or_update_tp_order(self, tp_price: Decimal):
        # ... (Cancellation and Placement logic remains COMMENTED for LIVE mode) ...
        if not self.connector:
            logger.error("OrderManager: Connector NA.")
            return
        if self.state.get('position') is None:
            logger.debug(
                "place_or_update_tp_order called but no position exists.")
            return
        log_prefix = "(SIM)" if self.SIMULATION_MODE else "(LIVE)"
        symbol = self.state['position']['symbol']
        quantity = self.state['position']['quantity']
        active_tp_order = self.state.get('active_tp_order')
        exchange_info = self.connector.get_exchange_info_cached()
        if not exchange_info:
            logger.error("Cannot place TP: Exchange info missing.")
            return
        sell_qty = apply_filter_rules_to_qty(
            symbol, quantity, exchange_info, operation='floor')
        if sell_qty is None or sell_qty <= 0:
            logger.error(
                f"Cannot place TP: Invalid sell qty {quantity} after filter.")
            return
        needs_action = False
        order_to_cancel = None
        if active_tp_order and isinstance(active_tp_order, dict) and active_tp_order.get('orderId'):
            current_tp_price_in_state = to_decimal(
                active_tp_order.get('price'))
            if not current_tp_price_in_state or abs(tp_price - current_tp_price_in_state) / current_tp_price_in_state >= Decimal('0.001'):
                needs_action = True
                order_to_cancel = active_tp_order['orderId']
                logger.info(
                    f"TP target {tp_price:.4f} differs from active {order_to_cancel} @ {current_tp_price_in_state:.4f}. Update needed.")
            else:
                logger.debug(
                    f"TP price {tp_price:.4f} close to existing {active_tp_order['orderId']}. No action.")
        else:
            needs_action = True
            logger.info(
                f"No active TP order found. Placing new one at {tp_price:.4f}.")
        if needs_action:
            if order_to_cancel:
                logger.info(
                    f"{log_prefix} Cancelling existing TP order {order_to_cancel} to update...")
                cancel_success = False
                if self.SIMULATION_MODE:
                    cancel_success = random.random() < self.SIM_PLACEMENT_SUCCESS_RATE
                else:  # Live mode - CANCEL COMMENTED
                    logger.warning(
                        f"LIVE MODE: Skipping actual cancel for TP order {order_to_cancel}")
                    cancel_success = True
                    # --- KEEP CANCEL COMMENTED ---
                    # try: cancel_result = self.connector.cancel_order(symbol, order_id=str(order_to_cancel)); cancel_success = cancel_result is not None
                    # except Exception as e: logger.error(f"API Error cancelling TP order {order_to_cancel}: {e}", exc_info=True); cancel_success = False
                if not cancel_success:
                    logger.error(
                        f"{log_prefix} Cancel FAILED for TP {order_to_cancel}. Update aborted.")
                    if self.SIMULATION_MODE:
                        self.state['sim_tp_cancel_fail'] += 1
                        self.state['active_tp_order'] = None
                        return
                self.state['active_tp_order'] = None
                logger.info(
                    f"{log_prefix} Successfully cancelled TP order {order_to_cancel}.")
                time.sleep(0.01 if self.SIMULATION_MODE else 0.2)
            logger.info(
                f"{log_prefix} Placing TP order: Sell {sell_qty}@{tp_price}")
            result = None
            if self.SIMULATION_MODE:
                if random.random() < self.SIM_PLACEMENT_SUCCESS_RATE:
                    sim_order_id = random.randint(10000000, 99999999)
                    result = {'symbol': symbol, 'orderId': sim_order_id, 'status': 'NEW', 'price': str(
                        tp_price), 'origQty': str(sell_qty)}
            else:  # Live mode - PLACE COMMENTED
                logger.warning(
                    f"LIVE MODE: Skipping actual placement for TP order at {tp_price}")
                sim_order_id = random.randint(10000000, 99999999)
                result = {'symbol': symbol, 'orderId': sim_order_id, 'status': 'NEW', 'price': str(
                    tp_price), 'origQty': str(sell_qty)}  # Fake result
                # --- KEEP PLACE COMMENTED ---
                # try: result = self.connector.create_limit_sell(symbol, sell_qty, tp_price)
                # except Exception as e: logger.error(f"API Error placing TP order at {tp_price}: {e}", exc_info=True); result = None
            if result and result.get('orderId'):
                self.state['active_tp_order'] = result
                logger.info(
                    f"{log_prefix} TP placed/updated successfully. New Order ID: {result.get('orderId')}")
            else:
                logger.error(f"{log_prefix} Placement FAILED for TP order.")
                self.state['active_tp_order'] = None
                if self.SIMULATION_MODE:
                    self.state['sim_tp_place_fail'] += 1

    def execute_market_sell(self, reason: str) -> bool:
        # ... (Cancellation and Placement logic remains COMMENTED for LIVE mode) ...
        if not self.connector:
            logger.error("OrderManager: Connector NA.")
            return False
        if self.state.get('position') is None:
            logger.warning("Market sell requested but no position exists.")
            return False
        log_prefix = "(SIM)" if self.SIMULATION_MODE else "(LIVE)"
        symbol = self.state['position']['symbol']
        quantity = self.state['position']['quantity']
        logger.warning(
            f"*** {log_prefix} Executing Market SELL for {quantity} {symbol} due to: {reason} ***")
        active_tp_order = self.state.get('active_tp_order')
        if active_tp_order and isinstance(active_tp_order, dict) and active_tp_order.get('orderId'):
            tp_order_id = active_tp_order['orderId']
            logger.info(
                f"{log_prefix} Cancelling associated TP order {tp_order_id} before market sell...")
            cancel_tp_success = False
            if self.SIMULATION_MODE:
                cancel_tp_success = random.random() < self.SIM_PLACEMENT_SUCCESS_RATE
            else:  # Live mode - CANCEL COMMENTED
                logger.warning(
                    f"LIVE MODE: Skipping actual cancel for TP order {tp_order_id}")
                cancel_tp_success = True
                # --- KEEP CANCEL COMMENTED ---
                # try: cancel_tp_result = self.connector.cancel_order(symbol, str(tp_order_id)); cancel_tp_success = cancel_tp_result is not None
                # except Exception as e: logger.error(f"API Error cancelling TP order {tp_order_id}: {e}", exc_info=True); cancel_tp_success = False
            if cancel_tp_success:
                logger.info(
                    f"{log_prefix} TP order {tp_order_id} cancelled successfully.")
                self.state['active_tp_order'] = None
            else:
                logger.error(
                    f"{log_prefix} FAILED to cancel TP order {tp_order_id}. Market sell aborted!")
                if self.SIMULATION_MODE:
                    self.state['sim_tp_cancel_fail'] += 1
                    return False
        else:
            logger.debug(
                "No active TP order found in state to cancel before market sell.")
        result = None
        if self.SIMULATION_MODE:
            sim_order_id = random.randint(10000000, 99999999)
            result = {'symbol': symbol, 'orderId': sim_order_id,
                      'status': 'FILLED', 'executedQty': str(quantity)}
        else:  # Live mode - MARKET SELL COMMENTED
            logger.warning(
                f"LIVE MODE: Skipping actual market sell for {quantity} {symbol}")
            sim_order_id = random.randint(10000000, 99999999)
            result = {'symbol': symbol, 'orderId': sim_order_id,
                      # Fake result
                      'status': 'FILLED', 'executedQty': str(quantity)}
            # --- KEEP MARKET SELL COMMENTED ---
            # try: result = self.connector.create_market_sell(symbol, quantity)
            # except Exception as e: logger.error(f"API Error executing market sell: {e}", exc_info=True); result = None
        if result and result.get('status') == 'FILLED':
            logger.warning(
                f"{log_prefix} *** Market SELL successful ***. Order ID: {result.get('orderId')}")
            logger.info(f"--- Position CLEARED {log_prefix} ---")
            if self.SIMULATION_MODE:
                self.state['sim_market_sells'] += 1
            self.state['position'] = None
            self.state['active_tp_order'] = None
            return True
        else:
            logger.error(f"{log_prefix} Market SELL FAILED! Result: {result}.")
            return False

# END OF FILE: src/core/order_manager.py
