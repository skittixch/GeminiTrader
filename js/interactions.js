// js/interactions.js

import * as config from "./config.js";
import state, { updateState } from "./state.js"; // Import state and update function
import * as dom from "./domElements.js";
import { redrawChart } from "./drawing.js";
import { calculateNiceStep } from "./utils.js"; // Needed for double-click Y range recalc

// --- Log Scale Math Helpers ---
const log = Math.log; // Use natural log
const exp = Math.exp;
const MIN_LOG_VALUE = 1e-9; // Prevent log(0)

function safeLog(value) {
  return log(Math.max(MIN_LOG_VALUE, value));
}

// --- Event Handlers ---

export function handleZoom(event) {
  // console.log("handleZoom triggered"); // Debugging line
  event.preventDefault();
  const chartRect = dom.chartArea.getBoundingClientRect();
  const mouseX = event.clientX - chartRect.left;
  const mouseY = event.clientY - chartRect.top;
  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;
  if (!chartHeight || !chartWidth) return;

  const zoomDirection = event.deltaY < 0 ? -1 : 1; // -1 for zoom in, 1 for zoom out
  let newState = {}; // Accumulate changes

  // --- Y-Axis Zoom ---
  const currentMinY = state.minVisiblePrice;
  const currentMaxY = state.maxVisiblePrice;

  if (state.isLogScale) {
    const logMin = safeLog(currentMinY);
    const logMax = safeLog(currentMaxY);
    const logRange = logMax - logMin;
    if (logRange > 0 && !isNaN(logRange)) {
      const logAtCursor = logMax - (mouseY / chartHeight) * logRange;
      const zoomAmountY = 1 + zoomDirection * config.ZOOM_FACTOR_Y; // Factor > 1 zooms out, < 1 zooms in
      const newLogMin = logAtCursor - (logAtCursor - logMin) * zoomAmountY;
      const newLogMax = logAtCursor + (logMax - logAtCursor) * zoomAmountY;
      newState.minVisiblePrice = Math.max(MIN_LOG_VALUE, exp(newLogMin));
      newState.maxVisiblePrice = exp(newLogMax);
      // Prevent excessive zoom in on log scale
      if (newState.maxVisiblePrice / newState.minVisiblePrice < 1.001) {
        const midPrice = Math.sqrt(
          newState.minVisiblePrice * newState.maxVisiblePrice
        ); // Geometric mean
        newState.minVisiblePrice = midPrice / 1.0005;
        newState.maxVisiblePrice = midPrice * 1.0005;
      }
    }
  } else {
    // Linear Y Zoom
    const linearRange = currentMaxY - currentMinY;
    if (linearRange > 0) {
      const priceAtCursor = currentMaxY - (mouseY / chartHeight) * linearRange;
      const zoomAmountY = 1 + zoomDirection * config.ZOOM_FACTOR_Y;
      let newMin = priceAtCursor - (priceAtCursor - currentMinY) * zoomAmountY;
      let newMax = priceAtCursor + (currentMaxY - priceAtCursor) * zoomAmountY;
      // Clamp linear range
      if (newMax - newMin < config.MIN_PRICE_RANGE_SPAN) {
        const mid = (newMax + newMin) / 2;
        newMin = mid - config.MIN_PRICE_RANGE_SPAN / 2;
        newMax = mid + config.MIN_PRICE_RANGE_SPAN / 2;
      }
      newState.minVisiblePrice = Math.max(0, newMin); // Clamp linear min at 0
      newState.maxVisiblePrice = newMax;
    }
  }

  // --- X-Axis Zoom ---
  const currentVisibleCount = state.visibleEndIndex - state.visibleStartIndex;
  if (currentVisibleCount > 0) {
    const indexAtCursor =
      state.visibleStartIndex + (mouseX / chartWidth) * currentVisibleCount;
    const zoomAmountX = 1 + zoomDirection * config.ZOOM_FACTOR_X;
    let newVisibleCount = Math.round(currentVisibleCount * zoomAmountX);
    newVisibleCount = Math.max(
      config.MIN_VISIBLE_CANDLES,
      Math.min(newVisibleCount, state.fullData.length * 5)
    ); // Limit zoom out
    let newStartIndex = Math.round(
      indexAtCursor - (mouseX / chartWidth) * newVisibleCount
    );
    let newEndIndex = newStartIndex + newVisibleCount;
    // No clamping needed for infinite scroll indices
    newState.visibleStartIndex = newStartIndex;
    newState.visibleEndIndex = newEndIndex;
  }

  updateState(newState); // Update state with accumulated changes
  requestAnimationFrame(redrawChart);
}

