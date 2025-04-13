-- src/db/schema.sql

-- Table for storing trade execution details from live trading or backtests
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,         -- Event timestamp (Unix Milliseconds)
    backtest_id TEXT,                   -- Identifier for the backtest run (NULL for live trades)
    symbol TEXT NOT NULL,               -- Trading symbol (e.g., BTCUSD)
    orderId TEXT UNIQUE NOT NULL,       -- Exchange Order ID (or unique simulated ID)
    clientOrderId TEXT,                 -- User-defined order ID
    price TEXT NOT NULL,                -- Execution price (Storing as TEXT for Decimal precision)
    origQty TEXT NOT NULL,              -- Original order quantity (Storing as TEXT)
    executedQty TEXT NOT NULL,          -- Filled quantity (Storing as TEXT)
    cumulativeQuoteQty TEXT,            -- Total quote amount filled (Storing as TEXT)
    avgFillPrice TEXT,                  -- Average fill price if available (Storing as TEXT)
    status TEXT,                        -- Order status (e.g., FILLED, CANCELED)
    timeInForce TEXT,                   -- Time in force (e.g., GTC)
    type TEXT,                          -- Order type (e.g., LIMIT, MARKET)
    side TEXT NOT NULL,                 -- Order side (BUY or SELL)
    commission TEXT,                    -- Commission paid (Storing as TEXT)
    commissionAsset TEXT,               -- Asset commission was paid in
    isMaker BOOLEAN,                    -- True if the trade was a maker trade
    source TEXT DEFAULT 'live',         -- 'live' or 'backtest'
    confidence_score REAL               -- Optional confidence score at time of trade (Storing as REAL/float)
);

-- Indexes for faster querying
CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades (timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades (symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_orderId ON trades (orderId); -- Already unique, but index helps lookups
CREATE INDEX IF NOT EXISTS idx_trades_backtest_id ON trades (backtest_id); -- Index for backtest analysis
CREATE INDEX IF NOT EXISTS idx_trades_source ON trades (source);