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

// --- Tooltip Functions (Using Direct Style Manipulation from Version B) ---

// Helper: Show Tooltip (with direct style manipulation test)
function showTooltip(dataIndex, mouseX, mouseY) {
  // console.log(`%cshowTooltip called for index: ${dataIndex}`, 'color: green'); // *** DEBUG ***

  // Check the DOM element RIGHT NOW
  if (!dom.chartTooltip) {
    console.error(
      "%c  -> FATAL in showTooltip: dom.chartTooltip is null or undefined!",
      "color: red; font-weight: bold;"
    );
    return; // Stop if element doesn't exist
  }
  // console.log('%c  -> dom.chartTooltip element:', 'color: cyan', dom.chartTooltip); // *** DEBUG ***

  if (dataIndex < 0 || dataIndex >= state.fullData.length) {
    // console.log('%c  -> showTooltip aborted: Invalid index.', 'color: orange'); // *** DEBUG ***
    hideTooltip();
    return;
  }
  const candleData = state.fullData[dataIndex];
  if (!candleData || candleData.length < 6) {
    // console.log('%c  -> showTooltip aborted: Invalid candle data.', 'color: orange'); // *** DEBUG ***
    hideTooltip();
    return;
  }

  const [timestamp, low, high, open, close, volume] = candleData;
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

  // Get dimensions *after* content is set
  const tooltipElementHeight = dom.chartTooltip.offsetHeight;
  const tooltipElementWidth = dom.chartTooltip.offsetWidth;

  let tooltipY =
    mouseY + chartRect.top - chartContainerRect.top - tooltipElementHeight - 10; // Prefer above
  if (tooltipY < 10) { // Below if too high
    tooltipY = mouseY + chartRect.top - chartContainerRect.top + 20;
  }

  let tooltipX = mouseX + chartRect.left - chartContainerRect.left + 15; // Prefer right
  const rightBoundary =
    chartContainerRect.width -
    (dom.yAxisLabelsContainer?.offsetWidth || 55) -
    10;
  if (tooltipX + tooltipElementWidth > rightBoundary) { // Left if off edge
    tooltipX =
      mouseX +
      chartRect.left -
      chartContainerRect.left -
      tooltipElementWidth -
      15;
  }
  if (tooltipX < 10) { // Clamp left
    tooltipX = 10;
  }

  // console.log(`%c  -> Setting tooltip position: X=${tooltipX.toFixed(1)}, Y=${tooltipY.toFixed(1)}`, 'color: green'); // *** DEBUG ***
  dom.chartTooltip.style.left = `${tooltipX.toFixed(1)}px`;
  dom.chartTooltip.style.top = `${tooltipY.toFixed(1)}px`;
  dom.chartTooltip.style.display = "block"; // Ensure display is block before visibility/opacity changes

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (!dom.chartTooltip) { return; } // Double check element
      try {
        // *** USE Direct Style Manipulation ***
        // console.log('%c     -> Setting style.opacity = 1', 'color: purple'); // DEBUG
        dom.chartTooltip.style.opacity = 1;
        // console.log('%c     -> Setting style.visibility = "visible"', 'color: purple'); // DEBUG
        dom.chartTooltip.style.visibility = "visible";
        // console.log('%c  -> ...Visibility attempt complete.', 'color: blue'); // DEBUG
      } catch (error) {
        console.error("%c  -> Error during visibility change:", "color: red; font-weight: bold;", error ); // DEBUG
      }
    });
  });
}

// Helper: Hide Tooltip (needs to revert direct styles - from Version B)
function hideTooltip() {
  const wasVisible =
    dom.chartTooltip &&
    (dom.chartTooltip.style.opacity === "1" || // Check direct style
      dom.chartTooltip.classList.contains("visible")); // Check class just in case

  if (dom.chartTooltip) {
    // Revert direct styles
    dom.chartTooltip.style.opacity = 0;
    dom.chartTooltip.style.visibility = "hidden";
    // Also remove class if it was ever added
    dom.chartTooltip.classList.remove("visible");

    // if (wasVisible) { // DEBUG
    //   console.log('%chideTooltip called', 'color: red'); // DEBUG
    // }
  }
  hoveredCandleIndex = null; // Reset index regardless
}


// --- Tooltip Interaction Handlers (These should be fine from Version A) ---

