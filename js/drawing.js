// js/drawing.js

import * as config from "./config.js";
import state from "./state.js";
import * as dom from "./domElements.js";
import { calculateNiceStep, formatTimestamp, formatDate } from "./utils.js";

const MIN_LOG_VALUE = 1e-9;

function getYCoordinate(price, chartHeight) {
  if (isNaN(price) || isNaN(chartHeight) || chartHeight <= 0) return null;
  const safeMinVisiblePrice = Math.max(MIN_LOG_VALUE, state.minVisiblePrice);
  const safeMaxVisiblePrice = Math.max(
    safeMinVisiblePrice + MIN_LOG_VALUE,
    state.maxVisiblePrice
  );
  const safePrice = Math.max(MIN_LOG_VALUE, price);

  if (state.isLogScale) {
    const logMin = Math.log(safeMinVisiblePrice);
    const logMax = Math.log(safeMaxVisiblePrice);
    const logPrice = Math.log(safePrice);
    const logRange = logMax - logMin;
    if (logRange <= 0 || isNaN(logRange)) {
      return chartHeight / 2;
    }
    const logScaleY = chartHeight / logRange;
    const yPos = chartHeight - (logPrice - logMin) * logScaleY;
    return isNaN(yPos) ? null : yPos;
  } else {
    const priceRange = safeMaxVisiblePrice - safeMinVisiblePrice;
    if (priceRange <= 0 || isNaN(priceRange)) {
      return chartHeight / 2;
    }
    const scaleY = chartHeight / priceRange;
    const yPos = chartHeight - (price - safeMinVisiblePrice) * scaleY;
    return isNaN(yPos) ? null : yPos;
  }
}

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

  if (visibleCount <= 0 || (linearPriceRange <= 0 && !state.isLogScale)) {
    return;
  }

  const totalCandleWidthRatio = 0.85;
  const candleWidth = Math.max(
    1,
    (chartWidth / visibleCount) * totalCandleWidthRatio
  );
  const candleMargin = Math.max(
    0.5,
    ((chartWidth / visibleCount) * (1 - totalCandleWidthRatio)) / 2
  );
  const candleTotalWidth = candleWidth + candleMargin * 2;

  try {
    // Draw Grid & Axes
    const yTickDensity = Math.max(3, Math.round(chartHeight / 40));
    const displayRange = linearPriceRange > 0 ? linearPriceRange : 1;
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
      if (
        yTicks <= Number.EPSILON ||
        (state.isLogScale && price <= 0) ||
        price > state.maxVisiblePrice + displayRange * 1.1
      )
        break;
      const y = getYCoordinate(price, chartHeight);
      if (y === null || isNaN(y)) continue;
      if (y >= -chartHeight && y <= chartHeight * 2) {
        const hLine = document.createElement("div");
        hLine.className = "grid-line horizontal";
        hLine.style.top = `${y.toFixed(1)}px`;
        dom.gridContainer.appendChild(hLine);
        if (y >= -5 && y <= chartHeight + 5) {
          const yLabel = document.createElement("div");
          yLabel.className = "axis-label y-axis-label";
          yLabel.style.top = `${y.toFixed(1)}px`;
          const decimals =
            displayRange < 10 ? (price < 1 ? 4 : 2) : price < 100 ? 1 : 0;
          yLabel.textContent = price.toFixed(Math.max(0, decimals));
          dom.yAxisLabelsContainer.appendChild(yLabel);
        }
      }
      if (price + yTicks <= price) break;
    }

    const xTickDensity = Math.max(3, Math.round(chartWidth / 70));
    const xTicks = Math.max(1, calculateNiceStep(visibleCount, xTickDensity));
    const checkMargin = Math.ceil(visibleCount * 0.1);
    const startIndexToCheck = Math.floor(state.visibleStartIndex - checkMargin);
    const endIndexToCheck = Math.ceil(state.visibleEndIndex + checkMargin);
    let previousDateString = null;
    for (
      let dataIndex = startIndexToCheck;
      dataIndex < endIndexToCheck;
      dataIndex++
    ) {
      if (dataIndex >= 0 && dataIndex < state.fullData.length) {
        const candleData = state.fullData[dataIndex];
        if (!candleData) continue;
        const timestamp = candleData[0];
        const currentJsDate = new Date(timestamp * 1000);
        const currentDateString = currentJsDate.toDateString();
        const relativeSlotIndex = dataIndex - state.visibleStartIndex; // Slot position relative to viewport start
        const x = relativeSlotIndex * candleTotalWidth + candleTotalWidth / 2; // Center for time label
        const xDatePosition =
          relativeSlotIndex * candleTotalWidth + candleMargin; // Near left for date label

        if (
          previousDateString === null ||
          currentDateString !== previousDateString
        ) {
          const dateLabel = document.createElement("div");
          dateLabel.className = "axis-label x-axis-date-label";
          dateLabel.textContent = formatDate(timestamp);
          dateLabel.style.left = `${xDatePosition.toFixed(1)}px`;
          dom.xAxisLabelsContainer.appendChild(dateLabel);
        }
        previousDateString = currentDateString;

        const isTick = (dataIndex + Math.floor(xTicks / 4)) % xTicks === 0;
        const shouldHaveTimeLabel =
          isTick || (xTicks === 1 && dataIndex % 5 === 0);
        const minutesPastMidnight =
          currentJsDate.getHours() * 60 + currentJsDate.getMinutes();
        const defaultGranularitySeconds = config.DEFAULT_GRANULARITY || 3600;
        const isNearMidnight =
          minutesPastMidnight < defaultGranularitySeconds / 60;

        if (shouldHaveTimeLabel && !isNearMidnight) {
          const timeLabel = document.createElement("div");
          timeLabel.className = "axis-label x-axis-label";
          timeLabel.textContent = formatTimestamp(timestamp);
          timeLabel.style.left = `${x.toFixed(1)}px`;
          dom.xAxisLabelsContainer.appendChild(timeLabel);
        }
      } else {
        previousDateString = null;
      }
    }
  } catch (e) {
    console.error("Error drawing axes/grid:", e);
  }

  try {
    // Draw Candles
    for (let i = 0; i < visibleCount; i++) {
      const dataIndex = state.visibleStartIndex + i;
      if (dataIndex >= 0 && dataIndex < state.fullData.length) {
        const candle = state.fullData[dataIndex];
        if (!candle || candle.length < 6) {
          continue;
        }
        const [timestamp, low, high, open, close, volume] = candle;
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
        candleElement.style.width = `${candleWidth}px`;
        candleElement.style.marginLeft = `${
          i === 0 ? candleMargin : candleMargin * 2
        }px`;
        const wickElement = document.createElement("div");
        wickElement.className = "wick";
        wickElement.style.top = `${wickHighY.toFixed(1)}px`;
        wickElement.style.height = `${wickHeight.toFixed(1)}px`;
        const bodyElement = document.createElement("div");
        bodyElement.className = `body ${isUp ? "color-up" : "color-down"}`;
        bodyElement.style.top = `${bodyTopY.toFixed(1)}px`;
        bodyElement.style.height = `${bodyHeight.toFixed(1)}px`;
        candleElement.appendChild(wickElement);
        candleElement.appendChild(bodyElement);
        dom.chartArea.appendChild(candleElement);
      }
    }
  } catch (e) {
    console.error("Error drawing candles:", e);
    dom.chartMessage.textContent = "Error drawing candles.";
    dom.chartMessage.style.display = "block";
  }
}
