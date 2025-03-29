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
  MIN_LOG_VALUE,
} from "./utils.js";

const SECONDS_PER_DAY = 86400;
const MIN_PIXELS_PER_LABEL = 60; // Minimum space between labels
const Y_AXIS_MAX_ITERATIONS = 500;

// --- Live Price Indicator ---
function updateLivePriceIndicatorUI(price, chartHeight) {
  /* ... no changes ... */
}

// --- Helper to draw a single Y-axis tick/label ---
function drawYTick(priceValue, chartHeight, minVisible, maxVisible) {
  // Keep previous logging inside this helper for Y-axis issues if they return
  // console.log(`[drawYTick] Trying price: ${priceValue}`);
  if (priceValue <= MIN_LOG_VALUE) {
    return;
  }
  const y = getYCoordinate(priceValue, chartHeight);
  // console.log(`[drawYTick] Calculated Y for ${priceValue}: ${y}`);
  if (y === null || !Number.isFinite(y)) {
    return;
  }
  if (y >= -chartHeight * 0.1 && y <= chartHeight * 1.1) {
    const hLine = document.createElement("div");
    hLine.className = "grid-line horizontal";
    hLine.style.top = `${y.toFixed(1)}px`;
    dom.gridContainer.appendChild(hLine);
  }
  if (y >= -5 && y <= chartHeight + 5) {
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
      // Wrap appendChild for safety
      dom.yAxisLabelsContainer.appendChild(yLabel);
      // console.log(`[drawYTick] Appended label for ${priceValue}`);
    } catch (e) {
      console.error(
        `[drawYTick] Error appending Y label for ${priceValue}:`,
        e
      );
    }
  }
}

