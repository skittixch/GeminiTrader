// js/drawing.js

import * as config from "./config.js";
import state from "./state.js";
import * as dom from "./domElements.js";
import {
  calculateNiceStep,
  formatTimestamp,
  formatDate,
  getYCoordinate,
  MIN_LOG_VALUE, // <<<--- IMPORT HERE
} from "./utils.js";
// Volume/Depth chart drawing is disabled

const SECONDS_PER_DAY = 86400;
const MIN_PIXELS_PER_LABEL = 60;
const Y_AXIS_MAX_ITERATIONS = 500; // Safety limit for Y-axis loop

// --- Live Price Indicator ---
function updateLivePriceIndicatorUI(price, chartHeight) {
  if (
    !dom.currentPriceLabel ||
    !dom.currentPriceLine ||
    isNaN(price) ||
    !Number.isFinite(price) ||
    !chartHeight ||
    chartHeight <= 0
  ) {
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
    return;
  }

  // getYCoordinate internally handles log/linear scaling for position
  const y = getYCoordinate(price, chartHeight);

  if (y !== null && Number.isFinite(y)) {
    // Adjust decimal places based on price magnitude for better readability
    let decimals = 0;
    if (price < 0.01) decimals = 6;
    else if (price < 1) decimals = 4;
    else if (price < 100) decimals = 2;
    else if (price < 10000) decimals = 1;
    else decimals = 0; // Or potentially use localeString for larger numbers
    decimals = Math.max(0, decimals);

    dom.currentPriceLabel.textContent = price.toFixed(decimals);
    dom.currentPriceLabel.style.top = `${y.toFixed(1)}px`;
    dom.currentPriceLine.style.top = `${y.toFixed(1)}px`;
    dom.currentPriceLabel.style.display = "block";
    dom.currentPriceLine.style.display = "block";
  } else {
    // Hide if Y coordinate is invalid
    dom.currentPriceLabel.style.display = "none";
    dom.currentPriceLine.style.display = "none";
  }
}

// --- Helper to draw a single Y-axis tick/label ---
// This function takes the *value* to display and uses the global state's
// isLogScale setting (via getYCoordinate) to determine the *position*.
function drawYTick(priceValue, chartHeight, minVisible, maxVisible) {
  // Skip drawing if price is essentially zero or negative
  // Crucial for log scale, harmless for linear.
  if (priceValue <= MIN_LOG_VALUE) return;

  // Get position using the scale-aware function
  const y = getYCoordinate(priceValue, chartHeight);

  // Only draw if y is a valid number
  if (y === null || !Number.isFinite(y)) {
    // console.warn("Skipped drawing Y grid/label for price:", priceValue, "due to invalid Y:", y);
    return;
  }

  // Draw grid line slightly outside main chart area too
  if (y >= -chartHeight * 0.1 && y <= chartHeight * 1.1) {
    const hLine = document.createElement("div");
    hLine.className = "grid-line horizontal";
    hLine.style.top = `${y.toFixed(1)}px`;
    dom.gridContainer.appendChild(hLine);
  }

  // Draw label only if clearly within or very near chart height
  if (y >= -5 && y <= chartHeight + 5) {
    const yLabel = document.createElement("div");
    yLabel.className = "axis-label y-axis-label";
    yLabel.style.top = `${y.toFixed(1)}px`;

    // Determine decimals based on price magnitude
    let decimals = 0;
    if (priceValue < 0.01) decimals = 6;
    else if (priceValue < 1) decimals = 4;
    else if (priceValue < 100) decimals = 2;
    else if (priceValue < 10000) decimals = 1;
    else decimals = 0;
    decimals = Math.max(0, decimals); // Ensure non-negative

    yLabel.textContent = priceValue.toFixed(decimals);
    dom.yAxisLabelsContainer.appendChild(yLabel);
  }
}

