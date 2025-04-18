# START OF FILE: src/strategies/risk_controls.py (Using Correct Sim Time)

from src.utils.formatting import to_decimal  # Use helper for safety
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

logger = logging.getLogger(__name__)

# --- Constants ---
DEFAULT_TIME_STOP_HOURS = 7 * 24  # Default: Exit after 1 week if stagnant/losing

# <<< MODIFIED: Added current_time parameter >>>


def check_time_stop(
    position: Dict[str, Any],
    current_klines: pd.DataFrame,  # Need recent price data
    config: Dict[str, Any],
    current_time: pd.Timestamp,  # <<< ADDED: Pass the current simulation timestamp
    # Optional: Use confidence drop as part of trigger
    confidence_score: Optional[float] = None
) -> bool:
    # <<< END MODIFICATION >>>
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
        current_time (pd.Timestamp): The current timestamp (from simulation or real-time). <<< ADDED DOC >>>
        confidence_score (Optional[float]): The current confidence score.

    Returns:
        bool: True if the time stop condition is met and the position should be exited,
              False otherwise.
    """
    # === Pre-checks ===
    if not position or 'entry_time' not in position or 'entry_price' not in position:
        logger.debug(
            "Time Stop Check: Invalid or incomplete position data provided.")
        return False

    if current_klines is None or current_klines.empty or 'close' not in current_klines.columns:
        logger.warning(
            "Time Stop Check: Insufficient kline data ('close' column missing or empty DF) to check current price.")
        return False  # Cannot determine profitability

    # <<< MODIFIED: Check current_time input >>>
    if not isinstance(current_time, pd.Timestamp):
        logger.error(
            f"Time Stop Check: Invalid current_time provided (Type: {type(current_time)}). Cannot calculate duration.")
        return False
    # Ensure current_time is timezone-aware (should be from main_trader state)
    if current_time.tzinfo is None:
        logger.warning(
            "Time Stop Check: current_time is timezone naive. Assuming UTC.")
        current_time = current_time.tz_localize('UTC')
    # <<< END MODIFICATION >>>

    # --- Get Time Stop Settings ---
    # <<< MODIFIED: Adjusted path based on updated config.yaml example >>>
    rc_config = config.get('risk_controls', {})  # Direct access from root
    # ts_config = rc_config.get('time_stop', {}) # Removed intermediate strategies level
    # <<< END MODIFICATION >>>
    ts_config = rc_config.get('time_stop', {})  # Use direct rc_config
    enabled = ts_config.get('enabled', True)
    duration_hours = ts_config.get('duration_hours', DEFAULT_TIME_STOP_HOURS)
    min_profit_pct = ts_config.get('min_profit_pct', 0.0)

    if not enabled:
        # logger.debug("Time Stop Check: Disabled in configuration.") # Can be verbose
        return False

    # --- Check Duration ---
    entry_time = position.get('entry_time')
    entry_price = to_decimal(position.get('entry_price'))  # Ensure Decimal

    if entry_price is None:
        logger.warning("Time Stop Check: Invalid entry_price format.")
        return False

    if not isinstance(entry_time, pd.Timestamp):
        try:
            entry_time = pd.Timestamp(entry_time)
            if entry_time.tzinfo is None:
                entry_time = entry_time.tz_localize(
                    'UTC')  # Assume UTC if naive
        except Exception as e:
            logger.warning(
                f"Time Stop Check: Invalid entry_time format '{position.get('entry_time')}': {e}")
            return False

    # <<< MODIFIED: Use passed current_time >>>
    # Ensure entry_time is timezone-aware for comparison (already done above)
    # Ensure current_time is timezone-aware (done in pre-check)
    if entry_time.tzinfo != current_time.tzinfo:
        logger.warning(
            f"Time Stop Check: Timezone mismatch between entry_time ({entry_time.tzinfo}) and current_time ({current_time.tzinfo}). Aligning...")
        try:
            # Defaulting to converting entry_time to current_time's zone (usually UTC)
            entry_time = entry_time.tz_convert(current_time.tzinfo)
        except Exception as tz_err:
            logger.error(
                f"Time Stop Check: Failed to align timezones: {tz_err}. Cannot calculate duration.")
            return False

    duration_open = current_time - entry_time
    # <<< END MODIFICATION >>>

    max_duration = pd.Timedelta(hours=duration_hours)

    if duration_open <= max_duration:
        # logger.debug(f"Time Stop Check: Position duration {duration_open} <= max {max_duration}. No exit.")
        return False

    logger.info(
        f"Time Stop Check: Position duration {duration_open} exceeds max {max_duration}. Evaluating exit conditions...")

    # --- Check Profitability ---
    try:
        current_price_raw = current_klines['close'].iloc[-1]
        current_price = to_decimal(current_price_raw)  # Ensure decimal

        if current_price is None:
            logger.warning("Time Stop Check: Current price value is invalid.")
            return False  # Cannot determine profitability

        if entry_price <= Decimal('0'):
            logger.warning(
                f"Time Stop Check: Cannot calculate PnL% with non-positive entry price ({entry_price}).")
            return False

        current_pnl_pct = (current_price - entry_price) / entry_price
        profit_threshold = to_decimal(str(min_profit_pct))  # Ensure decimal

        logger.debug(
            f"Time Stop Check: Current Price={current_price:.4f}, Entry Price={entry_price:.4f}, PnL={current_pnl_pct:.4%}, Min Profit Threshold={profit_threshold:.4%}")

        if current_pnl_pct >= profit_threshold:
            logger.info(
                f"Time Stop Check: Position duration exceeded, but profit ({current_pnl_pct:.4%}) >= threshold ({profit_threshold:.4%}). No exit.")
            return False  # Profitable enough, let it run

    except IndexError:
        logger.warning(
            "Time Stop Check: Kline DataFrame is empty when trying to access last row.")
        return False  # Cannot determine profitability
    except (InvalidOperation, TypeError, ZeroDivisionError) as e:
        logger.warning(f"Time Stop Check: Error calculating PnL: {e}")
        return False  # Cannot determine profitability, don't exit based on time alone
    except Exception as e:  # Catch any other unexpected error
        logger.error(
            f"Time Stop Check: Unexpected error during PnL check: {e}", exc_info=True)
        return False  # Safer not to exit

    # --- (Optional) Check Confidence Drop ---
    # TODO: Implement this check later

    # --- Trigger Exit ---
    # Use the calculated duration_open which now uses correct current_time
    logger.warning(
        f"Time Stop EXIT Triggered: Duration {duration_open} > {max_duration} AND PnL ({current_pnl_pct:.4%}) < threshold ({profit_threshold:.4%}).")
    return True


# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("--- Testing Time Stop Logic ---")

    # Use a fixed time for 'now' in the test for predictability
    mock_current_time_test = pd.Timestamp('2024-03-15 12:00:00', tz='UTC')

    mock_config_test = {
        'risk_controls': {  # Adjusted path
            'time_stop': {
                'enabled': True,
                'duration_hours': 24,
                'min_profit_pct': 0.005  # 0.5%
            }
        }
    }
    mock_klines_test = pd.DataFrame({
        'close': [Decimal('99'), Decimal('100'), Decimal('101'), Decimal('100.2')]
    }, index=pd.to_datetime(['2024-03-15 09:00', '2024-03-15 10:00', '2024-03-15 11:00', '2024-03-15 12:00'], utc=True))

    # Test Cases using mock_current_time_test
    entry_time_1 = mock_current_time_test - pd.Timedelta(hours=12)  # 12h < 24h
    exit1 = check_time_stop({'entry_time': entry_time_1, 'entry_price': Decimal(
        '100.0')}, mock_klines_test, mock_config_test, mock_current_time_test)
    logger.info(
        f"Test 1 (Not Long Enough): Duration={mock_current_time_test-entry_time_1}, Exit? {exit1}")

    entry_time_2 = mock_current_time_test - pd.Timedelta(hours=36)  # 36h > 24h
    # Profitable: 100.2 vs 99.0 -> PnL = 1.2 / 99 = ~1.2% > 0.5%
    exit2 = check_time_stop({'entry_time': entry_time_2, 'entry_price': Decimal(
        '99.0')}, mock_klines_test, mock_config_test, mock_current_time_test)
    logger.info(
        f"Test 2 (Long Enough, Profitable): Duration={mock_current_time_test-entry_time_2}, Exit? {exit2}")

    # Stagnant: 100.2 vs 100.0 -> PnL = 0.2 / 100 = 0.2% < 0.5% -> EXIT
    exit3 = check_time_stop({'entry_time': entry_time_2, 'entry_price': Decimal(
        '100.0')}, mock_klines_test, mock_config_test, mock_current_time_test)
    logger.info(
        f"Test 3 (Long Enough, Stagnant): Duration={mock_current_time_test-entry_time_2}, Exit? {exit3}")

    # Losing: 100.2 vs 101.0 -> PnL = -0.8 / 101 = ~-0.8% < 0.5% -> EXIT
    exit4 = check_time_stop({'entry_time': entry_time_2, 'entry_price': Decimal(
        '101.0')}, mock_klines_test, mock_config_test, mock_current_time_test)
    logger.info(
        f"Test 4 (Long Enough, Losing): Duration={mock_current_time_test-entry_time_2}, Exit? {exit4}")

    # Test Disabled
    mock_config_test['risk_controls']['time_stop']['enabled'] = False
    exit5 = check_time_stop({'entry_time': entry_time_2, 'entry_price': Decimal(
        '101.0')}, mock_klines_test, mock_config_test, mock_current_time_test)
    logger.info(
        f"Test 5 (Disabled): Duration={mock_current_time_test-entry_time_2}, Exit? {exit5}")
    # Reset for other tests
    mock_config_test['risk_controls']['time_stop']['enabled'] = True

    # Test Invalid Position
    exit6 = check_time_stop({}, mock_klines_test,
                            mock_config_test, mock_current_time_test)
    logger.info(f"Test 6 (Invalid Position): Exit? {exit6}")

    # Test Missing 'close' column
    mock_klines_no_close_test = mock_klines_test.drop(columns=['close'])
    exit7 = check_time_stop({'entry_time': entry_time_2, 'entry_price': Decimal(
        '101.0')}, mock_klines_no_close_test, mock_config_test, mock_current_time_test)
    logger.info(
        f"Test 7 (Missing 'close' column): Duration={mock_current_time_test-entry_time_2}, Exit? {exit7}")

    # Test Missing current_time
    exit8 = check_time_stop({'entry_time': entry_time_2, 'entry_price': Decimal(
        '101.0')}, mock_klines_test, mock_config_test, None)  # type: ignore
    logger.info(f"Test 8 (Missing current_time): Exit? {exit8}")

    logger.info("\n--- Time Stop Logic Test Complete ---")


# END OF FILE: src/strategies/risk_controls.py
