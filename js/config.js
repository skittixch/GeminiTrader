// js/config.js

// --- NEW: Define Theme Background Colors ---
export const LIGHT_MODE_BG_COLOR = "#f0f0f0"; // Default light theme background
export const DARK_MODE_BG_COLOR = "#190f11"; // Desired dark theme background
// --- End Theme Background Colors ---

// Chart configuration constants
export const ZOOM_FACTOR_X = 0.1;
export const ZOOM_FACTOR_Y = 0.1;
export const MIN_VISIBLE_CANDLES = 5;
export const DEFAULT_RESET_CANDLE_COUNT = 100;
export const MIN_PRICE_RANGE_SPAN = 0.1; // Smallest linear price diff allowed
export const Y_AXIS_PRICE_PADDING_FACTOR = 0.05; // Linear scale padding (used for initial load, maybe keep?)
export const Y_AXIS_LOG_PADDING_FACTOR = 0.08; // Multiplicative padding for log scale (used for initial load, maybe keep?)
export const Y_AXIS_RESET_FILL_FACTOR = 0.85; // Target fill % of chart height on double-click reset (e.g., 85%)
export const BALANCE_DUST_THRESHOLD_USD = 0.5; // USD value below which balances are considered "dust"
export const Y_AXIS_DRAG_SENSITIVITY = 2.0;
export const X_AXIS_DRAG_SENSITIVITY = 2.0;
export const MOUSE_MOVE_THROTTLE = 16; // ~60fps
export const DEBOUNCE_DELAY = 100; // Resize debounce
export const TOOLTIP_SHOW_DELAY = 300; // ms delay before showing tooltip
export const TOOLTIP_HIDE_DELAY = 100; // ms delay before hiding tooltip

// API Defaults (used in main.js)
export const DEFAULT_GRANULARITY = 3600; // 1 hour (must be a number)
export const DEFAULT_PRODUCT_ID = "BTC-USD"; // This should be a string
