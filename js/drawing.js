// FILE: js/drawing.js

import * as config from "./config.js";
import state from "./state.js";
import * as dom from "./domElements.js";
import { drawVolumeChart } from "./volumeChart.js";
import {
  calculateNiceStep,
  formatTimestamp,
  formatDate,
  getYCoordinate,
  getPriceFromYCoordinate,
  MIN_LOG_VALUE,
  formatCurrency,
} from "./utils.js";

const SECONDS_PER_DAY = 86400;
const MIN_PIXELS_PER_LABEL = 60;
const MIN_PIXELS_PER_LABEL_Y = 15;
const Y_AXIS_MAX_ITERATIONS = 500;

// --- Helper: Time to X Coordinate ---
function timeToX(timestamp, chartWidth) {
  // ... implementation unchanged ...
  if (isNaN(timestamp) || !chartWidth || chartWidth <= 0) return null;
  const { visibleStartIndex, visibleEndIndex, fullData, currentGranularity } =
    state;
  const visibleCount = visibleEndIndex - visibleStartIndex;
  if (visibleCount <= 0) return null;
  const firstVisibleCandleIndex = Math.max(0, visibleStartIndex);
  const firstVisibleCandleTimestamp =
    fullData && fullData[firstVisibleCandleIndex]
      ? fullData[firstVisibleCandleIndex][0]
      : null;
  if (firstVisibleCandleTimestamp === null || currentGranularity <= 0) {
    if (fullData && fullData.length > 0) {
      let exactMatchIndex = -1;
      for (let i = 0; i < fullData.length; i++) {
        if (fullData[i] && fullData[i][0] === timestamp) {
          exactMatchIndex = i;
          break;
        }
      }
      if (exactMatchIndex !== -1) {
        const relativeIndex = exactMatchIndex - visibleStartIndex;
        const candleTotalWidth = chartWidth / visibleCount;
        const x = (relativeIndex + 0.5) * candleTotalWidth;
        return Number.isFinite(x) ? x : null;
      }
    }
    return null;
  }
  const timeDifference = timestamp - firstVisibleCandleTimestamp;
  const candleIndexDifference = timeDifference / currentGranularity;
  const relativeIndexOnScreen = candleIndexDifference;
  const candleTotalWidth = chartWidth / visibleCount;
  const x = (relativeIndexOnScreen + 0.5) * candleTotalWidth;
  return Number.isFinite(x) ? x : null;
}

// --- Helper: Draw Order Rays (DOM Version) ---
function drawOrderRaysDOM(chartAreaElement, chartHeight, chartWidth) {
  // ... implementation unchanged ...
  if (
    !chartAreaElement ||
    !state.ordersToPlot ||
    state.ordersToPlot.length === 0
  ) {
    return;
  }
  const fragment = document.createDocumentFragment();
  let raysDrawn = 0;
  const verticalPadding = chartHeight * 0.1;
  state.ordersToPlot.forEach((order) => {
    if (order.side !== "BUY") return;
    const x = timeToX(order.time, chartWidth);
    const y = getYCoordinate(order.price, chartHeight);
    if (
      y === null ||
      !Number.isFinite(y) ||
      y < -verticalPadding ||
      y > chartHeight + verticalPadding
    ) {
      return;
    }
    if (x === null || !Number.isFinite(x) || x >= chartWidth) {
      return;
    }
    const rayLeft = Math.max(0, x);
    const rayWidth = Math.max(0, chartWidth - rayLeft);
    if (rayWidth > 0) {
      const ray = document.createElement("div");
      ray.className = "order-ray buy";
      ray.style.left = `${rayLeft.toFixed(1)}px`;
      ray.style.top = `${y.toFixed(1)}px`;
      ray.style.width = `${rayWidth.toFixed(1)}px`;
      ray.title = `BUY Order @ ${formatCurrency(
        order.price
      )} (${formatTimestamp(order.time)})`;
      fragment.appendChild(ray);
      raysDrawn++;
    }
  });
  chartAreaElement.appendChild(fragment);
}

