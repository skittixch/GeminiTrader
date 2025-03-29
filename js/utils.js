// js/utils.js
import state from "./state.js";
import * as config from "./config.js"; // Import config for MIN_PRICE_RANGE_SPAN

export const MIN_LOG_VALUE = 1e-9; // Ensure this is exported
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

// --- Time/Date Formatting ---

/**
 * Formats a timestamp or Date object into a human-readable string.
 * Handles both Unix timestamp (seconds) and JavaScript Date objects.
 * @param {number|Date} timestampOrDate - Unix timestamp (seconds) or Date object.
 * @returns {string} Formatted date/time string or "Invalid Date/Time".
 */
export function formatTimestamp(timestampOrDate) {
  try {
    let date;
    // ** Check input type **
    if (timestampOrDate instanceof Date) {
      date = timestampOrDate; // Use Date object directly
    } else if (
      typeof timestampOrDate === "number" &&
      Number.isFinite(timestampOrDate)
    ) {
      // Assume Unix timestamp in seconds, convert to milliseconds for Date constructor
      date = new Date(timestampOrDate * 1000);
    } else {
      // Handle other invalid inputs
      console.warn(
        "formatTimestamp received invalid input type:",
        typeof timestampOrDate,
        timestampOrDate
      );
      throw new Error(
        "Invalid input type: Expected number (Unix timestamp) or Date object."
      );
    }

    // Validate the resulting Date object
    if (isNaN(date.getTime())) {
      console.warn(
        "formatTimestamp resulted in an Invalid Date for input:",
        timestampOrDate
      );
      throw new Error("Invalid Date object produced");
    }

    // Use Intl.DateTimeFormat
    const options = {
      timeZone: "America/Chicago", // Set specific timezone
      // Adjust format as desired (e.g., remove year, add seconds)
      month: "numeric",
      day: "numeric",
      // year: 'numeric', // Optional: Add year if needed
      hour: "numeric",
      minute: "2-digit",
      // second: '2-digit', // Optional: Add seconds if needed
      hour12: state.is12HourFormat, // Use state setting
    };
    return date.toLocaleString("en-US", options);
  } catch (error) {
    console.error("Error formatting timestamp/date:", error, timestampOrDate);
    return "Time Error"; // More specific fallback
  }
}

export function formatDate(timestamp) {
  // This function primarily used for chart tooltips (assumes Unix timestamp)
  try {
    const date = new Date(timestamp * 1000); // Assumes Unix seconds
    const options = {
      timeZone: "America/Chicago",
      month: "short",
      day: "numeric",
      // Maybe add year?
      // year: 'numeric',
    };
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
  const numValue = typeof value === "string" ? parseFloat(value) : value;

  if (isNaN(numValue) || numValue === null || !Number.isFinite(numValue)) {
    // Return placeholder but maybe less visually intrusive than '--.--'
    return `?`;
  }
  try {
    // Determine decimals dynamically based on value, suitable for crypto prices
    let dynamicDecimals;
    if (numValue === 0) {
      dynamicDecimals = decimals; // Use default for zero
    } else if (Math.abs(numValue) < 0.0001) {
      dynamicDecimals = 8;
    } else if (Math.abs(numValue) < 0.1) {
      dynamicDecimals = 6;
    } else if (Math.abs(numValue) < 10) {
      dynamicDecimals = 4;
    } else if (Math.abs(numValue) < 1000) {
      dynamicDecimals = 2;
    } else {
      dynamicDecimals = 2; // Default for larger numbers
    }

    // Ensure minimum decimals if explicitly passed higher than dynamic default
    const finalDecimals = Math.max(decimals, dynamicDecimals);

    // Use compact notation for very large or small numbers if desired?
    // const notation = (Math.abs(numValue) > 1e6 || Math.abs(numValue) < 1e-3) ? 'compact' : 'standard';

    return numValue
      .toLocaleString("en-US", {
        style: "currency",
        currency: "USD", // Keep this as USD for the engine
        minimumFractionDigits: finalDecimals,
        maximumFractionDigits: finalDecimals,
        // notation: notation // Example if using compact notation
      })
      .replace("USD", currencySymbol) // Optional: Replace code if symbol is desired
      .replace(/^\$/, currencySymbol); // Ensure the passed symbol is used
  } catch (e) {
    console.error("Currency formatting error:", e, { value, decimals });
    // Fallback formatting
    const safeDecimals = Math.max(0, Math.floor(decimals));
    return `${currencySymbol}${numValue.toFixed(safeDecimals)}`;
  }
}

export function formatQuantity(value) {
  const numValue = typeof value === "string" ? parseFloat(value) : value;

  if (isNaN(numValue) || numValue === null || !Number.isFinite(numValue))
    return "--";

  const absValue = Math.abs(numValue);
  let decimals;

  // Determine decimals based on magnitude, optimized for crypto quantities
  if (absValue === 0) decimals = 2; // Show 0.00
  else if (absValue < 0.00000001)
    decimals = 10; // Even more precision for tiny amounts
  else if (absValue < 0.00001) decimals = 8;
  else if (absValue < 0.01) decimals = 6;
  else if (absValue < 1) decimals = 5;
  else if (absValue < 100) decimals = 4;
  else if (absValue < 10000) decimals = 3;
  else decimals = 2; // Standard for large quantities

  try {
    // Use number formatting for locale-specific separators
    return numValue.toLocaleString("en-US", {
      minimumFractionDigits: 2, // Show at least 2 for visual consistency
      maximumFractionDigits: decimals,
    });
  } catch (e) {
    console.error("Quantity formatting error:", e, { value, decimals });
    // Fallback to fixed decimal places
    return numValue.toFixed(decimals);
  }
}
