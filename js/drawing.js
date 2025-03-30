// js/drawing.js

import * as config from "./config.js";
import state from "./state.js";
import * as dom from "./domElements.js";
import { drawVolumeChart } from "./volumeChart.js";
import {
  calculateNiceStep,
  formatTimestamp,
  formatDate,
  getYCoordinate,
  getPriceFromYCoordinate, // Keep for interactions
  MIN_LOG_VALUE,
} from "./utils.js";

const SECONDS_PER_DAY = 86400;
const MIN_PIXELS_PER_LABEL = 60; // Minimum HORIZONTAL space between X labels
const MIN_PIXELS_PER_LABEL_Y = 15; // Minimum VERTICAL space between Y labels
const Y_AXIS_MAX_ITERATIONS = 500;

// --- Live Price Indicator ---
function updateLivePriceIndicatorUI(price, chartHeight) {
  if (!dom.currentPriceLabel || !dom.currentPriceLine || isNaN(price)) {
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
    return;
  }
  // getYCoordinate respects the current state.isLogScale internally
  const y = getYCoordinate(price, chartHeight);

  if (y !== null && !isNaN(y)) {
    const decimals = price < 1 ? 4 : price < 100 ? 2 : price < 10000 ? 1 : 0;
    dom.currentPriceLine.style.top = `${y.toFixed(1)}px`;
    dom.currentPriceLine.style.display = "block";
    dom.currentPriceLabel.textContent = price.toFixed(decimals);
    dom.currentPriceLabel.style.top = `${y.toFixed(1)}px`;
    dom.currentPriceLabel.style.display = "block";
    if (
      dom.yAxisLabelsContainer &&
      dom.currentPriceLabel.parentNode !== dom.yAxisLabelsContainer
    ) {
      dom.yAxisLabelsContainer.appendChild(dom.currentPriceLabel);
    }
  } else {
    dom.currentPriceLabel.style.display = "none";
    dom.currentPriceLine.style.display = "none";
  }
}

// --- Helper to draw a single Y-axis tick/label ---
function drawYTick(
  priceValue,
  y,
  chartHeight,
  minVisible,
  maxVisible,
  labelContainer,
  gridContainer,
  lastLabelYRef
) {
  // priceValue: The linear value to display
  // y: The calculated pixel position (can be linear or log based on state)
  if (y === null || !Number.isFinite(y)) {
    return false;
  }
  if (Math.abs(y - lastLabelYRef.y) < MIN_PIXELS_PER_LABEL_Y) {
    return false; // Skip if too close vertically
  }
  // Draw Grid Line at position y
  if (gridContainer && y >= -chartHeight * 0.1 && y <= chartHeight * 1.1) {
    const hLine = document.createElement("div");
    hLine.className = "grid-line horizontal";
    hLine.style.top = `${y.toFixed(1)}px`;
    gridContainer.appendChild(hLine);
  }
  // Draw Label with linear priceValue at position y
  if (labelContainer && y >= -10 && y <= chartHeight + 10) {
    const yLabel = document.createElement("div");
    yLabel.className = "axis-label y-axis-label";
    yLabel.style.top = `${y.toFixed(1)}px`; // Position based on calculated y
    let decimals = 0;
    if (priceValue < 0.01) decimals = 6;
    else if (priceValue < 1) decimals = 4;
    else if (priceValue < 100) decimals = 2;
    else if (priceValue < 10000) decimals = 1;
    else decimals = 0;
    decimals = Math.max(0, decimals);
    yLabel.textContent = priceValue.toFixed(decimals); // Display the linear value
    try {
      labelContainer.appendChild(yLabel);
      lastLabelYRef.y = y; // Update last drawn position
      return true;
    } catch (e) {
      console.error(`Error appending Y label for ${priceValue}:`, e);
      return false;
    }
  }
  return false;
}