// --- Live Price Indicator (Ensure display is set correctly) ---
function updateLivePriceIndicatorUI(price, chartHeight) {
  if (!dom.currentPriceLabel || !dom.currentPriceLine || isNaN(price)) {
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
    return;
  }
  const y = getYCoordinate(price, chartHeight);

  if (y !== null && !isNaN(y)) {
    const decimals = price < 1 ? 4 : price < 100 ? 2 : price < 10000 ? 1 : 0;
    // Update styles
    dom.currentPriceLine.style.top = `${y.toFixed(1)}px`;
    dom.currentPriceLabel.textContent = price.toFixed(decimals);
    dom.currentPriceLabel.style.top = `${y.toFixed(1)}px`;

    // *** Explicitly set display to block ***
    dom.currentPriceLine.style.display = "block";
    dom.currentPriceLabel.style.display = "block";

    // Appending logic (should be redundant now if handled in redrawChart, but safe fallback)
    if (
      dom.yAxisLabelsContainer &&
      dom.currentPriceLabel.parentNode !== dom.yAxisLabelsContainer
    ) {
      dom.yAxisLabelsContainer.appendChild(dom.currentPriceLabel);
    }
  } else {
    // Hide if coords are invalid
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
  // ... implementation unchanged ...
  if (y === null || !Number.isFinite(y)) {
    return false;
  }
  if (Math.abs(y - lastLabelYRef.y) < MIN_PIXELS_PER_LABEL_Y) {
    return false;
  }
  if (gridContainer && y >= -chartHeight * 0.1 && y <= chartHeight * 1.1) {
    const hLine = document.createElement("div");
    hLine.className = "grid-line horizontal";
    hLine.style.top = `${y.toFixed(1)}px`;
    gridContainer.appendChild(hLine);
  }
  if (labelContainer && y >= -10 && y <= chartHeight + 10) {
    const yLabel = document.createElement("div");
    yLabel.className = "axis-label y-axis-label";
    yLabel.style.top = `${y.toFixed(1)}px`;
    let decimals = 0;
    if (priceValue < 0.01) decimals = 6;
    else if (priceValue < 1) decimals = 4;
    else if (priceValue < 100) decimals = 2;
    else if (priceValue < 10000) decimals = 1;
    else decimals = 0;
    decimals = Math.max(0, decimals);
    yLabel.textContent = priceValue.toFixed(decimals);
    try {
      labelContainer.appendChild(yLabel);
      lastLabelYRef.y = y;
      return true;
    } catch (e) {
      console.error(`Error appending Y label for ${priceValue}:`, e);
      return false;
    }
  }
  return false;
}

// --- Main Chart Redraw (Modified Clearing) ---
export function redrawChart() {
  // Clear dynamic chart elements
  if (dom.chartArea) {
    const elementsToRemove = dom.chartArea.querySelectorAll(
      ".candle, .order-ray"
    );
    elementsToRemove.forEach((el) => el.remove());
  }
  // Clear static grid/axis elements
  if (dom.gridContainer) dom.gridContainer.innerHTML = "";
  // *** Clear Y-axis labels container completely ***
  if (dom.yAxisLabelsContainer) dom.yAxisLabelsContainer.innerHTML = "";
  if (dom.xAxisLabelsContainer) dom.xAxisLabelsContainer.innerHTML = "";
  if (dom.volumeYAxisLabels) dom.volumeYAxisLabels.innerHTML = "";

  // --- Check essential elements ---
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
    return;
  }
  if (!state.fullData || state.fullData.length === 0) {
    if (dom.volumeChartCanvas && dom.volumeChartCanvas.getContext) {
      const volCtx = dom.volumeChartCanvas.getContext("2d");
      volCtx?.clearRect(
        0,
        0,
        dom.volumeChartCanvas.width,
        dom.volumeChartCanvas.height
      );
    }
    return;
  }

  const {
    minVisiblePrice,
    maxVisiblePrice,
    isLogScale,
    visibleStartIndex,
    visibleEndIndex,
    fullData,
    currentGranularity,
  } = state;

  // --- Price Range Validation ---
  if (
    isNaN(minVisiblePrice) ||
    isNaN(maxVisiblePrice) ||
    !Number.isFinite(minVisiblePrice) ||
    !Number.isFinite(maxVisiblePrice) ||
    maxVisiblePrice <= minVisiblePrice
  ) {
    console.error("[redrawChart] Invalid price range.");
    return;
  }
  const safeMinVisiblePriceForLog = Math.max(MIN_LOG_VALUE, minVisiblePrice);

  const visibleCount = visibleEndIndex - visibleStartIndex;
  if (visibleCount <= 0) {
    return;
  }

  const candleTotalWidth = chartWidth / visibleCount;
  const candleBodyWidthRatio = 0.7;
  const candleWidth = Math.max(1, candleTotalWidth * candleBodyWidthRatio);
  const candleMargin = Math.max(0.5, (candleTotalWidth - candleWidth) / 2);

  // --- Draw Grid & Y-Axis ---
  // (Drawing logic remains the same)
  try {
    const yTickDensity = Math.max(3, Math.round(chartHeight / 40));
    let iterationCount = 0;
    const minPrice = minVisiblePrice;
    const maxPrice = maxVisiblePrice;
    let lastLabelYRef = { y: Infinity };
    const linearRange = maxPrice - minPrice;
    if (linearRange > 0 && Number.isFinite(linearRange)) {
      const linearStep = calculateNiceStep(linearRange, yTickDensity);
      if (linearStep > 0 && Number.isFinite(linearStep)) {
        let currentPrice = Math.ceil(minPrice / linearStep) * linearStep;
        if (currentPrice - minPrice > linearStep * 0.9) {
          currentPrice -= linearStep;
        }
        if (minPrice >= 0 && currentPrice < 0) {
          currentPrice = 0;
        } else if (
          minPrice > 0 &&
          minPrice < linearStep &&
          currentPrice > linearStep
        ) {
          currentPrice = 0;
        }
        const loopUpperBound = maxPrice + linearStep * 0.1;
        for (
          ;
          currentPrice <= loopUpperBound &&
          iterationCount < Y_AXIS_MAX_ITERATIONS;
          currentPrice += linearStep
        ) {
          iterationCount++;
          const y = getYCoordinate(currentPrice, chartHeight);
          drawYTick(
            currentPrice,
            y,
            chartHeight,
            minPrice,
            maxPrice,
            dom.yAxisLabelsContainer,
            dom.gridContainer,
            lastLabelYRef
          );
          if (
            linearStep <= Number.EPSILON ||
            currentPrice + linearStep <= currentPrice
          )
            break;
        }
      } else {
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

  // --- Draw X-Axis & Separators ---
  // (Drawing logic remains the same)
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
  // (Drawing logic remains the same)
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

  // --- Draw Order Rays ---
  // (Drawing logic remains the same)
  try {
    drawOrderRaysDOM(dom.chartArea, chartHeight, chartWidth);
  } catch (e) {
    console.error("[redrawChart] Error drawing order rays:", e);
  }

  // --- Update Live Price Indicator ---
  // *** Ensure label is appended before update ***
  if (dom.currentPriceLabel && dom.yAxisLabelsContainer) {
    dom.yAxisLabelsContainer.appendChild(dom.currentPriceLabel); // Make sure it's in the container
  }

  let priceForIndicator = state.lastTickerPrice;
  const lastDataIndexForPrice = fullData.length - 1;
  if (priceForIndicator === null && lastDataIndexForPrice >= 0) {
    const lastCandle = fullData[lastDataIndexForPrice];
    if (lastCandle && lastCandle.length >= 5 && !isNaN(lastCandle[4])) {
      priceForIndicator = lastCandle[4];
    }
  }
  if (priceForIndicator !== null && Number.isFinite(priceForIndicator)) {
    updateLivePriceIndicatorUI(priceForIndicator, chartHeight); // Update styles/position
  } else {
    // Explicitly hide if no valid price
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
  }

  // --- Draw Volume Chart ---
  // (Drawing logic remains the same)
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
