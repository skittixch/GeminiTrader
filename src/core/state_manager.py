# START OF FILE: src/core/state_manager.py

import logging
import json
from pathlib import Path
from decimal import Decimal, InvalidOperation
import pandas as pd
import os
import shutil
from typing import Optional, Dict, Any, List, Union  # Added Union

logger = logging.getLogger(__name__)

# --- Conversion Helpers ---


def _prepare_for_save(data: Any) -> Any:
    """Recursively converts Decimal, Timestamp, DataFrame for JSON."""
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            # --- DataFrame Handling ---
            if isinstance(v, pd.DataFrame):
                try:
                    df_dict = v.to_dict(orient='split')
                    df_dict['_is_dataframe'] = True
                    if isinstance(v.index, pd.DatetimeIndex) and v.index.tz is not None:
                        df_dict['_index_timezone'] = str(v.index.tz)
                    # Recursively prepare the contents of the DataFrame dict
                    new_dict[k] = _prepare_for_save(
                        df_dict)  # Prepare the converted dict
                except Exception as e:
                    logger.error(f"Could not convert DF key '{k}': {e}")
                    new_dict[k] = None
            # --- Recursive Call for other dict values ---
            else:
                new_dict[k] = _prepare_for_save(v)
        return new_dict
    elif isinstance(data, list):
        # Recursively process list items
        return [_prepare_for_save(item) for item in data]
    # --- Direct Type Conversions ---
    elif isinstance(data, Decimal):
        return str(data)
    elif isinstance(data, pd.Timestamp):
        return data.isoformat()
    # --- Numpy/Pandas Specific Handling ---
    elif hasattr(data, 'tolist'):  # Handle numpy arrays
        return data.tolist()
    elif pd.isna(data):  # Handle NaT/NaN - return None for JSON
        return None
    # --- Basic Types Pass Through ---
    elif isinstance(data, (str, int, float, bool, type(None))):
        return data
    # --- Fallback for Unknown Types ---
    else:
        logger.warning(
            f"Prepare unknown type {type(data)}, converting to string.")
        try:
            return str(data)
        except Exception:
            logger.error(f"Could not convert {type(data)} to string.")
            return None


def _restore_after_load(data: Any) -> Any:
    """Recursively converts specific strings/dicts back to Decimal/Timestamp/DataFrame."""
    if isinstance(data, dict):
        # --- DataFrame Restoration ---
        if data.get('_is_dataframe'):
            try:
                logger.debug("Restoring DataFrame from dict...")
                data.pop('_is_dataframe', None)
                timezone = data.pop('_index_timezone', None)
                # IMPORTANT: Recursively restore items *within* the dict *before* creating DF
                restored_data = {
                    'data': _restore_after_load(data.get('data')),
                    'index': _restore_after_load(data.get('index')),
                    'columns': _restore_after_load(data.get('columns'))
                }
                # Filter out None values if restore failed partially
                restored_data = {k: v for k,
                                 v in restored_data.items() if v is not None}

                df = pd.DataFrame.from_dict(restored_data, orient='split')
                # Restore index type and timezone
                try:
                    df.index = pd.to_datetime(df.index, errors='coerce')
                    if isinstance(df.index, pd.DatetimeIndex) and timezone:
                        try:
                            df.index = df.index.tz_localize(timezone)
                        except TypeError:
                            df.index = df.index.tz_convert(timezone)
                        except Exception as tz_err:
                            logger.warning(
                                f"Could not apply TZ '{timezone}': {tz_err}")
                    logger.debug(
                        f"DF restored (Shape:{df.shape}, Index:{df.index.dtype})")
                except Exception as idx_e:
                    logger.warning(
                        f"Could not convert DF index to DatetimeIndex: {idx_e}")
                # Convert known columns back to Decimal (more robust check)
                # List potentially containing Decimals in DataFrames
                df_decimal_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'Quote_asset_volume',  # Klines
                                   'MACD', 'Signal', 'Histogram',  # MACD
                                   'PP', 'R1', 'S1', 'R2', 'S2', 'R3', 'S3',  # Pivots
                                   # Example indicators
                                   f'SMA_{50}', f'SMA_{200}', f'RSI_{14}', f'ATR_{14}']
                for col in df.columns:
                    if col in df_decimal_cols:
                        try:
                            df[col] = df[col].apply(lambda x: Decimal(
                                str(x)) if pd.notna(x) else None)
                            df[col] = df[col].astype(object)
                        except (InvalidOperation, TypeError, ValueError) as conv_err:
                            logger.warning(
                                f"Could not convert col '{col}' back to Decimal in loaded DF: {conv_err}")

                return df
            except Exception as df_e:
                logger.error(f"Error restoring DataFrame from dict: {df_e}")
                return None
        # --- Process Regular Dict Items ---
        else:
            new_dict = {}
            for k, v in data.items():
                v_restored = _restore_after_load(v)  # Recurse first
                # Heuristic conversion based on keys
                decimal_keys = {'entry_price', 'quantity', 'price', 'origQty',
                                'executedQty', 'cummulativeQuoteQty', 'balance_base', 'balance_quote'}
                timestamp_keys = {'entry_time', 'last_state_save_time', 'timestamp',
                                  'last_processed_timestamp', 'position_entry_timestamp'}
                # Check for Decimal conversion
                if k in decimal_keys and isinstance(v_restored, (str, int, float)) and not isinstance(v_restored, bool):
                    try:
                        new_dict[k] = Decimal(str(v_restored))
                    except (InvalidOperation, TypeError):
                        logger.warning(
                            f"Failed Decimal restore: k='{k}', v='{v_restored}'")
                        new_dict[k] = None
                # Check for Timestamp conversion (ISO format)
                elif k in timestamp_keys and isinstance(v_restored, str) and 'T' in v_restored and ('Z' in v_restored or '+' in v_restored or '-' in v_restored[11:]):
                    try:
                        new_dict[k] = pd.Timestamp(v_restored)
                    except ValueError:
                        logger.warning(
                            f"Failed Timestamp restore: k='{k}', v='{v_restored}'")
                        new_dict[k] = None
                else:  # Assign restored value directly
                    new_dict[k] = v_restored
            return new_dict
    elif isinstance(data, list):
        # Recursively process list items
        return [_restore_after_load(item) for item in data]
    # Return data directly if not dict, list (e.g., str, int, float, None)
    return data


