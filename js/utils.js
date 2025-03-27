// js/utils.js
import state from "./state.js"; // Needs state for format/scale checks

const MIN_LOG_VALUE = 1e-9; // Prevent log(0)

/**
 * Calculates the Y screen coordinate for a given price based on scale type.
 */
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

/**
 * Calculates the price value for a given Y screen coordinate.
 * Inverse of getYCoordinate.
 * @param {number} yPos - The Y coordinate within the chart area (0 = top).
 * @param {number} chartHeight - The height of the chart area.
 * @returns {number|null} The calculated price or null if calculation fails.
 */
export function getPriceFromYCoordinate(yPos, chartHeight) {
  if (
    isNaN(yPos) ||
    isNaN(chartHeight) ||
    chartHeight <= 0 /*|| yPos < 0 || yPos > chartHeight*/
  ) {
    // Allow slight out-of-bounds yPos for calculation robustness near edges
    return null;
  }

  const { minVisiblePrice, maxVisiblePrice, isLogScale } = state;
  const clampedYPos = Math.max(0, Math.min(yPos, chartHeight)); // Clamp Y for calculation

  if (isLogScale) {
    const logMin = Math.log(Math.max(MIN_LOG_VALUE, minVisiblePrice));
    const logMax = Math.log(Math.max(MIN_LOG_VALUE, maxVisiblePrice));
    const logRange = logMax - logMin;

    if (logRange <= 0 || isNaN(logRange)) {
      // If range is zero or invalid, return the base price
      return Math.max(MIN_LOG_VALUE, minVisiblePrice);
    }

    // Inverse calculation: logPrice = logMin + ( (chartHeight - clampedYPos) / chartHeight * logRange )
    const fraction = (chartHeight - clampedYPos) / chartHeight;
    const logPrice = logMin + fraction * logRange;
    return Math.exp(logPrice);
  } else {
    const priceRange = maxVisiblePrice - minVisiblePrice;
    if (priceRange <= 0) {
      // If range is zero, price is constant
      return minVisiblePrice;
    }

    // Inverse calculation: price = minVisiblePrice + ( (chartHeight - clampedYPos) / chartHeight * priceRange )
    const fraction = (chartHeight - clampedYPos) / chartHeight;
    const price = minVisiblePrice + fraction * priceRange;
    return Math.max(0, price); // Ensure price doesn't go below zero
  }
}

/** Calculates 'nice' numerical steps for gridlines/labels. */
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
  // Ensure step is reasonably small compared to range but not zero
  return Math.max(niceStep, range * 1e-6, Number.EPSILON * 10);
}

/**
 * Formats a Unix timestamp (seconds) into HH:MM (or H:MM AM/PM) string (CST/CDT),
 * respecting the 12/24 hour format state.
 */
export function formatTimestamp(timestamp) {
  try {
    const date = new Date(timestamp * 1000);
    // Always request numeric hour for consistency
    const options = {
      timeZone: "America/Chicago",
      hour: "numeric",
      minute: "2-digit",
      hour12: state.is12HourFormat,
    };
    return date.toLocaleString("en-US", options);
  } catch (error) {
    console.error("Error formatting timestamp:", error, timestamp);
    const fallbackDate = new Date(timestamp * 1000); // Fallback to local time
    const h = fallbackDate.getHours().toString().padStart(2, "0");
    const m = fallbackDate.getMinutes().toString().padStart(2, "0");
    return `${h}:${m}?`; // Add indicator for fallback
  }
}

/** Formats a Unix timestamp into "Mmm D" string (CST/CDT). */
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
