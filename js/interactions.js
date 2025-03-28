// js/interactions.js

import * as config from "./config.js"; // Import config
import state, { updateState } from "./state.js";
import * as dom from "./domElements.js";
import { redrawChart } from "./drawing.js";
import {
  calculateNiceStep,
  getYCoordinate,
  formatDate,
  formatTimestamp,
  getPriceFromYCoordinate,
  MIN_LOG_VALUE, // Import MIN_LOG_VALUE
} from "./utils.js"; // <<< ENSURE IMPORT IS HERE

// Tooltip State
let hoveredCandleIndex = null;
let tooltipShowTimeout = null;
let tooltipHideTimeout = null;

// Log Scale Helpers
const log = Math.log;
const exp = Math.exp;
// const MIN_LOG_VALUE = 1e-9; // Defined and imported from utils.js now
function safeLog(value) {
  return log(Math.max(MIN_LOG_VALUE, value));
}

// --- Tooltip Functions ---
// ... (showTooltip, hideTooltip - no changes needed) ...
function showTooltip(dataIndex, mouseX, mouseY) {
  if (!dom.chartTooltip || !dom.chartArea) return;

  if (dataIndex < 0 || dataIndex >= state.fullData.length) {
    hideTooltip();
    return;
  }

  const candleData = state.fullData[dataIndex];
  // Need timestamp[0], low[1], high[2], open[3], close[4] for tooltip
  if (
    !candleData ||
    candleData.length < 5 ||
    candleData.slice(0, 5).some((v) => isNaN(v) || !Number.isFinite(v))
  ) {
    hideTooltip();
    return;
  }

  const [timestamp, low, high, open, close] = candleData;
  const chartRect = dom.chartArea.getBoundingClientRect();
  const chartHeight = dom.chartArea.offsetHeight; // Use offsetHeight
  const chartContainerRect = dom.chartContainer.getBoundingClientRect(); // Use container for positioning relative to it

  // Formatting
  const dateStr = formatDate(timestamp);
  const timeStr = formatTimestamp(timestamp);
  const priceRange = state.maxVisiblePrice - state.minVisiblePrice;
  let decimals = 0;
  if (priceRange < 0.1) decimals = 4;
  else if (priceRange < 1) decimals = 3;
  else if (priceRange < 10 || close < 10) decimals = 2;
  else if (close < 1000) decimals = 1;
  else decimals = 0;
  decimals = Math.max(0, decimals); // Ensure non-negative

  // Update Tooltip Content
  dom.chartTooltip.innerHTML = `
    <div class="date">${dateStr}, ${timeStr}</div>
    <div><span class="label">O:</span> <span class="value">${open.toFixed(
      decimals
    )}</span></div>
    <div><span class="label">H:</span> <span class="value">${high.toFixed(
      decimals
    )}</span></div>
    <div><span class="label">L:</span> <span class="value">${low.toFixed(
      decimals
    )}</span></div>
    <div><span class="label">C:</span> <span class="value">${close.toFixed(
      decimals
    )}</span></div>
    `;
  // Optionally add Volume:
  // ${candleData.length > 5 && !isNaN(candleData[5]) && Number.isFinite(candleData[5]) ? `<div><span class="label">Vol:</span> <span class="value">${candleData[5].toLocaleString()}</span></div>` : ''}

  // Calculate Tooltip Position
  // Get tooltip dimensions *after* setting content
  const tooltipElementHeight = dom.chartTooltip.offsetHeight;
  const tooltipElementWidth = dom.chartTooltip.offsetWidth;

  // Default position: above and slightly to the right of the cursor
  let tooltipY = mouseY - tooltipElementHeight - 10; // 10px offset above
  let tooltipX = mouseX + 15; // 15px offset right

  // Adjust if too high (flip below cursor)
  if (tooltipY < 10) {
    // 10px margin from top of chart area
    tooltipY = mouseY + 20; // 20px offset below
  }

  // Adjust if too far right (flip left of cursor)
  // Calculate right boundary within the chart container (excluding Y axis label width)
  const yAxisWidth = dom.yAxisLabelsContainer?.offsetWidth || 55; // Estimate width if not available
  const rightBoundary = dom.chartContainer.offsetWidth - yAxisWidth - 10; // 10px margin
  if (tooltipX + tooltipElementWidth > rightBoundary) {
    tooltipX = mouseX - tooltipElementWidth - 15; // 15px offset left
  }

  // Adjust if too far left
  if (tooltipX < 10) {
    // 10px margin from left edge
    tooltipX = 10;
  }

  // Apply position relative to the chart container
  const containerRelativeX =
    tooltipX + chartRect.left - chartContainerRect.left;
  const containerRelativeY = tooltipY + chartRect.top - chartContainerRect.top;

  dom.chartTooltip.style.left = `${containerRelativeX.toFixed(0)}px`;
  dom.chartTooltip.style.top = `${containerRelativeY.toFixed(0)}px`;

  // Show Tooltip with fade-in effect
  dom.chartTooltip.style.display = "block"; // Make it take space for measurements if needed?
  dom.chartTooltip.style.visibility = "visible"; // Make it visible
  dom.chartTooltip.style.opacity = 1; // Start fade-in (or ensure it's fully visible)
  dom.chartTooltip.classList.add("visible"); // Add class if transition relies on it
}