// Tooltip Mouse Move Handler
function handleMouseMoveForTooltip(event) {
  if (!dom.chartArea) { console.warn("Tooltip mousemove: chartArea not found"); return; }
  if (state.isPanning || state.isDraggingXAxis || state.isDraggingYAxis) {
    if (hoveredCandleIndex !== null) {
      clearTimeout(tooltipShowTimeout);
      if (!tooltipHideTimeout) {
        tooltipHideTimeout = setTimeout(() => { hideTooltip(); tooltipHideTimeout = null; }, config.TOOLTIP_HIDE_DELAY);
      }
    }
    return;
  }

  const chartRect = dom.chartArea.getBoundingClientRect();
  const mouseX = event.clientX - chartRect.left;
  const mouseY = event.clientY - chartRect.top;
  const chartWidth = dom.chartArea.offsetWidth;
  const chartHeight = chartRect.height; // Use height from rect
  const visibleCount = state.visibleEndIndex - state.visibleStartIndex;

  if (chartWidth <= 0 || chartHeight <= 0 || visibleCount <= 0 || !state.fullData.length ) {
    hideTooltip(); return;
  }

  const candleTotalWidth = chartWidth / visibleCount;
  const currentSlotIndex = Math.floor(mouseX / candleTotalWidth);
  const currentDataIndex = state.visibleStartIndex + currentSlotIndex;

  if ( mouseX >= 0 && mouseX <= chartWidth && mouseY >= 0 && mouseY <= chartHeight &&
       currentDataIndex >= 0 && currentDataIndex < state.fullData.length )
  {
    if (currentDataIndex !== hoveredCandleIndex) {
      clearTimeout(tooltipShowTimeout); clearTimeout(tooltipHideTimeout);
      tooltipHideTimeout = null;
      hideTooltip(); // Hide previous immediately

      hoveredCandleIndex = currentDataIndex;
      tooltipShowTimeout = setTimeout(() => {
        // console.log(`%cExecuting showTooltip timeout for index: ${hoveredCandleIndex}`, 'color: blue'); // DEBUG
        showTooltip(hoveredCandleIndex, mouseX, mouseY);
        tooltipShowTimeout = null;
      }, config.TOOLTIP_SHOW_DELAY);
    } else {
      clearTimeout(tooltipHideTimeout); // Still on same candle, clear hide timeout
      tooltipHideTimeout = null;
    }
  } else {
    // Cursor outside valid area
    clearTimeout(tooltipShowTimeout); tooltipShowTimeout = null;
    hoveredCandleIndex = null;

    // Start hide timeout only if not already hiding and tooltip is currently visible
    if ( !tooltipHideTimeout && dom.chartTooltip &&
         (dom.chartTooltip.style.visibility === "visible" || // Check direct style
          dom.chartTooltip.classList.contains("visible")) ) // Check class
    {
      tooltipHideTimeout = setTimeout(() => { hideTooltip(); tooltipHideTimeout = null; }, config.TOOLTIP_HIDE_DELAY);
    }
  }
}

// Tooltip Mouse Leave Handler for the specific chart area
function handleMouseLeaveChartArea(event) {
  // console.log('%cMouse left chartArea', 'color: orange'); // DEBUG
  clearTimeout(tooltipShowTimeout); tooltipShowTimeout = null;
  clearTimeout(tooltipHideTimeout); tooltipHideTimeout = null;
  hideTooltip(); // Hide immediately
}