// --- Main Chart Redraw ---
export function redrawChart() {
  // console.log(`[redrawChart] Function called.`); // Reduce noise

  if (
    !dom.chartArea ||
    !dom.gridContainer ||
    !dom.yAxisLabelsContainer ||
    !dom.xAxisLabelsContainer
  ) {
    console.error("[redrawChart] Missing drawing containers.");
    return;
  }

  dom.chartArea.innerHTML = "";
  dom.gridContainer.innerHTML = "";
  dom.yAxisLabelsContainer.innerHTML = "";
  dom.xAxisLabelsContainer.innerHTML = "";
  if (dom.volumeYAxisLabels) dom.volumeYAxisLabels.innerHTML = "";

  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;

  if (!state.fullData || state.fullData.length === 0) {
    console.warn("[redrawChart] No data.");
    return;
  }
  if (chartHeight <= 0 || chartWidth <= 0) {
    console.warn(`[redrawChart] Invalid dimensions.`);
    return;
  }

  const {
    minVisiblePrice,
    maxVisiblePrice,
    isLogScale,
    visibleStartIndex,
    visibleEndIndex,
  } = state;
  const visibleCount = visibleEndIndex - visibleStartIndex;

  if (
    isNaN(minVisiblePrice) ||
    isNaN(maxVisiblePrice) ||
    !Number.isFinite(minVisiblePrice) ||
    !Number.isFinite(maxVisiblePrice) ||
    maxVisiblePrice <= minVisiblePrice ||
    (isLogScale && minVisiblePrice <= 0)
  ) {
    console.error("[redrawChart] Invalid price range.");
    return;
  }
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
    const linearRange = maxVisiblePrice - minVisiblePrice;
    const linearTicks =
      linearRange > 0 && Number.isFinite(linearRange)
        ? calculateNiceStep(linearRange, yTickDensity)
        : 1;
    if (!linearTicks || linearTicks <= 0 || !Number.isFinite(linearTicks)) {
      /* Handle error */
    } else {
      let firstLinearTick;
      if (minVisiblePrice >= 0) {
        firstLinearTick =
          linearTicks > 0
            ? Math.ceil(minVisiblePrice / linearTicks) * linearTicks
            : minVisiblePrice;
      } else {
        firstLinearTick =
          linearTicks > 0
            ? Math.floor(minVisiblePrice / linearTicks) * linearTicks
            : minVisiblePrice;
      }
      if (
        linearTicks > 0 &&
        firstLinearTick - minVisiblePrice > linearTicks * 0.99
      ) {
        firstLinearTick -= linearTicks;
      }
      if (minVisiblePrice > 0 && firstLinearTick < 0) {
        firstLinearTick = 0;
      }
      const loopUpperBound = maxVisiblePrice + linearTicks * 0.1;
      for (
        let currentPrice = firstLinearTick;
        currentPrice <= loopUpperBound &&
        iterationCount < Y_AXIS_MAX_ITERATIONS;
        currentPrice =
          linearTicks > 0 ? currentPrice + linearTicks : loopUpperBound + 1
      ) {
        iterationCount++;
        drawYTick(currentPrice, chartHeight, minVisiblePrice, maxVisiblePrice);
        if (
          linearTicks > Number.EPSILON &&
          currentPrice + linearTicks <= currentPrice
        ) {
          break;
        }
      }
    }
  } catch (e) {
    console.error("[redrawChart] Error drawing Y grid/axis:", e);
  }

  // --- Draw X-Axis & Separators ---
  let xAxisLabelsDrawnCount = 0;
  try {
    // console.log("[redrawChart] Drawing X-Axis..."); // Reduce noise
    const xTickDensity = Math.max(3, Math.round(chartWidth / 70));
    const xTicks =
      visibleCount > 0
        ? Math.max(1, calculateNiceStep(visibleCount, xTickDensity))
        : 1;
    let lastLabelX = -Infinity;

    for (let i = 0; i < visibleCount; i++) {
      const dataIndex = visibleStartIndex + i;
      if (dataIndex < 0 || dataIndex >= state.fullData.length) continue;
      const candleData = state.fullData[dataIndex];
      if (!candleData || candleData.length < 1 || isNaN(candleData[0]))
        continue;
      const timestamp = candleData[0];

      const isFirst = i === 0;
      const isLast = i === visibleCount - 1;
      const isTickCandidate =
        xTicks > 0 && (i + Math.floor(xTicks / 2)) % xTicks === 0;

      if (isFirst || isLast || isTickCandidate) {
        const x = (i + 0.5) * candleTotalWidth;
        const spacingCondition = x - lastLabelX > MIN_PIXELS_PER_LABEL;

        if (spacingCondition || isFirst || isLast) {
          if (x >= -candleTotalWidth && x <= chartWidth + candleTotalWidth) {
            const xLabel = document.createElement("div");
            xLabel.className = "axis-label x-axis-label";
            xLabel.style.left = `${x.toFixed(1)}px`;

            // <<< Wrap formatTimestamp and appendChild in try...catch >>>
            try {
              const formattedTime = formatTimestamp(timestamp);
              if (formattedTime && formattedTime !== "Time Error") {
                // Check for valid formatted time
                xLabel.textContent = formattedTime;
                dom.xAxisLabelsContainer.appendChild(xLabel);
                xAxisLabelsDrawnCount++;
                lastLabelX = x;
                // console.log(`[X-Axis Tick ${i}] Appended label "${formattedTime}" at X=${x.toFixed(1)}`); // Optional log on success
              } else {
                console.warn(
                  `[X-Axis Tick ${i}] formatTimestamp returned invalid: "${formattedTime}" for timestamp ${timestamp}`
                );
              }
            } catch (labelError) {
              console.error(
                `[X-Axis Tick ${i}] Error formatting or appending label for timestamp ${timestamp}:`,
                labelError
              );
              // Continue to the next iteration even if one label fails
            }
            // <<< End try...catch wrapper >>>
          }
        }
      }
    }
    // console.log(`[redrawChart] X-Axis drawing finished. Appended Label Count: ${xAxisLabelsDrawnCount}`); // Reduce noise
  } catch (e) {
    // Catch errors in the main X-axis loop setup (less likely now)
    console.error("[redrawChart] Error drawing X grid/axis:", e);
  }

  // --- Draw Candles ---
  let candlesDrawn = 0;
  let candlesSkippedInvalidCoords = 0;
  try {
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < visibleCount; i++) {
      const dataIndex = visibleStartIndex + i;
      if (dataIndex < 0 || dataIndex >= state.fullData.length) continue;
      const candle = state.fullData[dataIndex];
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
        continue; // Skip this candle
      }
      const bodyTopY = Math.min(bodyOpenY, bodyCloseY);
      const bodyBottomY = Math.max(bodyOpenY, bodyCloseY);
      const wickHeight = Math.max(1, wickLowY - wickHighY);
      const bodyHeight = Math.max(1, bodyBottomY - bodyTopY);
      const candleElement = document.createElement("div");
      candleElement.className = "candle";
      candleElement.style.width = `${candleWidth.toFixed(1)}px`;
      const candleLeft = i * candleTotalWidth + candleMargin;
      candleElement.style.left = `${candleLeft.toFixed(1)}px`;
      let wickElement = null;
      if (wickHeight >= 1 && wickLowY >= wickHighY) {
        wickElement = document.createElement("div");
        wickElement.className = `wick ${isUp ? "color-up" : "color-down"}`;
        wickElement.style.top = `${wickHighY.toFixed(1)}px`;
        wickElement.style.height = `${wickHeight.toFixed(1)}px`;
      }
      let bodyElement = null;
      if (bodyHeight >= 1 && bodyBottomY >= bodyTopY) {
        bodyElement = document.createElement("div");
        bodyElement.className = `body ${isUp ? "color-up" : "color-down"}`;
        bodyElement.style.top = `${bodyTopY.toFixed(1)}px`;
        bodyElement.style.height = `${bodyHeight.toFixed(1)}px`;
      }
      if (wickElement) {
        candleElement.appendChild(wickElement);
      }
      if (bodyElement) {
        candleElement.appendChild(bodyElement);
      }
      if (candleElement.childNodes.length > 0) {
        fragment.appendChild(candleElement);
        candlesDrawn++;
      }
    }
    dom.chartArea.appendChild(fragment);
    // console.log(`[redrawChart] Candle drawing finished. Drawn: ${candlesDrawn}, Skipped: ${candlesSkippedInvalidCoords}`); // Reduce noise
  } catch (e) {
    console.error("[redrawChart] Error drawing candles:", e);
  }

  // --- Update Live Price Indicator ---
  let priceForIndicator = state.lastTickerPrice; /* ... existing logic ... */
  if (priceForIndicator !== null && Number.isFinite(priceForIndicator)) {
    updateLivePriceIndicatorUI(priceForIndicator, chartHeight);
  } else {
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
  }
  // console.log(`[redrawChart] Live price indicator updated/hidden.`); // Reduce noise

  // --- Draw Volume Chart ---
  try {
    drawVolumeChart(state, chartWidth);
  } catch (e) {
    console.error("[redrawChart] Error calling drawVolumeChart:", e);
    if (dom.volumeChartCanvas && dom.volumeChartCanvas.getContext) {
      const volCtx = dom.volumeChartCanvas.getContext("2d");
      if (volCtx) {
        volCtx.clearRect(
          0,
          0,
          dom.volumeChartCanvas.width,
          dom.volumeChartCanvas.height
        );
      }
    }
  }

  // console.log(`[redrawChart] Function finished completely.`); // Reduce noise
} // End of redrawChart function
