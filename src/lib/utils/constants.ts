// FILE: src/lib/utils/constants.ts

// API Endpoints
export const API_BASE_URL = "http://localhost:5000/api"; // Your backend
export const WEBSOCKET_URL = "wss://ws-feed.exchange.coinbase.com";

// Chart Configuration
export const ZOOM_FACTOR_X = 0.1;
export const ZOOM_FACTOR_Y = 0.1;
export const MIN_VISIBLE_CANDLES = 10;
export const DEFAULT_RESET_CANDLE_COUNT = 100;
export const MIN_PRICE_RANGE_SPAN = 0.01; // Min linear price diff
export const Y_AXIS_PRICE_PADDING_FACTOR = 0.05; // Linear scale padding
export const Y_AXIS_LOG_PADDING_FACTOR = 0.08; // Log scale padding factor
export const Y_AXIS_RESET_FILL_FACTOR = 0.85; // Target fill % on reset
export const Y_AXIS_DRAG_SENSITIVITY = 2.0;
export const X_AXIS_DRAG_SENSITIVITY = 2.0;
export const MIN_LOG_VALUE = 1e-9; // Minimum value allowed for log calculations

// Interaction Timings & Throttling
export const MOUSE_MOVE_THROTTLE_MS = 16; // ~60fps for drag redraws
export const DEBOUNCE_RESIZE_MS = 100;
export const TOOLTIP_SHOW_DELAY_MS = 200;
export const TOOLTIP_HIDE_DELAY_MS = 100;
export const WS_LIVE_UPDATE_THROTTLE_MS = 250; // Chart redraw throttle for WS ticks
export const WS_BALANCE_UPDATE_THROTTLE_MS = 1500; // Balance UI throttle for WS ticks

// API Defaults
export const DEFAULT_GRANULARITY = 3600; // 1 hour (seconds)
export const DEFAULT_PRODUCT_ID = "BTC-USD";

// UI Configuration
export const BALANCE_DUST_THRESHOLD_USD = 0.50; // USD value for "dust" balances
export const LIGHT_MODE_BG_COLOR = "#f0f0f0";
export const DARK_MODE_BG_COLOR = "#0f0f19";
export const AXIS_LABEL_WIDTH_Y = 55; // px width of Y axis label area
export const AXIS_LABEL_HEIGHT_X = 40; // px height of X axis label area
export const VOLUME_CHART_HEIGHT = 80; // px height of volume chart area
export const MIN_PANE_HEIGHT_PX = 100; // For resizable panes