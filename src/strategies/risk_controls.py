# START OF FILE: src/strategies/risk_controls.py

import logging
import pandas as pd
from decimal import Decimal
from typing import Optional, Dict, Any

# Project Modules (Ensure imports work if run standalone)
import sys
from pathlib import Path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
from src.utils.formatting import to_decimal # Use helper for safety

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
        current_klines (pd.DataFrame): DataFrame with recent kline data, including 'close'.
                                       Used to check current profitability.
        config (Dict[str, Any]): Main application configuration. Expects time stop settings
                                 under config['strategies']['risk_controls']['time_stop'].
        confidence_score (Optional[float]): The current confidence score.

    Returns:
        bool: True if the time stop condition is met and the position should be exited,
              False otherwise.
    """
    # === Pre-checks (remain the same) ===
    if not position or 'entry_time' not in position or 'entry_price' not in position:
        logger.debug("Time Stop Check: Invalid or incomplete position data provided.")
        return False

    # === FIX: Check for lowercase 'close' column ===
    if current_klines is None or current_klines.empty or 'close' not in current_klines.columns:
        logger.warning("Time Stop Check: Insufficient kline data ('close' column missing or empty DF) to check current price.")
        return False # Cannot determine profitability
    # ==============================================

    # --- Get Time Stop Settings (remain the same) ---
    rc_config = config.get('strategies', {}).get('risk_controls', {})
    ts_config = rc_config.get('time_stop', {})
    enabled = ts_config.get('enabled', True)
    duration_hours = ts_config.get('duration_hours', DEFAULT_TIME_STOP_HOURS)
    min_profit_pct = ts_config.get('min_profit_pct', 0.0)

    if not enabled:
        # logger.debug("Time Stop Check: Disabled in configuration.") # Can be verbose
        return False

    # --- Check Duration (remain the same, added safety with to_decimal) ---
    entry_time = position.get('entry_time')
    entry_price = to_decimal(position.get('entry_price')) # Ensure Decimal

    if entry_price is None:
        logger.warning("Time Stop Check: Invalid entry_price format.")
        return False

    if not isinstance(entry_time, pd.Timestamp):
        try:
            entry_time = pd.Timestamp(entry_time)
            if entry_time.tzinfo is None:
                entry_time = entry_time.tz_localize('UTC') # Assume UTC if naive
        except Exception as e:
            logger.warning(f"Time Stop Check: Invalid entry_time format '{position.get('entry_time')}': {e}")
            return False

    now_utc = pd.Timestamp.utcnow()
    # Ensure entry_time is timezone-aware for comparison
    if entry_time.tzinfo is None:
         entry_time = entry_time.tz_localize('UTC') # Default to UTC

    duration_open = now_utc - entry_time
    max_duration = pd.Timedelta(hours=duration_hours)

    if duration_open <= max_duration:
        # logger.debug(f"Time Stop Check: Position duration {duration_open} <= max {max_duration}. No exit.")
        return False

    logger.info(f"Time Stop Check: Position duration {duration_open} exceeds max {max_duration}. Evaluating exit conditions...")

    # --- Check Profitability (remain the same, added safety with to_decimal) ---
    try:
        # === FIX: Use lowercase 'close' column ===
        current_price_raw = current_klines['close'].iloc[-1]
        # ========================================
        current_price = to_decimal(current_price_raw) # Ensure decimal

        if current_price is None:
             logger.warning("Time Stop Check: Current price value is invalid.")
             return False # Cannot determine profitability

        # Ensure entry_price is not zero before calculating PnL %
        if entry_price <= Decimal('0'):
            logger.warning(f"Time Stop Check: Cannot calculate PnL% with non-positive entry price ({entry_price}).")
            # Decide behavior: maybe exit if duration exceeded and entry price is invalid?
            # For now, let's return False to avoid unintended exits based only on duration.
            return False

        current_pnl_pct = (current_price - entry_price) / entry_price
        profit_threshold = to_decimal(str(min_profit_pct)) # Ensure decimal

        logger.debug(f"Time Stop Check: Current Price={current_price:.4f}, Entry Price={entry_price:.4f}, PnL={current_pnl_pct:.4%}, Min Profit Threshold={profit_threshold:.4%}")

        if current_pnl_pct >= profit_threshold:
            logger.info(f"Time Stop Check: Position duration exceeded, but profit ({current_pnl_pct:.4%}) >= threshold ({profit_threshold:.4%}). No exit.")
            return False # Profitable enough, let it run

    except IndexError:
         logger.warning("Time Stop Check: Kline DataFrame is empty when trying to access last row.")
         return False # Cannot determine profitability
    except (InvalidOperation, TypeError, ZeroDivisionError) as e:
         logger.warning(f"Time Stop Check: Error calculating PnL: {e}")
         return False # Cannot determine profitability, don't exit based on time alone
    except Exception as e: # Catch any other unexpected error
         logger.error(f"Time Stop Check: Unexpected error during PnL check: {e}", exc_info=True)
         return False # Safer not to exit

    # --- (Optional) Check Confidence Drop (remains the same) ---
    # TODO: Implement this check later

    # --- Trigger Exit (remain the same) ---
    logger.warning(f"Time Stop EXIT Triggered: Duration {duration_open} > {max_duration} AND PnL ({current_pnl_pct:.4%}) < threshold ({profit_threshold:.4%}).")
    return True


# --- Example Usage (remains the same, but uses 'close' internally now) ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Time Stop Logic ---")

    mock_now = pd.Timestamp.utcnow()
    mock_config = {
        'strategies': {
            'risk_controls': {
                'time_stop': {
                    'enabled': True,
                    'duration_hours': 24,
                    'min_profit_pct': 0.005
                }
            }
        }
    }
    mock_klines = pd.DataFrame({
        'close': [Decimal('99'), Decimal('100'), Decimal('101'), Decimal('100.2')] # Use lowercase 'close'
    }, index=pd.to_datetime(['2023-01-10 10:00', '2023-01-10 11:00', '2023-01-10 12:00', '2023-01-10 13:00'], utc=True))

    # Test Cases (logic remains the same, just verifies against 'close' column)
    pos1 = {'entry_time': mock_now - pd.Timedelta(hours=12), 'entry_price': Decimal('100.0')}
    exit1 = check_time_stop({'entry_time': mock_now - pd.Timedelta(hours=12), 'entry_price': Decimal('100.0')}, mock_klines, mock_config)
    logger.info(f"Test 1 (Not Long Enough): Exit? {exit1}")

    exit2 = check_time_stop({'entry_time': mock_now - pd.Timedelta(hours=36), 'entry_price': Decimal('99.0')}, mock_klines, mock_config)
    logger.info(f"Test 2 (Long Enough, Profitable): Exit? {exit2}")

    exit3 = check_time_stop({'entry_time': mock_now - pd.Timedelta(hours=36), 'entry_price': Decimal('100.0')}, mock_klines, mock_config)
    logger.info(f"Test 3 (Long Enough, Stagnant): Exit? {exit3}")

    exit4 = check_time_stop({'entry_time': mock_now - pd.Timedelta(hours=36), 'entry_price': Decimal('101.0')}, mock_klines, mock_config)
    logger.info(f"Test 4 (Long Enough, Losing): Exit? {exit4}")

    mock_config['strategies']['risk_controls']['time_stop']['enabled'] = False
    exit5 = check_time_stop({'entry_time': mock_now - pd.Timedelta(hours=36), 'entry_price': Decimal('101.0')}, mock_klines, mock_config)
    logger.info(f"Test 5 (Disabled): Exit? {exit5}")
    mock_config['strategies']['risk_controls']['time_stop']['enabled'] = True

    exit6 = check_time_stop({}, mock_klines, mock_config)
    logger.info(f"Test 6 (Invalid Position): Exit? {exit6}")

    # Test 7: Missing 'close' column
    mock_klines_no_close = mock_klines.drop(columns=['close'])
    exit7 = check_time_stop({'entry_time': mock_now - pd.Timedelta(hours=36), 'entry_price': Decimal('101.0')}, mock_klines_no_close, mock_config)
    logger.info(f"Test 7 (Missing 'close' column): Exit? {exit7}") # Should be False, log warning

    logger.info("\n--- Time Stop Logic Test Complete ---")


# END OF FILE: src/strategies/risk_controls.py