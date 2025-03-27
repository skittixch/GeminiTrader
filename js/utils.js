// js/utils.js
import state from './state.js'; // Needs state for format/scale checks

const MIN_LOG_VALUE = 1e-9; // Prevent log(0)

/**
 * Calculates the Y screen coordinate for a given price based on scale type.
 */
export function getYCoordinate(price, chartHeight) {
    if (isNaN(price) || isNaN(chartHeight) || chartHeight <= 0) return null;
    const safeMinVisiblePrice = Math.max(MIN_LOG_VALUE, state.minVisiblePrice);
    const safeMaxVisiblePrice = Math.max(safeMinVisiblePrice + MIN_LOG_VALUE, state.maxVisiblePrice);
    const safePrice = Math.max(MIN_LOG_VALUE, price);

    if (state.isLogScale) {
        const logMin = Math.log(safeMinVisiblePrice);
        const logMax = Math.log(safeMaxVisiblePrice);
        const logPrice = Math.log(safePrice);
        const logRange = logMax - logMin;
        if (logRange <= 0 || isNaN(logRange)) { return chartHeight / 2; }
        const logScaleY = chartHeight / logRange;
        const yPos = chartHeight - ((logPrice - logMin) * logScaleY);
        return isNaN(yPos) ? null : yPos;
    } else {
        const priceRange = safeMaxVisiblePrice - safeMinVisiblePrice;
        if (priceRange <= 0 || isNaN(priceRange)) { return chartHeight / 2; }
        const scaleY = chartHeight / priceRange;
        const yPos = chartHeight - ((price - safeMinVisiblePrice) * scaleY);
        return isNaN(yPos) ? null : yPos;
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
    return Math.max(niceStep, Number.EPSILON * 10);
}

/**
 * Formats a Unix timestamp (seconds) into HH:MM (or H:MM AM/PM) string (CST/CDT),
 * respecting the 12/24 hour format state.
 */
export function formatTimestamp(timestamp) {
    const date = new Date(timestamp * 1000);
    const options = {
        timeZone: 'America/Chicago',
        minute: '2-digit',
        hour12: state.is12HourFormat // Use state flag
    };
    try {
        // Specify hour format based on hour12 flag for clarity with toLocaleString
        options.hour = state.is12HourFormat ? 'numeric' : '2-digit';
        let formatted = date.toLocaleString('en-US', options);
        // Optional: Adjust AM/PM spacing/casing
        // if(state.is12HourFormat) {
        //     formatted = formatted.replace(' AM', 'am').replace(' PM', 'pm');
        // }
        return formatted;
    }
    catch (error) {
        console.error("Error formatting timestamp:", error);
        const h = date.getHours().toString().padStart(2, '0'); // Fallback 24hr local
        const m = date.getMinutes().toString().padStart(2, '0');
        return `${h}:${m}`;
    }
}


/** Formats a Unix timestamp into "Mmm D" string (CST/CDT). */
export function formatDate(timestamp) {
    const date = new Date(timestamp * 1000);
    const options = { timeZone: 'America/Chicago', month: 'short', day: 'numeric' };
    try { return date.toLocaleDateString('en-US', options); }
    catch (error) { console.error("Error formatting date:", error); return ""; }
}