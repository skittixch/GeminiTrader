// js/utils.js
import state from "./state.js";

const MIN_LOG_VALUE = 1e-9;

export function getYCoordinate(price, chartHeight) {
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
export function getPriceFromYCoordinate(yPos, chartHeight) {
  if (isNaN(yPos) || isNaN(chartHeight) || chartHeight <= 0) {
    return null;
  }
  const { minVisiblePrice, maxVisiblePrice, isLogScale } = state;
  const clampedYPos = Math.max(0, Math.min(yPos, chartHeight));
  if (isLogScale) {
    const logMin = Math.log(Math.max(MIN_LOG_VALUE, minVisiblePrice));
    const logMax = Math.log(Math.max(MIN_LOG_VALUE, maxVisiblePrice));
    const logRange = logMax - logMin;
    if (logRange <= 0 || isNaN(logRange)) {
      return Math.max(MIN_LOG_VALUE, minVisiblePrice);
    }
    const fraction = (chartHeight - clampedYPos) / chartHeight;
    const logPrice = logMin + fraction * logRange;
    return Math.exp(logPrice);
  } else {
    const priceRange = maxVisiblePrice - minVisiblePrice;
    if (priceRange <= 0) {
      return minVisiblePrice;
    }
    const fraction = (chartHeight - clampedYPos) / chartHeight;
    const price = minVisiblePrice + fraction * priceRange;
    return Math.max(0, price);
  }
}
export function calculateNiceStep(range, maxTicks) {
  if (range <= 0 || maxTicks <= 0) return 1;
  const roughStep = range / maxTicks;
  const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep)));
  const residual = roughStep / magnitude;
  let niceStep;
  if (residual > 5) niceStep = 10 * magnitude;
  else if (residual > 2) niceStep = 5 * magnitude;
  else if (residual > 1) niceStep = 2 * magnitude;
  else niceStep = magnitude;
  return Math.max(niceStep, range * 1e-6, Number.EPSILON * 10);
}
export function formatTimestamp(timestamp) {
  try {
    const date = new Date(timestamp * 1000);
    const options = {
      timeZone: "America/Chicago",
      hour: "numeric",
      minute: "2-digit",
      hour12: state.is12HourFormat,
    };
    return date.toLocaleString("en-US", options);
  } catch (error) {
    console.error("Error formatting timestamp:", error, timestamp);
    const fallbackDate = new Date(timestamp * 1000);
    const h = fallbackDate.getHours().toString().padStart(2, "0");
    const m = fallbackDate.getMinutes().toString().padStart(2, "0");
    return `${h}:${m}?`;
  }
}
export function formatDate(timestamp) {
  try {
    const date = new Date(timestamp * 1000);
    const options = {
      timeZone: "America/Chicago",
      month: "short",
      day: "numeric",
    };
    return date.toLocaleDateString("en-US", options);
  } catch (error) {
    console.error("Error formatting date:", error, timestamp);
    return "Date Error";
  }
}

/** Formats currency value */
export function formatCurrency(value, currencySymbol = "$", decimals = 2) {
  if (isNaN(value) || value === null) {
    return `${currencySymbol}--.--`;
  }
  try {
    return value
      .toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })
      .replace("USD", currencySymbol)
      .replace(/^\$/, currencySymbol);
  } catch (e) {
    console.error("Currency formatting error:", e);
    return `${currencySymbol}${value.toFixed(decimals)}`;
  }
}

/** Formats quantity value with dynamic precision */
export function formatQuantity(value) {
  if (isNaN(value) || value === null) return "--";
  const absValue = Math.abs(value);
  let decimals;
  if (absValue === 0) decimals = 2;
  else if (absValue < 0.000001) decimals = 8;
  else if (absValue < 0.01) decimals = 6;
  else if (absValue < 1) decimals = 4;
  else decimals = 3;
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: decimals,
  });
}
