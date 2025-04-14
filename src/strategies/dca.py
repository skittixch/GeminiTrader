# src/strategies/dca.py

import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

# --- Add project root to sys.path FIRST (for testing block) ---
import os
import sys
from pathlib import Path # Import Path
_project_root_for_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if str(_project_root_for_path) not in sys.path:
    sys.path.insert(0, str(_project_root_for_path))
# --- End sys.path modification ---

# --- Project Imports ---
try:
    from src.utils.formatting import to_decimal
    from src.utils.logging_setup import setup_logging # For test block
    from config.settings import load_config # For test block
except ImportError as e:
    print(f"ERROR: Could not import project modules. Error: {e}")
    # Define dummies only if absolutely necessary for basic script structure
    def to_decimal(v, default=None): return Decimal(v) if v is not None else default
    # raise ImportError("Failed to import required project modules.") from e

# --- End Project Imports ---

logger = logging.getLogger(__name__)

def calculate_dca_amount_v1(
    dca_config: Dict,
    confidence_score: Optional[Decimal] = None # Placeholder for V2 modulation
) -> Optional[Decimal]:
    """
    Calculates the DCA amount based on configuration (V1 - fixed amount).

    Args:
        dca_config (Dict): The 'dca' section of the application config.
                           Expected keys: 'base_amount_usd'.
        confidence_score (Optional[Decimal]): Placeholder for future use where
                                               confidence might modulate the amount. Ignored in V1.

    Returns:
        Optional[Decimal]: The calculated DCA amount in quote currency (e.g., USD),
                           or None if configuration is invalid.
    """
    if not dca_config:
        logger.error("DCA configuration is missing.")
        return None

    base_amount_str = dca_config.get('base_amount_usd')
    if base_amount_str is None:
        logger.error("Missing 'base_amount_usd' key in DCA configuration.")
        return None

    base_amount = to_decimal(base_amount_str)
    if base_amount is None or base_amount <= 0:
        logger.error(f"Invalid 'base_amount_usd' value in DCA config: {base_amount_str}")
        return None

    # --- V1 Logic: Return fixed base amount ---
    calculated_amount = base_amount
    logger.info(f"DCA V1 calculation: Using fixed base amount = {calculated_amount:.2f} USD")

    # --- V2 Placeholder ---
    # if confidence_score is not None:
    #     # Example: Modulate amount based on confidence
    #     # Ensure confidence_score is valid (e.g., 0 to 2)
    #     # multiplier = calculate_dca_multiplier(confidence_score) # Define this helper
    #     # calculated_amount = base_amount * multiplier
    #     # logger.info(f"DCA V2: Modulated amount by confidence {confidence_score} -> {calculated_amount:.2f} USD")
    #     pass # Implement in Phase 4+

    if calculated_amount <= 0:
         logger.warning(f"Calculated DCA amount is zero or negative ({calculated_amount}). Returning None.")
         return None

    return calculated_amount


# --- Example Usage / Testing Block ---
if __name__ == '__main__':
    # Setup basic logging for testing
    project_root = Path(_project_root_for_path) # Use path calculated above
    log_file_path = project_root / "data" / "logs" / "test_dca.log"
    try:
        setup_logging(log_file=log_file_path, console_logging=True, log_level=logging.DEBUG)
    except NameError:
        print("WARNING: setup_logging not defined. Using basicConfig.")
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    except Exception as log_e:
         print(f"ERROR setting up logging: {log_e}. Using basicConfig.")
         logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


    logger.info("--- Starting DCA Calculation Test ---")

    # --- Mock Config ---
    # Option 1: Load from file
    config_for_test = load_config()
    mock_dca_config = config_for_test.get('strategies', {}).get('dca', {})

    # Option 2: Define directly for isolated test
    if not mock_dca_config:
        logger.warning("DCA config not found in file, using direct mock.")
        mock_dca_config = {
            'target_asset': 'BTCUSD',
            'base_amount_usd': '25.50', # String value like in YAML
            'schedule': 'bi-weekly'
        }

    logger.info(f"Using Mock DCA Config: {mock_dca_config}")

    # --- Test Cases ---
    logger.info("\n--- Test 1: Valid Config ---")
    amount1 = calculate_dca_amount_v1(mock_dca_config)
    logger.info(f"Result 1: {amount1}")
    if amount1: print(f"Test 1 Amount: {amount1:.2f}")

    logger.info("\n--- Test 2: Missing Amount Key ---")
    invalid_config_1 = {'target_asset': 'ETHUSD'}
    amount2 = calculate_dca_amount_v1(invalid_config_1)
    logger.info(f"Result 2: {amount2}")
    if amount2 is None: print("Test 2 Result: None (Correct)")

    logger.info("\n--- Test 3: Invalid Amount Value (Zero) ---")
    invalid_config_2 = {'base_amount_usd': '0'}
    amount3 = calculate_dca_amount_v1(invalid_config_2)
    logger.info(f"Result 3: {amount3}")
    if amount3 is None: print("Test 3 Result: None (Correct)")

    logger.info("\n--- Test 4: Invalid Amount Value (Negative) ---")
    invalid_config_3 = {'base_amount_usd': '-10.00'}
    amount4 = calculate_dca_amount_v1(invalid_config_3)
    logger.info(f"Result 4: {amount4}")
    if amount4 is None: print("Test 4 Result: None (Correct)")

    logger.info("\n--- Test 5: Empty Config ---")
    amount5 = calculate_dca_amount_v1({})
    logger.info(f"Result 5: {amount5}")
    if amount5 is None: print("Test 5 Result: None (Correct)")

    logger.info("\n--- Test 6: With Confidence Score (V1 - should be ignored) ---")
    amount6 = calculate_dca_amount_v1(mock_dca_config, confidence_score=Decimal('1.5'))
    logger.info(f"Result 6: {amount6}")
    if amount6: print(f"Test 6 Amount: {amount6:.2f}")


    logger.info("\n--- DCA Calculation Test Complete ---")


# File path: src/strategies/dca.py
