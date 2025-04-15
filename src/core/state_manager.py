# START OF FILE: src/core/state_manager.py

import logging
import json
from pathlib import Path
from decimal import Decimal
import pandas as pd
import os  # For atomic write
import shutil  # For atomic write
# --- ADDED: typing import ---
from typing import Optional, Dict, Any, List, Set  # Import Dict and others used

logger = logging.getLogger(__name__)

# --- Conversion Helpers ---


def _prepare_for_save(data):
    """Recursively converts Decimal and Timestamp in data to strings for JSON."""
    if isinstance(data, dict):
        return {k: _prepare_for_save(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_prepare_for_save(item) for item in data]
    elif isinstance(data, Decimal):
        return str(data)  # Convert Decimal to string
    elif isinstance(data, pd.Timestamp):
        # Save in ISO format with UTC timezone info
        return data.isoformat()
    # Add handling for other non-serializable types if needed
    return data


def _restore_after_load(data):
    """Recursively converts specific string fields back to Decimal/Timestamp."""
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            # --- Define keys that need type restoration ---
            # Combine price/qty keys for Decimal conversion
            decimal_keys = {'entry_price', 'quantity', 'price',
                            'origQty', 'executedQty', 'cummulativeQuoteQty'}
            # Combine time keys for Timestamp conversion
            # Add others if needed
            timestamp_keys = {'entry_time', 'last_state_save_time'}

            if k in decimal_keys:
                try:
                    new_dict[k] = Decimal(str(v)) if v is not None else None
                except Exception:
                    logger.warning(
                        f"Could not convert value '{v}' for key '{k}' back to Decimal. Setting to None.")
                    new_dict[k] = None
            elif k in timestamp_keys or ('time' in k.lower() and isinstance(v, str) and 'T' in v and ('Z' in v or '+' in v)):
                try:
                    new_dict[k] = pd.Timestamp(v) if v else None
                except Exception:
                    logger.warning(
                        f"Could not convert value '{v}' for key '{k}' back to Timestamp. Setting to None.")
                    new_dict[k] = None
            else:
                new_dict[k] = _restore_after_load(v)  # Recurse
        return new_dict
    elif isinstance(data, list):
        return [_restore_after_load(item) for item in data]
    return data

# --- State Manager Class ---


class StateManager:
    """Handles saving and loading of application state to/from a JSON file."""

    def __init__(self, filepath: str):
        """
        Initializes the StateManager.

        Args:
            filepath (str): The path to the state file (relative to project root).
        """
        self.filepath = Path(filepath)
        self._temp_filepath = self.filepath.with_suffix(
            self.filepath.suffix + '.tmp')
        self._backup_filepath = self.filepath.with_suffix(
            self.filepath.suffix + '.bak')
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"StateManager initialized. State file: {self.filepath}")

    # --- USE Dict type hint ---
    def save_state(self, state_data: Dict[str, Any]):
        """
        Saves the provided state dictionary to the JSON file atomically.
        Converts Decimal and Timestamp types to strings before saving.

        Args:
            state_data (Dict): The dictionary containing the state to save.
        """
        if not isinstance(state_data, dict):
            logger.error("save_state: Input must be a dictionary.")
            return False

        logger.debug(f"Preparing state for saving to {self.filepath}...")
        try:
            prepared_data = _prepare_for_save(state_data)
            with open(self._temp_filepath, 'w', encoding='utf-8') as f:
                json.dump(prepared_data, f, indent=4)
            if self.filepath.exists():
                shutil.copy2(self.filepath, self._backup_filepath)
            os.replace(self._temp_filepath, self.filepath)
            logger.info(f"State successfully saved to {self.filepath}")
            return True
        except TypeError as e:
            # Log keys only
            logger.exception(
                f"Error serializing state to JSON: {e}. State Data Dump (first level keys): {list(state_data.keys())}")
            return False
        except Exception as e:
            logger.exception(f"Error saving state to {self.filepath}: {e}")
            if not self.filepath.exists() and self._backup_filepath.exists():
                try:
                    logger.warning(
                        "Attempting to restore state from backup...")
                    shutil.copy2(self._backup_filepath, self.filepath)
                except Exception as backup_err:
                    logger.error(
                        f"Failed to restore state from backup: {backup_err}")
            return False

    # --- USE Dict type hint ---
    def load_state(self) -> Optional[Dict[str, Any]]:
        """
        Loads state from the JSON file.
        Converts specific string fields back to Decimal/Timestamp after loading.

        Returns:
            Optional[Dict]: The loaded state dictionary, or None if file not found or error occurs.
        """
        file_to_load = None
        if self.filepath.exists():
            file_to_load = self.filepath
        elif self._backup_filepath.exists():
            logger.warning(
                f"State file not found: {self.filepath}. Attempting to load backup: {self._backup_filepath}")
            file_to_load = self._backup_filepath
        else:
            logger.warning(
                f"State file not found: {self.filepath}. No backup file found either.")
            return None

        logger.info(f"Loading state from {file_to_load}...")
        try:
            return self._load_from_file(file_to_load)
        except Exception as e:
            logger.exception(f"Error loading state from {file_to_load}.")
            # If primary load failed, try backup (if primary wasn't already the backup)
            if file_to_load == self.filepath and self._backup_filepath.exists():
                logger.warning(
                    "Primary state load failed. Attempting backup...")
                try:
                    return self._load_from_file(self._backup_filepath)
                except Exception as backup_e:
                    logger.error(
                        f"Failed to load state from backup file {self._backup_filepath}: {backup_e}")
            return None

    # --- USE Dict type hint ---
    def _load_from_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Internal helper to load and process state from a specific file path."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                loaded_data_raw = json.load(f)
            if not isinstance(loaded_data_raw, dict):
                logger.error(
                    f"Loaded state from {file_path} is not a dictionary.")
                return None
            restored_data = _restore_after_load(loaded_data_raw)
            logger.info(
                f"State successfully loaded and processed from {file_path}")
            return restored_data
        except json.JSONDecodeError as e:
            logger.error(
                f"Error decoding JSON from state file {file_path}: {e}")
            return None
        except Exception as e:
            logger.exception(
                f"Unexpected error loading state from {file_path}")
            return None


