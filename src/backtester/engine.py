# src/backtester/engine.py

import logging
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation
import pandas as pd
import numpy as np  # For performance metrics calculation
from typing import List, Dict, Optional, Tuple, Any
from copy import deepcopy
import time

# --- Add project root to sys.path FIRST ---
import os
import sys
_project_root_for_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root_for_path not in sys.path:
    sys.path.insert(0, _project_root_for_path)
# --- End sys.path modification ---

# --- Project Imports ---
try:
    from src.utils.logging_setup import setup_logging  # For test block
    from src.utils.formatting import to_decimal  # For consistent Decimal conversion
    from src.db.manager import DBManager  # To log simulated trades
    from src.analysis.indicators import calculate_atr  # To calculate ATR on the fly
    from src.strategies.geometric_grid import plan_buy_grid_v1  # Grid planning logic
    from src.strategies.simple_tp import calculate_fixed_tp_price  # TP calculation logic
    # Load config for strategy params, fees
    from config.settings import load_config
except ImportError as e:
    # This block raises a standard ImportError if imports fail here
    print(
        f"ERROR: Could not import project modules for Backtester. Error: {e}")
    print(f"Project Root (calculated for path): {_project_root_for_path}")
    print(f"System Path: {sys.path}")
    raise ImportError(
        "Failed to import required project modules for Backtester.") from e
# --- End Project Imports ---

logger = logging.getLogger(__name__)


