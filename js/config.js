// js/config.js

// Chart configuration constants
export const ZOOM_FACTOR_X = 0.1;
export const ZOOM_FACTOR_Y = 0.1;
export const MIN_VISIBLE_CANDLES = 5;
export const DEFAULT_RESET_CANDLE_COUNT = 100;
export const MIN_PRICE_RANGE_SPAN = 0.1; // Smallest linear price diff allowed
export const Y_AXIS_PRICE_PADDING_FACTOR = 0.05;
export const Y_AXIS_DRAG_SENSITIVITY = 2.0;
export const X_AXIS_DRAG_SENSITIVITY = 2.0;
export const MOUSE_MOVE_THROTTLE = 16; // ~60fps
export const DEBOUNCE_DELAY = 100; // Resize debounce
export const TOOLTIP_SHOW_DELAY = 300; // ms delay before showing tooltip
export const TOOLTIP_HIDE_DELAY = 100; // ms delay before hiding tooltip

// API Defaults (used in main.js)
export const DEFAULT_GRANULARITY = 3600; // 1 hour (must be a number)
export const DEFAULT_PRODUCT_ID = "BTC-USD"; // This should be a string
