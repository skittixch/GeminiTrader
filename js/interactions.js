// js/interactions.js

import * as config from "./config.js";
import state, { updateState } from "./state.js";
import * as dom from "./domElements.js";
import { redrawChart } from "./drawing.js";
import {
  calculateNiceStep,
  getYCoordinate,
  formatDate,
  formatTimestamp,
  getPriceFromYCoordinate,
} from "./utils.js";

// Tooltip State
let hoveredCandleIndex = null;
let tooltipShowTimeout = null;
let tooltipHideTimeout = null;

// Log Scale Helpers
const log = Math.log;
const exp = Math.exp;
const MIN_LOG_VALUE = 1e-9;
function safeLog(value) {
  return log(Math.max(MIN_LOG_VALUE, value));
}

// --- Tooltip Functions (Using Direct Style Manipulation) ---
function showTooltip(dataIndex, mouseX, mouseY) {
  if (!dom.chartTooltip) return;
  if (dataIndex < 0 || dataIndex >= state.fullData.length) {
    hideTooltip();
    return;
  }
  const candleData = state.fullData[dataIndex];
  if (!candleData || candleData.length < 6) {
    hideTooltip();
    return;
  }
  const [timestamp, low, high, open, close] = candleData;
  const chartRect = dom.chartArea.getBoundingClientRect();
  const chartHeight = dom.chartArea.offsetHeight;
  const chartContainerRect = dom.chartContainer.getBoundingClientRect();
  const dateStr = formatDate(timestamp);
  const timeStr = formatTimestamp(timestamp);
  const decimals =
    state.maxVisiblePrice - state.minVisiblePrice < 10
      ? close < 1
        ? 4
        : 2
      : close < 100
      ? 1
      : 0;
  dom.chartTooltip.innerHTML = `<div class="date">${dateStr}, ${timeStr}</div><div><span class="label">Open:</span> <span class="value">${open.toFixed(
    decimals
  )}</span></div><div><span class="label">High:</span> <span class="value">${high.toFixed(
    decimals
  )}</span></div><div><span class="label">Low:</span> <span class="value">${low.toFixed(
    decimals
  )}</span></div><div><span class="label">Close:</span> <span class="value">${close.toFixed(
    decimals
  )}</span></div>`;
  const tooltipElementHeight = dom.chartTooltip.offsetHeight;
  const tooltipElementWidth = dom.chartTooltip.offsetWidth;
  let tooltipY =
    mouseY + chartRect.top - chartContainerRect.top - tooltipElementHeight - 10;
  if (tooltipY < 10) {
    tooltipY = mouseY + chartRect.top - chartContainerRect.top + 20;
  }
  let tooltipX = mouseX + chartRect.left - chartContainerRect.left + 15;
  const rightBoundary =
    chartContainerRect.width -
    (dom.yAxisLabelsContainer?.offsetWidth || 55) -
    10;
  if (tooltipX + tooltipElementWidth > rightBoundary) {
    tooltipX =
      mouseX +
      chartRect.left -
      chartContainerRect.left -
      tooltipElementWidth -
      15;
  }
  if (tooltipX < 10) {
    tooltipX = 10;
  }
  dom.chartTooltip.style.left = `${tooltipX.toFixed(1)}px`;
  dom.chartTooltip.style.top = `${tooltipY.toFixed(1)}px`;
  dom.chartTooltip.style.display = "block";
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (!dom.chartTooltip) return;
      try {
        dom.chartTooltip.style.opacity = 1;
        dom.chartTooltip.style.visibility = "visible";
      } catch (e) {
        console.error(e);
      }
    });
  });
}

function hideTooltip() {
  if (dom.chartTooltip) {
    dom.chartTooltip.style.opacity = 0;
    dom.chartTooltip.style.visibility = "hidden";
    dom.chartTooltip.classList.remove("visible");
  }
  hoveredCandleIndex = null;
}

// --- Crosshair Update Functions ---
function updateCrosshair(mouseX, mouseY, chartHeight, chartWidth) {
  if (
    !dom.crosshairLineX ||
    !dom.crosshairLabelY ||
    mouseX === null ||
    mouseY === null ||
    chartHeight <= 0
  ) {
    hideCrosshair();
    return;
  }
  const priceAtCursor = getPriceFromYCoordinate(mouseY, chartHeight);
  const clampedMouseY = Math.max(0, Math.min(mouseY, chartHeight));
  if (priceAtCursor !== null && !isNaN(priceAtCursor)) {
    dom.crosshairLineX.style.top = `${clampedMouseY.toFixed(1)}px`;
    dom.crosshairLineX.style.display = "block";
    const priceRange = state.maxVisiblePrice - state.minVisiblePrice;
    const decimals =
      priceRange < 1 ? 4 : priceRange < 10 ? 2 : priceAtCursor < 100 ? 1 : 0;
    dom.crosshairLabelY.textContent = priceAtCursor.toFixed(
      Math.max(0, decimals)
    );
    dom.crosshairLabelY.style.top = `${clampedMouseY.toFixed(1)}px`;
    dom.crosshairLabelY.style.display = "block";
  } else {
    hideCrosshair();
  }
}

