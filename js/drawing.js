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
const MIN_PIXELS_PER_LABEL = 60;
const Y_AXIS_MAX_ITERATIONS = 500;

// --- Live Price Indicator ---
function updateLivePriceIndicatorUI(price, chartHeight) {
  /* ... no changes ... */
}

// --- Helper to draw a single Y-axis tick/label ---
function drawYTick(priceValue, chartHeight, minVisible, maxVisible) {
  // <<< ADD Log inside helper >>>
  console.log(`[drawYTick] Trying price: ${priceValue}`);
  if (priceValue <= MIN_LOG_VALUE) {
    console.log(`[drawYTick] Price ${priceValue} <= MIN_LOG_VALUE, skipping.`);
    return;
  }

  const y = getYCoordinate(priceValue, chartHeight);
  console.log(`[drawYTick] Calculated Y for ${priceValue}: ${y}`); // Log coordinate

  if (y === null || !Number.isFinite(y)) {
    console.warn(
      `[drawYTick] Skipping draw for price ${priceValue} due to invalid Y coordinate.`
    );
    return;
  }

  // Draw grid line
  if (y >= -chartHeight * 0.1 && y <= chartHeight * 1.1) {
    const hLine = document.createElement("div");
    hLine.className = "grid-line horizontal";
    hLine.style.top = `${y.toFixed(1)}px`;
    dom.gridContainer.appendChild(hLine);
  }

  // Draw label
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
    dom.yAxisLabelsContainer.appendChild(yLabel);
    console.log(
      `[drawYTick] Appended label for ${priceValue} at Y=${y.toFixed(1)}`
    ); // Confirm appending
  } else {
    console.log(
      `[drawYTick] Label for ${priceValue} out of bounds (Y=${y.toFixed(1)}).`
    );
  }
}

