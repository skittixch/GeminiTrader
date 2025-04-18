import logging
import json
import shutil
from pathlib import Path
from decimal import Decimal
from typing import Dict, Any, Optional, List  # Added List
import pandas as pd

try:
    from src.utils.formatting import to_decimal
except ImportError:
    def to_decimal(v, default=None):
        try:
            return Decimal(str(v)) if v is not None else default
        except:
            return default
    logging.warning("StateManager using fallback to_decimal converter.")

logger = logging.getLogger(__name__)


class StateManager:
    """Handles loading and saving the application state."""

    def __init__(self, filepath: str = "data/state/trader_state.json", backup_count: int = 3):
        self.filepath = Path(filepath)
        self.backup_count = backup_count
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"StateManager initialized. State file: {self.filepath}")

    def _default_serializer(self, obj):
        # --- Serializer remains unchanged ---
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, pd.Timestamp):
            # Ensure timezone info is included (ISO format does this)
            return obj.isoformat(timespec='microseconds')
        try:
            # Standard JSON encoder handles bool, str, int, float, list, dict, None
            return json.JSONEncoder().default(obj)
        except TypeError as e:
            logger.error(
                f"Serialization Error: Type {type(obj)} not serializable: {e}. Value: {repr(obj)[:100]}...")
            return f"<Unserializable: {type(obj).__name__}>"
        # --- End Serializer ---

    def save_state(self, state: Dict[str, Any]):
        # --- save_state remains unchanged - Cascade keys are serializable ---
        if not isinstance(state, dict):
            logger.error(
                "Invalid state type provided for saving. Expected dict.")
            return
        state_to_save = state.copy()
        # Ensure all non-serializable / large keys are listed
        keys_to_exclude = ['historical_klines',
                           'indicators', 'current_kline', 'sr_zones']
        removed_keys = []
        for key in keys_to_exclude:
            if key in state_to_save:
                del state_to_save[key]
                removed_keys.append(key)
        # Log excluded keys only once after loop
        if removed_keys:
            logger.debug(
                f"Excluded keys from saved state: {', '.join(removed_keys)}")

        # Add save timestamp AFTER filtering
        state_to_save['last_state_save_time'] = pd.Timestamp.utcnow()

        # Backup logic
        if self.filepath.exists():
            try:
                for i in range(self.backup_count, 0, -1):
                    src = self.filepath.with_suffix(
                        f".json.bak{i}" if i > 1 else ".json.bak")
                    dst = self.filepath.with_suffix(f".json.bak{i+1}")
                    if i == self.backup_count and dst.exists():
                        dst.unlink()
                    if src.exists():
                        shutil.move(str(src), str(dst))
                shutil.copy2(str(self.filepath), str(
                    self.filepath.with_suffix(".json.bak")))
                # Reduce log level for backups? Or remove?
                # logger.debug(f"State file backup created: {self.filepath.with_suffix('.json.bak')}")
            except Exception as e:
                # Log full traceback for backup errors
                logger.error(
                    f"Error creating state backup: {e}", exc_info=True)

        # Atomic save
        temp_filepath = self.filepath.with_suffix(".json.tmp")
        bytes_written = -1  # For logging size
        try:
            state_str = json.dumps(
                state_to_save, indent=4, default=self._default_serializer)
            bytes_written = len(state_str.encode('utf-8'))  # Calculate bytes
            with open(temp_filepath, 'w', encoding='utf-8') as f:  # Specify encoding
                f.write(state_str)
            shutil.move(str(temp_filepath), str(self.filepath))
            # Include size and excluded keys in the final log message for clarity
            excluded_str = f"(excluded: {', '.join(removed_keys)})" if removed_keys else ""
            logger.info(
                f"State successfully saved to {self.filepath} ({bytes_written} bytes) {excluded_str}")
        except TypeError as te:
            logger.error(
                f"Serialization Error saving filtered state: {te}. State keys attempted: {list(state_to_save.keys())}", exc_info=True)
            if temp_filepath.exists():
                temp_filepath.unlink()
        except Exception as e:
            logger.error(
                f"Error saving filtered state to {self.filepath}: {e}", exc_info=True)
            if temp_filepath.exists():
                temp_filepath.unlink()
        # --- End save_state ---

    # --- START OF _post_load_process (Handle Cascade Keys) ---
    def _post_load_process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Converts specific fields back to appropriate types after loading."""
        if not isinstance(state, dict):
            logger.warning(
                f"Cannot post-process non-dict state: {type(state)}")
            return {}  # Return empty dict if input invalid

        processed_state = {}  # Start with empty, add processed keys

        # Process known keys, applying defaults *if missing* from the loaded dict
        # This ensures the structure is consistent even if loading an older state file

        # Numeric fields - Default to Decimal('0') if missing or invalid
        # Includes ts_exit_trigger_price
        for key in ['position_size', 'position_entry_price', 'balance_quote', 'balance_base', 'ts_exit_trigger_price']:
            # Get value, might be None if key missing
            value_str = state.get(key)
            # Use appropriate default
            default_val = Decimal('0') if key != 'ts_exit_trigger_price' else None
            decimal_value = to_decimal(value_str, default_val)
            if decimal_value is None and default_val is not None:
                logger.error(
                    f"CRITICAL: Failed to convert state key '{key}' to Decimal even with default! Value: {value_str}. Using default.")
                decimal_value = default_val
            processed_state[key] = decimal_value

        # Timestamp fields - Default to None if missing or invalid
        # Include last_state_save_time and ts_exit_timer_start here
        for key in ['position_entry_timestamp', 'last_processed_timestamp', 'last_state_save_time', 'ts_exit_timer_start']:
            ts_value = state.get(key)
            processed_ts = None  # Default to None
            if ts_value is not None:
                try:
                    ts = pd.Timestamp(ts_value)
                    # Assume saved timestamps are UTC or ISO format with offset
                    if ts.tzinfo is None:
                        # This case might indicate an older state file or serialization issue
                        # Assume UTC if naive, but log a warning
                        logger.warning(
                            f"Loaded timestamp for '{key}' is timezone naive. Assuming UTC.")
                        ts = ts.tz_localize('UTC')
                    else:
                        # Convert to UTC if it's not already
                        ts = ts.tz_convert('UTC')
                    processed_ts = ts
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Could not convert state value for '{key}' ('{ts_value}') to Timestamp: {e}. Setting to None.")
                    # processed_ts remains None
            processed_state[key] = processed_ts

        # Boolean field - Default to False if missing or invalid
        # Use standard bool conversion which handles None, 0, "", False etc.
        processed_state['ts_exit_active'] = bool(state.get('ts_exit_active', False))

        # String fields (Optional) - Default to None if missing
        # Ensure they are strings or None
        for key in ['ts_exit_step', 'ts_exit_active_order_id']:
            value = state.get(key)
            if value is None or isinstance(value, str):
                 processed_state[key] = value
            else:
                 logger.warning(f"Loaded value for '{key}' is not a string or None (type: {type(value)}). Setting to None.")
                 processed_state[key] = None


        # List field - Default to empty list if missing or invalid
        # Default to [] if key missing
        grid_orders = state.get('active_grid_orders', [])
        processed_grid = []
        if isinstance(grid_orders, list):
            for order in grid_orders:
                if isinstance(order, dict):
                    proc_order = order.copy()
                    for k in ['price', 'origQty', 'executedQty', 'cummulativeQuoteQty']:
                        if k in proc_order and proc_order[k] is not None:
                            # Use default=None here, as we want to keep None if conversion fails
                            dec_val = to_decimal(proc_order[k], default=None)
                            if dec_val is not None:
                                proc_order[k] = dec_val
                            else:
                                logger.warning(
                                    f"Could not convert order field '{k}' to Decimal: {proc_order[k]}")
                    processed_grid.append(proc_order)
                else:
                    logger.warning(
                        f"Skipping non-dict item found in loaded active_grid_orders: {order}")
        else:
            logger.warning(
                f"Loaded 'active_grid_orders' is not a list (type: {type(grid_orders)}). Initializing to empty list.")
            # processed_grid remains []
        processed_state['active_grid_orders'] = processed_grid

        # Dict field (optional) - Default to None if missing or invalid
        # Get value, could be None or dict
        tp_order = state.get('active_tp_order')
        processed_tp_order = None  # Default to None
        if isinstance(tp_order, dict):
            proc_tp_order = tp_order.copy()
            for k in ['price', 'origQty', 'executedQty', 'cummulativeQuoteQty']:
                if k in proc_tp_order and proc_tp_order[k] is not None:
                    dec_val = to_decimal(proc_tp_order[k], default=None)
                    if dec_val is not None:
                        proc_tp_order[k] = dec_val
                    else:
                        logger.warning(
                            f"Could not convert TP order field '{k}' to Decimal: {proc_tp_order[k]}")
            processed_tp_order = proc_tp_order
        elif tp_order is not None:  # It exists but is not a dict
            logger.warning(
                f"Loaded 'active_tp_order' is not a dict (type: {type(tp_order)}). Initializing to None.")
            # processed_tp_order remains None
        processed_state['active_tp_order'] = processed_tp_order

        # Process other known keys, providing defaults if necessary
        # Note: confidence_score is often float, handle conversion if stored as str
        conf_score_loaded = state.get('confidence_score')
        if conf_score_loaded is not None:
            try:
                processed_state['confidence_score'] = float(conf_score_loaded)
            except (ValueError, TypeError):
                logger.warning(
                    f"Could not convert loaded confidence_score '{conf_score_loaded}' to float. Setting to None.")
                processed_state['confidence_score'] = None
        else:
            processed_state['confidence_score'] = None  # Keep None if missing

        processed_state['planned_grid'] = state.get(
            'planned_grid', [])  # Default []
        # Planned TP price needs to be Decimal or None
        processed_state['planned_tp_price'] = to_decimal(
            state.get('planned_tp_price'), default=None)

        # --- Ensure essential keys that *must* exist for the bot are present ---
        # (Belt-and-suspenders check after processing defaults)
        # Add cascade keys that might be needed downstream even if None/False
        essential_keys = ['position_size', 'position_entry_price',
                          'balance_quote', 'balance_base', 'active_grid_orders', 'active_tp_order',
                          'ts_exit_active', 'ts_exit_step', 'ts_exit_timer_start', 'ts_exit_trigger_price', 'ts_exit_active_order_id']
        for key in essential_keys:
            if key not in processed_state:
                # This case should be rare given the default handling above, but log critically if it occurs
                logger.critical(
                    f"Essential key '{key}' missing from state after processing! This indicates a logic error.")
                # Force a default value here to prevent downstream errors
                if key in ['position_size', 'position_entry_price', 'balance_quote', 'balance_base']:
                    processed_state[key] = Decimal('0')
                elif key == 'active_grid_orders':
                    processed_state[key] = []
                elif key == 'ts_exit_active':
                    processed_state[key] = False
                else: # Default to None for others
                    processed_state[key] = None

        # Log keys that were present in loaded file but *not* processed (potential old/new keys)
        # Only log if there are unprocessed keys to avoid noise
        processed_keys = set(processed_state.keys())
        loaded_keys = set(state.keys())
        unprocessed_keys = loaded_keys - processed_keys
        if unprocessed_keys:
            logger.info(
                f"Unprocessed keys found in loaded state (will be ignored): {unprocessed_keys}")
            # Optionally copy them over if desired:
            # for key in unprocessed_keys: processed_state[key] = state[key]

        return processed_state
    # --- END OF _post_load_process ---

    # START OF METHOD: src/core/state_manager.py -> load_state (Unchanged)
    def load_state(self) -> Optional[Dict[str, Any]]:
        """
        Loads the state from the JSON file, trying backups if necessary.
        Returns the processed state dictionary or None if loading fails completely.
        """
        files_to_try = [self.filepath] + [self.filepath.with_suffix(f".json.bak{i}" if i > 0 else ".json.bak")
                                          for i in range(1, self.backup_count + 1)]

        raw_state = None  # <<< Store the raw loaded dict here
        loaded_file_path = None  # <<< Track which file succeeded

        for file_path in files_to_try:
            if file_path.exists():
                logger.info(f"Attempting to load state from {file_path}...")
                try:
                    # Check size before reading
                    if file_path.stat().st_size <= 2:  # Check size > 2 bytes (e.g., '{}')
                        logger.warning(
                            f"State file {file_path} is too small or empty ({file_path.stat().st_size} bytes). Trying next backup.")
                        continue  # Try next backup if too small

                    with open(file_path, 'r', encoding='utf-8') as f:  # Specify encoding
                        # Basic JSON load first
                        content = f.read()
                        # Sanity check content again? Maybe redundant if size check passed
                        if not content.strip():
                            logger.warning(
                                f"State file {file_path} contains only whitespace. Trying next backup.")
                            continue  # Try next backup if empty

                        # Parse non-empty content
                        raw_state = json.loads(content)
                        loaded_file_path = file_path  # Mark success
                        logger.debug(
                            f"Successfully parsed JSON from {loaded_file_path}")
                        break  # Stop trying files once one is loaded successfully

                except json.JSONDecodeError as e:
                    logger.error(
                        f"JSON Decode Error loading state from {file_path}: {e}. Trying next backup.")
                    raw_state = None  # Reset on error
                    continue  # Try next backup
                except OSError as os_err:
                    logger.error(
                        f"OS Error accessing state file {file_path}: {os_err}. Trying next backup.")
                    raw_state = None  # Reset on error
                    continue  # Try next backup
                except Exception as e:
                    logger.error(
                        f"Unexpected Error loading state file {file_path}: {e}. Trying next backup.", exc_info=True)
                    raw_state = None  # Reset on error
                    continue  # Try next backup
            # else: logger.debug(f"State file {file_path} does not exist.")

        # --- Process the loaded state (or handle failure) ---
        if raw_state is not None and isinstance(raw_state, dict):
            # <<< Process only if raw_state is a valid dict loaded from a file >>>
            logger.info(
                f"Successfully loaded raw state from {loaded_file_path}. Processing...")
            processed_state = self._post_load_process(raw_state)
            # Log missing key warnings *after* processing attempts defaults
            # (These warnings are now mainly for older state files)
            # Example: Check if a key expected by the current code is missing
            required_keys = ['position_size',
                             'balance_quote']  # Add more as needed
            missing_keys = [
                k for k in required_keys if k not in processed_state]
            if missing_keys:
                logger.warning(
                    f"Keys missing after processing loaded state (initialized to defaults): {missing_keys}")

            return processed_state
        elif raw_state is not None and not isinstance(raw_state, dict):
            # This case means the loaded JSON was valid but not a dictionary
            logger.error(
                f"Loaded state from {loaded_file_path} is not a dictionary (type: {type(raw_state)}). Cannot process.")
            return None  # Indicate failure to load valid state structure
        else:
            # This means no file was found or all files were empty/corrupt/inaccessible
            logger.warning(
                f"Could not load valid state from {self.filepath} or any backups. Returning None.")
            return None  # <<< Return None if all attempts failed
    # END OF METHOD: src/core/state_manager.py -> load_state

    # START OF METHOD: src/core/state_manager.py -> clear_state_file (Unchanged)
    def clear_state_file(self):
        # ... (clear_state_file remains the same) ...
        logger.warning(f"Clearing state file and backups for: {self.filepath}")
        files_to_delete = [self.filepath] + [self.filepath.with_suffix(f".json.bak{i}" if i > 0 else ".json.bak")
                                             # Also clear temp
                                             for i in range(1, self.backup_count + 1)] + [self.filepath.with_suffix(".json.tmp")]
        deleted_count = 0
        for file_path in files_to_delete:
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Deleted state file: {file_path}")
                    deleted_count += 1
            except OSError as e:
                logger.error(f"Error deleting state file {file_path}: {e}")
        logger.warning(
            f"State file clearing complete. Deleted {deleted_count} files.")
    # END OF METHOD: src/core/state_manager.py -> clear_state_file


# Example Usage (Optional)
if __name__ == '__main__':
    # --- Example Usage remains unchanged ---
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s')
    # Example state including new keys
    test_state = {
        'position_size': Decimal('1.23456789'),
        'position_entry_price': Decimal('50000.12'),
        'position_entry_timestamp': pd.Timestamp.utcnow(),
        'balance_quote': Decimal('12345.67'),
        'balance_base': Decimal('2.5'),
        'active_grid_orders': [{'orderId': 1, 'price': Decimal('49000.00'), 'origQty': Decimal('0.1')}],
        'active_tp_order': {'orderId': 2, 'price': Decimal('51000.00'), 'origQty': Decimal('1.23456789')},
        'some_other_data': [1, 2, None, "test"],
        'last_processed_timestamp': pd.Timestamp.utcnow() - pd.Timedelta(hours=1),
        # Add Cascade keys
        'ts_exit_active': True,
        'ts_exit_step': 'INITIAL_MAKER',
        'ts_exit_timer_start': pd.Timestamp.utcnow() - pd.Timedelta(seconds=30),
        'ts_exit_trigger_price': Decimal('50100.00'),
        'ts_exit_active_order_id': 'ts_order_123',
        # Add DataFrame to test exclusion
        'historical_klines': pd.DataFrame({'A': [1, 2], 'B': [3, 4]}),
        'indicators': pd.DataFrame({'C': [5, 6], 'D': [7, 8]})
    }

    # Create manager in a test directory
    sm = StateManager("data/test_state/test_state.json")
    sm.clear_state_file()  # Start clean

    # Save state
    logger.info("\n--- Saving State (Including Cascade Keys) ---")
    sm.save_state(test_state)

    # Load state
    logger.info("\n--- Loading State ---")
    loaded = sm.load_state()

    if loaded:
        logger.info("\n--- Verifying Loaded Types ---")
        # Check which keys were loaded
        print(f"Loaded Keys: {list(loaded.keys())}")
        print(f"TS Exit Active: {loaded.get('ts_exit_active')} (Type: {type(loaded.get('ts_exit_active'))})")
        print(f"TS Exit Step: {loaded.get('ts_exit_step')} (Type: {type(loaded.get('ts_exit_step'))})")
        print(f"TS Exit Timer Start: {loaded.get('ts_exit_timer_start')} (Type: {type(loaded.get('ts_exit_timer_start'))})")
        print(f"TS Exit Trigger Price: {loaded.get('ts_exit_trigger_price')} (Type: {type(loaded.get('ts_exit_trigger_price'))})")
        print(f"TS Exit Active Order ID: {loaded.get('ts_exit_active_order_id')} (Type: {type(loaded.get('ts_exit_active_order_id'))})")
        # Should be False (still excluded)
        print(f"Historical Klines Present: {'historical_klines' in loaded}")
        # Should be False (still excluded)
        print(f"Indicators Present: {'indicators' in loaded}")
    else:
        print("Failed to load state.")

    # Test loading missing cascade keys (should default correctly)
    logger.info("\n--- Testing Load Missing Cascade Keys ---")
    test_state_old = { k: v for k, v in test_state.items() if not k.startswith('ts_exit_') and k not in ['historical_klines', 'indicators']}
    sm.save_state(test_state_old)
    loaded_old = sm.load_state()
    if loaded_old:
        print(f"TS Exit Active (loaded old): {loaded_old.get('ts_exit_active')} (Type: {type(loaded_old.get('ts_exit_active'))}) - Expected: False")
        print(f"TS Exit Step (loaded old): {loaded_old.get('ts_exit_step')} (Type: {type(loaded_old.get('ts_exit_step'))}) - Expected: None")
        print(f"TS Exit Timer Start (loaded old): {loaded_old.get('ts_exit_timer_start')} (Type: {type(loaded_old.get('ts_exit_timer_start'))}) - Expected: None")
        print(f"TS Exit Trigger Price (loaded old): {loaded_old.get('ts_exit_trigger_price')} (Type: {type(loaded_old.get('ts_exit_trigger_price'))}) - Expected: None")
        print(f"TS Exit Active Order ID (loaded old): {loaded_old.get('ts_exit_active_order_id')} (Type: {type(loaded_old.get('ts_exit_active_order_id'))}) - Expected: None")
    else:
        print("Failed to load old state.")

    # Clear state again
    logger.info("\n--- Clearing State ---")
    sm.clear_state_file()


# END OF FILE: src/core/state_manager.py (Add Cascade State Keys)