function hideCrosshair() {
  if (dom.crosshairLineX) dom.crosshairLineX.style.display = "none";
  if (dom.crosshairLabelY) dom.crosshairLabelY.style.display = "none";
}

// --- Modified Interaction Handlers ---
function handleMouseMoveForTooltip(event) {
  // Handles BOTH tooltip and crosshair
  if (!dom.chartArea) return;
  const chartRect = dom.chartArea.getBoundingClientRect();
  const mouseX = event.clientX - chartRect.left;
  const mouseY = event.clientY - chartRect.top;
  const chartWidth = dom.chartArea.offsetWidth;
  const chartHeight = chartRect.height;
  if (state.isPanning || state.isDraggingXAxis || state.isDraggingYAxis) {
    hideCrosshair();
    if (hoveredCandleIndex !== null) {
      clearTimeout(tooltipShowTimeout);
      hideTooltip();
      tooltipHideTimeout = null;
    }
    return;
  }
  if (chartWidth <= 0 || chartHeight <= 0 || !state.fullData.length) {
    hideTooltip();
    hideCrosshair();
    return;
  }
  if (
    mouseX >= 0 &&
    mouseX <= chartWidth &&
    mouseY >= 0 &&
    mouseY <= chartHeight
  ) {
    updateCrosshair(mouseX, mouseY, chartHeight, chartWidth);
    // Tooltip Logic
    const visibleCount = state.visibleEndIndex - state.visibleStartIndex;
    if (visibleCount <= 0) {
      hideTooltip();
      return;
    }
    const candleTotalWidth = chartWidth / visibleCount;
    const currentSlotIndex = Math.floor(mouseX / candleTotalWidth);
    const currentDataIndex = state.visibleStartIndex + currentSlotIndex;
    if (currentDataIndex >= 0 && currentDataIndex < state.fullData.length) {
      if (currentDataIndex !== hoveredCandleIndex) {
        clearTimeout(tooltipShowTimeout);
        clearTimeout(tooltipHideTimeout);
        tooltipHideTimeout = null;
        hideTooltip();
        hoveredCandleIndex = currentDataIndex;
        tooltipShowTimeout = setTimeout(() => {
          showTooltip(hoveredCandleIndex, mouseX, mouseY);
          tooltipShowTimeout = null;
        }, config.TOOLTIP_SHOW_DELAY);
      } else {
        clearTimeout(tooltipHideTimeout);
        tooltipHideTimeout = null;
      }
    } else {
      clearTimeout(tooltipShowTimeout);
      tooltipShowTimeout = null;
      hoveredCandleIndex = null;
      if (dom.chartTooltip && dom.chartTooltip.style.visibility === "visible") {
        if (!tooltipHideTimeout) {
          tooltipHideTimeout = setTimeout(() => {
            hideTooltip();
            tooltipHideTimeout = null;
          }, config.TOOLTIP_HIDE_DELAY);
        }
      } else {
        hideTooltip();
      }
    }
  } else {
    hideCrosshair();
    hideTooltip();
    clearTimeout(tooltipShowTimeout);
    tooltipShowTimeout = null;
    hoveredCandleIndex = null;
    clearTimeout(tooltipHideTimeout);
    tooltipHideTimeout = null;
  }
}

function handleMouseLeaveChartArea(event) {
  // Handles BOTH
  hideCrosshair();
  hideTooltip();
  clearTimeout(tooltipShowTimeout);
  tooltipShowTimeout = null;
  clearTimeout(tooltipHideTimeout);
  tooltipHideTimeout = null;
  hoveredCandleIndex = null;
}

// --- Chart Interaction Handlers (Zoom, Pan, Scale, Resize, DoubleClick) ---
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
    newStartIndex = Math.max(0, Math.min(newStartIndex, state.fullData.length));
    let newEndIndex = newStartIndex + newVisibleCount;
    newEndIndex = Math.min(newEndIndex, state.fullData.length);
    newStartIndex = Math.max(0, newEndIndex - newVisibleCount);
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
  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;
  if (state.isDraggingYAxis) {
    const deltaY = event.clientY - state.panStartY;
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
    newStartIndex = Math.max(0, Math.min(newStartIndex, state.fullData.length));
    let newEndIndex = newStartIndex + newVisibleCount;
    newEndIndex = Math.min(newEndIndex, state.fullData.length);
    newStartIndex = Math.max(0, newEndIndex - newVisibleCount);
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
  if (
    event.target !== dom.chartArea &&
    event.target !== dom.chartWrapper &&
    event.target !== dom.chartContainer &&
    !event.target.classList.contains("candle")
  )
    return;
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
  if (dom.chartContainer) dom.chartContainer.classList.add("panning");
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
    if (dom.chartContainer) dom.chartContainer.classList.remove("panning");
  }
}
let resizeTimeout;
export function handleResize() {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    requestAnimationFrame(redrawChart);
  }, config.DEBOUNCE_DELAY);
}