export function handleMouseMove(event) {
  // console.log("handleMouseMove triggered, isPanning:", state.isPanning, "isDraggingY:", state.isDraggingYAxis, "isDraggingX:", state.isDraggingXAxis); // Debugging line
  if (!state.isPanning && !state.isDraggingYAxis && !state.isDraggingXAxis)
    return;

  const now = Date.now();
  if (now - state.lastDrawTime < config.MOUSE_MOVE_THROTTLE) return;

  let needsRedraw = false;
  let newState = {};

  // --- Y-Axis Drag (Scaling Price) ---
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
        if (exp(newLogRange) < 1.001) newLogRange = log(1.001); // Prevent extreme zoom in

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
      // Linear Y Drag Scale
      const initialRange = state.panStartMaxPrice - state.panStartMinPrice;
      if (initialRange > 0) {
        const midPrice = (state.panStartMaxPrice + state.panStartMinPrice) / 2;
        const scaleFactor = Math.pow(
          2,
          (deltaY / chartHeight) * config.Y_AXIS_DRAG_SENSITIVITY
        );
        let newRange = initialRange * scaleFactor;
        newRange = Math.max(config.MIN_PRICE_RANGE_SPAN, newRange);
        const newMin = Math.max(0, midPrice - newRange / 2); // Clamp linear min at 0
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
  }
  // --- X-Axis Drag (Scaling Time) ---
  else if (state.isDraggingXAxis) {
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
  }
  // --- Main Chart Pan (Both Axes) ---
  else if (state.isPanning) {
    const deltaX = event.clientX - state.panStartX;
    const deltaY = event.clientY - state.panStartY;
    const chartHeight = dom.chartArea.offsetHeight;
    const chartWidth = dom.chartArea.offsetWidth;
    if (!chartWidth || !chartHeight) return;

    let changedX = false;
    let changedY = false;

    // X-Axis Pan (No clamping)
    if (state.panStartVisibleCount > 0) {
      const indexDelta = (deltaX / chartWidth) * state.panStartVisibleCount;
      let newStartIndex = state.panStartVisibleIndex - Math.round(indexDelta);
      if (newStartIndex !== state.visibleStartIndex) {
        newState.visibleStartIndex = newStartIndex;
        newState.visibleEndIndex = newStartIndex + state.panStartVisibleCount; // Keep count same
        changedX = true;
      }
    }

    // Y-Axis Pan
    if (state.isLogScale) {
      const logMinStart = safeLog(state.panStartMinPrice);
      const logMaxStart = safeLog(state.panStartMaxPrice);
      const logRangeStart = logMaxStart - logMinStart;
      if (logRangeStart > 0 && !isNaN(logRangeStart)) {
        const logDelta = (deltaY / chartHeight) * logRangeStart; // Pan amount in log space
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
      // Linear Y Pan
      const initialPriceRange = state.panStartMaxPrice - state.panStartMinPrice;
      if (initialPriceRange > 0) {
        const priceDelta = (deltaY / chartHeight) * initialPriceRange;
        const newMinPrice = state.panStartMinPrice + priceDelta;
        const newMaxPrice = state.panStartMaxPrice + priceDelta;
        if (
          Math.abs(newMinPrice - state.minVisiblePrice) > 1e-9 ||
          Math.abs(newMaxPrice - state.maxVisiblePrice) > 1e-9
        ) {
          newState.minVisiblePrice = Math.max(0, newMinPrice); // Clamp linear min pan at 0
          newState.maxVisiblePrice = newMaxPrice;
          changedY = true;
        }
      }
    }
    needsRedraw = changedX || changedY;
  }

  if (needsRedraw) {
    // Update accumulated state changes and the draw timestamp
    updateState({ ...newState, lastDrawTime: now });
    requestAnimationFrame(redrawChart);
  }
}

export function handleMouseDownChart(event) {
  // console.log("handleMouseDownChart triggered"); // Debugging line
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
  // console.log("handleMouseDownYAxis triggered"); // Debugging line
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
  // console.log("handleMouseDownXAxis triggered"); // Debugging line
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
  // console.log("handleMouseUpOrLeave triggered"); // Debugging line
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
  // console.log("handleResize triggered"); // Debugging line
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    requestAnimationFrame(redrawChart);
  }, config.DEBOUNCE_DELAY);
}

