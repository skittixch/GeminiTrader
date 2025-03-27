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
  is12HourFormat: false, // *** ADDED: Default to 24-hour format ***
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
  lastTickerPrice: null,
};

export function updateState(newState) {
  Object.assign(chartState, newState);
}
export function getState() {
  return { ...chartState };
}
export default chartState;
