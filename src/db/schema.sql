-- GeminiTrader Database Schema v6.5 - SQLite

-- Table to store executed trades (both live and simulated)
CREATE TABLE IF NOT EXISTS trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique identifier for each trade record
    order_id TEXT NOT NULL UNIQUE,             -- Exchange's order ID (can be composite for grid fills)
    client_order_id TEXT UNIQUE,               -- Exchange's client order ID (if used)
    symbol TEXT NOT NULL,                      -- Trading pair (e.g., BTCUSD)
    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')), -- BUY or SELL
    order_type TEXT NOT NULL CHECK(order_type IN ('LIMIT', 'MARKET', 'STOP_LOSS_LIMIT', 'TAKE_PROFIT_LIMIT', 'GRID')), -- Type of order placed
    status TEXT NOT NULL,                      -- Order status (e.g., FILLED, PARTIALLY_FILLED, CANCELED, NEW)
    price TEXT NOT NULL,                       -- Execution price (Decimal stored as TEXT)
    quantity TEXT NOT NULL,                    -- Executed quantity (Decimal stored as TEXT)
    commission TEXT,                           -- Commission paid (Decimal stored as TEXT)
    commission_asset TEXT,                     -- Asset commission was paid in
    notional_value TEXT,                       -- Total value of trade (price * quantity) (Decimal stored as TEXT)
    timestamp INTEGER NOT NULL,                -- Execution time (Unix timestamp milliseconds UTC)
    is_maker BOOLEAN,                          -- True if maker, False if taker
    strategy TEXT,                             -- Strategy that generated the trade (e.g., 'geometric_grid', 'dca', 'time_stop')
    source TEXT NOT NULL CHECK(source IN ('live', 'backtest', 'paper')), -- live, backtest, paper
    confidence_score REAL,                     -- Confidence score at time of trade decision (0.0 to 1.0 or similar)
    grid_level INTEGER,                        -- Grid level number if applicable (e.g., 1, 2, 3...)
    related_trade_id INTEGER,                  -- Link to related trade (e.g., TP links to entry)
    notes TEXT                                 -- Any additional notes
);

-- Indexing for faster lookups
CREATE INDEX IF NOT EXISTS idx_trades_symbol_timestamp ON trades (symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_order_id ON trades (order_id);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades (strategy);


-- Table to store periodic portfolio value snapshots
CREATE TABLE IF NOT EXISTS portfolio_history (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL UNIQUE,          -- Snapshot time (Unix timestamp seconds UTC)
    total_value_usd TEXT NOT NULL,              -- Total estimated portfolio value in USD (Decimal as TEXT)
    free_usd TEXT NOT NULL,                     -- Free USD balance (Decimal as TEXT)
    locked_usd TEXT NOT NULL,                   -- Locked USD balance (Decimal as TEXT)
    asset_balances_json TEXT                    -- JSON string containing balances of all other assets { "BTC": {"free": "...", "locked": "..."}, ...}
);

-- Indexing for time-series analysis
CREATE INDEX IF NOT EXISTS idx_portfolio_history_timestamp ON portfolio_history (timestamp);


-- Table to track DCA execution history
CREATE TABLE IF NOT EXISTS dca_history (
    dca_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,          -- Time the DCA process was triggered (Unix timestamp seconds UTC)
    requested_usd_amount TEXT NOT NULL,      -- Initial USD amount intended for DCA (Decimal as TEXT)
    calculated_usd_amount TEXT NOT NULL,     -- Actual USD amount used after confidence modulation (Decimal as TEXT)
    target_asset TEXT NOT NULL,          -- Asset targeted for purchase (e.g., BTC)
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'FUNDING', 'EXECUTED', 'FAILED', 'SKIPPED')), -- Status of the DCA operation
    funding_source TEXT,                 -- e.g., 'Coinbase', 'Manual'
    exchange_trade_ids TEXT,             -- JSON list of trade_ids from 'trades' table if executed on exchange
    notes TEXT                           -- e.g., Reason for failure or skipping
);

-- Indexing
CREATE INDEX IF NOT EXISTS idx_dca_history_timestamp ON dca_history (timestamp);


