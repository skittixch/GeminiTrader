# src/db/manager.py

import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal, InvalidOperation # Added InvalidOperation
import threading
import re # Import regex for potentially better comment handling if needed

logger = logging.getLogger(__name__)

# Use a thread-local storage for connections to ensure thread safety if used concurrently
local_storage = threading.local()

class DBManager:
    """
    Manages the connection to the SQLite database and provides methods
    for interacting with trade and potentially other relevant data.
    Ensures thread safety for connections.
    """
    def __init__(self, db_path: str):
        """
        Initializes the DBManager.

        Args:
            db_path (str): The full path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        self._create_tables_if_not_exist() # Call table creation on init
        logger.info(f"DBManager initialized for database: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Gets a thread-local database connection."""
        connection = getattr(local_storage, 'connection', None)
        if connection is None:
            try:
                # Note: Direct Decimal support can be tricky; storing as TEXT is often safer.
                connection = sqlite3.connect(
                    self.db_path,
                    detect_types=sqlite3.PARSE_DECLTYPES,
                    check_same_thread=False # Required for thread-local but manage manually
                )
                # Set ROW factory AFTER connection for easy dict access
                connection.row_factory = sqlite3.Row
                setattr(local_storage, 'connection', connection)
                logger.debug(f"New DB connection established for thread {threading.current_thread().name}")
            except sqlite3.Error as e:
                logger.exception(f"Failed to connect to database {self.db_path}: {e}")
                raise
        return connection

    def close_connection(self):
        """Closes the thread-local database connection if it exists."""
        connection = getattr(local_storage, 'connection', None)
        if connection is not None:
            connection.close()
            setattr(local_storage, 'connection', None)
            logger.debug(f"DB connection closed for thread {threading.current_thread().name}")

    def _execute_sql(self, sql: str, params: Optional[Tuple] = None, fetch_one: bool = False, fetch_all: bool = False, commit: bool = False) -> Any:
        """Executes SQL queries with error handling and optional fetching/committing."""
        conn = self._get_connection()
        result = None
        try:
            cursor = conn.execute(sql, params or ()) # Use connection.execute directly
            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()

            if commit:
                conn.commit()
            # logger.debug(f"Executed SQL: {sql} | Params: {params} | Commit: {commit}") # Reduce noise
            return result
        except sqlite3.Error as e:
            # Provide more context in the error log
            err_msg = f"Database error executing SQL: Error={e}\n"
            err_msg += f"  SQL: {sql}\n"
            if params:
                 err_msg += f"  Params: {params}"
            logger.error(err_msg)
            # logger.exception("SQL Execution Traceback:") # Optional full traceback

            if commit: # Attempt rollback on error during commit operations
                try:
                    conn.rollback()
                    logger.warning("Transaction rolled back due to error.")
                except sqlite3.Error as rb_e:
                    logger.error(f"Failed to rollback transaction: {rb_e}")
            return None # Indicate failure

    def _create_tables_if_not_exist(self):
        """Creates the necessary database tables if they don't already exist."""
        schema_path = Path(__file__).parent / 'schema.sql'
        sql_commands = []

        if schema_path.exists():
            logger.info(f"Found schema file at: {schema_path}. Reading commands.")
            try:
                with open(schema_path, 'r') as f:
                    schema_content = f.read()

                # --- CORRECTED SCHEMA PARSING ---
                # Split by semicolon first, then clean comments from each statement
                sql_commands = []
                for statement in schema_content.split(';'):
                    # Remove block comments /* ... */ if any (simple version)
                    statement = re.sub(r'/\*.*?\*/', '', statement, flags=re.DOTALL)
                    # Remove line comments -- ... and empty lines
                    cleaned_statement = '\n'.join(
                        line for line in statement.splitlines() if line.strip() and not line.strip().startswith('--')
                    ).strip()
                    if cleaned_statement: # Only add if there's SQL left
                        sql_commands.append(cleaned_statement)
                # --- END CORRECTION ---

                if not sql_commands:
                     logger.error("Schema file is empty or contains no valid SQL commands after cleaning.")
            except Exception as e:
                logger.exception(f"Failed to read or parse schema file {schema_path}: {e}")
                sql_commands = [] # Ensure empty list to trigger fallback
        else:
             logger.warning(f"Database schema file not found at: {schema_path}. Using fallback schema.")

        # Define fallback schema inline ONLY if file reading failed or file doesn't exist
        if not sql_commands:
             fallback_schema = """
             CREATE TABLE IF NOT EXISTS trades (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 timestamp INTEGER NOT NULL,
                 backtest_id TEXT,           -- Included in fallback
                 symbol TEXT NOT NULL,
                 orderId TEXT UNIQUE NOT NULL,
                 clientOrderId TEXT,
                 price TEXT NOT NULL,
                 origQty TEXT NOT NULL,
                 executedQty TEXT NOT NULL,
                 cumulativeQuoteQty TEXT,
                 avgFillPrice TEXT,
                 status TEXT,
                 timeInForce TEXT,
                 type TEXT,
                 side TEXT NOT NULL,
                 commission TEXT,
                 commissionAsset TEXT,
                 isMaker BOOLEAN,
                 source TEXT DEFAULT 'live',
                 confidence_score REAL
             );

             CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades (timestamp);
             CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades (symbol, timestamp);
             CREATE INDEX IF NOT EXISTS idx_trades_backtest_id ON trades (backtest_id);
             CREATE INDEX IF NOT EXISTS idx_trades_source ON trades (source);
             CREATE INDEX IF NOT EXISTS idx_trades_orderId ON trades (orderId);
             """
             logger.warning("Using fallback schema definition.")
             # Parse the fallback schema correctly
             sql_commands = []
             for statement in fallback_schema.split(';'):
                 cleaned_statement = '\n'.join(
                     line for line in statement.splitlines() if line.strip() and not line.strip().startswith('--')
                 ).strip()
                 if cleaned_statement:
                     sql_commands.append(cleaned_statement)

        if not sql_commands:
             logger.error("No SQL commands found in schema file or fallback. Cannot create tables.")
             return

        # Execute commands using _execute_sql for consistency and error handling
        logger.info(f"Executing {len(sql_commands)} schema commands...")
        all_successful = True
        for command in sql_commands:
            logger.debug(f"Executing schema command: {command}")
            # Commit each schema change; IF NOT EXISTS handles reruns mostly gracefully
            result = self._execute_sql(command, commit=True)
            # The execute function returns the cursor on success for non-select, None on error
            # Let's check if None was explicitly returned due to handled error
            if result is None:
                 # We need a way to differentiate actual execution errors from "table already exists" etc.
                 # This basic check isn't perfect. A better way might be needed if IF NOT EXISTS isn't used.
                 # For now, assume _execute_sql logs the specific error.
                 logger.warning(f"Execution of schema command may have failed (check logs): {command}")
                 # We won't set all_successful to False just for this, as IF NOT EXISTS is permissive
                 # all_successful = False

        # We can't reliably tell if all *needed* operations succeeded with IF NOT EXISTS
        # So we just log completion. User should check logs for specific errors.
        logger.info("Database tables check/creation process complete.")


    def log_trade(self, trade_data: Dict):
        """
        Logs a single trade into the database.

        Args:
            trade_data (Dict): A dictionary containing trade details, matching
                               the columns in the 'trades' table (or convertible).
                               Keys should match column names. Values will be adapted.
        """
        # Map dictionary keys to table columns, ensure all required fields are present
        # Convert Decimals to strings before insertion
        sql = """
        INSERT INTO trades (
            timestamp, backtest_id, symbol, orderId, clientOrderId, price,
            origQty, executedQty, cumulativeQuoteQty, avgFillPrice, status,
            timeInForce, type, side, commission, commissionAsset, isMaker,
            source, confidence_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            params = (
                int(trade_data['time']), # Ensure integer timestamp
                trade_data.get('backtest_id'), # Included
                trade_data['symbol'],
                str(trade_data['orderId']),
                trade_data.get('clientOrderId'),
                str(trade_data['price']), # Store price as string
                str(trade_data['origQty']), # Store qty as string
                str(trade_data.get('executedQty', trade_data['origQty'])), # Use origQty if executed not present
                str(trade_data.get('cumulativeQuoteQty')),
                str(trade_data.get('avgFillPrice', trade_data['price'])), # Use price if avg not present
                trade_data.get('status'),
                trade_data.get('timeInForce'),
                trade_data.get('type'),
                trade_data['side'],
                str(trade_data.get('commission')), # Store commission as string
                trade_data.get('commissionAsset'),
                bool(trade_data.get('isMaker', False)), # Ensure boolean
                trade_data.get('source', 'live'),
                float(trade_data['confidence_score']) if trade_data.get('confidence_score') is not None else None # Store as REAL/float
            )
            # Use execute_sql which handles errors and logging
            result = self._execute_sql(sql, params, commit=True)
            if result is not None: # Check if execution succeeded
                 # Use DEBUG level for successful logs to reduce verbosity
                 logger.debug(f"Successfully logged trade {trade_data['orderId']}")
            # Error is logged within _execute_sql

        except KeyError as e:
            logger.error(f"Missing required key in trade_data for logging: {e}. Data: {trade_data}")
        except Exception as e:
             logger.exception(f"Unexpected error preparing data for trade log {trade_data.get('orderId', 'N/A')}: {e}")


    def get_trades(self, symbol: Optional[str] = None, start_time: Optional[int] = None, end_time: Optional[int] = None, backtest_id: Optional[str] = None) -> List[sqlite3.Row]:
        """
        Retrieves trades from the database, optionally filtered.

        Args:
            symbol (Optional[str]): Filter by symbol.
            start_time (Optional[int]): Filter by start timestamp (Unix millis).
            end_time (Optional[int]): Filter by end timestamp (Unix millis).
            backtest_id (Optional[str]): Filter by backtest ID.

        Returns:
            List[sqlite3.Row]: A list of trade Row objects (dict-like access).
                               Returns empty list on error.
        """
        base_sql = "SELECT * FROM trades WHERE 1=1"
        filters = []
        params = []

        if symbol:
            filters.append("symbol = ?")
            params.append(symbol)
        if start_time:
            filters.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            filters.append("timestamp <= ?")
            params.append(end_time)
        if backtest_id:
             filters.append("backtest_id = ?") # Column included in query
             params.append(backtest_id)

        if filters:
            base_sql += " AND " + " AND ".join(filters)

        base_sql += " ORDER BY timestamp ASC"

        rows = self._execute_sql(base_sql, tuple(params), fetch_all=True)

        if rows is None: # Indicates an error occurred during execution
             return []

        # Row objects are returned directly because row_factory was set
        return rows


# Example usage block
if __name__ == "__main__":
    from pathlib import Path # Ensure Path is imported if running standalone
    import time # Ensure time is imported

    log_dir = Path(__file__).parent.parent.parent / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "test_db_manager.log")
        ]
    )

    logger.info("Testing DBManager...")
    project_root_db = Path(__file__).parent.parent.parent
    # Use a distinct test DB name to avoid conflict with main DB
    db_file_path = project_root_db / "data" / "db" / "test_manager_standalone.db"

    # Delete existing test DB to ensure clean run
    if db_file_path.exists():
        logger.warning(f"Deleting existing standalone test database: {db_file_path}")
        try:
             db_file_path.unlink()
        except OSError as e:
             logger.error(f"Could not delete test database: {e}")


    manager = None # Define manager in this scope
    try:
        manager = DBManager(db_path=str(db_file_path))

        mock_trade = {
            'time': int(time.time() * 1000), # Current time
            'backtest_id': 'manager_test_123', # Test the column
            'symbol': 'ETHUSD',
            'orderId': f'mgr_test_{int(time.time() * 1e6)}',
            'clientOrderId': 'mgr_client_id_1',
            'price': '3500.10',
            'origQty': '0.05',
            'executedQty': '0.05',
            'cumulativeQuoteQty': '175.005',
            'avgFillPrice': '3500.10',
            'status': 'FILLED',
            'timeInForce': 'GTC',
            'type': 'LIMIT',
            'side': 'SELL',
            'commission': '0.175',
            'commissionAsset': 'USD',
            'isMaker': False,
            'source': 'test',
            'confidence_score': 0.95
        }
        logger.info(f"Attempting to log mock trade: {mock_trade['orderId']}")
        manager.log_trade(mock_trade)

        logger.info("Attempting to retrieve trades...")
        retrieved_trades = manager.get_trades(symbol='ETHUSD', backtest_id='manager_test_123')

        if retrieved_trades:
             logger.info(f"Retrieved {len(retrieved_trades)} trades:")
             first_trade = retrieved_trades[0]
             # Access using keys thanks to row_factory
             print(f"  ID: {first_trade['id']}")
             print(f"  Symbol: {first_trade['symbol']}")
             print(f"  Backtest ID: {first_trade['backtest_id']}") # Verify column exists
             print(f"  Price: {first_trade['price']} (Type: {type(first_trade['price'])})") # Should be str
             print(f"  Source: {first_trade['source']}")
        else:
             logger.warning("No trades retrieved.")

    except Exception as e:
         logger.exception(f"An error occurred during DBManager test: {e}")
    finally:
         if manager:
             manager.close_connection()
             logger.info("Test DB connection closed.")


# File path: src/db/manager.py