// js/interactions.js

import * as config from "./config.js";
import state, { updateState } from "./state.js";
import * as dom from "./domElements.js";
import { redrawChart } from "./drawing.js";
import { calculateNiceStep } from "./utils.js";

const log = Math.log;
const exp = Math.exp;
const MIN_LOG_VALUE = 1e-9;
function safeLog(value) {
  return log(Math.max(MIN_LOG_VALUE, value));
}

export function handleZoom(event) {
  event.preventDefault();
  const chartRect = dom.chartArea.getBoundingClientRect();
  const mouseX = event.clientX - chartRect.left;
  const mouseY = event.clientY - chartRect.top;
  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;
  if (!chartHeight || !chartWidth) return;
  const zoomDirection = event.deltaY < 0 ? -1 : 1;
  let newState = {};

  const currentMinY = state.minVisiblePrice;
  const currentMaxY = state.maxVisiblePrice;
  if (state.isLogScale) {
    const logMin = safeLog(currentMinY);
    const logMax = safeLog(currentMaxY);
    const logRange = logMax - logMin;
    if (logRange > 0 && !isNaN(logRange)) {
      const logAtCursor = logMax - (mouseY / chartHeight) * logRange;
      const zoomAmountY = 1 + zoomDirection * config.ZOOM_FACTOR_Y;
      const newLogMin = logAtCursor - (logAtCursor - logMin) * zoomAmountY;
      const newLogMax = logAtCursor + (logMax - logAtCursor) * zoomAmountY;
      newState.minVisiblePrice = Math.max(MIN_LOG_VALUE, exp(newLogMin));
      newState.maxVisiblePrice = exp(newLogMax);
      if (newState.maxVisiblePrice / newState.minVisiblePrice < 1.001) {
        const midPrice = Math.sqrt(
          newState.minVisiblePrice * newState.maxVisiblePrice
        );
        newState.minVisiblePrice = midPrice / 1.0005;
        newState.maxVisiblePrice = midPrice * 1.0005;
      }
    }
  } else {
    const linearRange = currentMaxY - currentMinY;
    if (linearRange > 0) {
      const priceAtCursor = currentMaxY - (mouseY / chartHeight) * linearRange;
      const zoomAmountY = 1 + zoomDirection * config.ZOOM_FACTOR_Y;
      let newMin = priceAtCursor - (priceAtCursor - currentMinY) * zoomAmountY;
      let newMax = priceAtCursor + (currentMaxY - priceAtCursor) * zoomAmountY;
      if (newMax - newMin < config.MIN_PRICE_RANGE_SPAN) {
        const mid = (newMax + newMin) / 2;
        newMin = mid - config.MIN_PRICE_RANGE_SPAN / 2;
        newMax = mid + config.MIN_PRICE_RANGE_SPAN / 2;
      }
      newState.minVisiblePrice = Math.max(0, newMin);
      newState.maxVisiblePrice = newMax;
    }
  }

  const currentVisibleCount = state.visibleEndIndex - state.visibleStartIndex;
  if (currentVisibleCount > 0) {
    const indexAtCursor =
      state.visibleStartIndex + (mouseX / chartWidth) * currentVisibleCount;
    const zoomAmountX = 1 + zoomDirection * config.ZOOM_FACTOR_X;
    let newVisibleCount = Math.round(currentVisibleCount * zoomAmountX);
    newVisibleCount = Math.max(
      config.MIN_VISIBLE_CANDLES,
      Math.min(newVisibleCount, state.fullData.length * 5)
    );
    let newStartIndex = Math.round(
      indexAtCursor - (mouseX / chartWidth) * newVisibleCount
    );
    let newEndIndex = newStartIndex + newVisibleCount;
    newState.visibleStartIndex = newStartIndex;
    newState.visibleEndIndex = newEndIndex;
  }

  updateState(newState);
  requestAnimationFrame(redrawChart);
}

