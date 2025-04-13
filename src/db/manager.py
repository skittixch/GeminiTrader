# src/db/manager.py

import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
import threading

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
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_tables_if_not_exist()
        logger.info(f"DBManager initialized for database: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Gets a thread-local database connection."""
        if not hasattr(local_storage, 'connection') or local_storage.connection is None:
            try:
                # Use detect_types to handle Decimal conversion potentially
                # sqlite3.register_adapter(Decimal, str)
                # sqlite3.register_converter("DECIMAL", lambda b: Decimal(b.decode('utf-8')))
                # Note: Direct Decimal support can be tricky; storing as TEXT is often safer.
                local_storage.connection = sqlite3.connect(
                    self.db_path,
                    detect_types=sqlite3.PARSE_DECLTYPES,
                    check_same_thread=False  # Required for thread-local but manage manually
                )
                # Set ROW factory for easy dict access, but it might interfere with detect_types
                # local_storage.connection.row_factory = sqlite3.Row
                logger.debug(
                    f"New DB connection established for thread {threading.current_thread().name}")
            except sqlite3.Error as e:
                logger.exception(
                    f"Failed to connect to database {self.db_path}: {e}")
                raise
        return local_storage.connection

    def close_connection(self):
        """Closes the thread-local database connection if it exists."""
        if hasattr(local_storage, 'connection') and local_storage.connection is not None:
            local_storage.connection.close()
            local_storage.connection = None
            logger.debug(
                f"DB connection closed for thread {threading.current_thread().name}")

    def _execute_sql(self, sql: str, params: Optional[Tuple] = None, fetch_one: bool = False, fetch_all: bool = False, commit: bool = False) -> Any:
        """Executes SQL queries with error handling and optional fetching/committing."""
        conn = self._get_connection()
        cursor = conn.cursor()
        result = None
        try:
            cursor.execute(sql, params or ())
            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()

            if commit:
                conn.commit()
            logger.debug(
                f"Executed SQL: {sql} | Params: {params} | Commit: {commit}")
            return result
        except sqlite3.Error as e:
            logger.exception(
                f"Database error executing SQL: {sql} | Params: {params} | Error: {e}")
            if commit:  # Attempt rollback on error during commit operations
                try:
                    conn.rollback()
                    logger.warning("Transaction rolled back due to error.")
                except sqlite3.Error as rb_e:
                    logger.error(f"Failed to rollback transaction: {rb_e}")
            # Do not close connection here, let the caller manage lifecycle or rely on thread end
            return None  # Indicate failure

    def _create_tables_if_not_exist(self):
        """Creates the necessary database tables if they don't already exist."""
        # Load schema from schema.sql (assuming it's adjacent or path known)
        schema_path = Path(__file__).parent / 'schema.sql'
        if not schema_path.exists():
            logger.error(f"Database schema file not found at: {schema_path}")
            # Define fallback schema inline if file missing (less ideal)
            fallback_schema = """
             CREATE TABLE IF NOT EXISTS trades (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 timestamp INTEGER NOT NULL, -- Unix Milliseconds
                 backtest_id TEXT,           -- Identifier for backtest run
                 symbol TEXT NOT NULL,
                 orderId TEXT UNIQUE NOT NULL,
                 clientOrderId TEXT,
                 price TEXT NOT NULL,        -- Store as TEXT for Decimal precision
                 origQty TEXT NOT NULL,      -- Store as TEXT
                 executedQty TEXT NOT NULL,  -- Store as TEXT
                 cumulativeQuoteQty TEXT,    -- Store as TEXT
                 avgFillPrice TEXT,          -- Store as TEXT
                 status TEXT,
                 timeInForce TEXT,
                 type TEXT,
                 side TEXT NOT NULL,
                 commission TEXT,            -- Store as TEXT
                 commissionAsset TEXT,
                 isMaker BOOLEAN,
                 source TEXT DEFAULT 'live', -- 'live' or 'backtest'
                 confidence_score REAL       -- Optional confidence score at time of trade
             );

             CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades (timestamp);
             CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades (symbol, timestamp);
             CREATE INDEX IF NOT EXISTS idx_trades_backtest_id ON trades (backtest_id);
             """
            logger.warning("Using fallback schema definition.")
            sql_commands = fallback_schema.split(';')
        else:
            try:
                with open(schema_path, 'r') as f:
                    schema_content = f.read()
                # Split SQL commands correctly, handling potential comments or empty lines
                sql_commands = [cmd.strip()
                                for cmd in schema_content.split(';') if cmd.strip()]
            except Exception as e:
                logger.exception(
                    f"Failed to read schema file {schema_path}: {e}")
                return

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            for command in sql_commands:
                if command:  # Ensure command is not empty
                    logger.debug(f"Executing schema command: {command}")
                    cursor.execute(command)
            conn.commit()
            logger.info("Database tables checked/created successfully.")
        except sqlite3.Error as e:
            logger.exception(f"Error creating database tables: {e}")
            conn.rollback()
        # Don't close connection here

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
                int(trade_data['time']),  # Ensure integer timestamp
                trade_data.get('backtest_id'),
                trade_data['symbol'],
                str(trade_data['orderId']),
                trade_data.get('clientOrderId'),
                str(trade_data['price']),  # Store price as string
                str(trade_data['origQty']),  # Store qty as string
                # Use origQty if executed not present
                str(trade_data.get('executedQty', trade_data['origQty'])),
                str(trade_data.get('cumulativeQuoteQty')),
                # Use price if avg not present
                str(trade_data.get('avgFillPrice', trade_data['price'])),
                trade_data.get('status'),
                trade_data.get('timeInForce'),
                trade_data.get('type'),
                trade_data['side'],
                # Store commission as string
                str(trade_data.get('commission')),
                trade_data.get('commissionAsset'),
                bool(trade_data.get('isMaker', False)),  # Ensure boolean
                trade_data.get('source', 'live'),
                float(trade_data['confidence_score']) if trade_data.get(
                    'confidence_score') is not None else None  # Store as REAL/float
            )
            self._execute_sql(sql, params, commit=True)
            logger.debug(f"Successfully logged trade {trade_data['orderId']}")
        except KeyError as e:
            logger.error(
                f"Missing required key in trade_data for logging: {e}. Data: {trade_data}")
        except Exception as e:
            logger.error(
                f"Failed to log trade {trade_data.get('orderId', 'N/A')}: {e}")

    def get_trades(self, symbol: Optional[str] = None, start_time: Optional[int] = None, end_time: Optional[int] = None, backtest_id: Optional[str] = None) -> List[Dict]:
        """
        Retrieves trades from the database, optionally filtered.

        Args:
            symbol (Optional[str]): Filter by symbol.
            start_time (Optional[int]): Filter by start timestamp (Unix millis).
            end_time (Optional[int]): Filter by end timestamp (Unix millis).
            backtest_id (Optional[str]): Filter by backtest ID.

        Returns:
            List[Dict]: A list of trade dictionaries. Returns empty list on error.
                        Decimal values are returned as strings and need conversion.
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
            filters.append("backtest_id = ?")
            params.append(backtest_id)

        if filters:
            base_sql += " AND " + " AND ".join(filters)

        base_sql += " ORDER BY timestamp ASC"

        rows = self._execute_sql(base_sql, tuple(params), fetch_all=True)

        if rows is None:  # Indicates an error occurred during execution
            return []

        # Convert rows to dictionaries (if row_factory wasn't set)
        # Need to manually get column names if not using row_factory
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA table_info(trades)")
            columns = [column[1] for column in cursor.fetchall()]
        except sqlite3.Error:
            logger.error("Could not retrieve column names for trades table.")
            return []  # Cannot form dictionaries without column names

        results = [dict(zip(columns, row)) for row in rows]

        # Optional: Convert numeric strings back to Decimal here if needed by caller
        # for trade in results:
        #     for key in ['price', 'origQty', 'executedQty', 'cumulativeQuoteQty', 'avgFillPrice', 'commission']:
        #         if trade.get(key) is not None:
        #             try:
        #                 trade[key] = Decimal(trade[key])
        #             except InvalidOperation:
        #                 logger.warning(f"Could not convert {key}='{trade[key]}' back to Decimal for trade {trade.get('id')}")
        #     # Convert confidence score back to Decimal too? Or keep as float?
        #     if trade.get('confidence_score') is not None:
        #          trade['confidence_score'] = Decimal(str(trade['confidence_score']))

        return results


# Example usage (typically not run directly like this)
if __name__ == "__main__":
    # Setup basic logging for testing this module
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
    # Define path relative to project root (assuming script is run from project root via -m)
    project_root_db = Path(__file__).parent.parent.parent
    db_file_path = project_root_db / "data" / "db" / "test_geminitrader.db"

    try:
        manager = DBManager(db_path=str(db_file_path))

        # Test logging a trade
        mock_trade = {
            # Use file mod time as example timestamp
            'time': int(Path.cwd().stat().st_mtime * 1000),
            'backtest_id': 'test_run_123',
            'symbol': 'BTCUSD',
            'orderId': f'test_{int(Path.cwd().stat().st_mtime * 1e6)}',
            'clientOrderId': 'test_client_id_1',
            'price': '65000.50',  # Pass as string
            'origQty': '0.001',  # Pass as string
            'executedQty': '0.001',
            'cumulativeQuoteQty': '65.0005',
            'avgFillPrice': '65000.50',
            'status': 'FILLED',
            'timeInForce': 'GTC',
            'type': 'LIMIT',
            'side': 'BUY',
            'commission': '0.065',
            'commissionAsset': 'USD',
            'isMaker': True,
            'source': 'backtest',
            'confidence_score': 0.75
        }
        logger.info(f"Attempting to log mock trade: {mock_trade['orderId']}")
        manager.log_trade(mock_trade)

        # Test retrieving trades
        logger.info("Attempting to retrieve trades...")
        retrieved_trades = manager.get_trades(
            symbol='BTCUSD', backtest_id='test_run_123')

        if retrieved_trades:
            logger.info(f"Retrieved {len(retrieved_trades)} trades:")
            # Print first retrieved trade
            print(retrieved_trades[0])
            # Verify types (should be strings for decimals, float for confidence)
            first_trade = retrieved_trades[0]
            print(f"  Price type: {type(first_trade.get('price'))}")
            print(f"  Qty type: {type(first_trade.get('origQty'))}")
            print(
                f"  Confidence type: {type(first_trade.get('confidence_score'))}")
        else:
            logger.warning("No trades retrieved.")

    except Exception as e:
        logger.exception(f"An error occurred during DBManager test: {e}")
    finally:
        # Ensure connection is closed if manager was created
        if 'manager' in locals() and manager:
            manager.close_connection()
            logger.info("Test DB connection closed.")

# File path: src/db/manager.py