// --- Chart Interaction Handlers (Should be fine from Version A) ---
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
  // Y-Axis Zoom (Log)
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
        const midPrice = Math.sqrt(newState.minVisiblePrice * newState.maxVisiblePrice);
        newState.minVisiblePrice = midPrice / 1.0005;
        newState.maxVisiblePrice = midPrice * 1.0005;
      }
    }
  }
  // Y-Axis Zoom (Linear)
  else {
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
  // X-Axis Zoom
  const currentVisibleCount = state.visibleEndIndex - state.visibleStartIndex;
  if (currentVisibleCount > 0) {
    const indexAtCursor = state.visibleStartIndex + (mouseX / chartWidth) * currentVisibleCount;
    const zoomAmountX = 1 + zoomDirection * config.ZOOM_FACTOR_X;
    let newVisibleCount = Math.round(currentVisibleCount * zoomAmountX);
    newVisibleCount = Math.max(config.MIN_VISIBLE_CANDLES, Math.min(newVisibleCount, state.fullData.length * 5));
    let newStartIndex = Math.round(indexAtCursor - (mouseX / chartWidth) * newVisibleCount);
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
  if (!state.isPanning && !state.isDraggingYAxis && !state.isDraggingXAxis) return;
  const now = Date.now();
  if (now - state.lastDrawTime < config.MOUSE_MOVE_THROTTLE) return;
  let needsRedraw = false;
  let newState = {};
  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;

  // Y-Axis Drag/Scale
  if (state.isDraggingYAxis) {
    const deltaY = event.clientY - state.panStartY;
    if (!chartHeight) return;
    if (state.isLogScale) {
      const logMinStart = safeLog(state.panStartMinPrice);
      const logMaxStart = safeLog(state.panStartMaxPrice);
      const logRangeStart = logMaxStart - logMinStart;
      if (logRangeStart > 0 && !isNaN(logRangeStart)) {
        const midLogPrice = (logMaxStart + logMinStart) / 2;
        const scaleFactor = Math.pow(2, (deltaY / chartHeight) * config.Y_AXIS_DRAG_SENSITIVITY);
        let newLogRange = logRangeStart * scaleFactor;
        if (exp(newLogRange) < 1.001) newLogRange = log(1.001);
        const newLogMin = midLogPrice - newLogRange / 2;
        const newLogMax = midLogPrice + newLogRange / 2;
        const newMin = Math.max(MIN_LOG_VALUE, exp(newLogMin));
        const newMax = exp(newLogMax);
        if ( Math.abs(newMin - state.minVisiblePrice) > 1e-9 || Math.abs(newMax - state.maxVisiblePrice) > 1e-9 ) {
          newState.minVisiblePrice = newMin; newState.maxVisiblePrice = newMax; needsRedraw = true;
        }
      }
    } else {
      const initialRange = state.panStartMaxPrice - state.panStartMinPrice;
      if (initialRange > 0) {
        const midPrice = (state.panStartMaxPrice + state.panStartMinPrice) / 2;
        const scaleFactor = Math.pow(2, (deltaY / chartHeight) * config.Y_AXIS_DRAG_SENSITIVITY);
        let newRange = initialRange * scaleFactor;
        newRange = Math.max(config.MIN_PRICE_RANGE_SPAN, newRange);
        const newMin = Math.max(0, midPrice - newRange / 2);
        const newMax = midPrice + newRange / 2;
        if ( Math.abs(newMin - state.minVisiblePrice) > 1e-9 || Math.abs(newMax - state.maxVisiblePrice) > 1e-9 ) {
          newState.minVisiblePrice = newMin; newState.maxVisiblePrice = newMax; needsRedraw = true;
        }
      }
    }
  }
  // X-Axis Drag/Scale
  else if (state.isDraggingXAxis) {
    const deltaX = event.clientX - state.panStartX;
    if (!chartWidth || state.panStartVisibleCount <= 0) return;
    const centerIndex = state.panStartVisibleIndex + state.panStartVisibleCount / 2;
    const scaleFactor = Math.pow(2, (deltaX / chartWidth) * config.X_AXIS_DRAG_SENSITIVITY);
    let newVisibleCount = Math.round(state.panStartVisibleCount * scaleFactor);
    newVisibleCount = Math.max(config.MIN_VISIBLE_CANDLES, Math.min(newVisibleCount, state.fullData.length * 5));
    let newStartIndex = Math.round(centerIndex - newVisibleCount / 2);
    newStartIndex = Math.max(0, Math.min(newStartIndex, state.fullData.length));
    let newEndIndex = newStartIndex + newVisibleCount;
    newEndIndex = Math.min(newEndIndex, state.fullData.length);
    newStartIndex = Math.max(0, newEndIndex - newVisibleCount);
    if ( newStartIndex !== state.visibleStartIndex || newEndIndex !== state.visibleEndIndex ) {
      newState.visibleStartIndex = newStartIndex; newState.visibleEndIndex = newEndIndex; needsRedraw = true;
    }
  }
  // Chart Panning
  else if (state.isPanning) {
    const deltaX = event.clientX - state.panStartX;
    const deltaY = event.clientY - state.panStartY;
    if (!chartWidth || !chartHeight) return;
    let changedX = false; let changedY = false;
    if (state.panStartVisibleCount > 0) {
      const indexDelta = (deltaX / chartWidth) * state.panStartVisibleCount;
      let newStartIndex = state.panStartVisibleIndex - Math.round(indexDelta);
      if (newStartIndex !== state.visibleStartIndex) {
        newState.visibleStartIndex = newStartIndex; newState.visibleEndIndex = newStartIndex + state.panStartVisibleCount; changedX = true;
      }
    }
    if (state.isLogScale) {
      const logMinStart = safeLog(state.panStartMinPrice); const logMaxStart = safeLog(state.panStartMaxPrice);
      const logRangeStart = logMaxStart - logMinStart;
      if (logRangeStart > 0 && !isNaN(logRangeStart)) {
        const logDelta = (deltaY / chartHeight) * logRangeStart;
        const newLogMin = logMinStart + logDelta; const newLogMax = logMaxStart + logDelta;
        const newMin = Math.max(MIN_LOG_VALUE, exp(newLogMin)); const newMax = exp(newLogMax);
        if ( Math.abs(newMin - state.minVisiblePrice) > 1e-9 || Math.abs(newMax - state.maxVisiblePrice) > 1e-9 ) {
          newState.minVisiblePrice = newMin; newState.maxVisiblePrice = newMax; changedY = true;
        }
      }
    } else {
      const initialPriceRange = state.panStartMaxPrice - state.panStartMinPrice;
      if (initialPriceRange > 0) {
        const priceDelta = (deltaY / chartHeight) * initialPriceRange;
        const newMinPrice = state.panStartMinPrice + priceDelta; const newMaxPrice = state.panStartMaxPrice + priceDelta;
        if ( Math.abs(newMinPrice - state.minVisiblePrice) > 1e-9 || Math.abs(newMaxPrice - state.maxVisiblePrice) > 1e-9 ) {
          newState.minVisiblePrice = Math.max(0, newMinPrice); newState.maxVisiblePrice = newMaxPrice; changedY = true;
        }
      }
    }
    needsRedraw = changedX || changedY;
  }
  // Trigger Redraw
  if (needsRedraw) {
    updateState({ ...newState, lastDrawTime: now });
    requestAnimationFrame(redrawChart);
  }
}

export function handleMouseDownChart(event) {
  if ( event.target !== dom.chartArea && event.target !== dom.chartWrapper && event.target !== dom.chartContainer && !event.target.classList.contains("candle") ) return;
  updateState({
    isPanning: true, isDraggingYAxis: false, isDraggingXAxis: false,
    panStartX: event.clientX, panStartY: event.clientY,
    panStartVisibleIndex: state.visibleStartIndex,
    panStartMinPrice: state.minVisiblePrice, panStartMaxPrice: state.maxVisiblePrice,
    panStartVisibleCount: state.visibleEndIndex - state.visibleStartIndex,
  });
  if (dom.chartContainer) dom.chartContainer.classList.add("panning");
}

export function handleMouseDownYAxis(event) {
  event.stopPropagation();
  updateState({
    isDraggingYAxis: true, isPanning: false, isDraggingXAxis: false,
    panStartY: event.clientY,
    panStartMinPrice: state.minVisiblePrice, panStartMaxPrice: state.maxVisiblePrice,
  });
}

export function handleMouseDownXAxis(event) {
  event.stopPropagation();
  updateState({
    isDraggingXAxis: true, isPanning: false, isDraggingYAxis: false,
    panStartX: event.clientX,
    panStartVisibleIndex: state.visibleStartIndex,
    panStartVisibleCount: state.visibleEndIndex - state.visibleStartIndex,
  });
}

export function handleMouseUpOrLeave(event) {
  if (state.isPanning || state.isDraggingYAxis || state.isDraggingXAxis) {
    updateState({ isPanning: false, isDraggingYAxis: false, isDraggingXAxis: false });
    if (dom.chartContainer) dom.chartContainer.classList.remove("panning");
  }
}

let resizeTimeout;
export function handleResize() {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => { requestAnimationFrame(redrawChart); }, config.DEBOUNCE_DELAY);
}