export function handleMouseMove(event) {
  if (!state.isPanning && !state.isDraggingYAxis && !state.isDraggingXAxis)
    return;
  const now = Date.now();
  if (now - state.lastDrawTime < config.MOUSE_MOVE_THROTTLE) return;
  let needsRedraw = false;
  let newState = {};

  if (state.isDraggingYAxis) {
    const deltaY = event.clientY - state.panStartY;
    const chartHeight = dom.chartArea.offsetHeight;
    if (!chartHeight) return;
    if (state.isLogScale) {
      const logMinStart = safeLog(state.panStartMinPrice);
      const logMaxStart = safeLog(state.panStartMaxPrice);
      const logRangeStart = logMaxStart - logMinStart;
      if (logRangeStart > 0 && !isNaN(logRangeStart)) {
        const midLogPrice = (logMaxStart + logMinStart) / 2;
        const scaleFactor = Math.pow(
          2,
          (deltaY / chartHeight) * config.Y_AXIS_DRAG_SENSITIVITY
        );
        let newLogRange = logRangeStart * scaleFactor;
        if (exp(newLogRange) < 1.001) newLogRange = log(1.001);
        const newLogMin = midLogPrice - newLogRange / 2;
        const newLogMax = midLogPrice + newLogRange / 2;
        const newMin = Math.max(MIN_LOG_VALUE, exp(newLogMin));
        const newMax = exp(newLogMax);
        if (
          Math.abs(newMin - state.minVisiblePrice) > 1e-9 ||
          Math.abs(newMax - state.maxVisiblePrice) > 1e-9
        ) {
          newState.minVisiblePrice = newMin;
          newState.maxVisiblePrice = newMax;
          needsRedraw = true;
        }
      }
    } else {
      const initialRange = state.panStartMaxPrice - state.panStartMinPrice;
      if (initialRange > 0) {
        const midPrice = (state.panStartMaxPrice + state.panStartMinPrice) / 2;
        const scaleFactor = Math.pow(
          2,
          (deltaY / chartHeight) * config.Y_AXIS_DRAG_SENSITIVITY
        );
        let newRange = initialRange * scaleFactor;
        newRange = Math.max(config.MIN_PRICE_RANGE_SPAN, newRange);
        const newMin = Math.max(0, midPrice - newRange / 2);
        const newMax = midPrice + newRange / 2;
        if (
          Math.abs(newMin - state.minVisiblePrice) > 1e-9 ||
          Math.abs(newMax - state.maxVisiblePrice) > 1e-9
        ) {
          newState.minVisiblePrice = newMin;
          newState.maxVisiblePrice = newMax;
          needsRedraw = true;
        }
      }
    }
  } else if (state.isDraggingXAxis) {
    const deltaX = event.clientX - state.panStartX;
    const chartWidth = dom.chartArea.offsetWidth;
    if (!chartWidth || state.panStartVisibleCount <= 0) return;
    const centerIndex =
      state.panStartVisibleIndex + state.panStartVisibleCount / 2;
    const scaleFactor = Math.pow(
      2,
      (deltaX / chartWidth) * config.X_AXIS_DRAG_SENSITIVITY
    );
    let newVisibleCount = Math.round(state.panStartVisibleCount * scaleFactor);
    newVisibleCount = Math.max(
      config.MIN_VISIBLE_CANDLES,
      Math.min(newVisibleCount, state.fullData.length * 5)
    );
    let newStartIndex = Math.round(centerIndex - newVisibleCount / 2);
    let newEndIndex = newStartIndex + newVisibleCount;
    if (
      newStartIndex !== state.visibleStartIndex ||
      newEndIndex !== state.visibleEndIndex
    ) {
      newState.visibleStartIndex = newStartIndex;
      newState.visibleEndIndex = newEndIndex;
      needsRedraw = true;
    }
  } else if (state.isPanning) {
    const deltaX = event.clientX - state.panStartX;
    const deltaY = event.clientY - state.panStartY;
    const chartHeight = dom.chartArea.offsetHeight;
    const chartWidth = dom.chartArea.offsetWidth;
    if (!chartWidth || !chartHeight) return;
    let changedX = false;
    let changedY = false;
    if (state.panStartVisibleCount > 0) {
      const indexDelta = (deltaX / chartWidth) * state.panStartVisibleCount;
      let newStartIndex = state.panStartVisibleIndex - Math.round(indexDelta);
      if (newStartIndex !== state.visibleStartIndex) {
        newState.visibleStartIndex = newStartIndex;
        newState.visibleEndIndex = newStartIndex + state.panStartVisibleCount;
        changedX = true;
      }
    }
    if (state.isLogScale) {
      const logMinStart = safeLog(state.panStartMinPrice);
      const logMaxStart = safeLog(state.panStartMaxPrice);
      const logRangeStart = logMaxStart - logMinStart;
      if (logRangeStart > 0 && !isNaN(logRangeStart)) {
        const logDelta = (deltaY / chartHeight) * logRangeStart;
        const newLogMin = logMinStart + logDelta;
        const newLogMax = logMaxStart + logDelta;
        const newMin = Math.max(MIN_LOG_VALUE, exp(newLogMin));
        const newMax = exp(newLogMax);
        if (
          Math.abs(newMin - state.minVisiblePrice) > 1e-9 ||
          Math.abs(newMax - state.maxVisiblePrice) > 1e-9
        ) {
          newState.minVisiblePrice = newMin;
          newState.maxVisiblePrice = newMax;
          changedY = true;
        }
      }
    } else {
      const initialPriceRange = state.panStartMaxPrice - state.panStartMinPrice;
      if (initialPriceRange > 0) {
        const priceDelta = (deltaY / chartHeight) * initialPriceRange;
        const newMinPrice = state.panStartMinPrice + priceDelta;
        const newMaxPrice = state.panStartMaxPrice + priceDelta;
        if (
          Math.abs(newMinPrice - state.minVisiblePrice) > 1e-9 ||
          Math.abs(newMaxPrice - state.maxVisiblePrice) > 1e-9
        ) {
          newState.minVisiblePrice = Math.max(0, newMinPrice);
          newState.maxVisiblePrice = newMaxPrice;
          changedY = true;
        }
      }
    }
    needsRedraw = changedX || changedY;
  }
  if (needsRedraw) {
    updateState({ ...newState, lastDrawTime: now });
    requestAnimationFrame(redrawChart);
  }
}