// --- Main Chart Redraw ---
export function redrawChart() {
  if (
    !dom.chartArea ||
    !dom.gridContainer ||
    !dom.yAxisLabelsContainer ||
    !dom.xAxisLabelsContainer
  ) {
    console.error(
      "Cannot redraw main chart: Essential drawing containers missing."
    );
    return;
  }

  // Clear previous content
  dom.chartArea.innerHTML = "";
  dom.gridContainer.innerHTML = "";
  dom.yAxisLabelsContainer.innerHTML = "";
  dom.xAxisLabelsContainer.innerHTML = "";

  const chartHeight = dom.chartArea.offsetHeight;
  const chartWidth = dom.chartArea.offsetWidth;

  // Validate chart dimensions and data
  if (!state.fullData || chartHeight <= 0 || chartWidth <= 0) {
    console.warn("Main chart redraw skipped: No data or invalid dimensions.");
    return;
  }

  const {
    minVisiblePrice,
    maxVisiblePrice,
    isLogScale, // We still need this for positioning via getYCoordinate
    visibleStartIndex,
    visibleEndIndex,
  } = state;
  const visibleCount = visibleEndIndex - visibleStartIndex;

  // More robust validation of price range state
  if (
    isNaN(minVisiblePrice) ||
    isNaN(maxVisiblePrice) ||
    !Number.isFinite(minVisiblePrice) ||
    !Number.isFinite(maxVisiblePrice) ||
    maxVisiblePrice <= minVisiblePrice ||
    (isLogScale && minVisiblePrice <= 0) // Log scale requires positive min price
  ) {
    console.error("Redraw failed: Invalid price range in state!", {
      minVisiblePrice,
      maxVisiblePrice,
      isLogScale,
    });
    if (dom.chartMessage) {
      dom.chartMessage.textContent = "Error: Invalid Price Range";
      dom.chartMessage.style.display = "block";
      dom.chartMessage.style.color = "red";
    }
    return; // Stop drawing
  }

  if (visibleCount <= 0) {
    console.warn("Redraw skipped: No visible candles.");
    return; // Nothing to draw
  }

  // Constants for candle drawing
  const candleTotalWidth = chartWidth / visibleCount;
  const candleBodyWidthRatio = 0.7; // Relative width of body to total candle space
  const candleWidth = Math.max(1, candleTotalWidth * candleBodyWidthRatio);
  const candleMargin = Math.max(0.5, (candleTotalWidth - candleWidth) / 2);

  // --- Draw Grid & Y-Axis ---
  try {
    const yTickDensity = Math.max(3, Math.round(chartHeight / 40));
    let iterationCount = 0;

    // --- Calculate Tick Values using LINEAR logic REGARDLESS of scale type ---
    const linearRange = maxVisiblePrice - minVisiblePrice;
    const linearTicks =
      linearRange > 0 && Number.isFinite(linearRange)
        ? calculateNiceStep(linearRange, yTickDensity)
        : 1; // Fallback step

    if (!linearTicks || linearTicks <= 0 || !Number.isFinite(linearTicks)) {
      console.error(
        "Y-Axis drawing aborted: Invalid linear tick step calculated.",
        linearTicks
      );
    } else {
      let firstLinearTick;
      // Find the first linear tick >= minVisiblePrice
      if (minVisiblePrice >= 0) {
        firstLinearTick =
          linearTicks > 0
            ? Math.ceil(minVisiblePrice / linearTicks) * linearTicks
            : minVisiblePrice;
      } else {
        // Handle negative minVisiblePrice (though unlikely for price charts)
        firstLinearTick =
          linearTicks > 0
            ? Math.floor(minVisiblePrice / linearTicks) * linearTicks
            : minVisiblePrice;
      }
      // Adjust if the first tick is too far above minVisiblePrice
      if (
        linearTicks > 0 &&
        firstLinearTick - minVisiblePrice > linearTicks * 0.99
      ) {
        firstLinearTick -= linearTicks;
      }
      // Ensure first tick isn't below zero if min price is positive
      if (minVisiblePrice > 0 && firstLinearTick < 0) {
        firstLinearTick = 0;
      }

      const loopUpperBound = maxVisiblePrice + linearTicks * 0.1; // Loop slightly beyond max

      // --- Loop using LINEAR price increments ---
      for (
        let currentPrice = firstLinearTick;
        currentPrice <= loopUpperBound &&
        iterationCount < Y_AXIS_MAX_ITERATIONS;
        currentPrice =
          linearTicks > 0 ? currentPrice + linearTicks : loopUpperBound + 1 // Add linear step, break if step invalid
      ) {
        iterationCount++;

        // --- Draw Tick using the scale-aware helper function ---
        // The drawYTick function will use getYCoordinate which checks
        // state.isLogScale to determine the CORRECT POSITION.
        // The value displayed will be `currentPrice`.
        drawYTick(currentPrice, chartHeight, minVisiblePrice, maxVisiblePrice);

        // Safety break if price isn't increasing
        if (
          linearTicks > Number.EPSILON &&
          currentPrice + linearTicks <= currentPrice
        ) {
          console.warn("Y-Axis loop safety break: Price not increasing.", {
            currentPrice,
            linearTicks,
          });
          break;
        }
      } // End for loop

      if (iterationCount >= Y_AXIS_MAX_ITERATIONS) {
        console.warn("Y-Axis drawing loop hit max iteration limit.");
      }
    } // End else (valid linearTicks)
  } catch (e) {
    console.error("Error drawing Y grid/axis:", e);
  }

  // --- Draw X-Axis & Separators --- (No changes needed here)
  try {
    const xTickDensity = Math.max(3, Math.round(chartWidth / 70));
    // Ensure visibleCount is positive for step calculation
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
        continue; // Check timestamp
      const timestamp = candleData[0];

      // Decide if this index should have a label
      const isFirst = i === 0;
      const isLast = i === visibleCount - 1;
      // Simple modulo check for ticks (ensure xTicks is positive)
      const isTick = xTicks > 0 && (i + Math.floor(xTicks / 2)) % xTicks === 0;

      if (isFirst || isLast || isTick) {
        const x = (i + 0.5) * candleTotalWidth; // Center label on candle

        // Prevent labels overlapping too much
        if (x - lastLabelX > MIN_PIXELS_PER_LABEL || isFirst || isLast) {
          // Only draw if within reasonable bounds of the chart width
          if (x >= -candleTotalWidth && x <= chartWidth + candleTotalWidth) {
            const xLabel = document.createElement("div");
            xLabel.className = "axis-label x-axis-label";
            xLabel.style.left = `${x.toFixed(1)}px`;
            xLabel.textContent = formatTimestamp(timestamp); // Use state-aware formatter
            dom.xAxisLabelsContainer.appendChild(xLabel);
            lastLabelX = x;
          }
        }
      }
    }
  } catch (e) {
    console.error("Error drawing X grid/axis:", e);
  }

  // --- Draw Candles --- (No changes needed here)
  try {
    const fragment = document.createDocumentFragment(); // Use fragment for performance

    for (let i = 0; i < visibleCount; i++) {
      const dataIndex = visibleStartIndex + i;
      if (dataIndex < 0 || dataIndex >= state.fullData.length) continue;

      const candle = state.fullData[dataIndex];
      // Ensure candle data is valid (time, low, high, open, close)
      if (
        !candle ||
        candle.length < 5 ||
        candle.slice(0, 5).some((v) => isNaN(v) || !Number.isFinite(v))
      ) {
        // console.warn(`Skipping candle at index ${dataIndex}: Invalid data`, candle);
        continue;
      }

      const [timestamp, low, high, open, close] = candle;

      // Calculate Y coordinates using the robust utility function
      // getYCoordinate internally handles log/linear based on state.isLogScale
      const wickHighY = getYCoordinate(high, chartHeight);
      const wickLowY = getYCoordinate(low, chartHeight);
      const bodyOpenY = getYCoordinate(open, chartHeight);
      const bodyCloseY = getYCoordinate(close, chartHeight);

      // *** CRITICAL CHECK: Ensure all coordinates are valid finite numbers ***
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
        // console.warn(`Skipping candle index ${dataIndex}: Invalid Y coordinate calculated.`);
        // console.warn({wickHighY, wickLowY, bodyOpenY, bodyCloseY});
        continue; // Skip this candle entirely if any coordinate is invalid
      }

      const bodyTopY = Math.min(bodyOpenY, bodyCloseY);
      const bodyBottomY = Math.max(bodyOpenY, bodyCloseY);

      // Calculate heights, ensuring minimum of 1px if coordinates are valid
      // Also check that wickLowY >= wickHighY and bodyBottomY >= bodyTopY
      const wickHeight = Math.max(1, wickLowY - wickHighY);
      const bodyHeight = Math.max(1, bodyBottomY - bodyTopY);

      const isUp = close >= open;

      // Create candle elements
      const candleElement = document.createElement("div");
      candleElement.className = "candle";
      candleElement.style.width = `${candleWidth.toFixed(1)}px`;
      // Position based on the center of the candle slot
      const candleLeft = i * candleTotalWidth + candleMargin;
      candleElement.style.left = `${candleLeft.toFixed(1)}px`;

      // Wick Element (only draw if height is valid)
      if (wickHeight >= 1 && wickLowY >= wickHighY) {
        const wickElement = document.createElement("div");
        wickElement.className = "wick";
        wickElement.style.top = `${wickHighY.toFixed(1)}px`;
        wickElement.style.height = `${wickHeight.toFixed(1)}px`;
        candleElement.appendChild(wickElement);
      }

      // Body Element (only draw if height is valid)
      if (bodyHeight >= 1 && bodyBottomY >= bodyTopY) {
        const bodyElement = document.createElement("div");
        bodyElement.className = `body ${isUp ? "color-up" : "color-down"}`;
        bodyElement.style.top = `${bodyTopY.toFixed(1)}px`;
        bodyElement.style.height = `${bodyHeight.toFixed(1)}px`;
        candleElement.appendChild(bodyElement);
      }

      // Only append candleElement if it has a body or wick
      if (candleElement.childNodes.length > 0) {
        fragment.appendChild(candleElement); // Append to fragment
      }
    }

    dom.chartArea.appendChild(fragment); // Append fragment once
  } catch (e) {
    console.error("Error drawing candles:", e);
  }

  // --- Update Live Price Indicator --- (No changes needed here)
  let priceForIndicator = state.lastTickerPrice;
  // Fallback to last candle's close if ticker price isn't available
  if (
    (priceForIndicator === null || !Number.isFinite(priceForIndicator)) &&
    state.fullData.length > 0
  ) {
    const lastCandle = state.fullData[state.fullData.length - 1];
    if (
      lastCandle &&
      lastCandle.length >= 5 &&
      Number.isFinite(lastCandle[4])
    ) {
      priceForIndicator = lastCandle[4]; // Use close price
    }
  }

  // Check again if price is valid before updating UI
  if (priceForIndicator !== null && Number.isFinite(priceForIndicator)) {
    updateLivePriceIndicatorUI(priceForIndicator, chartHeight);
  } else {
    // Ensure it's hidden if no valid price
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
  }
} // End of redrawChart function
