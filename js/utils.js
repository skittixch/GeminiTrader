// js/utils.js
import state from "./state.js";
import * as config from "./config.js"; // Import config for MIN_PRICE_RANGE_SPAN

export const MIN_LOG_VALUE = 1e-9; // <<<--- ADD export HERE
const MIN_LINEAR_RANGE_EPSILON = 1e-9; // Small value to check against zero range
const MIN_LOG_RANGE_EPSILON = 1e-9; // Small value for log range

export function getYCoordinate(price, chartHeight) {
  if (
    isNaN(price) ||
    isNaN(chartHeight) ||
    chartHeight <= 0 ||
    price < 0 // Allow price to be 0 on linear scale, but handle below
  ) {
    // console.warn("getYCoordinate: Invalid input price or chartHeight", { price, chartHeight });
    return null;
  }

  const { minVisiblePrice, maxVisiblePrice, isLogScale } = state;

  // Stricter validation of the visible price range
  if (
    isNaN(minVisiblePrice) ||
    isNaN(maxVisiblePrice) ||
    !Number.isFinite(minVisiblePrice) ||
    !Number.isFinite(maxVisiblePrice) ||
    maxVisiblePrice <= minVisiblePrice
  ) {
    // console.warn("getYCoordinate: Invalid visible price range in state", { minVisiblePrice, maxVisiblePrice });
    return null;
  }

  if (isLogScale) {
    const safeMinVisiblePrice = Math.max(MIN_LOG_VALUE, minVisiblePrice);
    const safeMaxVisiblePrice = Math.max(MIN_LOG_VALUE, maxVisiblePrice);
    // Ensure price itself is also treated as positive for log calculation
    const safePrice = Math.max(MIN_LOG_VALUE, price);

    if (safeMaxVisiblePrice <= safeMinVisiblePrice) return null; // Should be caught above, but double-check

    const logMin = Math.log(safeMinVisiblePrice);
    const logMax = Math.log(safeMaxVisiblePrice);
    const logPrice = Math.log(safePrice);

    if (
      !Number.isFinite(logMin) ||
      !Number.isFinite(logMax) ||
      !Number.isFinite(logPrice)
    ) {
      // console.warn("getYCoordinate (Log): Non-finite log value", { logMin, logMax, logPrice });
      return null;
    }

    const logRange = logMax - logMin;

    // Check for near-zero or invalid log range
    if (!Number.isFinite(logRange) || logRange < MIN_LOG_RANGE_EPSILON) {
      // If range is effectively zero, map based on comparison to min/max
      if (logPrice <= logMin) return chartHeight;
      if (logPrice >= logMax) return 0;
      return chartHeight / 2; // Fallback for prices within the zero range
    }

    const logScaleY = chartHeight / logRange;
    const yPos = chartHeight - (logPrice - logMin) * logScaleY;

    if (!Number.isFinite(yPos)) {
      // console.warn("getYCoordinate (Log): Calculated yPos is not finite", { price, yPos });
      return null;
    }
    return yPos;
  } else {
    // Linear Scale
    const priceRange = maxVisiblePrice - minVisiblePrice;

    // Check for near-zero or invalid linear range
    if (!Number.isFinite(priceRange) || priceRange < MIN_LINEAR_RANGE_EPSILON) {
      // If range is effectively zero, map based on comparison to min/max
      if (price <= minVisiblePrice) return chartHeight;
      if (price >= maxVisiblePrice) return 0;
      return chartHeight / 2; // Fallback for prices within the zero range
    }

    const scaleY = chartHeight / priceRange;
    const yPos = chartHeight - (price - minVisiblePrice) * scaleY;

    if (!Number.isFinite(yPos)) {
      // console.warn("getYCoordinate (Linear): Calculated yPos is not finite", { price, yPos });
      return null;
    }
    // Let drawing clip if needed, just ensure it's finite
    return yPos;
  }
}

export function getPriceFromYCoordinate(yPos, chartHeight) {
  if (isNaN(yPos) || isNaN(chartHeight) || chartHeight <= 0) return null;

  const { minVisiblePrice, maxVisiblePrice, isLogScale } = state;

  // Stricter validation of the visible price range
  if (
    isNaN(minVisiblePrice) ||
    isNaN(maxVisiblePrice) ||
    !Number.isFinite(minVisiblePrice) ||
    !Number.isFinite(maxVisiblePrice) ||
    maxVisiblePrice <= minVisiblePrice
  ) {
    // console.warn("getPriceFromYCoordinate: Invalid visible price range", { minVisiblePrice, maxVisiblePrice });
    return null;
  }

  // Clamp Y position to chart boundaries before calculation
  const clampedYPos = Math.max(0, Math.min(yPos, chartHeight));
  const fraction = (chartHeight - clampedYPos) / chartHeight; // Fraction from bottom (0) to top (1)

  if (isLogScale) {
    const safeMinVisiblePrice = Math.max(MIN_LOG_VALUE, minVisiblePrice);
    const safeMaxVisiblePrice = Math.max(MIN_LOG_VALUE, maxVisiblePrice);

    if (safeMaxVisiblePrice <= safeMinVisiblePrice) return safeMinVisiblePrice;

    const logMin = Math.log(safeMinVisiblePrice);
    const logMax = Math.log(safeMaxVisiblePrice);

    if (!Number.isFinite(logMin) || !Number.isFinite(logMax)) return null;

    const logRange = logMax - logMin;

    if (!Number.isFinite(logRange) || logRange < MIN_LOG_RANGE_EPSILON) {
      // If range is negligible, return the min price
      return safeMinVisiblePrice;
    }

    const logPrice = logMin + fraction * logRange;
    const price = Math.exp(logPrice);

    // Ensure result is finite
    return Number.isFinite(price) ? price : null;
  } else {
    // Linear Scale
    const priceRange = maxVisiblePrice - minVisiblePrice;

    if (!Number.isFinite(priceRange) || priceRange < MIN_LINEAR_RANGE_EPSILON) {
      // If range is negligible, return the min price
      return minVisiblePrice;
    }

    const price = minVisiblePrice + fraction * priceRange;

    // Ensure price is not negative and is finite
    return Number.isFinite(price) ? Math.max(0, price) : null;
  }
}