export function handleMouseDownChart(event) {
  updateState({
    isPanning: true,
    isDraggingYAxis: false,
    isDraggingXAxis: false,
    panStartX: event.clientX,
    panStartY: event.clientY,
    panStartVisibleIndex: state.visibleStartIndex,
    panStartMinPrice: state.minVisiblePrice,
    panStartMaxPrice: state.maxVisiblePrice,
    panStartVisibleCount: state.visibleEndIndex - state.visibleStartIndex,
  });
  dom.chartContainer.classList.add("panning");
}
export function handleMouseDownYAxis(event) {
  event.stopPropagation();
  updateState({
    isDraggingYAxis: true,
    isPanning: false,
    isDraggingXAxis: false,
    panStartY: event.clientY,
    panStartMinPrice: state.minVisiblePrice,
    panStartMaxPrice: state.maxVisiblePrice,
  });
}
export function handleMouseDownXAxis(event) {
  event.stopPropagation();
  updateState({
    isDraggingXAxis: true,
    isPanning: false,
    isDraggingYAxis: false,
    panStartX: event.clientX,
    panStartVisibleIndex: state.visibleStartIndex,
    panStartVisibleCount: state.visibleEndIndex - state.visibleStartIndex,
  });
}
export function handleMouseUpOrLeave(event) {
  if (state.isPanning || state.isDraggingYAxis || state.isDraggingXAxis) {
    updateState({
      isPanning: false,
      isDraggingYAxis: false,
      isDraggingXAxis: false,
    });
    dom.chartContainer.classList.remove("panning");
  }
}
let resizeTimeout;
export function handleResize() {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    requestAnimationFrame(redrawChart);
  }, config.DEBOUNCE_DELAY);
}

