// js/state.js
import * as config from "./config.js";

const chartState = {
  fullData: [],
  visibleStartIndex: 0,
  visibleEndIndex: 0,
  minVisiblePrice: 0,
  maxVisiblePrice: 1,
  isLogScale: false,
  currentGranularity: config.DEFAULT_GRANULARITY,
  is12HourFormat: false, // Default to 24-hour format
  isPanning: false,
  isDraggingYAxis: false,
  isDraggingXAxis: false,
  panStartX: 0,
  panStartY: 0,
  panStartVisibleIndex: 0,
  panStartVisibleCount: 0,
  panStartMinPrice: 0,
  panStartMaxPrice: 0,
  lastDrawTime: 0,
  lastTickerPrice: null, // Store last known ticker price (for main chart indicator)
  latestPrices: new Map(), // <<<--- ADDED: Map to store latest price for each asset { 'BTC': 65000.12, 'ETH': 3400.50, ... }
};

export function updateState(newState) {
  Object.assign(chartState, newState);
}
export function getState() {
  return { ...chartState };
}
// Helper to update a single price in the map
export function updateLatestPrice(currencyCode, price) {
  if (
    currencyCode &&
    typeof currencyCode === "string" &&
    price !== null &&
    Number.isFinite(price)
  ) {
    chartState.latestPrices.set(currencyCode.toUpperCase(), price);
    // console.log(`Updated price for ${currencyCode}: ${price}`); // Optional debug
  }
}

export default chartState;