// --- CORRECTED Double Click Handler (Reset to Now - from Version A) ---
export function handleDoubleClick(event) {
  // No longer need mouse position for this "reset to recent" action
  if (!state.fullData.length || !dom.chartArea) return; // Check if data exists

  // --- Calculate new view range based on MOST RECENT data ---
  const totalDataCount = state.fullData.length;
  let newVisibleCount = Math.min(config.DEFAULT_RESET_CANDLE_COUNT, totalDataCount);
  let newEndIndex = totalDataCount; // Always end at the last data point
  let newStartIndex = Math.max(0, newEndIndex - newVisibleCount); // Calculate start based on end

  // If data is very short, recalculate visible count based on actual indices
  newVisibleCount = newEndIndex - newStartIndex;
  // --- End of new view range calculation ---

  // Calculate Y range for the new view (the most recent candles)
  let newMin = Infinity, newMax = -Infinity;
  for (let i = newStartIndex; i < newEndIndex; i++) {
    if (!state.fullData[i] || state.fullData[i].length < 5) continue; // Ensure candle data is valid
    newMin = Math.min(newMin, state.fullData[i][1]); // low
    newMax = Math.max(newMax, state.fullData[i][2]); // high
  }
  // Handle cases where no valid min/max found
  if (newMin === Infinity || newMax === -Infinity) {
    console.warn("Could not determine price range for reset view, using default.");
    newMin = 0; newMax = state.lastTickerPrice ? state.lastTickerPrice * 1.1 : 1;
  }

  // Add padding to the calculated range
  const padding = Math.max(config.MIN_PRICE_RANGE_SPAN * 0.1, (newMax - newMin) * config.Y_AXIS_PRICE_PADDING_FACTOR);
  let newMinPrice = Math.max(0, newMin - padding); // Ensure min price is not negative
  let newMaxPrice = newMax + padding;

  // Ensure minimum price range span
  if (newMaxPrice - newMinPrice < config.MIN_PRICE_RANGE_SPAN) {
    const mid = (newMaxPrice + newMinPrice) / 2;
    newMinPrice = mid - config.MIN_PRICE_RANGE_SPAN / 2;
    newMaxPrice = mid + config.MIN_PRICE_RANGE_SPAN / 2;
    newMinPrice = Math.max(0, newMinPrice); // Re-check non-negativity
  }

  // console.log(`Resetting view to show indices [${newStartIndex}, ${newEndIndex})`); // Optional log

  // Update state with the new view range and reset toggles
  updateState({
    visibleStartIndex: newStartIndex, visibleEndIndex: newEndIndex,
    minVisiblePrice: newMinPrice, maxVisiblePrice: newMaxPrice,
    isLogScale: false, // Reset log scale
    is12HourFormat: false, // Reset time format
  });

  // Visually reset the toggles in the UI
  if (dom.logScaleToggle) dom.logScaleToggle.checked = false;
  if (dom.timeFormatToggle) dom.timeFormatToggle.checked = false;

  // Request redraw with the new state
  requestAnimationFrame(redrawChart);
}
// --- End of CORRECTED Double Click Handler ---


