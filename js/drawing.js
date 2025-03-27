// js/drawing.js

import * as config from "./config.js";
import state from "./state.js";
import * as dom from "./domElements.js";
import {
  calculateNiceStep,
  formatTimestamp,
  formatDate,
  getYCoordinate,
} from "./utils.js";

// Constants for label density logic
const SECONDS_PER_DAY = 86400;
const MIN_PIXELS_PER_LABEL = 60; // Minimum space between labels (adjust as needed)

/**
 * Updates the position and text of the live price indicator UI elements.
 * (This function remains the same)
 */
function updateLivePriceIndicatorUI(price, chartHeight) {
  // ... (Keep existing code for this function) ...
  if (
    !dom.currentPriceLabel ||
    !dom.currentPriceLine ||
    isNaN(price) ||
    !chartHeight
  ) {
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
    return;
  }
  const y = getYCoordinate(price, chartHeight);
  if (y !== null && !isNaN(y)) {
    const decimals = price < 1 ? 4 : price < 100 ? 2 : price < 10000 ? 1 : 0;
    dom.currentPriceLabel.textContent = price.toFixed(decimals);
    dom.currentPriceLabel.style.top = `${y.toFixed(1)}px`;
    dom.currentPriceLine.style.top = `${y.toFixed(1)}px`;
    dom.currentPriceLabel.style.display = "block";
    dom.currentPriceLine.style.display = "block";
  } else {
    dom.currentPriceLabel.style.display = "none";
    dom.currentPriceLine.style.display = "none";
  }
}

/**
 * Clears and redraws the entire chart area (candles, grid, axes).
 * Includes updated logic for X-axis labels and candle centering.
 */
