# src/db/manager.py

import sqlite3
import logging
import os
from typing import Optional, List, Tuple, Any
# Note: datetime and timezone are imported *only* within the `if __name__ == "__main__"` block below
#       as they are only needed for the test code, not the class itself.

# Attempt to import settings, handle potential ImportError during early setup/testing
try:
    from config.settings import settings, PROJECT_ROOT
except ImportError:
    import sys  # Import sys here for the error message
    print("FATAL: Could not import settings for DB manager setup. Ensure settings.py exists and PYTHONPATH is correct.", file=sys.stderr)
    # Define minimal defaults so basic setup might work, but this indicates a setup problem
    settings = {'database': {'type': 'sqlite',
                             'path': 'data/db/geminitrader_log.db'}}
    PROJECT_ROOT = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))  # Guess project root

log = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages the connection and execution of queries for the SQLite database.
    Handles database creation and schema initialization.
    """

    def __init__(self):
        """Initializes the DatabaseManager, finding the DB path and schema path."""
        db_config = settings.get('database', {})
        if db_config.get('type') != 'sqlite':
            log.error(
                f"Database type '{db_config.get('type')}' not supported by this manager. Only 'sqlite' is implemented.")
            raise ValueError(
                "Unsupported database type configured. Only SQLite is supported.")

        db_path_rel = db_config.get('path', 'data/db/geminitrader_log.db')
        self.db_path = os.path.join(PROJECT_ROOT, db_path_rel)
        self.schema_path = os.path.join(
            PROJECT_ROOT, 'src', 'db', 'schema.sql')
        log.info(f"DatabaseManager initialized. DB path: {self.db_path}")
        self._ensure_db_and_tables_exist()  # Ensure DB and schema are ready on init

    def _connect(self) -> Optional[sqlite3.Connection]:
        """Establishes a connection to the SQLite database."""
        try:
            # Ensure the directory exists before connecting
            db_dir = os.path.dirname(self.db_path)
            os.makedirs(db_dir, exist_ok=True)

            conn = sqlite3.connect(self.db_path, timeout=10)  # Set a timeout
            log.debug(f"Database connection established: {self.db_path}")
            return conn
        except sqlite3.Error as e:
            log.error(
                f"Error connecting to database at {self.db_path}: {e}", exc_info=True)
            return None

    def _execute_script_from_file(self, conn: sqlite3.Connection, script_path: str) -> bool:
        """Executes a SQL script file against the given connection."""
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                sql_script = f.read()
            conn.executescript(sql_script)
            conn.commit()  # Commit after script execution
            log.info(f"Successfully executed SQL script: {script_path}")
            return True
        except FileNotFoundError:
            log.error(f"SQL script file not found: {script_path}")
            return False
        except sqlite3.Error as e:
            log.error(
                f"Error executing SQL script {script_path}: {e}", exc_info=True)
            conn.rollback()  # Rollback changes if script fails
            return False
        except Exception as e:
            log.error(
                f"Unexpected error reading/executing script {script_path}: {e}", exc_info=True)
            conn.rollback()
            return False

    def _ensure_db_and_tables_exist(self):
        """Checks if the database file and tables exist, creating them if necessary."""
        conn = self._connect()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='trades';")
                table_exists = cursor.fetchone()
                cursor.close()

                if not table_exists:
                    log.info(
                        "Tables not found. Attempting to create schema from script...")
                    self._execute_script_from_file(conn, self.schema_path)
                else:
                    log.debug("Database file and 'trades' table already exist.")

            finally:
                conn.close()
                log.debug("Closed connection after ensuring DB exists.")
        else:
            log.error("Failed to connect to database to ensure tables exist.")

    def execute_query(self, query: str, params: tuple = ()) -> Optional[List[Tuple]]:
        """
        Executes a SELECT query and fetches all results.

        Args:
            query (str): The SQL SELECT statement.
            params (tuple, optional): Parameters to substitute into the query. Defaults to ().

        Returns:
            List[Tuple] or None: A list of tuples representing the rows fetched, or None on error.
        """
        conn = self._connect()
        if not conn:
            return None

        cursor = None
        try:
            cursor = conn.cursor()
            log.debug(f"Executing query: {query} with params: {params}")
            cursor.execute(query, params)
            results = cursor.fetchall()
            log.debug(
                f"Query executed successfully. Fetched {len(results)} rows.")
            return results
        except sqlite3.Error as e:
            log.error(
                f"Error executing query: {query} | Params: {params} | Error: {e}", exc_info=True)
            return None
        finally:
            if cursor:
                cursor.close()
            conn.close()
            log.debug("Closed connection after execute_query.")

    def execute_update(self, query: str, params: tuple = ()) -> Optional[int]:
        """
        Executes an INSERT, UPDATE, or DELETE query.

        Args:
            query (str): The SQL statement (INSERT, UPDATE, DELETE).
            params (tuple, optional): Parameters to substitute into the query. Defaults to ().

        Returns:
            int or None: The number of rows affected (for UPDATE/DELETE) or the last inserted row ID (for INSERT),
                         or None on error. Returns 0 if no rows were affected but query was successful.
        """
        conn = self._connect()
        if not conn:
            return None

        cursor = None
        try:
            cursor = conn.cursor()
            log.debug(f"Executing update: {query} with params: {params}")
            cursor.execute(query, params)
            conn.commit()
            rowcount = cursor.rowcount
            lastrowid = cursor.lastrowid
            log.debug(
                f"Update executed successfully. Rows affected: {rowcount}, Last Row ID: {lastrowid}")
            return lastrowid if lastrowid is not None and lastrowid > 0 else rowcount
        except sqlite3.Error as e:
            log.error(
                f"Error executing update: {query} | Params: {params} | Error: {e}", exc_info=True)
            conn.rollback()  # Rollback on error
            return None
        finally:
            if cursor:
                cursor.close()
            conn.close()
            log.debug("Closed connection after execute_update.")

    def log_trade(self, order_data: dict) -> Optional[int]:
        """
        Logs a trade record to the 'trades' table.

        Args:
            order_data (dict): A dictionary containing trade details. Expected keys match
                               columns in the 'trades' table (or are convertible).
                               Numerical values (price, quantity, etc.) should ideally be
                               passed as strings for direct insertion into TEXT columns.

        Returns:
            int or None: The trade_id of the inserted record, or None on failure.
        """
        required_keys = ['order_id', 'symbol', 'side', 'order_type',
                         'status', 'price', 'quantity', 'timestamp', 'source']
        if not all(key in order_data for key in required_keys):
            log.error(
                f"Missing required keys in order_data for log_trade: {required_keys}. Data: {order_data}")
            return None

        sql = """
            INSERT INTO trades (
                order_id, client_order_id, symbol, side, order_type, status, price,
                quantity, commission, commission_asset, notional_value, timestamp,
                is_maker, strategy, source, confidence_score, grid_level,
                related_trade_id, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            order_data.get('order_id'),
            order_data.get('client_order_id'),
            order_data.get('symbol'),
            order_data.get('side'),
            order_data.get('order_type'),
            order_data.get('status'),
            str(order_data.get('price')),
            str(order_data.get('quantity')),
            str(order_data.get('commission')) if order_data.get(
                'commission') is not None else None,
            order_data.get('commission_asset'),
            str(order_data.get('notional_value')) if order_data.get(
                'notional_value') is not None else None,
            order_data.get('timestamp'),
            order_data.get('is_maker'),
            order_data.get('strategy'),
            order_data.get('source'),
            order_data.get('confidence_score'),
            order_data.get('grid_level'),
            order_data.get('related_trade_id'),
            order_data.get('notes')
        )

        last_row_id = self.execute_update(sql, params)
        if last_row_id is not None:
            log.info(
                f"Successfully logged trade {order_data.get('symbol')} OrderID {order_data.get('order_id')} with trade_id {last_row_id}.")
            return last_row_id
        else:
            log.error(f"Failed to log trade: {order_data}")
            return None