function hideTooltip() {
  if (dom.chartTooltip) {
    dom.chartTooltip.style.opacity = 0;
    dom.chartTooltip.style.visibility = "hidden";
    dom.chartTooltip.classList.remove("visible");
  }
  hoveredCandleIndex = null; // Reset hovered index when hiding
}

// --- Crosshair Update Functions ---
// ... (updateCrosshair, hideCrosshair - no changes needed) ...
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

  // Clamp mouse Y to chart boundaries for price calculation and line position
  const clampedMouseY = Math.max(0, Math.min(mouseY, chartHeight));

  const priceAtCursor = getPriceFromYCoordinate(clampedMouseY, chartHeight);

  if (priceAtCursor !== null && Number.isFinite(priceAtCursor)) {
    // Position horizontal line
    dom.crosshairLineX.style.top = `${clampedMouseY.toFixed(1)}px`;
    dom.crosshairLineX.style.display = "block";

    // Update and position price label
    const priceRange = state.maxVisiblePrice - state.minVisiblePrice;
    let decimals = 0;
    if (priceRange < 0.1) decimals = 4;
    else if (priceRange < 1) decimals = 3;
    else if (priceRange < 10 || priceAtCursor < 10) decimals = 2;
    else if (priceAtCursor < 1000) decimals = 1;
    else decimals = 0;
    decimals = Math.max(0, decimals); // Ensure non-negative

    dom.crosshairLabelY.textContent = priceAtCursor.toFixed(decimals);
    dom.crosshairLabelY.style.top = `${clampedMouseY.toFixed(1)}px`; // Align label with line
    dom.crosshairLabelY.style.display = "block";
  } else {
    // Hide if price calculation failed
    hideCrosshair();
  }
}

function hideCrosshair() {
  if (dom.crosshairLineX) dom.crosshairLineX.style.display = "none";
  if (dom.crosshairLabelY) dom.crosshairLabelY.style.display = "none";
}

// --- Interaction Handlers ---
// ... (handleMouseMoveForTooltip, handleMouseLeaveChartArea - no changes needed) ...
function handleMouseMoveForTooltip(event) {
  if (!dom.chartArea) return;

  const chartRect = dom.chartArea.getBoundingClientRect();
  const mouseX = event.clientX - chartRect.left;
  const mouseY = event.clientY - chartRect.top;
  const chartWidth = dom.chartArea.offsetWidth;
  const chartHeight = dom.chartArea.offsetHeight;

  // Hide crosshair and tooltip immediately if panning/dragging
  if (state.isPanning || state.isDraggingXAxis || state.isDraggingYAxis) {
    hideCrosshair();
    clearTimeout(tooltipShowTimeout);
    clearTimeout(tooltipHideTimeout);
    tooltipHideTimeout = null; // Reset hide timeout flag
    hideTooltip();
    return;
  }

  // Check if mouse is within chart bounds
  const isInsideChart =
    mouseX >= 0 && mouseX <= chartWidth && mouseY >= 0 && mouseY <= chartHeight;

  if (
    isInsideChart &&
    chartWidth > 0 &&
    chartHeight > 0 &&
    state.fullData.length > 0
  ) {
    // Update Crosshair
    updateCrosshair(mouseX, mouseY, chartHeight, chartWidth);

    // --- Tooltip Logic ---
    const visibleCount = state.visibleEndIndex - state.visibleStartIndex;
    if (visibleCount <= 0) {
      hideTooltip(); // Hide if no candles visible
      return;
    }

    const candleTotalWidth = chartWidth / visibleCount;
    // Calculate index based on mouse position
    const currentSlotIndex = Math.floor(mouseX / candleTotalWidth);
    const currentDataIndex = state.visibleStartIndex + currentSlotIndex;

    // Check if the calculated index is valid
    if (currentDataIndex >= 0 && currentDataIndex < state.fullData.length) {
      if (currentDataIndex !== hoveredCandleIndex) {
        // Mouse moved to a new candle index
        clearTimeout(tooltipShowTimeout); // Cancel any pending show
        clearTimeout(tooltipHideTimeout); // Cancel any pending hide
        tooltipHideTimeout = null;
        hideTooltip(); // Hide previous tooltip immediately

        hoveredCandleIndex = currentDataIndex; // Update hovered index

        // Set timeout to show the new tooltip after a delay
        tooltipShowTimeout = setTimeout(() => {
          showTooltip(hoveredCandleIndex, mouseX, mouseY);
          tooltipShowTimeout = null; // Clear the timeout ID once shown
        }, config.TOOLTIP_SHOW_DELAY);
      } else {
        // Mouse is still over the same candle index
        clearTimeout(tooltipHideTimeout); // Cancel hide timeout if mouse re-enters quickly
        tooltipHideTimeout = null;
        // Optional: Update tooltip position while hovering over the same candle?
        // showTooltip(hoveredCandleIndex, mouseX, mouseY); // This would make it follow cursor exactly
      }
    } else {
      // Mouse is inside chart but not over a valid candle index (e.g., padding areas)
      clearTimeout(tooltipShowTimeout); // Cancel pending show
      tooltipShowTimeout = null;
      hoveredCandleIndex = null; // No candle is hovered

      // Start hide timeout if tooltip is currently visible
      if (dom.chartTooltip && dom.chartTooltip.style.visibility === "visible") {
        if (!tooltipHideTimeout) {
          // Only start hide timer if not already running
          tooltipHideTimeout = setTimeout(() => {
            hideTooltip();
            tooltipHideTimeout = null;
          }, config.TOOLTIP_HIDE_DELAY);
        }
      } else {
        hideTooltip(); // Hide immediately if not visible
      }
    }
  } else {
    // Mouse is outside chart bounds
    hideCrosshair();
    clearTimeout(tooltipShowTimeout); // Cancel pending show
    tooltipShowTimeout = null;
    clearTimeout(tooltipHideTimeout); // Cancel pending hide
    tooltipHideTimeout = null;
    hoveredCandleIndex = null; // No candle hovered
    hideTooltip(); // Hide immediately
  }
}