// --- Main Chart Redraw ---
export function redrawChart() {
  // Clear previous drawings
  if (dom.chartArea) dom.chartArea.innerHTML = "";
  if (dom.gridContainer) dom.gridContainer.innerHTML = "";
  if (dom.yAxisLabelsContainer) dom.yAxisLabelsContainer.innerHTML = "";
  if (dom.xAxisLabelsContainer) dom.xAxisLabelsContainer.innerHTML = "";
  if (dom.volumeYAxisLabels) dom.volumeYAxisLabels.innerHTML = "";

  if (
    !dom.chartArea ||
    !dom.gridContainer ||
    !dom.yAxisLabelsContainer ||
    !dom.xAxisLabelsContainer
  ) {
    console.error("[redrawChart] Missing drawing containers after clear.");
    return;
  }

  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;

  if (chartHeight <= 0 || chartWidth <= 0) {
    console.warn(`[redrawChart] Invalid dimensions.`);
    return;
  }

  if (!state.fullData || state.fullData.length === 0) {
    console.warn("[redrawChart] No data to draw.");
    return;
  }

  const {
    minVisiblePrice,
    maxVisiblePrice,
    isLogScale, // isLogScale only affects getYCoordinate now
    visibleStartIndex,
    visibleEndIndex,
    fullData,
    currentGranularity,
  } = state;

  const visibleCount = visibleEndIndex - visibleStartIndex;

  if (
    isNaN(minVisiblePrice) ||
    isNaN(maxVisiblePrice) ||
    !Number.isFinite(minVisiblePrice) ||
    !Number.isFinite(maxVisiblePrice) ||
    maxVisiblePrice <= minVisiblePrice
    // Removed: (isLogScale && minVisiblePrice <= 0) - Min price check done below
  ) {
    console.error("[redrawChart] Invalid price range.");
    return;
  }
  // Ensure min price is valid for potential log calculation later
  const safeMinVisiblePriceForLog = Math.max(MIN_LOG_VALUE, minVisiblePrice);

  if (visibleCount <= 0) {
    console.warn(`[redrawChart] visibleCount is ${visibleCount}.`);
    return;
  }

  const candleTotalWidth = chartWidth / visibleCount;
  const candleBodyWidthRatio = 0.7;
  const candleWidth = Math.max(1, candleTotalWidth * candleBodyWidthRatio);
  const candleMargin = Math.max(0.5, (candleTotalWidth - candleWidth) / 2);

  // --- Draw Grid & Y-Axis ---
  try {
    const yTickDensity = Math.max(3, Math.round(chartHeight / 40));
    let iterationCount = 0;
    const minPrice = minVisiblePrice; // Use actual min for range calculation
    const maxPrice = maxVisiblePrice;
    let lastLabelYRef = { y: Infinity };

    // *** Always calculate ticks based on LINEAR range ***
    const linearRange = maxPrice - minPrice;
    if (linearRange > 0 && Number.isFinite(linearRange)) {
      const linearStep = calculateNiceStep(linearRange, yTickDensity); // Get nice linear step

      if (linearStep > 0 && Number.isFinite(linearStep)) {
        let currentPrice = Math.ceil(minPrice / linearStep) * linearStep; // Start tick value
        if (currentPrice - minPrice > linearStep * 0.9) {
          currentPrice -= linearStep;
        }
        // Ensure start is non-negative if min price is non-negative
        if (minPrice >= 0 && currentPrice < 0) {
          currentPrice = 0;
        }
        // Adjust for very small min prices close to zero
        else if (
          minPrice > 0 &&
          minPrice < linearStep &&
          currentPrice > linearStep
        ) {
          currentPrice = 0; // Start at 0 if min is small positive and first tick is > step
        }

        const loopUpperBound = maxPrice + linearStep * 0.1; // Iterate slightly beyond max visible

        for (
          ;
          currentPrice <= loopUpperBound &&
          iterationCount < Y_AXIS_MAX_ITERATIONS;
          currentPrice += linearStep
        ) {
          iterationCount++;

          // *** Get Y position using the CURRENT scale (linear OR log) ***
          const y = getYCoordinate(currentPrice, chartHeight);

          // *** Draw tick with LINEAR value but at calculated Y position ***
          drawYTick(
            currentPrice, // The linear value for the label text
            y, // The calculated pixel Y (respects isLogScale)
            chartHeight,
            minPrice,
            maxPrice,
            dom.yAxisLabelsContainer,
            dom.gridContainer,
            lastLabelYRef
          );

          // Prevent infinite/stuck loops
          if (
            linearStep <= Number.EPSILON ||
            currentPrice + linearStep <= currentPrice
          )
            break;
        }
      } else {
        // Fallback: Draw min/max if step calculation fails
        drawYTick(
          minPrice,
          getYCoordinate(minPrice, chartHeight),
          chartHeight,
          minPrice,
          maxPrice,
          dom.yAxisLabelsContainer,
          dom.gridContainer,
          lastLabelYRef
        );
        drawYTick(
          maxPrice,
          getYCoordinate(maxPrice, chartHeight),
          chartHeight,
          minPrice,
          maxPrice,
          dom.yAxisLabelsContainer,
          dom.gridContainer,
          lastLabelYRef
        );
      }
    } else {
      // Fallback: Draw min/max if range is invalid
      drawYTick(
        minPrice,
        getYCoordinate(minPrice, chartHeight),
        chartHeight,
        minPrice,
        maxPrice,
        dom.yAxisLabelsContainer,
        dom.gridContainer,
        lastLabelYRef
      );
      drawYTick(
        maxPrice,
        getYCoordinate(maxPrice, chartHeight),
        chartHeight,
        minPrice,
        maxPrice,
        dom.yAxisLabelsContainer,
        dom.gridContainer,
        lastLabelYRef
      );
    }
  } catch (e) {
    console.error("[redrawChart] Error drawing Y grid/axis:", e);
  }

  // === Draw X-Axis & Separators ===
  let xAxisLabelsDrawnCount = 0;
  try {
    const xTickDensity = Math.max(3, Math.round(chartWidth / 70));
    const xTickCandleInterval = Math.max(
      1,
      Math.round(visibleCount / xTickDensity)
    );
    let lastLabelX = -Infinity;

    const lastDataIndex = fullData.length - 1;
    const lastCandleTimestamp =
      lastDataIndex >= 0 ? fullData[lastDataIndex]?.[0] : null;
    const hasValidLastTimestamp =
      typeof lastCandleTimestamp === "number" && !isNaN(lastCandleTimestamp);

    for (let i = 0; i < visibleCount; i++) {
      const dataIndex = visibleStartIndex + i;
      const x = (i + 0.5) * candleTotalWidth;

      let currentTimestamp = null;
      if (dataIndex >= 0 && dataIndex <= lastDataIndex) {
        const candleData = fullData[dataIndex];
        if (
          candleData?.[0] !== undefined &&
          typeof candleData[0] === "number" &&
          !isNaN(candleData[0])
        ) {
          currentTimestamp = candleData[0];
        }
      } else if (
        dataIndex > lastDataIndex &&
        hasValidLastTimestamp &&
        currentGranularity > 0
      ) {
        const candlesPastEnd = dataIndex - lastDataIndex;
        currentTimestamp =
          lastCandleTimestamp + candlesPastEnd * currentGranularity;
      }

      if (currentTimestamp === null) {
        continue;
      }

      const isTickCandidate = i % xTickCandleInterval === 0;
      const spacingCondition = x - lastLabelX > MIN_PIXELS_PER_LABEL;

      if (isTickCandidate && spacingCondition) {
        if (x >= -candleTotalWidth && x <= chartWidth + candleTotalWidth) {
          const xLabel = document.createElement("div");
          xLabel.className = "axis-label x-axis-label";
          xLabel.style.left = `${x.toFixed(1)}px`;

          try {
            const formattedTime = formatTimestamp(currentTimestamp);
            if (formattedTime && formattedTime !== "Time Error") {
              xLabel.textContent = formattedTime;
              dom.xAxisLabelsContainer.appendChild(xLabel);
              xAxisLabelsDrawnCount++;
              lastLabelX = x;
            }
          } catch (labelError) {}
        }
      }
    }
  } catch (e) {
    console.error("[redrawChart] Error drawing X grid/axis:", e);
  }

  // --- Draw Candles ---
  let candlesDrawn = 0;
  let candlesSkippedInvalidCoords = 0;
  try {
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < visibleCount; i++) {
      const dataIndex = visibleStartIndex + i;
      if (dataIndex < 0 || dataIndex >= fullData.length) {
        continue;
      }

      const candle = fullData[dataIndex];
      if (
        !candle ||
        candle.length < 5 ||
        candle.slice(0, 5).some((v) => isNaN(v) || !Number.isFinite(v))
      ) {
        continue;
      }

      const [timestamp, low, high, open, close] = candle;
      const isUp = close >= open;
      const wickHighY = getYCoordinate(high, chartHeight);
      const wickLowY = getYCoordinate(low, chartHeight);
      const bodyOpenY = getYCoordinate(open, chartHeight);
      const bodyCloseY = getYCoordinate(close, chartHeight);
      if (
        wickHighY === null ||
        !Number.isFinite(wickHighY) ||
        wickLowY === null ||
        !Number.isFinite(wickLowY) ||
        bodyOpenY === null ||
        !Number.isFinite(bodyOpenY) ||
        bodyCloseY === null ||
        !Number.isFinite(bodyCloseY)
      ) {
        candlesSkippedInvalidCoords++;
        continue;
      }

      const bodyTopY = Math.min(bodyOpenY, bodyCloseY);
      const bodyBottomY = Math.max(bodyOpenY, bodyCloseY);
      const wickHeight = Math.max(0, wickLowY - wickHighY);
      const bodyHeight = Math.max(1, bodyBottomY - bodyTopY);

      const candleElement = document.createElement("div");
      candleElement.className = "candle";
      candleElement.style.width = `${candleWidth.toFixed(1)}px`;
      const candleLeft = i * candleTotalWidth + candleMargin;
      candleElement.style.left = `${candleLeft.toFixed(1)}px`;

      if (wickHeight >= 1 && wickLowY >= wickHighY) {
        const wickElement = document.createElement("div");
        wickElement.className = `wick ${isUp ? "color-up" : "color-down"}`;
        wickElement.style.top = `${wickHighY.toFixed(1)}px`;
        wickElement.style.height = `${wickHeight.toFixed(1)}px`;
        candleElement.appendChild(wickElement);
      }
      if (bodyHeight >= 1 && bodyBottomY >= bodyTopY) {
        const bodyElement = document.createElement("div");
        bodyElement.className = `body ${isUp ? "color-up" : "color-down"}`;
        bodyElement.style.top = `${bodyTopY.toFixed(1)}px`;
        bodyElement.style.height = `${bodyHeight.toFixed(1)}px`;
        candleElement.appendChild(bodyElement);
      }
      if (candleElement.childNodes.length > 0) {
        fragment.appendChild(candleElement);
        candlesDrawn++;
      }
    }
    dom.chartArea.appendChild(fragment);
  } catch (e) {
    console.error("[redrawChart] Error drawing candles:", e);
  }

  // --- Update Live Price Indicator ---
  let priceForIndicator = state.lastTickerPrice;
  const lastDataIndexForPrice = fullData.length - 1;
  if (priceForIndicator === null && lastDataIndexForPrice >= 0) {
    const lastCandle = fullData[lastDataIndexForPrice];
    if (lastCandle && lastCandle.length >= 5 && !isNaN(lastCandle[4])) {
      priceForIndicator = lastCandle[4];
    }
  }
  if (priceForIndicator !== null && Number.isFinite(priceForIndicator)) {
    updateLivePriceIndicatorUI(priceForIndicator, chartHeight);
  } else {
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
  }

  // --- Draw Volume Chart ---
  try {
    drawVolumeChart(state, chartWidth);
  } catch (e) {
    console.error("[redrawChart] Error calling drawVolumeChart:", e);
    if (dom.volumeChartCanvas && dom.volumeChartCanvas.getContext) {
      const volCtx = dom.volumeChartCanvas.getContext("2d");
      volCtx?.clearRect(
        0,
        0,
        dom.volumeChartCanvas.width,
        dom.volumeChartCanvas.height
      );
    }
  }
} // End of redrawChart function