# Example Usage remains the same
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    test_file = 'temp_state_test.json'
    manager = StateManager(test_file)
    state_to_save = {
        'position': {'symbol': 'BTCUSDT', 'entry_price': Decimal('45000.12345678'), 'quantity': Decimal('0.001'), 'entry_time': pd.Timestamp.utcnow()},
        'active_grid_orders': [{'orderId': 123, 'price': Decimal('44000.0'), 'origQty': Decimal('0.001')}, {'orderId': 456, 'price': Decimal('43000.5'), 'origQty': Decimal('0.0012')}],
        'active_tp_order': {'orderId': 789, 'price': Decimal('46000.0'), 'origQty': Decimal('0.001')},
        'simulation_index': 500, 'some_other_setting': 'test',
        'a_list': [1, Decimal('2.5'), {'ts': pd.Timestamp('2023-01-01')}]
    }
    print("\n--- Saving State ---")
    manager.save_state(state_to_save)
    print("\n--- Loading State ---")
    loaded_state = manager.load_state()
    if loaded_state:
        print("State Loaded Successfully:")
        import pprint
        pprint.pprint(loaded_state)
        print("\n--- Verifying Types ---")
        pos = loaded_state.get('position')
        grid = loaded_state.get('active_grid_orders')
        tp = loaded_state.get('active_tp_order')
        other_list = loaded_state.get('a_list')
        if pos:
            print(
                f"Pos Entry Price: {type(pos.get('entry_price'))}, Entry Time: {type(pos.get('entry_time'))}")
        if grid:
            print(f"Grid Order Price: {type(grid[0].get('price'))}")
        if tp:
            print(f"TP Order Price: {type(tp.get('price'))}")
        if other_list and len(other_list) > 1:
            print(f"List[1]: {type(other_list[1])}")
        if isinstance(other_list[2], dict):
            print(f"List[2]['ts']: {type(other_list[2].get('ts'))}")
    else:
        print("Failed to load state.")
    try:
        Path(test_file).unlink()
        Path(test_file + '.tmp').unlink(missing_ok=True)
        Path(test_file + '.bak').unlink(missing_ok=True)
        print("\nCleaned up test files.")
    except OSError:
        pass

# END OF FILE: src/core/state_manager.py