function handleMouseLeaveChartArea(event) {
  // Handles BOTH crosshair and tooltip when mouse leaves the specific chartArea element
  hideCrosshair();
  clearTimeout(tooltipShowTimeout);
  tooltipShowTimeout = null;
  clearTimeout(tooltipHideTimeout);
  tooltipHideTimeout = null;
  hoveredCandleIndex = null;
  hideTooltip();
}

// --- Chart Interaction Handlers (Zoom, Pan, Scale, Resize, DoubleClick) ---
// ... (handleZoom, handleMouseMove, handleMouseDownChart, etc. - no changes needed) ...
export function handleZoom(event) {
  event.preventDefault();
  if (!dom.chartArea) return;

  const chartRect = dom.chartArea.getBoundingClientRect();
  const mouseX = event.clientX - chartRect.left;
  const mouseY = event.clientY - chartRect.top;
  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;

  if (!chartHeight || !chartWidth || !state.fullData.length) return;

  const zoomDirection = event.deltaY < 0 ? -1 : 1; // -1 for zoom in, 1 for zoom out
  let newState = {};

  // --- Y-Axis Zoom ---
  const currentMinY = state.minVisiblePrice;
  const currentMaxY = state.maxVisiblePrice;

  if (state.isLogScale) {
    const logMin = safeLog(currentMinY);
    const logMax = safeLog(currentMaxY);
    const logRange = logMax - logMin;

    // Check if range is valid for zooming
    if (logRange > 0 && Number.isFinite(logRange)) {
      const logAtCursor = logMax - (mouseY / chartHeight) * logRange; // Price (in log space) at cursor Y
      const zoomAmountY = 1 + zoomDirection * config.ZOOM_FACTOR_Y;

      // Calculate new log min/max based on zooming around the cursor position
      let newLogMin = logAtCursor - (logAtCursor - logMin) * zoomAmountY;
      let newLogMax = logAtCursor + (logMax - logAtCursor) * zoomAmountY;

      // Convert back to linear scale and ensure min is positive
      newState.minVisiblePrice = Math.max(MIN_LOG_VALUE, exp(newLogMin));
      newState.maxVisiblePrice = exp(newLogMax);

      // Prevent excessive zoom-in (minimum ratio)
      if (newState.maxVisiblePrice / newState.minVisiblePrice < 1.001) {
        const midPriceLog = (newLogMin + newLogMax) / 2;
        const halfRangeLog = Math.log(1.0005); // ~0.05% ratio
        newState.minVisiblePrice = Math.max(
          MIN_LOG_VALUE,
          exp(midPriceLog - halfRangeLog)
        );
        newState.maxVisiblePrice = exp(midPriceLog + halfRangeLog);
      }
    }
  } else {
    // Linear Scale Zoom
    const linearRange = currentMaxY - currentMinY;

    if (linearRange > 0 && Number.isFinite(linearRange)) {
      const priceAtCursor = currentMaxY - (mouseY / chartHeight) * linearRange;
      const zoomAmountY = 1 + zoomDirection * config.ZOOM_FACTOR_Y;

      let newMin = priceAtCursor - (priceAtCursor - currentMinY) * zoomAmountY;
      let newMax = priceAtCursor + (currentMaxY - priceAtCursor) * zoomAmountY;

      // Ensure minimum price span and non-negative min
      if (newMax - newMin < config.MIN_PRICE_RANGE_SPAN) {
        const mid = (newMax + newMin) / 2;
        newMin = mid - config.MIN_PRICE_RANGE_SPAN / 2;
        newMax = mid + config.MIN_PRICE_RANGE_SPAN / 2;
      }
      newState.minVisiblePrice = Math.max(0, newMin); // Clamp min at 0
      newState.maxVisiblePrice = newMax;
    }
  }

  // --- X-Axis Zoom ---
  const currentVisibleCount = state.visibleEndIndex - state.visibleStartIndex;
  if (currentVisibleCount > 0) {
    // Calculate the data index under the cursor
    const indexAtCursorFloat =
      state.visibleStartIndex + (mouseX / chartWidth) * currentVisibleCount;
    const zoomAmountX = 1 + zoomDirection * config.ZOOM_FACTOR_X;

    // Calculate new number of visible candles
    let newVisibleCount = Math.round(currentVisibleCount * zoomAmountX);
    newVisibleCount = Math.max(
      config.MIN_VISIBLE_CANDLES,
      // Limit zoom out to maybe 5x the total data length? Prevents excessive range.
      Math.min(newVisibleCount, state.fullData.length * 5)
    );
    // Clamp further to not exceed total data length when zooming in fully
    newVisibleCount = Math.min(newVisibleCount, state.fullData.length);

    // Calculate new start index to keep the index under the cursor stationary
    let newStartIndex = Math.round(
      indexAtCursorFloat - (mouseX / chartWidth) * newVisibleCount
    );

    // Clamp start/end indices to valid range [0, fullData.length]
    newStartIndex = Math.max(0, newStartIndex);
    let newEndIndex = newStartIndex + newVisibleCount;

    // Adjust if end index exceeds data bounds
    if (newEndIndex > state.fullData.length) {
      newEndIndex = state.fullData.length;
      newStartIndex = Math.max(0, newEndIndex - newVisibleCount); // Recalculate start index based on clamped end
    }
    // Final clamp on start index (shouldn't be needed if logic above is correct, but safe)
    newStartIndex = Math.max(0, newStartIndex);

    newState.visibleStartIndex = newStartIndex;
    newState.visibleEndIndex = newEndIndex;
  }

  // Apply the combined state changes
  if (Object.keys(newState).length > 0) {
    updateState(newState);
    requestAnimationFrame(redrawChart);
  }
}