# --- Example Usage (when run directly via python -m src.db.manager) ---
if __name__ == '__main__':
    # --- Imports specific to the test block ---
    from datetime import datetime, timezone
    from decimal import Decimal  # Needed for the Decimal conversion test
    # -----------------------------------------

    # Setup basic logging for direct script execution test
    logging.basicConfig(
        level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log.info("--- Testing DatabaseManager ---")

    db_manager = DatabaseManager()

    log.info(
        "\n--- Testing Basic Query (Should fetch 0 rows initially unless run before) ---")
    results = db_manager.execute_query("SELECT * FROM trades LIMIT 5")
    if results is not None:
        log.info(
            f"Initial query fetched {len(results)} rows from 'trades' table.")
    else:
        log.error("Failed to execute initial query.")

    log.info("\n--- Testing Dummy Trade Log ---")
    # Create some dummy data matching expected structure
    dummy_trade = {
        'order_id': 'TEST_ORDER_123',
        'client_order_id': 'TEST_CLIENT_ID_456',
        'symbol': 'BTCUSD',
        'side': 'BUY',
        'order_type': 'LIMIT',
        'status': 'FILLED',
        'price': '65000.50',  # Pass as string
        'quantity': '0.001',  # Pass as string
        'commission': '0.065',  # Pass as string
        'commission_asset': 'USD',
        'notional_value': '65.0005',  # Pass as string
        # Milliseconds UTC
        'timestamp': int(datetime.now(timezone.utc).timestamp() * 1000),
        'is_maker': False,
        'strategy': 'test_strategy',
        'source': 'live',  # Or 'backtest'/'paper'
        'confidence_score': 0.75,
        'grid_level': 1,
        'related_trade_id': None,
        'notes': 'This is a test trade log entry.'
    }
    trade_id = db_manager.log_trade(dummy_trade)

    if trade_id:
        log.info(f"Dummy trade logged successfully with trade_id: {trade_id}")

        log.info("\n--- Testing Query After Insert ---")
        results_after = db_manager.execute_query(
            "SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
        if results_after:
            log.info(f"Fetched trade after insert: {results_after[0]}")
            # Note: Values retrieved from TEXT columns will be strings initially.
            # Code using this needs to convert back to Decimal, e.g., Decimal(results_after[0][7]) for price
            # Index 7 corresponds to price column
            retrieved_price_str = results_after[0][7]
            log.info(f"Retrieved price (as string): {retrieved_price_str}")
            try:
                # Need Decimal imported here for test
                retrieved_price_decimal = Decimal(retrieved_price_str)
                log.info(
                    f"Retrieved price (converted to Decimal): {retrieved_price_decimal} (Type: {type(retrieved_price_decimal)})")
            except Exception as e:
                log.error(
                    f"Failed to convert retrieved price string back to Decimal: {e}")

        else:
            log.error("Failed to fetch trade after insert.")

        log.info("\n--- Testing Update/Delete (Optional, Commented Out) ---")
        # Example: Update notes for the trade
        # update_result = db_manager.execute_update("UPDATE trades SET notes = ? WHERE trade_id = ?", ("Updated test notes.", trade_id))
        # if update_result is not None:
        #     log.info(f"Update affected {update_result} rows.")
        # # Be careful with delete tests if you want to keep the data
        # delete_result = db_manager.execute_update("DELETE FROM trades WHERE trade_id = ?", (trade_id,))
        # if delete_result is not None:
        #     log.info(f"Delete affected {delete_result} rows.")

    else:
        log.error("Failed to log dummy trade.")

    log.info("\n--- DatabaseManager Test Complete ---")