-- Table to store snapshots of the configuration used (optional but useful)
CREATE TABLE IF NOT EXISTS config_history (
    config_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL UNIQUE,          -- Time the configuration was logged (Unix timestamp seconds UTC)
    config_hash TEXT NOT NULL UNIQUE,           -- Hash (e.g., SHA256) of the config content to detect changes
    config_content TEXT NOT NULL                -- Full configuration content (e.g., YAML or JSON string)
);


-- Table for storing asset metadata (categories, etc.) (Phase 4+)
CREATE TABLE IF NOT EXISTS asset_info (
    asset_symbol TEXT PRIMARY KEY,             -- Base asset symbol (e.g., BTC, ETH)
    category TEXT,                             -- e.g., Layer 1, DeFi, Meme, Infrastructure
    narrative TEXT,                            -- Current dominant narrative (e.g., AI, RWA)
    description TEXT,
    last_updated INTEGER                       -- Timestamp when info was last updated
);


-- Table for storing cached exchange filters (can reduce API calls) (Optional, alternative to file cache)
-- CREATE TABLE IF NOT EXISTS filters (
--     symbol TEXT PRIMARY KEY,
--     filters_json TEXT NOT NULL,                -- JSON string of the parsed filters dictionary
--     last_updated INTEGER NOT NULL
-- );


-- Table to store detected Support/Resistance zones (Phase 3+)
CREATE TABLE IF NOT EXISTS sr_zones (
    zone_id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    price_low TEXT NOT NULL,                    -- Lower bound of the zone (Decimal as TEXT)
    price_high TEXT NOT NULL,                   -- Upper bound of the zone (Decimal as TEXT)
    zone_type TEXT NOT NULL CHECK(zone_type IN ('SUPPORT', 'RESISTANCE')),
    strength_score REAL,                       -- Score based on touches, volume, recency (e.g., 0-1)
    first_detected_ts INTEGER,                  -- Timestamp when zone was first identified
    last_confirmed_ts INTEGER,                  -- Timestamp when zone was last confirmed by price action
    timeframe TEXT                             -- Timeframe the zone was detected on (e.g., 1h, 4h, 1d)
);

-- Indexing
CREATE INDEX IF NOT EXISTS idx_sr_zones_symbol_ts ON sr_zones (symbol, last_confirmed_ts);


-- Table to store detected Trendlines (Phase 3+)
CREATE TABLE IF NOT EXISTS trendlines (
    trendline_id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    start_ts INTEGER NOT NULL,                  -- Timestamp of the starting point
    start_price TEXT NOT NULL,                  -- Price at the starting point (Decimal as TEXT)
    end_ts INTEGER NOT NULL,                    -- Timestamp of the (most recent) ending point
    end_price TEXT NOT NULL,                    -- Price at the ending point (Decimal as TEXT)
    slope TEXT NOT NULL,                        -- Slope of the line (Decimal as TEXT)
    touches INTEGER DEFAULT 2,                  -- Number of confirmation touches
    reliability_score REAL,                    -- Score based on touches, length, slope consistency (e.g., 0-1)
    is_active BOOLEAN DEFAULT TRUE,             -- Flag if the trendline is currently considered active
    timeframe TEXT                             -- Timeframe the trendline was detected on
);

-- Indexing
CREATE INDEX IF NOT EXISTS idx_trendlines_symbol_active ON trendlines (symbol, is_active, end_ts);


-- Table to log confidence score over time (Phase 3+)
CREATE TABLE IF NOT EXISTS confidence_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,                 -- Timestamp of the score calculation (Unix timestamp seconds UTC)
    symbol TEXT NOT NULL,                       -- Symbol the score applies to
    confidence_score REAL NOT NULL,             -- The calculated confidence score (e.g., 0-1)
    contributing_factors_json TEXT              -- JSON detailing factors contributing to the score (e.g., {"rsi": 0.7, "macd": 0.5, "news": -0.2})
);

-- Indexing
CREATE INDEX IF NOT EXISTS idx_confidence_log_symbol_ts ON confidence_log (symbol, timestamp);

-- Add more tables as needed for NewsItems, NewsAnalysis, InfluencerPosts, etc. in later phases