export function handleMouseMove(event) {
  if (!state.isPanning && !state.isDraggingYAxis && !state.isDraggingXAxis) {
    // If not dragging/panning, delegate to tooltip/crosshair handler
    // handleMouseMoveForTooltip(event); // This causes issues if mouse moves outside chartArea
    return;
  }

  // Throttle redraw calls during drag/pan
  const now = Date.now();
  if (now - state.lastDrawTime < config.MOUSE_MOVE_THROTTLE) return;

  let needsRedraw = false;
  let newState = {};
  const chartHeight = dom.chartArea?.offsetHeight;
  const chartWidth = dom.chartArea?.offsetWidth;

  // --- Y-Axis Scaling (Dragging Y Axis) ---
  if (state.isDraggingYAxis) {
    const deltaY = event.clientY - state.panStartY;
    if (!chartHeight || chartHeight <= 0) return;

    if (state.isLogScale) {
      const logMinStart = safeLog(state.panStartMinPrice);
      const logMaxStart = safeLog(state.panStartMaxPrice);
      const logRangeStart = logMaxStart - logMinStart;

      if (logRangeStart > 0 && Number.isFinite(logRangeStart)) {
        const midLogPrice = (logMaxStart + logMinStart) / 2;
        // Exponential scaling based on drag distance
        const scaleFactor = Math.pow(
          2,
          (deltaY / chartHeight) * config.Y_AXIS_DRAG_SENSITIVITY
        );
        let newLogRange = logRangeStart * scaleFactor;

        // Prevent excessive zoom-in (minimum ratio ~0.1%)
        if (exp(newLogRange) < 1.001) {
          newLogRange = log(1.001);
        }

        const newLogMin = midLogPrice - newLogRange / 2;
        const newLogMax = midLogPrice + newLogRange / 2;

        const newMin = Math.max(MIN_LOG_VALUE, exp(newLogMin));
        const newMax = exp(newLogMax);

        // Check if changes are significant enough to redraw
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
      // Linear Scale Y-Axis Drag
      const initialRange = state.panStartMaxPrice - state.panStartMinPrice;
      if (initialRange > 0 && Number.isFinite(initialRange)) {
        const midPrice = (state.panStartMaxPrice + state.panStartMinPrice) / 2;
        const scaleFactor = Math.pow(
          2,
          (deltaY / chartHeight) * config.Y_AXIS_DRAG_SENSITIVITY
        );
        let newRange = initialRange * scaleFactor;
        newRange = Math.max(config.MIN_PRICE_RANGE_SPAN, newRange); // Enforce min span

        const newMin = midPrice - newRange / 2;
        const newMax = midPrice + newRange / 2;

        // Check if changes are significant
        if (
          Math.abs(newMin - state.minVisiblePrice) > 1e-9 ||
          Math.abs(newMax - state.maxVisiblePrice) > 1e-9
        ) {
          newState.minVisiblePrice = Math.max(0, newMin); // Clamp min at 0
          newState.maxVisiblePrice = newMax;
          needsRedraw = true;
        }
      }
    }
  }
  // --- X-Axis Scaling (Dragging X Axis) ---
  else if (state.isDraggingXAxis) {
    const deltaX = event.clientX - state.panStartX;
    if (!chartWidth || chartWidth <= 0 || state.panStartVisibleCount <= 0)
      return;

    const centerIndex =
      state.panStartVisibleIndex + state.panStartVisibleCount / 2;
    const scaleFactor = Math.pow(
      2,
      (deltaX / chartWidth) * config.X_AXIS_DRAG_SENSITIVITY
    );

    let newVisibleCount = Math.round(state.panStartVisibleCount * scaleFactor);
    // Clamp new count: min candles, max data length * factor, max total data length
    newVisibleCount = Math.max(config.MIN_VISIBLE_CANDLES, newVisibleCount);
    newVisibleCount = Math.min(newVisibleCount, state.fullData.length * 5); // Limit zoom out
    newVisibleCount = Math.min(newVisibleCount, state.fullData.length); // Cannot show more than exist

    let newStartIndex = Math.round(centerIndex - newVisibleCount / 2);

    // Clamp start/end indices
    newStartIndex = Math.max(0, newStartIndex);
    let newEndIndex = newStartIndex + newVisibleCount;
    if (newEndIndex > state.fullData.length) {
      newEndIndex = state.fullData.length;
      newStartIndex = Math.max(0, newEndIndex - newVisibleCount);
    }
    newStartIndex = Math.max(0, newStartIndex); // Final start clamp

    // Check if indices changed
    if (
      newStartIndex !== state.visibleStartIndex ||
      newEndIndex !== state.visibleEndIndex
    ) {
      newState.visibleStartIndex = newStartIndex;
      newState.visibleEndIndex = newEndIndex;
      needsRedraw = true;
    }
  }
  // --- Chart Panning ---
  else if (state.isPanning) {
    const deltaX = event.clientX - state.panStartX;
    const deltaY = event.clientY - state.panStartY;
    if (!chartWidth || !chartHeight || chartWidth <= 0 || chartHeight <= 0)
      return;

    let changedX = false;
    let changedY = false;

    // Pan X (Time)
    if (state.panStartVisibleCount > 0) {
      const indexDelta = (deltaX / chartWidth) * state.panStartVisibleCount;
      let newStartIndex = state.panStartVisibleIndex - Math.round(indexDelta);

      // Clamp panning within data bounds [0, N - visibleCount]
      const maxStartIndex = state.fullData.length - state.panStartVisibleCount;
      newStartIndex = Math.max(0, Math.min(newStartIndex, maxStartIndex));

      if (newStartIndex !== state.visibleStartIndex) {
        newState.visibleStartIndex = newStartIndex;
        newState.visibleEndIndex = newStartIndex + state.panStartVisibleCount;
        changedX = true;
      }
    }

    // Pan Y (Price)
    if (state.isLogScale) {
      const logMinStart = safeLog(state.panStartMinPrice);
      const logMaxStart = safeLog(state.panStartMaxPrice);
      const logRangeStart = logMaxStart - logMinStart;

      if (logRangeStart > 0 && Number.isFinite(logRangeStart)) {
        const logDelta = (deltaY / chartHeight) * logRangeStart;
        const newLogMin = logMinStart + logDelta;
        const newLogMax = logMaxStart + logDelta;

        const newMin = Math.max(MIN_LOG_VALUE, exp(newLogMin));
        const newMax = exp(newLogMax);

        // Check for significant change
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
      // Linear Scale Pan Y
      const initialPriceRange = state.panStartMaxPrice - state.panStartMinPrice;
      if (initialPriceRange > 0 && Number.isFinite(initialPriceRange)) {
        const priceDelta = (deltaY / chartHeight) * initialPriceRange;
        const newMinPrice = state.panStartMinPrice + priceDelta;
        const newMaxPrice = state.panStartMaxPrice + priceDelta;

        // Check for significant change
        if (
          Math.abs(newMinPrice - state.minVisiblePrice) > 1e-9 ||
          Math.abs(newMaxPrice - state.maxVisiblePrice) > 1e-9
        ) {
          newState.minVisiblePrice = Math.max(0, newMinPrice); // Clamp min at 0
          newState.maxVisiblePrice = newMaxPrice;
          changedY = true;
        }
      }
    }
    needsRedraw = changedX || changedY;
  }

  // If changes occurred, update state and request redraw
  if (needsRedraw) {
    updateState({ ...newState, lastDrawTime: now });
    requestAnimationFrame(redrawChart);
  }
}

export function handleMouseDownChart(event) {
  // Only initiate panning if the click is directly on the chart area/wrapper
  // or potentially on grid lines, but NOT on axis labels or other controls within container
  const target = event.target;
  if (!dom.chartArea || !dom.chartWrapper || !dom.gridContainer) return;

  if (
    target === dom.chartArea ||
    target === dom.chartWrapper ||
    target === dom.gridContainer ||
    target.classList.contains("grid-line") ||
    target.classList.contains("candle")
  ) {
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
  } else {
    // If click wasn't on a pannable element, ensure panning state is false
    if (state.isPanning) {
      updateState({ isPanning: false });
      if (dom.chartContainer) dom.chartContainer.classList.remove("panning");
    }
  }
}

export function handleMouseDownYAxis(event) {
  event.stopPropagation(); // Prevent chart panning
  updateState({
    isDraggingYAxis: true,
    isPanning: false,
    isDraggingXAxis: false,
    panStartY: event.clientY,
    panStartMinPrice: state.minVisiblePrice,
    panStartMaxPrice: state.maxVisiblePrice,
    // No need for X axis pan start info here
  });
}

export function handleMouseDownXAxis(event) {
  event.stopPropagation(); // Prevent chart panning
  updateState({
    isDraggingXAxis: true,
    isPanning: false,
    isDraggingYAxis: false,
    panStartX: event.clientX,
    panStartVisibleIndex: state.visibleStartIndex,
    panStartVisibleCount: state.visibleEndIndex - state.visibleStartIndex,
    // No need for Y axis pan start info here
  });
}

export function handleMouseUpOrLeave(event) {
  // This handles mouseup anywhere on the window or leaving the window
  if (state.isPanning || state.isDraggingYAxis || state.isDraggingXAxis) {
    updateState({
      isPanning: false,
      isDraggingYAxis: false,
      isDraggingXAxis: false,
    });
    if (dom.chartContainer) dom.chartContainer.classList.remove("panning");
  }
  // Note: handleMouseLeaveChartArea handles leaving the specific chart drawing area
  // for hiding tooltips/crosshairs. This handler is for drag/pan state globally.
}

let resizeTimeout;
export function handleResize() {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    // Redrawing handles canvas resizing internally now
    requestAnimationFrame(redrawChart);
  }, config.DEBOUNCE_DELAY);
}