export function calculateNiceStep(range, maxTicks) {
  if (
    isNaN(range) ||
    range <= 0 ||
    isNaN(maxTicks) ||
    maxTicks <= 0 ||
    !Number.isFinite(range)
  ) {
    return 1; // Return a default step if input is invalid
  }

  const roughStep = range / Math.max(1, maxTicks);
  if (roughStep <= 0 || isNaN(roughStep) || !Number.isFinite(roughStep)) {
    return 1; // Default if rough step calculation fails
  }

  // Handle extremely small rough steps that might cause log10 issues
  if (roughStep < Number.EPSILON) {
    return Number.EPSILON * 10;
  }

  const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep)));
  if (magnitude <= 0 || !Number.isFinite(magnitude)) {
    // Fallback if magnitude calculation fails (e.g., extremely large range)
    return roughStep > 1 ? roughStep : 1;
  }

  const residual = roughStep / magnitude;

  let niceStep;
  if (residual > 5) niceStep = 10 * magnitude;
  else if (residual > 2) niceStep = 5 * magnitude;
  else if (residual > 1) niceStep = 2 * magnitude;
  else niceStep = magnitude;

  // Ensure the step is a reasonably small fraction of the range if range is tiny
  // and also ensure it's at least a minimum value to prevent near-zero steps.
  const minStep = Math.max(Number.EPSILON * 10, range * 1e-9);

  // Ensure niceStep is finite before returning
  return Number.isFinite(niceStep) ? Math.max(niceStep, minStep) : minStep;
}

// --- Time/Date Formatting --- (remain the same)
export function formatTimestamp(timestamp) {
  try {
    const date = new Date(timestamp * 1000);
    const options = {
      timeZone: "America/Chicago", // Consider making this configurable later
      hour: "numeric",
      minute: "2-digit",
      hour12: state.is12HourFormat,
    };
    // Check for invalid date
    if (isNaN(date.getTime())) {
      throw new Error("Invalid timestamp resulted in Invalid Date");
    }
    return date.toLocaleString("en-US", options);
  } catch (error) {
    console.error("Error formatting timestamp:", error, timestamp);
    // Provide a fallback, but indicate error
    const fallbackDate = new Date(timestamp * 1000);
    if (isNaN(fallbackDate.getTime())) return "??:??";
    const h = fallbackDate.getHours().toString().padStart(2, "0");
    const m = fallbackDate.getMinutes().toString().padStart(2, "0");
    return `${h}:${m}?`;
  }
}

export function formatDate(timestamp) {
  try {
    const date = new Date(timestamp * 1000);
    const options = {
      timeZone: "America/Chicago", // Consider making this configurable later
      month: "short",
      day: "numeric",
    };
    // Check for invalid date
    if (isNaN(date.getTime())) {
      throw new Error("Invalid timestamp resulted in Invalid Date");
    }
    return date.toLocaleDateString("en-US", options);
  } catch (error) {
    console.error("Error formatting date:", error, timestamp);
    return "Date Err";
  }
}

export function formatCurrency(value, currencySymbol = "$", decimals = 2) {
  if (isNaN(value) || value === null || !Number.isFinite(value)) {
    return `${currencySymbol}--.--`;
  }
  try {
    // Ensure decimals is a non-negative integer
    const safeDecimals = Math.max(0, Math.floor(decimals));
    return value
      .toLocaleString("en-US", {
        style: "currency",
        currency: "USD", // Assuming USD for now
        minimumFractionDigits: safeDecimals,
        maximumFractionDigits: safeDecimals,
      })
      .replace("USD", currencySymbol) // Replace if needed, though style: 'currency' often adds it
      .replace(/^\$/, currencySymbol); // Ensure correct symbol if default '$' is used
  } catch (e) {
    console.error("Currency formatting error:", e, { value, decimals });
    // Fallback formatting
    const safeDecimals = Math.max(0, Math.floor(decimals));
    return `${currencySymbol}${value.toFixed(safeDecimals)}`;
  }
}

export function formatQuantity(value) {
  if (isNaN(value) || value === null || !Number.isFinite(value)) return "--";

  const absValue = Math.abs(value);
  let decimals;

  // Determine decimals based on magnitude
  if (absValue === 0) decimals = 2; // Show 0.00 for zero
  else if (absValue < 0.000001) decimals = 8;
  else if (absValue < 0.001) decimals = 6; // Adjusted breakpoint
  else if (absValue < 1) decimals = 4;
  else if (absValue < 1000) decimals = 3; // More precision for values > 1
  else decimals = 2; // Standard for larger numbers

  try {
    // Ensure decimals is valid
    const safeDecimals = Math.max(0, Math.floor(decimals));
    return value.toLocaleString("en-US", {
      minimumFractionDigits: 2, // Always show at least two for consistency
      maximumFractionDigits: safeDecimals,
    });
  } catch (e) {
    console.error("Quantity formatting error:", e, { value, decimals });
    const safeDecimals = Math.max(0, Math.floor(decimals));
    return value.toFixed(safeDecimals); // Fallback
  }
}