export function handleDoubleClick(event) {
  if (!state.fullData.length) return;
  const chartRect = dom.chartArea.getBoundingClientRect();
  const mouseX = event.clientX - chartRect.left;
  const chartWidth = dom.chartArea.offsetWidth;
  if (!chartWidth) return;
  const currentVisibleCount = state.visibleEndIndex - state.visibleStartIndex;
  const fractionalIndex =
    state.visibleStartIndex + (mouseX / chartWidth) * currentVisibleCount;
  let targetIndex = Math.round(fractionalIndex);
  targetIndex = Math.max(0, Math.min(targetIndex, state.fullData.length - 1));
  let newVisibleCount = Math.min(
    config.DEFAULT_RESET_CANDLE_COUNT,
    state.fullData.length
  );
  let newStartIndex = Math.round(targetIndex - newVisibleCount / 2);
  newStartIndex = Math.max(
    0,
    Math.min(newStartIndex, state.fullData.length - newVisibleCount)
  );
  let newEndIndex = Math.min(
    state.fullData.length,
    newStartIndex + newVisibleCount
  );
  newStartIndex = Math.max(0, newEndIndex - newVisibleCount);
  let newMin = Infinity,
    newMax = -Infinity;
  for (let i = newStartIndex; i < newEndIndex; i++) {
    if (!state.fullData[i] || state.fullData[i].length < 5) continue;
    newMin = Math.min(newMin, state.fullData[i][1]);
    newMax = Math.max(newMax, state.fullData[i][2]);
  }
  if (newMin === Infinity) {
    newMin = 0;
    newMax = 1;
  }
  const padding = Math.max(
    config.MIN_PRICE_RANGE_SPAN * 0.1,
    (newMax - newMin) * config.Y_AXIS_PRICE_PADDING_FACTOR
  );
  let newMinPrice = Math.max(0, newMin - padding);
  let newMaxPrice = newMax + padding;
  if (newMaxPrice - newMinPrice < config.MIN_PRICE_RANGE_SPAN) {
    const mid = (newMaxPrice + newMinPrice) / 2;
    newMinPrice = mid - config.MIN_PRICE_RANGE_SPAN / 2;
    newMaxPrice = mid + config.MIN_PRICE_RANGE_SPAN / 2;
  }
  updateState({
    visibleStartIndex: newStartIndex,
    visibleEndIndex: newEndIndex,
    minVisiblePrice: newMinPrice,
    maxVisiblePrice: newMaxPrice,
    isLogScale: false,
  });
  if (dom.logScaleToggle) dom.logScaleToggle.checked = false;
  requestAnimationFrame(redrawChart);
}

export function handleLogScaleToggle() {
  const isChecked = dom.logScaleToggle.checked;
  updateState({ isLogScale: isChecked });
  localStorage.setItem("logScalePref", isChecked);
  requestAnimationFrame(redrawChart);
}

export function attachInteractionListeners() {
  dom.chartContainer.addEventListener("wheel", handleZoom, { passive: false });
  dom.chartContainer.addEventListener("mousedown", handleMouseDownChart);
  dom.yAxisLabelsContainer.addEventListener("mousedown", handleMouseDownYAxis);
  dom.xAxisLabelsContainer.addEventListener("mousedown", handleMouseDownXAxis);
  window.addEventListener("mousemove", handleMouseMove);
  window.addEventListener("mouseup", handleMouseUpOrLeave);
  window.addEventListener("resize", handleResize);
  dom.chartContainer.addEventListener("dblclick", handleDoubleClick);
  if (dom.logScaleToggle) {
    dom.logScaleToggle.addEventListener("change", handleLogScaleToggle);
  } else {
    console.warn(
      "Log scale toggle element not found during listener attachment."
    );
  }
}
