# START OF FILE: src/strategies/risk_controls.py

import logging
import pandas as pd
from decimal import Decimal
from typing import Optional, Dict, Any

# --- Add project root ---
# import os, sys, pathlib ... (if needed for standalone testing)

logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_TIME_STOP_HOURS = 7 * 24 # Default: Exit after 1 week if stagnant/losing

def check_time_stop(
    position: Dict[str, Any],
    current_klines: pd.DataFrame, # Need recent price data
    config: Dict[str, Any],
    confidence_score: Optional[float] = None # Optional: Use confidence drop as part of trigger
    ) -> bool:
    """
    Checks if an open position should be closed based on a time stop rule.

    The rule triggers if:
    1. The position has been open longer than a configured duration.
    AND
    2. The position is currently unprofitable (or hasn't hit a certain profit threshold).
    AND (Optional)
    3. The confidence score has significantly dropped since entry (if implemented).

    Args:
        position (Dict[str, Any]): The dictionary representing the open position.
                                   Expected keys: 'entry_time' (Timestamp),
                                                  'entry_price' (Decimal).
        current_klines (pd.DataFrame): DataFrame with recent kline data, including 'Close'.
                                       Used to check current profitability.
        config (Dict[str, Any]): Main application configuration. Expects time stop settings
                                 under config['strategies']['risk_controls']['time_stop'].
        confidence_score (Optional[float]): The current confidence score.

    Returns:
        bool: True if the time stop condition is met and the position should be exited,
              False otherwise.
    """
    if not position or 'entry_time' not in position or 'entry_price' not in position:
        logger.debug("Time Stop Check: Invalid or incomplete position data provided.")
        return False

    if current_klines is None or current_klines.empty or 'Close' not in current_klines.columns:
        logger.warning("Time Stop Check: Insufficient kline data to check current price.")
        return False # Cannot determine profitability

    # --- Get Time Stop Settings ---
    # Use risk_controls section, add time_stop subsection
    rc_config = config.get('strategies', {}).get('risk_controls', {})
    ts_config = rc_config.get('time_stop', {})
    enabled = ts_config.get('enabled', True) # Default to enabled
    duration_hours = ts_config.get('duration_hours', DEFAULT_TIME_STOP_HOURS)
    # Optional: Profit threshold - only exit if below this % profit
    min_profit_pct = ts_config.get('min_profit_pct', 0.0) # Default: exit even if slightly profitable

    if not enabled:
        logger.debug("Time Stop Check: Disabled in configuration.")
        return False

    # --- Check Duration ---
    entry_time = position.get('entry_time')
    entry_price = position.get('entry_price')
    if not isinstance(entry_time, pd.Timestamp):
        # Attempt conversion if it's a string/datetime object
        try: entry_time = pd.Timestamp(entry_time, tz='UTC') # Assume UTC
        except Exception: logger.warning("Time Stop Check: Invalid entry_time format."); return False
    if not isinstance(entry_price, Decimal):
        logger.warning("Time Stop Check: Invalid entry_price format."); return False


    now_utc = pd.Timestamp.utcnow()
    duration_open = now_utc - entry_time
    max_duration = pd.Timedelta(hours=duration_hours)

    if duration_open <= max_duration:
        # logger.debug(f"Time Stop Check: Position duration {duration_open} <= max {max_duration}. No exit.")
        return False # Not open long enough

    logger.info(f"Time Stop Check: Position duration {duration_open} exceeds max {max_duration}. Evaluating exit conditions...")

    # --- Check Profitability ---
    try:
        current_price = current_klines['Close'].iloc[-1]
        if not isinstance(current_price, Decimal): current_price = Decimal(str(current_price)) # Ensure decimal

        current_pnl_pct = (current_price - entry_price) / entry_price
        profit_threshold = Decimal(str(min_profit_pct))

        logger.debug(f"Time Stop Check: Current PnL: {current_pnl_pct:.4%}, Min Profit Threshold: {profit_threshold:.4%}")

        if current_pnl_pct >= profit_threshold:
            logger.info(f"Time Stop Check: Position duration exceeded, but profit ({current_pnl_pct:.4%}) >= threshold ({profit_threshold:.4%}). No exit.")
            return False # Profitable enough, let it run

    except Exception as e:
         logger.warning(f"Time Stop Check: Error calculating PnL: {e}")
         return False # Cannot determine profitability, don't exit based on time alone

    # --- (Optional) Check Confidence Drop ---
    # TODO: Implement this check later when confidence score history is tracked
    # if confidence_score is not None and position.get('entry_confidence') is not None:
    #     confidence_drop_threshold = ts_config.get('confidence_drop_threshold', 0.3) # e.g., exit if conf drops by 30%
    #     if (position['entry_confidence'] - confidence_score) >= confidence_drop_threshold:
    #         logger.info(f"Time Stop EXIT Triggered: Duration exceeded, unprofitable/stagnant, AND confidence dropped significantly.")
    #         return True

    # --- Trigger Exit ---
    # If we reach here, duration exceeded AND position is unprofitable/stagnant
    logger.warning(f"Time Stop EXIT Triggered: Duration {duration_open} > {max_duration} AND PnL ({current_pnl_pct:.4%}) < threshold ({profit_threshold:.4%}).")
    return True


# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Time Stop Logic ---")

    # Mock Data
    mock_now = pd.Timestamp.utcnow()
    mock_config = {
        'strategies': {
            'risk_controls': {
                'time_stop': {
                    'enabled': True,
                    'duration_hours': 24, # Exit after 1 day if losing
                    'min_profit_pct': 0.005 # Only exit if profit < 0.5%
                }
            }
        }
    }
    mock_klines = pd.DataFrame({
        'Close': [Decimal('99'), Decimal('100'), Decimal('101'), Decimal('100.2')] # Last close is 100.2
    }, index=pd.to_datetime(['2023-01-10 10:00', '2023-01-10 11:00', '2023-01-10 12:00', '2023-01-10 13:00'], utc=True))

    # Test Cases
    # 1. Not open long enough
    pos1 = {'entry_time': mock_now - pd.Timedelta(hours=12), 'entry_price': Decimal('100.0')}
    exit1 = check_time_stop(pos1, mock_klines, mock_config)
    logger.info(f"Test 1 (Not Long Enough): Exit? {exit1}")

    # 2. Open long enough, profitable enough
    pos2 = {'entry_time': mock_now - pd.Timedelta(hours=36), 'entry_price': Decimal('99.0')} # Entered at 99, current 100.2 -> Profit > 0.5%
    exit2 = check_time_stop(pos2, mock_klines, mock_config)
    logger.info(f"Test 2 (Long Enough, Profitable): Exit? {exit2}")

    # 3. Open long enough, unprofitable/stagnant (below min profit threshold)
    pos3 = {'entry_time': mock_now - pd.Timedelta(hours=36), 'entry_price': Decimal('100.0')} # Entered at 100, current 100.2 -> Profit = 0.2% < 0.5%
    exit3 = check_time_stop(pos3, mock_klines, mock_config)
    logger.info(f"Test 3 (Long Enough, Stagnant): Exit? {exit3}")

    # 4. Open long enough, losing
    pos4 = {'entry_time': mock_now - pd.Timedelta(hours=36), 'entry_price': Decimal('101.0')} # Entered at 101, current 100.2 -> Losing
    exit4 = check_time_stop(pos4, mock_klines, mock_config)
    logger.info(f"Test 4 (Long Enough, Losing): Exit? {exit4}")

    # 5. Disabled
    mock_config['strategies']['risk_controls']['time_stop']['enabled'] = False
    pos5 = {'entry_time': mock_now - pd.Timedelta(hours=36), 'entry_price': Decimal('101.0')}
    exit5 = check_time_stop(pos5, mock_klines, mock_config)
    logger.info(f"Test 5 (Disabled): Exit? {exit5}")
    mock_config['strategies']['risk_controls']['time_stop']['enabled'] = True # Re-enable for next test

    # 6. Invalid position data
    exit6 = check_time_stop({}, mock_klines, mock_config)
    logger.info(f"Test 6 (Invalid Position): Exit? {exit6}")


    logger.info("\n--- Time Stop Logic Test Complete ---")

# END OF FILE: src/strategies/risk_controls.py