class StateManager:
    """Handles saving/loading of application state via JSON."""

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self._temp_filepath = self.filepath.with_suffix(
            self.filepath.suffix + '.tmp')
        self._backup_filepath = self.filepath.with_suffix(
            self.filepath.suffix + '.bak')
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._is_saving = False
        logger.info(f"StateManager initialized. State file: {self.filepath}")

    def save_state(self, state_data: Dict[str, Any], force_save: bool = False):
        """Saves state dict to JSON atomically. Converts non-serializable types."""
        if self._is_saving and not force_save:
            logger.warning("Save already in progress, skipping.")
            return False
        self._is_saving = True
        if not isinstance(state_data, dict):
            logger.error("save_state: Input must be dict.")
            self._is_saving = False
            return False
        # Create deep copy to avoid modifying original state during preparation
        try:
            # Using json loads/dumps for a deep copy that handles basic types well
            state_copy = json.loads(json.dumps(state_data, default=str))
        except TypeError:
            # Fallback if basic deepcopy is needed (less safe for nested complex types)
            import copy
            state_copy = copy.deepcopy(state_data)
            logger.warning(
                "Used copy.deepcopy for state_copy, potential issues with complex types.")

        # Add save timestamp AFTER copy
        state_copy['last_state_save_time'] = pd.Timestamp.utcnow()
        logger.debug(f"Preparing state for saving to {self.filepath}...")
        try:
            prepared_data = _prepare_for_save(state_copy)  # Prepare the copy
            if prepared_data is None:
                raise TypeError("State preparation resulted in None")

            with open(self._temp_filepath, 'w', encoding='utf-8') as f:
                json.dump(prepared_data, f, indent=4, ensure_ascii=False)

            # Atomic rename / Backup logic
            backup_made = False
            if self.filepath.exists():
                try:
                    shutil.copy2(str(self.filepath), str(
                        self._backup_filepath))  # Copy to backup first
                    backup_made = True
                except Exception as copy_err:
                    logger.warning(
                        f"Could not create backup before saving: {copy_err}")
            try:
                # Atomic replace/rename
                os.replace(self._temp_filepath, self.filepath)
                logger.info(f"State successfully saved to {self.filepath}")
                self._is_saving = False
                return True
            except OSError as replace_err:
                # If replace fails, try to restore backup if it was made
                logger.error(
                    f"Atomic replace failed: {replace_err}. Attempting recovery.")
                if backup_made:
                    try:
                        shutil.move(str(self._backup_filepath), str(
                            self.filepath))  # Move backup back
                        logger.info(
                            "Recovered original state file from backup after replace failure.")
                    except Exception as restore_err:
                        logger.error(
                            f"CRITICAL: Failed to restore state from backup after replace error: {restore_err}")
                self._is_saving = False
                return False

        except TypeError as e:
            logger.exception(
                f"Error serializing state to JSON: {e}. State Keys: {list(state_copy.keys())}")
            self._is_saving = False
            return False
        except Exception as e:
            logger.exception(f"Error saving state to {self.filepath}: {e}")
            self._is_saving = False
            return False  # Don't attempt recovery here, rely on load logic

    def load_state(self) -> Optional[Dict[str, Any]]:
        """Loads state from JSON, falls back to backup."""
        file_to_load = None
        try:  # Check existence and size
            if self.filepath.exists() and os.path.getsize(self.filepath) > 2:
                file_to_load = self.filepath
            elif self._backup_filepath.exists() and os.path.getsize(self._backup_filepath) > 2:
                logger.warning(
                    f"State file {self.filepath} missing/empty. Loading backup.")
                file_to_load = self._backup_filepath
            else:
                logger.warning(
                    f"State file {self.filepath} missing/empty. No valid backup found. Returning empty state.")
                return {}
        except OSError as os_err:
            logger.error(f"OS Error checking state file: {os_err}")
            return None
        logger.info(f"Loading state from {file_to_load}...")
        try:
            loaded_state = self._load_from_file(file_to_load)
            if loaded_state is None:
                raise ValueError("State loaded as None.")
            if not isinstance(loaded_state.get('active_grid_orders', []), list):
                logger.warning(
                    "Loaded 'active_grid_orders' not list. Resetting.")
                return {}
            return loaded_state
        except Exception as e:
            logger.exception(f"Error loading state from {file_to_load}.")
            if file_to_load == self.filepath and self._backup_filepath.exists() and os.path.getsize(self._backup_filepath) > 2:
                logger.warning("Primary load failed. Attempting backup...")
                try:
                    return self._load_from_file(self._backup_filepath)
                except Exception as backup_e:
                    logger.error(
                        f"Failed load backup {self._backup_filepath}: {backup_e}")
            return None

    def _load_from_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Internal helper to load/process state from file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                loaded_data_raw = json.load(f)
            if not isinstance(loaded_data_raw, dict):
                logger.error(f"Loaded state not dict: {file_path}.")
                return None
            restored_data = _restore_after_load(loaded_data_raw)
            logger.info(
                f"State successfully loaded/processed from {file_path}")
            return restored_data
        except json.JSONDecodeError as e:
            logger.error(f"Error decode JSON {file_path}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error loading state {file_path}")
            return None