export function redrawChart() {
  if (
    !state.fullData ||
    !dom.chartArea.offsetHeight ||
    !dom.chartArea.offsetWidth
  ) {
    return;
  }

  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;
  const linearPriceRange = state.maxVisiblePrice - state.minVisiblePrice;
  const visibleCount = state.visibleEndIndex - state.visibleStartIndex;

  dom.chartArea.innerHTML = "";
  dom.gridContainer.innerHTML = "";
  dom.yAxisLabelsContainer.innerHTML = "";
  dom.xAxisLabelsContainer.innerHTML = "";

  if (visibleCount <= 0 || chartWidth <= 0 || chartHeight <= 0) {
    return;
  }
  // Ensure price range is valid or default
  if (linearPriceRange <= 0 && !state.isLogScale) {
    // Avoid drawing if range is invalid in linear scale, maybe show message?
    // For now, let's proceed but Y calculations might be centered
  }

  // --- Candle Width Calculation (No Margins Needed for Centering) ---
  const candleTotalWidth = chartWidth / visibleCount; // Total space per candle
  const candleBodyWidthRatio = 0.7; // Ratio of space the candle body occupies
  const candleWidth = Math.max(1, candleTotalWidth * candleBodyWidthRatio);

  try {
    // Draw Grid & Y-Axis (largely unchanged)
    const yTickDensity = Math.max(3, Math.round(chartHeight / 45)); // Slightly denser
    const displayRange =
      linearPriceRange > 0
        ? linearPriceRange
        : state.isLogScale
        ? state.maxVisiblePrice
        : 1; // Adjust for log/linear default
    const yTicks = calculateNiceStep(displayRange, yTickDensity);
    const firstYTick =
      yTicks > Number.EPSILON
        ? Math.ceil(state.minVisiblePrice / yTicks) * yTicks
        : state.minVisiblePrice;

    for (
      let price = firstYTick;
      price <= state.maxVisiblePrice + yTicks * 0.1;
      price += yTicks
    ) {
      if (yTicks <= Number.EPSILON || (state.isLogScale && price <= 0)) break; // Prevent infinite loops or log(0) issues
      const y = getYCoordinate(price, chartHeight);
      if (y === null || isNaN(y)) continue;

      // Draw grid line if within reasonable bounds
      if (y >= -chartHeight * 0.1 && y <= chartHeight * 1.1) {
        // Allow slight overflow for labels
        const hLine = document.createElement("div");
        hLine.className = "grid-line horizontal";
        hLine.style.top = `${y.toFixed(1)}px`;
        dom.gridContainer.appendChild(hLine);
      }
      // Draw label only if clearly within visible bounds
      if (y >= -5 && y <= chartHeight + 5) {
        const yLabel = document.createElement("div");
        yLabel.className = "axis-label y-axis-label";
        yLabel.style.top = `${y.toFixed(1)}px`;
        const priceRangeForDecimals =
          state.maxVisiblePrice - state.minVisiblePrice;
        const decimals =
          priceRangeForDecimals < 1
            ? 4
            : priceRangeForDecimals < 10
            ? 2
            : price < 100
            ? 1
            : 0;
        yLabel.textContent = price.toFixed(Math.max(0, decimals));
        dom.yAxisLabelsContainer.appendChild(yLabel);
      }
      if (price + yTicks <= price) break; // Prevent infinite loop on floating point issues
    }
  } catch (e) {
    console.error("Error drawing Y grid/axis:", e);
  }

  // --- Draw X-Axis & Separators (Major Changes Here) ---
  try {
    const timeSpanVisible = visibleCount * state.currentGranularity; // Approx seconds visible
    const showTimeLabels =
      state.currentGranularity < SECONDS_PER_DAY &&
      timeSpanVisible < 2 * SECONDS_PER_DAY; // Show time only for <1d intervals and <2 days visible span
    const showMonthSeparators = timeSpanVisible > 5 * SECONDS_PER_DAY; // Add month emphasis if viewing > 5 days
    const showYearSeparators = timeSpanVisible > 180 * SECONDS_PER_DAY; // Add year emphasis if viewing > 6 months

    let lastLabelX = -Infinity; // Track position of the last placed date/time label
    let lastDateLabelX = -Infinity; // Track position of the last major date label (Day/Month/Year)
    let previousTimestamp = null;
    let previousJsDate = null;

    // Iterate slightly beyond visible range to catch labels/lines near edges
    const startIndexToDraw = Math.max(0, state.visibleStartIndex - 2);
    const endIndexToDraw = Math.min(
      state.fullData.length,
      state.visibleEndIndex + 2
    );

    for (let i = startIndexToDraw; i < endIndexToDraw; i++) {
      const candleData = state.fullData[i];
      if (!candleData || candleData.length < 1) continue; // Need at least timestamp

      const timestamp = candleData[0];
      const currentJsDate = new Date(timestamp * 1000);
      const relativeIndex = i - state.visibleStartIndex; // Index relative to the start of the visible area

      // *** Calculate center X position for this candle ***
      const candleCenterX = (relativeIndex + 0.5) * candleTotalWidth;

      // Check if position is within drawable area
      if (
        candleCenterX < -candleTotalWidth ||
        candleCenterX > chartWidth + candleTotalWidth
      ) {
        previousTimestamp = timestamp; // Still update previous timestamp for next iteration's checks
        previousJsDate = currentJsDate;
        continue;
      }

      // --- Date Change Logic ---
      const isFirst = previousJsDate === null;
      const dayChanged =
        isFirst || currentJsDate.getDate() !== previousJsDate.getDate();
      const monthChanged =
        isFirst || currentJsDate.getMonth() !== previousJsDate.getMonth();
      const yearChanged =
        isFirst || currentJsDate.getFullYear() !== previousJsDate.getFullYear();

      // --- Draw Separator Lines ---
      let separatorClass = "";
      if (yearChanged)
        separatorClass =
          "year-separator-line"; // Define this class in CSS if needed
      else if (monthChanged && showMonthSeparators)
        separatorClass =
          "month-separator-line"; // Define this class in CSS if needed
      else if (dayChanged && !showTimeLabels)
        separatorClass = "day-separator-line"; // Only show day lines if time isn't shown

      // Draw separator at the *start* of the candle's space (between candles)
      const separatorX = relativeIndex * candleTotalWidth;
      if (
        !isFirst &&
        separatorClass &&
        separatorX >= 0 &&
        separatorX <= chartWidth
      ) {
        const separatorLine = document.createElement("div");
        // Use day-separator-line style for now, can add specific styles later
        separatorLine.className = `day-separator-line ${separatorClass}`;
        separatorLine.style.left = `${separatorX.toFixed(1)}px`;
        dom.gridContainer.appendChild(separatorLine);
      }

      // --- Draw Labels (Adaptive Logic) ---
      let dateLabelString = null;
      let isMajorDateLabel = false;

      // Determine what date label to show (if any) based on significance and spacing
      if (yearChanged && showYearSeparators) {
        dateLabelString = currentJsDate.getFullYear().toString();
        isMajorDateLabel = true;
      } else if (monthChanged && showMonthSeparators) {
        // Show "Mmm YYYY" if year also changed or it's the first label, else just "Mmm"
        const yearStr =
          yearChanged || isFirst ? ` ${currentJsDate.getFullYear()}` : "";
        dateLabelString =
          currentJsDate.toLocaleString("en-US", { month: "short" }) + yearStr;
        isMajorDateLabel = true;
      } else if (dayChanged && !showTimeLabels) {
        // Show Day only if not showing time labels
        dateLabelString = formatDate(timestamp); // Mmm D
        isMajorDateLabel = true; // Treat day label as major if time isn't shown
      }

      // Draw the Major Date Label if determined and enough space exists
      if (
        dateLabelString &&
        candleCenterX >= 0 &&
        candleCenterX <= chartWidth &&
        candleCenterX - lastDateLabelX > MIN_PIXELS_PER_LABEL * 1.5
      ) {
        const dateLabel = document.createElement("div");
        dateLabel.className = "axis-label x-axis-date-label"; // Main date label style
        dateLabel.textContent = dateLabelString;
        dateLabel.style.left = `${candleCenterX.toFixed(1)}px`;
        dom.xAxisLabelsContainer.appendChild(dateLabel);
        lastLabelX = candleCenterX;
        lastDateLabelX = candleCenterX; // Update position of last major date label
      }

      // Draw Time Label if applicable and enough space exists since *any* last label
      if (
        showTimeLabels &&
        candleCenterX >= 0 &&
        candleCenterX <= chartWidth &&
        candleCenterX - lastLabelX > MIN_PIXELS_PER_LABEL
      ) {
        // Simple tick logic: label every N candles based on density, maybe make N dynamic later
        const tickInterval = Math.max(
          1,
          Math.round(MIN_PIXELS_PER_LABEL / candleTotalWidth)
        );
        if (i % tickInterval === 0) {
          const timeLabel = document.createElement("div");
          timeLabel.className = "axis-label x-axis-label"; // Subdued time label style
          timeLabel.textContent = formatTimestamp(timestamp);
          timeLabel.style.left = `${candleCenterX.toFixed(1)}px`;
          dom.xAxisLabelsContainer.appendChild(timeLabel);
          lastLabelX = candleCenterX; // Update position of the last placed label
        }
      }

      previousTimestamp = timestamp;
      previousJsDate = currentJsDate;
    }
  } catch (e) {
    console.error("Error drawing X grid/axis:", e);
  }

  // --- Draw Candles (Centering Logic) ---
  try {
    for (let i = 0; i < visibleCount; i++) {
      const dataIndex = state.visibleStartIndex + i;
      if (dataIndex < 0 || dataIndex >= state.fullData.length) continue; // Skip if index out of bounds

      const candleData = state.fullData[dataIndex];
      if (!candleData || candleData.length < 6) {
        continue;
      } // Skip incomplete data

      const [timestamp, low, high, open, close, volume] = candleData;
      const wickHighY = getYCoordinate(high, chartHeight);
      const wickLowY = getYCoordinate(low, chartHeight);
      const bodyTopY = getYCoordinate(Math.max(open, close), chartHeight);
      const bodyBottomY = getYCoordinate(Math.min(open, close), chartHeight);

      if (
        wickHighY === null ||
        wickLowY === null ||
        bodyTopY === null ||
        bodyBottomY === null
      ) {
        continue;
      }

      const wickHeight = Math.max(1, wickLowY - wickHighY);
      const bodyHeight = Math.max(1, bodyBottomY - bodyTopY);
      const isUp = close >= open;

      const candleElement = document.createElement("div");
      candleElement.className = "candle";

      // *** Calculate position based on center ***
      const candleCenterX = (i + 0.5) * candleTotalWidth;
      const candleLeft = candleCenterX - candleWidth / 2;

      candleElement.style.position = "absolute"; // Use absolute positioning
      candleElement.style.left = `${candleLeft.toFixed(1)}px`;
      candleElement.style.width = `${candleWidth.toFixed(1)}px`;
      candleElement.style.height = `${chartHeight}px`; // Set height to container height for positioning wick/body
      candleElement.style.top = "0"; // Align to top for absolute positioning within chartArea

      const wickElement = document.createElement("div");
      wickElement.className = "wick";
      wickElement.style.top = `${wickHighY.toFixed(1)}px`;
      wickElement.style.height = `${wickHeight.toFixed(1)}px`;
      // Wick is already centered horizontally by its CSS (left: 50%, transform: translateX(-50%))

      const bodyElement = document.createElement("div");
      bodyElement.className = `body ${isUp ? "color-up" : "color-down"}`;
      bodyElement.style.top = `${bodyTopY.toFixed(1)}px`;
      bodyElement.style.height = `${bodyHeight.toFixed(1)}px`;
      // Body width/left are handled by its CSS (width: 80%, left: 10%) relative to candleElement

      candleElement.appendChild(wickElement);
      candleElement.appendChild(bodyElement);
      dom.chartArea.appendChild(candleElement);
    }
  } catch (e) {
    console.error("Error drawing candles:", e);
    if (dom.chartMessage) {
      dom.chartMessage.textContent = "Error drawing candles.";
      dom.chartMessage.style.display = "block";
    }
  }

  // Update Live Price Indicator Position on Full Redraw
  let priceForIndicator = state.lastTickerPrice;
  if (priceForIndicator === null && state.fullData.length > 0) {
    const lastCandle = state.fullData[state.fullData.length - 1];
    if (lastCandle && lastCandle.length >= 5) {
      priceForIndicator = lastCandle[4];
    } // Fallback to close
  }
  if (priceForIndicator !== null) {
    updateLivePriceIndicatorUI(priceForIndicator, chartHeight);
  } else {
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
  }
} // End of redrawChart function