class Backtester:
    """
    Simulates the geometric grid trading strategy on historical kline data.

    Handles portfolio management, order simulation, fee calculation,
    and performance metric reporting.
    """

    def __init__(
        self,
        symbol: str,
        historical_data: pd.DataFrame,
        strategy_config: Dict,
        exchange_filters: Dict,
        initial_cash: Decimal = Decimal('10000.0'),
        maker_fee: Decimal = Decimal('0.001'),  # Example fee (0.1%)
        taker_fee: Decimal = Decimal('0.001'),  # Example fee (0.1%)
        db_manager: Optional[DBManager] = None,  # Optional DB connection
        backtest_id: str = "backtest_01"  # Identifier for this run
    ):
        """
        Initializes the Backtester.

        Args:
            symbol (str): The trading symbol (e.g., 'BTCUSD').
            historical_data (pd.DataFrame): DataFrame containing kline data
                                            (Timestamp index, Open, High, Low, Close, Volume, ATR_X).
                                            Requires 'High', 'Low', 'Close' and ATR columns.
            strategy_config (Dict): Configuration for the grid strategy.
            exchange_filters (Dict): Exchange filters for the symbol.
            initial_cash (Decimal): Starting quote currency balance.
            maker_fee (Decimal): Fee for limit orders (maker).
            taker_fee (Decimal): Fee for market orders (taker - less relevant here).
            db_manager (Optional[DBManager]): Instance for logging trades.
            backtest_id (str): Unique ID for this backtest run, used in logging.
        """
        self.symbol = symbol
        # Simplistic base asset extraction
        self.base_asset = symbol[:-
                                 3] if symbol.endswith('USD') else symbol.split('/')[0]
        self.quote_asset = 'USD' if symbol.endswith(
            'USD') else symbol.split('/')[1]
        self.historical_data = historical_data.copy()  # Work on a copy
        self.strategy_config = strategy_config
        self.exchange_filters = exchange_filters
        # Ensure initial cash is Decimal
        self.initial_cash = to_decimal(initial_cash, Decimal('10000.0'))
        self.maker_fee = to_decimal(maker_fee, Decimal('0.001'))
        self.taker_fee = to_decimal(taker_fee, Decimal('0.001'))
        self.db_manager = db_manager
        self.backtest_id = backtest_id

        # --- Portfolio State ---
        self.cash = self.initial_cash  # Start with the Decimal initial cash
        self.base_asset_balance = Decimal('0.0')
        # List of (timestamp, value<Decimal>) tuples
        self.portfolio_value_history = []

        # --- Order Management ---
        # Simulated open limit buy orders
        self.open_buy_orders: List[Dict] = []
        # Simulated open limit sell (TP) orders
        self.open_sell_orders: List[Dict] = []
        self.filled_trades: List[Dict] = []  # Log of filled orders (simulated)

        # --- Internal State ---
        self._current_bar_index = 0
        self._current_timestamp = None
        self._current_price_info = {}  # Holds O,H,L,C<Decimal> for the current bar

        # --- Performance Metrics ---
        self.metrics = {}

        logger.info(
            f"Backtester initialized for {self.symbol} ({self.backtest_id})")
        logger.info(f"Initial Cash: {self.cash} {self.quote_asset}")
        logger.info(
            f"Data Range: {self.historical_data.index.min()} to {self.historical_data.index.max()}")

        # Ensure required ATR column exists and calculate if missing
        atr_length_config = self.strategy_config.get("atr_length")
        if atr_length_config is None:
            atr_len = 14  # Default if not specified
            logger.warning(
                f"'atr_length' not found in strategy_config, defaulting to {atr_len}.")
        else:
            try:
                atr_len = int(atr_length_config)
            except ValueError:
                logger.error(
                    f"Invalid non-integer value for 'atr_length' in config: {atr_length_config}. Using default 14.")
                atr_len = 14

        self.atr_column_name = f'ATR_{atr_len}'

        if self.atr_column_name not in self.historical_data.columns:
            logger.warning(
                f"Required ATR column '{self.atr_column_name}' not found in historical data. Attempting calculation.")
            self.historical_data = calculate_atr(
                self.historical_data, length=atr_len)
            if self.atr_column_name not in self.historical_data.columns:
                raise ValueError(
                    f"Failed to calculate required {self.atr_column_name} column.")
            # Drop NaN rows introduced by ATR calculation
            initial_len = len(self.historical_data)
            self.historical_data.dropna(
                subset=[self.atr_column_name], inplace=True)
            logger.info(
                f"Dropped {initial_len - len(self.historical_data)} rows with NaN ATR values.")

    def _update_portfolio_value(self):
        """Calculates and records the current portfolio value as Decimal."""
        # Use the current bar's closing price for valuation
        current_price = self._current_price_info.get(
            'Close')  # Should be Decimal
        if current_price is None or current_price <= 0:
            current_price = self._current_price_info.get('Open')  # Try Open
            if current_price is None or current_price <= 0:
                logger.warning(
                    f"[{self._current_timestamp}] Cannot value portfolio: Invalid current price.")
                # Use last known value if possible, or keep cash value
                if self.portfolio_value_history:
                    last_value = self.portfolio_value_history[-1][1]
                    self.portfolio_value_history.append(
                        (self._current_timestamp, last_value))
                else:
                    # Append initial cash if very first bar has bad price
                    self.portfolio_value_history.append(
                        (self._current_timestamp, self.initial_cash if not self.portfolio_value_history else self.cash))
                return

        try:
            base_value = self.base_asset_balance * current_price
            total_value = self.cash + base_value  # Decimal + Decimal * Decimal
            self.portfolio_value_history.append(
                (self._current_timestamp, total_value))
            # logger.debug(f"[{self._current_timestamp}] Portfolio Value: {total_value:.2f} (Cash: {self.cash:.2f}, Base: {self.base_asset_balance:.8f} @ {current_price:.2f})")
        except (TypeError, InvalidOperation) as e:
            logger.error(
                f"[{self._current_timestamp}] Error calculating portfolio value: {e}. Cash={self.cash}, Base Balance={self.base_asset_balance}, Price={current_price}")
            # Append last known value or cash value as fallback
            fallback_value = self.portfolio_value_history[-1][1] if self.portfolio_value_history else self.cash
            self.portfolio_value_history.append(
                (self._current_timestamp, fallback_value))

    def _simulate_order_fill(self, order: Dict, fill_price: Decimal, fill_timestamp: pd.Timestamp):
        """Simulates filling an order and updates portfolio state."""
        order_type = order['side']
        quantity = order['quantity']  # Should be Decimal
        # Assume limit orders are makers
        fee_multiplier = Decimal('1.0') - self.maker_fee

        trade_info = {
            'timestamp': fill_timestamp,
            'backtest_id': self.backtest_id,
            'symbol': self.symbol,
            # Unique simulated ID
            'order_id': f"sim_{order_type.lower()}_{int(time.time()*1e6)}_{len(self.filled_trades)}",
            # Preserve if exists
            'client_order_id': order.get('clientOrderId', f"sim_{len(self.filled_trades)}"),
            'price': fill_price,  # Decimal
            'quantity': quantity,  # Decimal
            'side': order_type,
            'fee': Decimal('0.0'),  # Decimal
            'fee_asset': '',
            'is_maker': True,
            'source': 'backtest'
        }

        try:
            if order_type == 'BUY':
                cost = fill_price * quantity
                fee = cost * self.maker_fee
                self.cash -= (cost + fee)
                # Assume fee doesn't affect received quantity for simplicity
                self.base_asset_balance += quantity
                trade_info['fee'] = fee
                trade_info['fee_asset'] = self.quote_asset
                logger.info(
                    f"[{fill_timestamp}] --- BUY FILLED --- Price: {fill_price:.2f}, Qty: {quantity:.8f}, Cost: {cost:.2f}, Fee: {fee:.4f} {self.quote_asset}")

                # Plan TP order immediately after buy fill
                current_atr = self._current_price_info.get(
                    self.atr_column_name)
                tp_method_config = self.strategy_config.get(
                    'tp_method', 'percentage')
                tp_value_config = self.strategy_config.get('tp_value', '0.02')

                if not tp_method_config or not tp_value_config:
                    logger.error(
                        "Missing tp_method or tp_value in strategy config. Cannot plan TP.")
                else:
                    tp_value_decimal = to_decimal(tp_value_config)
                    if tp_value_decimal is None:
                        logger.error(
                            f"Invalid TP value in config: {tp_value_config}. Cannot plan TP.")
                    else:
                        tp_price = calculate_fixed_tp_price(
                            entry_price=fill_price,
                            method=tp_method_config,
                            value=tp_value_decimal,
                            atr=current_atr,  # Use current ATR
                            exchange_filters=self.exchange_filters
                            # Later: Pass confidence score to modulate TP target
                        )
                        if tp_price:
                            sell_order = {
                                'symbol': self.symbol,
                                'side': 'SELL',
                                'type': 'LIMIT',
                                'quantity': quantity,  # Sell the same quantity bought
                                'price': tp_price,  # Decimal
                                'timeInForce': 'GTC',
                                # Link TP to its buy
                                'linked_buy_id': trade_info['order_id']
                            }
                            self.open_sell_orders.append(sell_order)
                            logger.debug(
                                f"[{fill_timestamp}] Placed TP SELL Order: Price={tp_price:.2f}, Qty={quantity:.8f}")
                        else:
                            logger.warning(
                                f"[{fill_timestamp}] Could not calculate TP price for buy at {fill_price:.2f}. No TP order placed.")

            elif order_type == 'SELL':
                revenue = fill_price * quantity
                fee = revenue * self.maker_fee
                self.cash += (revenue - fee)
                self.base_asset_balance -= quantity
                trade_info['fee'] = fee
                trade_info['fee_asset'] = self.quote_asset
                logger.info(
                    f"[{fill_timestamp}] --- SELL FILLED (TP) --- Price: {fill_price:.2f}, Qty: {quantity:.8f}, Revenue: {revenue:.2f}, Fee: {fee:.4f} {self.quote_asset}")

            else:
                logger.error(f"Unknown order type simulation: {order_type}")
                return  # Don't log unknown types

            self.filled_trades.append(trade_info)

            # Log to Database if manager is provided
            if self.db_manager:
                try:
                    # Prepare data for log_trade function signature
                    trade_data_for_db = {
                        'symbol': trade_info['symbol'],
                        'orderId': trade_info['order_id'],
                        'clientOrderId': trade_info['client_order_id'],
                        # Ensure strings for DB
                        'price': str(trade_info['price']),
                        'origQty': str(trade_info['quantity']),
                        # Assume fully filled
                        'executedQty': str(trade_info['quantity']),
                        'status': 'FILLED',
                        'timeInForce': order.get('timeInForce', 'GTC'),
                        'type': order.get('type', 'LIMIT'),
                        'side': trade_info['side'],
                        'stopPrice': '0.0',  # N/A for basic limit
                        'icebergQty': '0.0',  # N/A
                        # Milliseconds
                        'time': int(fill_timestamp.timestamp() * 1000),
                        'updateTime': int(fill_timestamp.timestamp() * 1000),
                        'isWorking': False,
                        'commission': str(trade_info['fee']),
                        'commissionAsset': trade_info['fee_asset'],
                        'isMaker': trade_info['is_maker'],
                        # Add any other fields expected by log_trade, potentially nullable
                        'avgFillPrice': str(trade_info['price']),
                        'cumulativeQuoteQty': str(trade_info['price'] * trade_info['quantity']),
                        'source': trade_info['source'],  # 'backtest'
                        'backtest_id': trade_info['backtest_id'],
                        'confidence_score': None  # Placeholder, add later
                    }
                    self.db_manager.log_trade(trade_data_for_db)
                    logger.debug(
                        f"Logged trade {trade_info['order_id']} to database.")
                except Exception as e:
                    logger.error(
                        f"Failed to log trade {trade_info['order_id']} to database: {e}")

        except (TypeError, InvalidOperation) as calc_e:
            logger.error(
                f"[{fill_timestamp}] Decimal calculation error during order fill simulation: {calc_e}")
            # Consider how to handle this - potentially revert state or stop backtest?

    def _check_order_fills(self):
        """Checks open orders against the current bar's High/Low prices."""
        low_price = self._current_price_info.get('Low')  # Should be Decimal
        high_price = self._current_price_info.get('High')  # Should be Decimal
        timestamp = self._current_timestamp

        if low_price is None or high_price is None:
            logger.warning(
                f"[{timestamp}] Missing Low/High price for bar. Skipping fill checks.")
            return

        # Check BUY orders (fill if order price >= low_price)
        filled_buy_indices = []
        for i, buy_order in enumerate(self.open_buy_orders):
            order_price = buy_order.get('price')  # Should be Decimal
            if order_price is None:
                continue  # Skip invalid orders
            if order_price >= low_price:
                # Simplistic fill assumption: fills at order price if touched/passed
                fill_price = order_price
                self._simulate_order_fill(buy_order, fill_price, timestamp)
                filled_buy_indices.append(i)

        # Remove filled buy orders (iterate in reverse to avoid index issues)
        if filled_buy_indices:
            logger.debug(
                f"[{timestamp}] Filled BUY orders at indices: {filled_buy_indices}")
            for i in sorted(filled_buy_indices, reverse=True):
                del self.open_buy_orders[i]

        # Check SELL orders (fill if order price <= high_price)
        filled_sell_indices = []
        for i, sell_order in enumerate(self.open_sell_orders):
            order_price = sell_order.get('price')  # Should be Decimal
            if order_price is None:
                continue
            if order_price <= high_price:
                fill_price = order_price
                self._simulate_order_fill(sell_order, fill_price, timestamp)
                filled_sell_indices.append(i)

        # Remove filled sell orders
        if filled_sell_indices:
            logger.debug(
                f"[{timestamp}] Filled SELL orders at indices: {filled_sell_indices}")
            for i in sorted(filled_sell_indices, reverse=True):
                del self.open_sell_orders[i]

    def _calculate_performance_metrics(self):
        """Calculates performance metrics after the backtest."""
        if not self.portfolio_value_history:
            logger.warning(
                "No portfolio value history recorded. Cannot calculate metrics.")
            self.metrics = {'Error': 'No portfolio history'}
            return

        # Ensure values in history are suitable for DataFrame (e.g., float or Decimal)
        # We stored Decimals, let's convert to float for pandas/numpy calculations
        try:
            # Ensure values are numeric, converting None to NaN for pandas handling
            numeric_values = [
                float(v[1]) if isinstance(v[1], Decimal) else (
                    np.nan if v[1] is None else float(v[1]))
                for v in self.portfolio_value_history
            ]
            timestamps = [v[0] for v in self.portfolio_value_history]
        except Exception as e:
            logger.error(
                f"Error processing portfolio history values for metrics calculation: {e}")
            self.metrics = {'Error': 'Error processing portfolio history'}
            return

        equity_curve = pd.DataFrame(
            {'Value': numeric_values}, index=pd.Index(timestamps, name='Timestamp'))
        # Drop any rows that ended up NaN
        equity_curve.dropna(subset=['Value'], inplace=True)

        # or equity_curve['Value'].isnull().all(): # Check after dropna
        if equity_curve.empty:
            logger.error(
                "Equity curve is empty or contains only NaN values after processing.")
            self.metrics = {
                'Error': 'Invalid equity curve (empty after NaN drop)'}
            return

        # --- Basic Metrics ---
        final_value_float = equity_curve['Value'].iloc[-1]
        try:
            # Convert float final_value back to Decimal for calculation with initial_cash (Decimal)
            final_value_decimal = Decimal(str(final_value_float))
        except (InvalidOperation, ValueError) as e:
            logger.error(
                f"Could not convert final portfolio value {final_value_float} to Decimal: {e}")
            self.metrics = {'Error': 'Invalid final value'}
            return  # Exit metric calculation early

        # Now perform calculations using Decimals
        total_pnl = final_value_decimal - self.initial_cash
        if self.initial_cash == 0:
            total_return_pct = Decimal('0.0')  # Avoid division by zero
        else:
            # Ensure calculation uses Decimals only
            total_return_pct = (
                (final_value_decimal / self.initial_cash) - Decimal('1.0')) * Decimal('100.0')

        # --- Drawdown (using float values for efficiency with pandas/numpy) ---
        equity_curve['Peak'] = equity_curve['Value'].cummax()
        equity_curve['Drawdown'] = equity_curve['Peak'] - equity_curve['Value']
        # Handle potential division by zero if peak is 0 or NaN
        equity_curve['DrawdownPct'] = (
            equity_curve['Drawdown'] / equity_curve['Peak']).replace([np.inf, -np.inf, np.nan], 0) * 100
        max_drawdown_pct_float = equity_curve['DrawdownPct'].max()
        max_drawdown_abs_float = equity_curve['Drawdown'].max()

        # --- Returns Analysis (Requires Daily/Regular Returns) ---
        sharpe_ratio = np.nan
        sortino_ratio = np.nan
        try:
            # Use appropriate resampling frequency (e.g., 'D' for daily, 'H' for hourly if data allows)
            # Determine frequency dynamically or make it configurable? For now, assume daily.
            resample_freq = 'D'  # Default to daily, adjust if needed based on data interval
            # Ensure index is datetime before resampling
            if not pd.api.types.is_datetime64_any_dtype(equity_curve.index):
                equity_curve.index = pd.to_datetime(equity_curve.index)

            returns = equity_curve['Value'].resample(
                resample_freq).last().pct_change().dropna()
            periods_per_year = 365 if resample_freq == 'D' else (
                365*24 if resample_freq == 'h' else 1)  # Adjust factor

            if len(returns) < 2:
                logger.warning(
                    f"Insufficient return data points (<2) after resampling to '{resample_freq}' for Sharpe/Sortino.")
            else:
                returns = returns.replace(
                    [np.inf, -np.inf], 0).fillna(0)  # Clean returns
                # --- Sharpe Ratio --- (Rf=0 assumed)
                annualized_return = returns.mean() * periods_per_year
                annualized_volatility = returns.std() * np.sqrt(periods_per_year)
                sharpe_ratio = annualized_return / \
                    annualized_volatility if annualized_volatility != 0 and not np.isnan(
                        annualized_volatility) else np.nan

                # --- Sortino Ratio --- (Rf=0 assumed)
                negative_returns = returns[returns < 0]
                if negative_returns.empty:
                    downside_deviation = 0  # No negative returns, Sortino is undefined or infinite
                    sortino_ratio = np.inf if annualized_return > 0 else (
                        0 if annualized_return == 0 else np.nan)  # Avoid -inf
                else:
                    downside_std_dev = np.sqrt(np.mean(negative_returns**2))
                    downside_deviation = downside_std_dev * \
                        np.sqrt(periods_per_year)
                    sortino_ratio = annualized_return / \
                        downside_deviation if downside_deviation != 0 and not np.isnan(
                            downside_deviation) else np.nan

        except Exception as e:
            logger.error(f"Error during Sharpe/Sortino calculation: {e}")
            # Keep sharpe/sortino as np.nan

        # --- Trade Analysis ---
        buys = [t for t in self.filled_trades if t['side'] == 'BUY']
        sells = [t for t in self.filled_trades if t['side'] == 'SELL']
        total_trades = len(sells)  # Approx round trips

        # Store final metrics
        self.metrics = {
            'Backtest ID': self.backtest_id,
            'Symbol': self.symbol,
            'Initial Cash': f"{self.initial_cash:.2f} {self.quote_asset}",
            'Final Portfolio Value': f"{final_value_decimal:.2f} {self.quote_asset}",
            'Total PnL': f"{total_pnl:.2f} {self.quote_asset}",
            'Total Return (%)': f"{total_return_pct:.2f}%",
            'Max Drawdown (%)': f"{max_drawdown_pct_float:.2f}%",
            'Max Drawdown (Absolute)': f"{max_drawdown_abs_float:.2f} {self.quote_asset}",
            'Sharpe Ratio (Daily, Rf=0)': f"{sharpe_ratio:.3f}" if not np.isnan(sharpe_ratio) else "N/A",
            'Sortino Ratio (Daily, Rf=0)': f"{sortino_ratio:.3f}" if not np.isnan(sortino_ratio) else "N/A",
            'Total BUY Trades': len(buys),
            'Total SELL Trades (TP)': len(sells),
            'Total Closed Trades (estimate)': total_trades,
            # Add Win Rate & Profit Factor here once proper trade PnL is implemented
        }
        logger.info("--- Backtest Performance Metrics ---")
        for key, value in self.metrics.items():
            logger.info(f"{key}: {value}")

    def run(self):
        """Runs the backtest simulation loop."""
        logger.info(f"Starting backtest run for {self.symbol}...")
        start_time = time.time()

        # Ensure data is sorted by time
        self.historical_data.sort_index(inplace=True)

        # --- Main Simulation Loop ---
        for i in range(len(self.historical_data)):
            self._current_bar_index = i
            row = self.historical_data.iloc[i]
            self._current_timestamp = self.historical_data.index[i]

            # Extract current bar prices and ATR (ensure they are Decimal)
            try:
                self._current_price_info = {
                    'Open': to_decimal(row['Open']),
                    'High': to_decimal(row['High']),
                    'Low': to_decimal(row['Low']),
                    'Close': to_decimal(row['Close']),
                    self.atr_column_name: to_decimal(row[self.atr_column_name])
                }
                # Check if any conversion failed
                if None in self._current_price_info.values():
                    logger.warning(
                        f"[{self._current_timestamp}] Null value encountered in price/ATR data for row. Skipping bar logic. Data: {row.to_dict()}")
                    # Still update portfolio value (might use previous price)
                    self._update_portfolio_value()
                    continue  # Skip to next bar
            except Exception as e:
                logger.error(
                    f"[{self._current_timestamp}] Error processing data row: {e}. Row: {row.to_dict()}. Skipping bar logic.")
                self._update_portfolio_value()
                continue

            # --- Core Logic Steps ---
            # 1. Check for Order Fills based on current H/L prices
            self._check_order_fills()

            # 2. Update Portfolio Value based on current Close price
            self._update_portfolio_value()

            # 3. Plan New Grid Orders (only if no open BUY orders exist for simplicity in V1)
            if not self.open_buy_orders:
                current_atr = self._current_price_info.get(
                    self.atr_column_name)
                current_close = self._current_price_info.get('Close')
                if current_atr and current_close and current_atr > 0 and current_close > 0:
                    # Mock confidence score for adaptive sizing
                    # Later: Replace with actual confidence calculation
                    mock_confidence_multiplier = Decimal('1.0')

                    planned_buys = plan_buy_grid_v1(
                        symbol=self.symbol,
                        current_price=current_close,
                        # Pass current available cash (Decimal)
                        available_balance=self.cash,
                        atr=current_atr,
                        exchange_filters=self.exchange_filters,
                        strategy_config=self.strategy_config,
                        confidence_multiplier=mock_confidence_multiplier
                    )
                    if planned_buys:
                        logger.debug(
                            f"[{self._current_timestamp}] Planning new grid of {len(planned_buys)} orders.")
                        self.open_buy_orders.extend(planned_buys)
                else:
                    logger.warning(
                        f"[{self._current_timestamp}] Cannot plan grid: Missing or invalid ATR/Close price. ATR={current_atr}, Close={current_close}")

            # --- End of Bar ---
            # Log progress periodically and on last bar
            if (i + 1) % 100 == 0 or i == len(self.historical_data) - 1:
                logger.debug(
                    f"Processed bar {i+1}/{len(self.historical_data)} ({self._current_timestamp}) - Cash: {self.cash:.2f}, Base: {self.base_asset_balance:.8f}")

        # --- End of Simulation Loop ---
        end_time = time.time()
        logger.info(
            f"Backtest simulation loop finished in {end_time - start_time:.2f} seconds.")

        # Final portfolio valuation
        logger.info("Performing final portfolio valuation...")
        self._update_portfolio_value()  # Update with the last bar's close

        logger.info("Calculating performance metrics...")
        self._calculate_performance_metrics()

        logger.info("Backtest run complete.")

        # Prepare trades DataFrame, converting Decimals to strings for broader compatibility if needed
        trades_df = pd.DataFrame(
            self.filled_trades) if self.filled_trades else pd.DataFrame()
        if not trades_df.empty:
            # Example: convert price/qty/fee back to string if needed by downstream tools
            for col in ['price', 'quantity', 'fee']:
                if col in trades_df.columns:
                    # Ensure conversion handles potential non-Decimal types gracefully if they sneak in
                    trades_df[col] = trades_df[col].apply(
                        lambda d: str(d) if isinstance(d, Decimal) else d)

        # Return results
        return {
            "metrics": self.metrics,
            "equity_curve": pd.DataFrame(self.portfolio_value_history, columns=['Timestamp', 'Value']).set_index('Timestamp'),
            "trades": trades_df
        }