// --- Double Click Handler with Dynamic Y-Axis Scaling ---
export function handleDoubleClick(event) {
  if (!state.fullData.length || !dom.chartArea) return;
  const chartHeight = dom.chartArea.offsetHeight;
  if (!chartHeight || chartHeight <= 0) return; // Need height for scaling

  // --- Reset X-Axis (Time) ---
  const totalDataCount = state.fullData.length;
  let newVisibleCount = Math.min(
    config.DEFAULT_RESET_CANDLE_COUNT,
    totalDataCount
  );
  let newEndIndex = totalDataCount; // Show up to the latest candle
  let newStartIndex = Math.max(0, newEndIndex - newVisibleCount);
  newVisibleCount = newEndIndex - newStartIndex; // Recalculate actual count

  // --- Find Actual Data Range (Y-Axis) in the New Time Window ---
  let newMinY = Infinity,
    newMaxY = -Infinity;
  for (let i = newStartIndex; i < newEndIndex; i++) {
    if (!state.fullData[i] || state.fullData[i].length < 5) continue;
    const low = state.fullData[i][1];
    const high = state.fullData[i][2];
    if (!isNaN(low) && Number.isFinite(low)) {
      newMinY = Math.min(newMinY, low);
    }
    if (!isNaN(high) && Number.isFinite(high)) {
      newMaxY = Math.max(newMaxY, high);
    }
  }

  // Handle cases where range couldn't be determined or is invalid
  let dataRangeY;
  const minValidRange = 1e-9; // A very small number to represent effectively zero range

  if (
    newMinY === Infinity ||
    newMaxY === -Infinity ||
    newMaxY - newMinY < minValidRange
  ) {
    console.warn(
      "Could not determine valid price range for reset view or range too small, using fallback."
    );
    // Center around last price or a default value
    const lastCandle = state.fullData[state.fullData.length - 1];
    const centerPrice =
      lastCandle && lastCandle.length >= 5 && Number.isFinite(lastCandle[4])
        ? lastCandle[4]
        : (state.minVisiblePrice + state.maxVisiblePrice) / 2 || 100;

    // Use a small default span based on scale type
    if (state.isLogScale) {
      newMinY = Math.max(MIN_LOG_VALUE, centerPrice / 1.01); // +/- 1%
      newMaxY = centerPrice * 1.01;
    } else {
      const halfSpan = config.MIN_PRICE_RANGE_SPAN / 2 || 0.05;
      newMinY = Math.max(0, centerPrice - halfSpan);
      newMaxY = centerPrice + halfSpan;
    }
    dataRangeY = newMaxY - newMinY; // Recalculate data range for fallback
    if (dataRangeY < minValidRange) dataRangeY = minValidRange; // Ensure positive range
  } else {
    dataRangeY = newMaxY - newMinY;
  }

  // Ensure minimums are positive for log scale calculations
  newMinY = Math.max(MIN_LOG_VALUE, newMinY);
  newMaxY = Math.max(newMinY + minValidRange, newMaxY); // Ensure max > min

  // --- Calculate Required Total Y-Range for Target Fill ---
  let newMinPrice, newMaxPrice;
  const targetFill = config.Y_AXIS_RESET_FILL_FACTOR; // e.g., 0.85
  const inverseFill = 1.0 / targetFill;

  if (state.isLogScale) {
    // Log Scale Calculation
    const safeMinY = Math.max(MIN_LOG_VALUE, newMinY);
    const safeMaxY = Math.max(safeMinY * 1.0001, newMaxY); // Ensure Max > Min slightly

    const logDataRangeY = safeLog(safeMaxY) - safeLog(safeMinY);

    if (!Number.isFinite(logDataRangeY) || logDataRangeY <= 0) {
      // Fallback if log range calculation fails
      console.warn(
        "Log range calculation failed in reset, using simple padding."
      );
      const logPadding = 1 + config.Y_AXIS_LOG_PADDING_FACTOR;
      newMinPrice = Math.max(MIN_LOG_VALUE, safeMinY / logPadding);
      newMaxPrice = safeMaxY * logPadding;
    } else {
      const logTotalRange = logDataRangeY * inverseFill;
      const logPaddingTotal = logTotalRange - logDataRangeY;
      const logPaddingAmount = logPaddingTotal / 2.0;

      const newLogMin = safeLog(safeMinY) - logPaddingAmount;
      const newLogMax = safeLog(safeMaxY) + logPaddingAmount;

      newMinPrice = Math.max(MIN_LOG_VALUE, exp(newLogMin));
      newMaxPrice = exp(newLogMax);

      // Ensure minimum range ratio after calculation
      if (newMaxPrice / newMinPrice < 1.01) {
        const midLog = (newLogMax + newLogMin) / 2;
        const halfRangeLog = Math.log(1.005);
        newMinPrice = Math.max(MIN_LOG_VALUE, exp(midLog - halfRangeLog));
        newMaxPrice = exp(midLog + halfRangeLog);
      }
    }
  } else {
    // Linear Scale Calculation
    if (dataRangeY <= 0) {
      // Should be handled by fallback above, but double check
      console.warn("Linear range is zero in reset, using simple padding.");
      const halfSpan = config.MIN_PRICE_RANGE_SPAN / 2 || 0.05;
      newMinPrice = Math.max(0, newMinY - halfSpan);
      newMaxPrice = newMaxY + halfSpan;
    } else {
      const totalRange = dataRangeY * inverseFill;
      const paddingTotal = totalRange - dataRangeY;
      const paddingAmount = paddingTotal / 2.0;

      newMinPrice = Math.max(0, newMinY - paddingAmount); // Clamp at 0
      newMaxPrice = newMaxY + paddingAmount;

      // Ensure minimum linear range span
      if (newMaxPrice - newMinPrice < config.MIN_PRICE_RANGE_SPAN) {
        const mid = (newMaxPrice + newMinPrice) / 2;
        newMinPrice = Math.max(0, mid - config.MIN_PRICE_RANGE_SPAN / 2);
        newMaxPrice = mid + config.MIN_PRICE_RANGE_SPAN / 2;
      }
    }
  }

  // Update state with new X and Y ranges
  updateState({
    visibleStartIndex: newStartIndex,
    visibleEndIndex: newEndIndex,
    minVisiblePrice: newMinPrice,
    maxVisiblePrice: newMaxPrice,
    // DO NOT reset isLogScale or is12HourFormat here
  });

  // Request redraw with the new state
  requestAnimationFrame(redrawChart);
}
// --- End of Double Click Handler ---