# Example Usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    test_file = 'temp_state_test_df.json'
    manager = StateManager(test_file)
    dummy_df_index = pd.to_datetime(
        ['2023-01-01 10:00', '2023-01-01 11:00'], utc=True)
    dummy_df = pd.DataFrame(
        {'A': [Decimal('1.0'), Decimal('2.5')], 'B': [3, 4]}, index=dummy_df_index)
    dummy_df = dummy_df.astype(object)
    # Add nested Decimal in a list within the DataFrame dict representation
    df_as_dict_prepared = {
        '_is_dataframe': True,
        'index': [1672567200000, 1672570800000],
        'columns': ['A', 'B'],
        # Ensure Decimals are strings here
        'data': [[str(Decimal('1.0')), 3], [str(Decimal('2.5')), 4]]
    }

    state_to_save = {
        'position': {'symbol': 'BTCUSDT', 'entry_price': Decimal('45000.12'), 'quantity': Decimal('0.001'), 'entry_time': pd.Timestamp.utcnow()},
        'active_grid_orders': [{'orderId': 123, 'price': '44000.0', 'origQty': '0.001'}],
        'active_tp_order': {'orderId': 789, 'price': '46000.0', 'origQty': '0.001'},
        'historical_klines': dummy_df,  # DataFrame object
        'indicators': df_as_dict_prepared,  # Pre-prepared dict example
        'last_processed_timestamp': pd.Timestamp('2023-01-01 11:00', tz='UTC'),
        'balance_quote': Decimal("1234.56"),
        'current_kline': {'open': Decimal('45100.0'), 'high': Decimal('45200.1'), 'low': Decimal('45050.5'), 'close': Decimal('45150.9'), 'volume': Decimal('12.345'), 'timestamp': pd.Timestamp('2023-01-01 11:00', tz='UTC')},
        'confidence_score': 0.75
    }
    print("\n--- Saving State ---")
    save_ok = manager.save_state(state_to_save)
    print(f"Save OK: {save_ok}")
    # Inspect saved file manually if needed: cat temp_state_test_df.json
    print("\n--- Loading State ---")
    loaded_state = manager.load_state()
    if loaded_state:
        print("Loaded State OK:")
        hist_klines = loaded_state.get('historical_klines')
        if isinstance(hist_klines, pd.DataFrame):
            print(f"Hist Klines: DataFrame {hist_klines.shape}")
            hist_klines.info()
            print(hist_klines.head())
        else:
            print(f"Hist Klines NOT DF: {type(hist_klines)}")
        indicators = loaded_state.get('indicators')
        if isinstance(indicators, pd.DataFrame):
            print(f"\nIndicators: DataFrame {indicators.shape}")
            indicators.info()
            print(indicators.head())
        else:
            print(f"Indicators NOT DF: {type(indicators)}")
        print(
            f"\nLast TS Type: {type(loaded_state.get('last_processed_timestamp'))}")
        print(f"Balance Quote Type: {type(loaded_state.get('balance_quote'))}")
        print(
            f"Current Kline Close Type: {type(loaded_state.get('current_kline', {}).get('close'))}")
        # Check restored type
        print(
            f"Active Grid Order Price Type: {type(loaded_state.get('active_grid_orders', [{}])[0].get('price'))}")
    else:
        print("Load failed.")
    try:
        Path(test_file).unlink(missing_ok=True)
        Path(test_file + '.tmp').unlink(missing_ok=True)
        Path(test_file + '.bak').unlink(missing_ok=True)
        print("\nCleaned up.")
    except OSError:
        pass


# END OF FILE: src/core/state_manager.py