# --- Example Usage / Testing Block ---
if __name__ == '__main__':
    from pathlib import Path
    # Ensure these imports are available if running this block directly
    from src.utils.formatting import to_decimal
    from src.analysis.indicators import calculate_atr
    from config.settings import load_config  # Need config for testing block

    # Use the real setup_logging if available
    project_root = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    log_file_path = Path(project_root) / "data" / \
        "logs" / "test_backtester.log"
    try:
        # Make sure setup_logging is imported or defined if using this block
        setup_logging(log_file=log_file_path, console_logging=True,
                      log_level=logging.INFO)  # Use INFO for less noise
    except NameError:
        print("WARNING: Real setup_logging not found, using basic config.")
        logging.basicConfig(
            level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    except Exception as log_e:
        print(f"ERROR setting up logging: {log_e}. Using basic config.")
        logging.basicConfig(
            level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("--- Starting Backtester Test ---")

    # --- Load Mock Data (Replace with actual data loading) ---
    logger.info("Loading mock historical data...")
    mock_data = None
    try:
        # Attempt to load previously fetched data if available
        # Ensure path is correct relative to project root
        data_path = Path(project_root) / "data" / "cache" / \
            "BTCUSD_1h_Jan2024.csv"  # Example path
        if data_path.exists():
            logger.info(f"Attempting to load data from {data_path}...")
            temp_df = pd.read_csv(
                data_path, index_col='Timestamp', parse_dates=True)
            logger.info(f"Loaded {len(temp_df)} rows from CSV.")
            # Convert columns back to Decimal AFTER loading CSV
            # Recreate with correct index type
            mock_data = pd.DataFrame(index=temp_df.index)
            conversion_errors = 0
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                if col in temp_df.columns:
                    # Use our robust to_decimal converter
                    converted_col = temp_df[col].apply(
                        lambda x: to_decimal(x, default=None))
                    mock_data[col] = converted_col
                    errors_in_col = converted_col.isnull().sum()
                    if errors_in_col > 0:
                        logger.warning(
                            f"Found {errors_in_col} conversion errors in column '{col}'.")
                        conversion_errors += errors_in_col
                else:
                    logger.warning(f"Column '{col}' not found in CSV.")

            logger.info(
                f"Converted numerics to Decimal (Total conversion errors: {conversion_errors}).")
            # Drop rows where essential price data conversion failed
            initial_rows = len(mock_data)
            mock_data.dropna(
                subset=['Open', 'High', 'Low', 'Close'], inplace=True)
            dropped_rows = initial_rows - len(mock_data)
            if dropped_rows > 0:
                logger.warning(
                    f"Dropped {dropped_rows} rows due to NaN in price columns after conversion.")

            if mock_data.empty:
                logger.error(
                    "Data became empty after dropping rows with invalid price data.")
                mock_data = None  # Force creation of synthetic data
            else:
                logger.info(
                    f"Data has {len(mock_data)} valid rows after loading and cleaning.")
        else:
            logger.warning(
                f"Mock data file not found at {data_path}. Creating minimal sample.")
            # mock_data remains None

    except FileNotFoundError:
        logger.warning(
            f"File not found at {data_path}. Creating synthetic data...")
        mock_data = None
    except Exception as e:
        logger.exception(
            f"Could not load from file ({data_path}): {e}, creating synthetic data...")
        mock_data = None  # Ensure it's None before synthetic creation

    if mock_data is None:
        logger.info("Creating synthetic data...")
        # Pandas >= 2.2 warning for 'H', use 'h'
        freq = 'h'  # Use lowercase 'h' for hourly frequency
        periods = 100  # Number of bars for synthetic data
        dates = pd.date_range(start='2024-01-01 00:00',
                              periods=periods, freq=freq, tz='UTC')
        mock_data = pd.DataFrame(index=dates)
        # Create data directly as Decimal
        opens = [Decimal(str(42000 + i*10 + np.random.randn()*50)
                         ).quantize(Decimal('0.01')) for i in range(periods)]
        mock_data['Open'] = opens
        mock_data['High'] = [
            o + Decimal(str(abs(np.random.randn()*50))).quantize(Decimal('0.01')) for o in opens]
        mock_data['Low'] = [
            o - Decimal(str(abs(np.random.randn()*50))).quantize(Decimal('0.01')) for o in opens]
        mock_data['Close'] = [
            o + Decimal(str(np.random.randn()*20)).quantize(Decimal('0.01')) for o in opens]
        # Ensure High >= Open/Close and Low <= Open/Close
        mock_data['High'] = mock_data[['High', 'Open', 'Close']].max(axis=1)
        mock_data['Low'] = mock_data[['Low', 'Open', 'Close']].min(axis=1)
        mock_data['Volume'] = [Decimal(str(
            10 + abs(np.random.randn()*5))).quantize(Decimal('0.001')) for _ in range(periods)]
        logger.info(f"Synthetic data with {periods} bars created.")

    # --- Calculate ATR for mock data ---
    atr_len_test = 14  # Match strategy config or default
    mock_data = calculate_atr(mock_data, length=atr_len_test)
    atr_col_name_test = f'ATR_{atr_len_test}'
    if atr_col_name_test not in mock_data.columns or mock_data[atr_col_name_test].isnull().all():
        logger.error(
            "Failed to calculate ATR on mock data. Cannot run backtest.")
        sys.exit(1)
    # Drop initial rows where ATR is NaN
    initial_len = len(mock_data)
    mock_data.dropna(subset=[atr_col_name_test], inplace=True)
    logger.info(
        f"Prepared mock data with {len(mock_data)} bars after dropping {initial_len - len(mock_data)} NaN ATR rows.")
    if mock_data.empty:
        logger.error("Mock data is empty after dropping NaN ATR rows.")
        sys.exit(1)

    # --- Mock Configs ---
    # Load config to get parameters used by backtester (e.g., fees, could also get strategy params)
    app_config = load_config()
    if not app_config:
        logger.error(
            "Failed to load app configuration for backtest defaults. Exiting.")
        sys.exit(1)

    test_symbol_bt = 'BTCUSD'
    # Get strategy params from config OR use test defaults
    test_strategy_config_bt = app_config.get('strategies', {}).get('geometric_grid', {
        # Fallback defaults if not in config
        'base_order_size_usd': '100.00',
        'grid_spacing_atr_multiplier': '0.4',
        'grid_spacing_geometric_factor': '1.1',
        'order_size_geometric_factor': '1.2',
        'max_grid_levels': 5,
        'max_total_grid_quantity_base': '0.5',
        'atr_length': atr_len_test,
        'tp_method': 'percentage',
        'tp_value': '0.015'
    })
    # Ensure values are Decimal if loaded from config without conversion (though load_config should handle it)
    for k, v in test_strategy_config_bt.items():
        if isinstance(v, str) and k not in ['tp_method']:  # Example check
            test_strategy_config_bt[k] = to_decimal(v)

    # Use filters similar to previous tests - needed by backtester
    test_filters_bt = {
        'symbol': test_symbol_bt,
        'filters': [
            {'filterType': 'PRICE_FILTER', 'minPrice': '0.01',
                'maxPrice': '1000000.00', 'tickSize': '0.01'},
            {'filterType': 'LOT_SIZE', 'minQty': '0.00001',
             'maxQty': '100.0', 'stepSize': '0.00001'},
            {'filterType': 'MIN_NOTIONAL', 'minNotional': '10.0'}  # Simplified
        ]
    }
    # Get initial cash and fees from loaded config, with defaults
    initial_cash_bt = app_config.get('portfolio', {}).get(
        'initial_cash', Decimal('20000.00'))
    maker_fee = app_config.get('fees', {}).get('maker', Decimal('0.001'))
    taker_fee = app_config.get('fees', {}).get('taker', Decimal('0.001'))

    test_b_id = f"test_run_{int(time.time())}"

    # --- Optional: Initialize DBManager ---
    db_manager_instance = None  # Keep it simple for initial test

    # --- Initialize Backtester ---
    try:
        backtester = Backtester(
            symbol=test_symbol_bt,
            historical_data=mock_data,
            strategy_config=test_strategy_config_bt,
            exchange_filters=test_filters_bt,
            initial_cash=initial_cash_bt,
            maker_fee=maker_fee,
            taker_fee=taker_fee,
            db_manager=db_manager_instance,  # Pass instance or None
            backtest_id=test_b_id
        )
    except Exception as init_e:
        logger.exception(f"Failed to initialize Backtester: {init_e}")
        sys.exit(1)

    # --- Run Backtest ---
    logger.info("Running backtest simulation...")
    results = None
    try:
        results = backtester.run()
    except Exception as run_e:
        logger.exception(f"An error occurred during backtester.run(): {run_e}")

    # --- Display Results ---
    logger.info("\n--- Backtest Results Summary ---")
    if results and results.get("metrics"):
        logger.info("Metrics:")
        # Check for error metric first
        if 'Error' in results['metrics']:
            logger.error(
                f"Backtest ended with error: {results['metrics']['Error']}")
        else:
            # Use print for direct output in terminal test runs
            for k, v in results["metrics"].items():
                print(f"  {k}: {v}")

        # Check equity curve
        equity_curve_df = results.get("equity_curve")
        if equity_curve_df is not None and not equity_curve_df.empty:
            logger.info(f"\nEquity Curve has {len(equity_curve_df)} points.")
            # Optional: print head/tail or save to CSV for inspection
            # print(equity_curve_df.head().to_markdown(numalign="right", stralign="right"))
            equity_curve_path = Path(
                project_root) / "data" / "backtests" / f"{test_b_id}_equity.csv"
            equity_curve_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                equity_curve_df.to_csv(equity_curve_path)
                logger.info(f"Saved equity curve to {equity_curve_path}")
            except Exception as save_e:
                logger.error(f"Failed to save equity curve: {save_e}")

        else:
            logger.info("\nEquity Curve is empty or missing.")

        # Check trades log
        trades_df_res = results.get("trades")
        if trades_df_res is not None and not trades_df_res.empty:
            logger.info(f"\nTrades Log has {len(trades_df_res)} entries.")
            # Optional: print head/tail or save to CSV
            # print(trades_df_res.head().to_markdown(index=False, numalign="right", stralign="right"))
            trades_log_path = Path(project_root) / "data" / \
                "backtests" / f"{test_b_id}_trades.csv"
            trades_log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                trades_df_res.to_csv(trades_log_path, index=False)
                logger.info(f"Saved trades log to {trades_log_path}")
            except Exception as save_e:
                logger.error(f"Failed to save trades log: {save_e}")
        else:
            logger.info("\nTrades Log is empty or missing.")

        # Suggest plotting in Jupyter Notebook
        logger.info(
            "\nFor visualization, load results into 01_MVP_Backtest.ipynb")

    else:
        logger.error("Backtest did not return results or metrics.")

    logger.info("--- Backtester Test Complete ---")


# File path: src/backtester/engine.py