export function handleLogScaleToggle() {
  const isChecked = dom.logScaleToggle.checked;
  updateState({ isLogScale: isChecked });
  localStorage.setItem("logScalePref", isChecked.toString()); // Store as string
  requestAnimationFrame(redrawChart);
}

export function handleTimeFormatToggle() {
  const isChecked = dom.timeFormatToggle.checked;
  updateState({ is12HourFormat: isChecked });
  localStorage.setItem("timeFormatPref", isChecked.toString()); // Store as string
  requestAnimationFrame(redrawChart);
}

// Function to attach all interaction listeners
export function attachInteractionListeners() {
  // console.log("Attaching interaction listeners..."); // DEBUG

  if (!dom.chartContainer || !dom.yAxisLabelsContainer || !dom.xAxisLabelsContainer || !dom.chartArea) {
    console.error("Cannot attach listeners: One or more required DOM elements are missing."); return;
  }

  // Chart container listeners
  dom.chartContainer.addEventListener("wheel", handleZoom, { passive: false });
  dom.chartContainer.addEventListener("mousedown", handleMouseDownChart);
  dom.chartContainer.addEventListener("dblclick", handleDoubleClick);

  // Axis drag listeners
  dom.yAxisLabelsContainer.addEventListener("mousedown", handleMouseDownYAxis);
  dom.xAxisLabelsContainer.addEventListener("mousedown", handleMouseDownXAxis);

  // Window listeners
  window.addEventListener("mousemove", handleMouseMove);
  window.addEventListener("mouseup", handleMouseUpOrLeave);
  window.addEventListener("resize", handleResize);

  // Tooltip listeners
  dom.chartArea.addEventListener("mousemove", handleMouseMoveForTooltip);
  // console.log("Attached mousemove listener to chartArea for tooltip."); // DEBUG
  dom.chartArea.addEventListener("mouseleave", handleMouseLeaveChartArea);
  // console.log("Attached mouseleave listener to chartArea for tooltip."); // DEBUG

  // Toggle listeners
  if (dom.logScaleToggle) { dom.logScaleToggle.addEventListener("change", handleLogScaleToggle); }
  if (dom.timeFormatToggle) { dom.timeFormatToggle.addEventListener("change", handleTimeFormatToggle); }

  // Granularity listener is attached in main.js
  // console.log("Interaction listeners attached."); // DEBUG
}