// --- CORRECTED Double Click Handler (Reset to Now - Does NOT reset toggles) ---
export function handleDoubleClick(event) {
  if (!state.fullData.length || !dom.chartArea) return;

  // Calculate new view range based on MOST RECENT data
  const totalDataCount = state.fullData.length;
  let newVisibleCount = Math.min(
    config.DEFAULT_RESET_CANDLE_COUNT,
    totalDataCount
  );
  let newEndIndex = totalDataCount;
  let newStartIndex = Math.max(0, newEndIndex - newVisibleCount);
  newVisibleCount = newEndIndex - newStartIndex;

  // Calculate Y range for the new view
  let newMin = Infinity,
    newMax = -Infinity;
  for (let i = newStartIndex; i < newEndIndex; i++) {
    if (!state.fullData[i] || state.fullData[i].length < 5) continue;
    newMin = Math.min(newMin, state.fullData[i][1]);
    newMax = Math.max(newMax, state.fullData[i][2]);
  }
  if (newMin === Infinity || newMax === -Infinity) {
    console.warn(
      "Could not determine price range for reset view, using default."
    );
    newMin = 0;
    newMax = state.lastTickerPrice ? state.lastTickerPrice * 1.1 : 1;
  }

  // Add padding
  const padding = Math.max(
    config.MIN_PRICE_RANGE_SPAN * 0.1,
    (newMax - newMin) * config.Y_AXIS_PRICE_PADDING_FACTOR
  );
  let newMinPrice = Math.max(0, newMin - padding);
  let newMaxPrice = newMax + padding;

  // Ensure minimum price range span
  if (newMaxPrice - newMinPrice < config.MIN_PRICE_RANGE_SPAN) {
    const mid = (newMaxPrice + newMinPrice) / 2;
    newMinPrice = mid - config.MIN_PRICE_RANGE_SPAN / 2;
    newMaxPrice = mid + config.MIN_PRICE_RANGE_SPAN / 2;
    newMinPrice = Math.max(0, newMinPrice);
  }

  // Update state ONLY for the view range
  updateState({
    visibleStartIndex: newStartIndex,
    visibleEndIndex: newEndIndex,
    minVisiblePrice: newMinPrice,
    maxVisiblePrice: newMaxPrice,
    // DO NOT reset isLogScale or is12HourFormat here
  });

  // DO NOT visually reset the toggles here

  // Request redraw with the new state
  requestAnimationFrame(redrawChart);
}
// --- End of CORRECTED Double Click Handler ---

export function handleLogScaleToggle() {
  const isChecked = dom.logScaleToggle.checked;
  updateState({ isLogScale: isChecked });
  localStorage.setItem("logScalePref", isChecked.toString());
  requestAnimationFrame(redrawChart);
}
export function handleTimeFormatToggle() {
  const isChecked = dom.timeFormatToggle.checked;
  updateState({ is12HourFormat: isChecked });
  localStorage.setItem("timeFormatPref", isChecked.toString());
  requestAnimationFrame(redrawChart);
}

// --- Attach Listeners ---
export function attachInteractionListeners() {
  if (
    !dom.chartContainer ||
    !dom.yAxisLabelsContainer ||
    !dom.xAxisLabelsContainer ||
    !dom.chartArea
  ) {
    console.error("Cannot attach listeners: DOM elements missing.");
    return;
  }
  dom.chartContainer.addEventListener("wheel", handleZoom, { passive: false });
  dom.chartContainer.addEventListener("mousedown", handleMouseDownChart);
  dom.chartContainer.addEventListener("dblclick", handleDoubleClick);
  dom.yAxisLabelsContainer.addEventListener("mousedown", handleMouseDownYAxis);
  dom.xAxisLabelsContainer.addEventListener("mousedown", handleMouseDownXAxis);
  window.addEventListener("mousemove", handleMouseMove);
  window.addEventListener("mouseup", handleMouseUpOrLeave);
  window.addEventListener("resize", handleResize);
  dom.chartArea.addEventListener("mousemove", handleMouseMoveForTooltip);
  dom.chartArea.addEventListener("mouseleave", handleMouseLeaveChartArea);
  if (dom.logScaleToggle) {
    dom.logScaleToggle.addEventListener("change", handleLogScaleToggle);
  }
  if (dom.timeFormatToggle) {
    dom.timeFormatToggle.addEventListener("change", handleTimeFormatToggle);
  }
}