export function handleDoubleClick(event) {
  // console.log("handleDoubleClick triggered"); // Debugging line
  if (!state.fullData.length) return;
  const chartRect = dom.chartArea.getBoundingClientRect();
  const mouseX = event.clientX - chartRect.left;
  const chartWidth = dom.chartArea.offsetWidth;
  if (!chartWidth) return;

  const currentVisibleCount = state.visibleEndIndex - state.visibleStartIndex;
  const fractionalIndex =
    state.visibleStartIndex + (mouseX / chartWidth) * currentVisibleCount;
  let targetIndex = Math.round(fractionalIndex);
  targetIndex = Math.max(0, Math.min(targetIndex, state.fullData.length - 1)); // Clamp target to actual data

  let newVisibleCount = Math.min(
    config.DEFAULT_RESET_CANDLE_COUNT,
    state.fullData.length
  );
  let newStartIndex = Math.round(targetIndex - newVisibleCount / 2);
  // Clamp reset view strictly within data bounds
  newStartIndex = Math.max(
    0,
    Math.min(newStartIndex, state.fullData.length - newVisibleCount)
  );
  let newEndIndex = Math.min(
    state.fullData.length,
    newStartIndex + newVisibleCount
  );
  newStartIndex = Math.max(0, newEndIndex - newVisibleCount);

  // Recalculate Y range linearly for reset view
  let newMin = Infinity,
    newMax = -Infinity;
  for (let i = newStartIndex; i < newEndIndex; i++) {
    if (!state.fullData[i] || state.fullData[i].length < 5) continue;
    newMin = Math.min(newMin, state.fullData[i][1]); // low
    newMax = Math.max(newMax, state.fullData[i][2]); // high
  }
  if (newMin === Infinity) {
    newMin = 0;
    newMax = 1;
  } // Fallback

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

  // Reset state, including turning OFF log scale and resetting time format maybe? (User choice)
  updateState({
    visibleStartIndex: newStartIndex,
    visibleEndIndex: newEndIndex,
    minVisiblePrice: newMinPrice,
    maxVisiblePrice: newMaxPrice,
    isLogScale: false, // Default to linear on reset
    // is12HourFormat: false // Reset time format too? Or keep user pref?
  });
  // Sync checkboxes
  if (dom.logScaleToggle) dom.logScaleToggle.checked = false;
  // if (dom.timeFormatToggle) dom.timeFormatToggle.checked = false; // If resetting time format

  requestAnimationFrame(redrawChart);
}

// --- Log Scale Toggle Handler ---
export function handleLogScaleToggle() {
  // console.log("handleLogScaleToggle triggered"); // Debugging line
  const isChecked = dom.logScaleToggle.checked;
  updateState({ isLogScale: isChecked });
  localStorage.setItem("logScalePref", isChecked); // Optional: Save preference
  requestAnimationFrame(redrawChart); // Redraw immediately
}

// --- Time Format Toggle Handler ---
export function handleTimeFormatToggle() {
  // console.log("handleTimeFormatToggle triggered"); // Debugging line
  const isChecked = dom.timeFormatToggle.checked; // true = 12hr AM/PM
  updateState({ is12HourFormat: isChecked });
  localStorage.setItem("timeFormatPref", isChecked); // Optional: Save preference
  requestAnimationFrame(redrawChart); // Redraw with new time format
}

// Function to attach all interaction listeners
export function attachInteractionListeners() {
  // console.log("Attaching interaction listeners"); // Debugging line
  dom.chartContainer.addEventListener("wheel", handleZoom, { passive: false });
  dom.chartContainer.addEventListener("mousedown", handleMouseDownChart);
  dom.yAxisLabelsContainer.addEventListener("mousedown", handleMouseDownYAxis);
  dom.xAxisLabelsContainer.addEventListener("mousedown", handleMouseDownXAxis);
  window.addEventListener("mousemove", handleMouseMove);
  window.addEventListener("mouseup", handleMouseUpOrLeave);
  window.addEventListener("resize", handleResize);
  dom.chartContainer.addEventListener("dblclick", handleDoubleClick);

  // Attach listener for the log scale toggle
  if (dom.logScaleToggle) {
    dom.logScaleToggle.addEventListener("change", handleLogScaleToggle);
  } else {
    console.warn(
      "Log scale toggle element not found during listener attachment."
    );
  }

  // Attach listener for the time format toggle
  if (dom.timeFormatToggle) {
    dom.timeFormatToggle.addEventListener("change", handleTimeFormatToggle);
  } else {
    console.warn(
      "Time format toggle element not found during listener attachment."
    );
  }

  // Granularity listener is attached in main.js
}