// --- Main Chart Redraw ---
export function redrawChart() {
  console.log(`[redrawChart] Function called. Timestamp: ${Date.now()}`);

  if (
    !dom.chartArea ||
    !dom.gridContainer ||
    !dom.yAxisLabelsContainer ||
    !dom.xAxisLabelsContainer
  ) {
    console.error(
      "[redrawChart] Cannot redraw: Essential drawing containers missing."
    );
    return;
  }

  dom.chartArea.innerHTML = "";
  dom.gridContainer.innerHTML = "";
  dom.yAxisLabelsContainer.innerHTML = "";
  dom.xAxisLabelsContainer.innerHTML = "";
  if (dom.volumeYAxisLabels) dom.volumeYAxisLabels.innerHTML = "";

  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;
  console.log(
    `[redrawChart] Dimensions - Width: ${chartWidth}, Height: ${chartHeight}`
  );

  if (!state.fullData || state.fullData.length === 0) {
    console.warn("[redrawChart] Redraw skipped: No chart data.");
    if (dom.chartMessage) {
      dom.chartMessage.textContent = "No data loaded.";
      dom.chartMessage.style.display = "block";
    }
    return;
  }
  if (chartHeight <= 0 || chartWidth <= 0) {
    console.warn(`[redrawChart] Redraw skipped: Invalid dimensions.`);
    if (dom.chartMessage) {
      dom.chartMessage.textContent = "Invalid dimensions.";
      dom.chartMessage.style.display = "block";
    }
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
  console.log(
    `[redrawChart] State - Idx: ${visibleStartIndex}-${visibleEndIndex}, Count: ${visibleCount}, Price: ${minVisiblePrice.toFixed(
      2
    )}-${maxVisiblePrice.toFixed(2)}, Log: ${isLogScale}`
  );

  if (
    isNaN(minVisiblePrice) ||
    isNaN(maxVisiblePrice) ||
    !Number.isFinite(minVisiblePrice) ||
    !Number.isFinite(maxVisiblePrice) ||
    maxVisiblePrice <= minVisiblePrice ||
    (isLogScale && minVisiblePrice <= 0)
  ) {
    console.error("[redrawChart] Redraw failed: Invalid price range.");
    if (dom.chartMessage) {
      dom.chartMessage.textContent = "Error: Invalid Price Range";
      dom.chartMessage.style.display = "block";
    }
    return;
  }
  if (visibleCount <= 0) {
    console.warn(
      `[redrawChart] Redraw skipped: visibleCount is ${visibleCount}.`
    );
    return;
  }

  const candleTotalWidth = chartWidth / visibleCount;
  const candleBodyWidthRatio = 0.7;
  const candleWidth = Math.max(1, candleTotalWidth * candleBodyWidthRatio);
  const candleMargin = Math.max(0.5, (candleTotalWidth - candleWidth) / 2);
  console.log(
    `[redrawChart] Candle Calcs - TotalW: ${candleTotalWidth.toFixed(
      2
    )}, BodyW: ${candleWidth.toFixed(2)}, Margin: ${candleMargin.toFixed(2)}`
  );

  // --- Draw Grid & Y-Axis ---
  try {
    console.log("[redrawChart] Drawing Y-Axis...");
    const yTickDensity = Math.max(3, Math.round(chartHeight / 40));
    let iterationCount = 0;
    const linearRange = maxVisiblePrice - minVisiblePrice;
    const linearTicks =
      linearRange > 0 && Number.isFinite(linearRange)
        ? calculateNiceStep(linearRange, yTickDensity)
        : 1;
    if (!linearTicks || linearTicks <= 0 || !Number.isFinite(linearTicks)) {
      console.error(
        "[redrawChart] Y-Axis aborted: Invalid linear tick step.",
        linearTicks
      );
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
      console.log(
        `[redrawChart] Y-Axis Loop: Start=${firstLinearTick.toFixed(
          2
        )}, End~=${loopUpperBound.toFixed(2)}, Step=${linearTicks.toFixed(4)}`
      );
      for (
        let currentPrice = firstLinearTick;
        currentPrice <= loopUpperBound &&
        iterationCount < Y_AXIS_MAX_ITERATIONS;
        currentPrice =
          linearTicks > 0 ? currentPrice + linearTicks : loopUpperBound + 1
      ) {
        iterationCount++;
        drawYTick(currentPrice, chartHeight, minVisiblePrice, maxVisiblePrice); // Log is inside drawYTick
        if (
          linearTicks > Number.EPSILON &&
          currentPrice + linearTicks <= currentPrice
        ) {
          console.warn("[redrawChart] Y-Axis loop safety break.");
          break;
        }
      }
      if (iterationCount >= Y_AXIS_MAX_ITERATIONS) {
        console.warn("[redrawChart] Y-Axis loop hit max iteration limit.");
      }
    }
    console.log(`[redrawChart] Y-Axis drawing finished loop.`);
  } catch (e) {
    console.error("[redrawChart] Error drawing Y grid/axis:", e);
  }

  // --- Draw X-Axis & Separators ---
  try {
    /* ... existing X-axis logic, no logging added here yet ... */
  } catch (e) {
    console.error("[redrawChart] Error drawing X grid/axis:", e);
  }
  console.log(`[redrawChart] X-Axis drawing finished.`);

  // --- Draw Candles ---
  let candlesDrawn = 0;
  let candlesSkippedInvalidCoords = 0;
  try {
    console.log("[redrawChart] Drawing Candles...");
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

      // <<< ADD Candle Coordinate Logging >>>
      const wickHighY = getYCoordinate(high, chartHeight);
      const wickLowY = getYCoordinate(low, chartHeight);
      const bodyOpenY = getYCoordinate(open, chartHeight);
      const bodyCloseY = getYCoordinate(close, chartHeight);
      // Log ONLY if any coordinate is problematic for brevity
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
        console.warn(
          `[Candle ${i} (Idx ${dataIndex})] Invalid coords: H=${high}->${wickHighY?.toFixed(
            1
          )}, L=${low}->${wickLowY?.toFixed(
            1
          )}, O=${open}->${bodyOpenY?.toFixed(
            1
          )}, C=${close}->${bodyCloseY?.toFixed(1)}`
        );
        candlesSkippedInvalidCoords++;
        continue; // Skip this candle
      }
      // <<< END Candle Coordinate Logging >>>

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
      } else {
        // Log if a candle resulted in no visible parts
        // console.log(`[Candle ${i} (Idx ${dataIndex})] No body or wick drawn.`);
      }
    }
    dom.chartArea.appendChild(fragment);
    console.log(
      `[redrawChart] Candle drawing finished. Drawn: ${candlesDrawn}, Skipped (Invalid Coords): ${candlesSkippedInvalidCoords}`
    );
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
  console.log(`[redrawChart] Live price indicator updated/hidden.`);

  // --- Draw Volume Chart ---
  try {
    console.log("[redrawChart] Calling drawVolumeChart...");
    drawVolumeChart(state, chartWidth); // Pass main chart area width
    console.log("[redrawChart] drawVolumeChart call finished.");
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

  console.log(`[redrawChart] Function finished completely.`);
} // End of redrawChart function