export function handleLogScaleToggle() {
  const isChecked = dom.logScaleToggle.checked;
  updateState({ isLogScale: isChecked });
  localStorage.setItem("logScalePref", isChecked.toString());
  // Recalculate Y range based on the center price of the *current* view
  // to make the transition smoother.
  const centerY = dom.chartArea.offsetHeight / 2;
  const centerPrice = getPriceFromYCoordinate(
    centerY,
    dom.chartArea.offsetHeight
  );

  if (centerPrice !== null && Number.isFinite(centerPrice)) {
    const currentMin = state.minVisiblePrice;
    const currentMax = state.maxVisiblePrice;
    let newMin, newMax;

    if (isChecked) {
      // Switching TO Log
      const linearRange = currentMax - currentMin;
      const logCenter = safeLog(centerPrice);
      // Estimate equivalent log range (this is approximate)
      const logRangeEstimate = safeLog(currentMax) - safeLog(currentMin); // Use current log range

      if (Number.isFinite(logRangeEstimate) && logRangeEstimate > 0) {
        const halfLogRange = logRangeEstimate / 2;
        newMin = Math.max(MIN_LOG_VALUE, exp(logCenter - halfLogRange));
        newMax = exp(logCenter + halfLogRange);
      } else {
        // Fallback if range fails
        newMin = Math.max(MIN_LOG_VALUE, centerPrice / 1.1);
        newMax = centerPrice * 1.1;
      }
      // Ensure min log ratio
      if (newMax / newMin < 1.01) {
        const midLog = (safeLog(newMax) + safeLog(newMin)) / 2;
        newMin = Math.max(MIN_LOG_VALUE, exp(midLog - Math.log(1.005)));
        newMax = exp(midLog + Math.log(1.005));
      }
    } else {
      // Switching TO Linear
      const logRange = safeLog(currentMax) - safeLog(currentMin);
      // Estimate equivalent linear range based on center price (approximate)
      const linearRatio = currentMax / currentMin; // Ratio
      const linearRangeEstimate = centerPrice * (linearRatio - 1); // Very rough estimate
      let halfLinearRange = linearRangeEstimate / 2;

      // Use a more stable fallback if estimate is bad
      if (
        !Number.isFinite(halfLinearRange) ||
        halfLinearRange <= config.MIN_PRICE_RANGE_SPAN / 2
      ) {
        halfLinearRange =
          (currentMax - currentMin) / 2 || config.MIN_PRICE_RANGE_SPAN; // Use current linear diff or default
      }
      halfLinearRange = Math.max(
        config.MIN_PRICE_RANGE_SPAN / 2,
        halfLinearRange
      );

      newMin = Math.max(0, centerPrice - halfLinearRange);
      newMax = centerPrice + halfLinearRange;
      // Ensure min linear span
      if (newMax - newMin < config.MIN_PRICE_RANGE_SPAN) {
        const mid = (newMax + newMin) / 2;
        newMin = Math.max(0, mid - config.MIN_PRICE_RANGE_SPAN / 2);
        newMax = mid + config.MIN_PRICE_RANGE_SPAN / 2;
      }
    }

    updateState({ minVisiblePrice: newMin, maxVisiblePrice: newMax });
  } else {
    console.warn("Could not get center price for scale toggle adjustment.");
  }

  requestAnimationFrame(redrawChart);
}

export function handleTimeFormatToggle() {
  const isChecked = dom.timeFormatToggle.checked;
  updateState({ is12HourFormat: isChecked });
  localStorage.setItem("timeFormatPref", isChecked.toString());
  requestAnimationFrame(redrawChart); // Redraw to update X-axis labels
}

// --- Attach Listeners ---
export function attachInteractionListeners() {
  if (
    !dom.chartContainer ||
    !dom.yAxisLabelsContainer ||
    !dom.xAxisLabelsContainer ||
    !dom.chartArea
  ) {
    console.error(
      "Cannot attach interaction listeners: Essential chart DOM elements missing."
    );
    return;
  }

  // Chart container handles wheel (zoom), main panning mousedown, and double click reset
  dom.chartContainer.addEventListener("wheel", handleZoom, { passive: false });
  dom.chartContainer.addEventListener("mousedown", handleMouseDownChart);
  dom.chartContainer.addEventListener("dblclick", handleDoubleClick);

  // Axis labels handle scaling mousedown
  dom.yAxisLabelsContainer.addEventListener("mousedown", handleMouseDownYAxis);
  dom.xAxisLabelsContainer.addEventListener("mousedown", handleMouseDownXAxis);

  // Window handles mouse move (for drag/pan/scale) and mouseup (to end actions)
  window.addEventListener("mousemove", handleMouseMove);
  window.addEventListener("mouseup", handleMouseUpOrLeave);
  window.addEventListener("mouseleave", handleMouseUpOrLeave); // Handle mouse leaving window during drag

  // Window handles resize
  window.addEventListener("resize", handleResize);

  // Chart area handles mouse move and leave specifically for tooltips/crosshairs
  dom.chartArea.addEventListener("mousemove", handleMouseMoveForTooltip);
  dom.chartArea.addEventListener("mouseleave", handleMouseLeaveChartArea);

  // Settings toggles
  if (dom.logScaleToggle) {
    dom.logScaleToggle.addEventListener("change", handleLogScaleToggle);
  } else {
    console.warn("Log scale toggle checkbox not found.");
  }

  if (dom.timeFormatToggle) {
    dom.timeFormatToggle.addEventListener("change", handleTimeFormatToggle);
  } else {
    console.warn("Time format toggle checkbox not found.");
  }

  console.log("Chart interaction listeners attached.");
}
