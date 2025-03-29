// js/main.js

import * as dom from "./domElements.js";
import state, { updateState } from "./state.js";
import * as config from "./config.js";
import { initializeTheme } from "./theme.js";
import { redrawChart } from "./drawing.js";
import { attachInteractionListeners } from "./interactions.js";
import {
  initializeWebSocket,
  closeWebSocket,
  updateWebSocketSubscription,
} from "./liveUpdate.js";
import { initializeBalances } from "./balance.js";
import { initializeResizer } from "./layout.js";
import { initializeSettingsMenu } from "./settingsMenu.js";
import { initializeTabs } from "./tabs.js";
import { initializePromptTab } from "./promptTab.js";
import { MIN_LOG_VALUE } from "./utils.js";
// Note: orders.js doesn't need explicit import here if triggered via tabs.js
// import { initializeVolumeChart } from './volumeChart.js'; // Import volume chart initialization <-- COMMENTED OUT

// --- Status Indicator ---
function updateApiStatusIndicator(loaded, message = null) {
  if (!dom.apiStatusIndicator) return;
  dom.apiStatusIndicator.className = loaded ? "loaded" : "error";
  dom.apiStatusIndicator.textContent = message || (loaded ? "Loaded" : "Error");
}
function checkApiStatus() {
  if (!dom.apiStatusIndicator) return;
  dom.apiStatusIndicator.textContent = "Checking...";
  dom.apiStatusIndicator.className = "loading";
  fetch("http://localhost:5000/api/status")
    .then((response) => {
      if (!response.ok) {
        return response
          .json()
          .catch(() => {
            throw new Error(`HTTP error ${response.status}`);
          })
          .then((errData) => {
            throw new Error(errData.error || `HTTP error ${response.status}`);
          });
      }
      return response.json();
    })
    .then((data) => {
      if (data.credentials_loaded) {
        updateApiStatusIndicator(true);
      } else {
        updateApiStatusIndicator(false, "Creds Failed");
      }
    })
    .catch((error) => {
      console.error("Error checking API status:", error);
      updateApiStatusIndicator(false, "Unavailable");
    });
}

// --- Initialize Chart View State ---
function initializeChartView(data) {
  if (!data || !data.length) {
    console.warn("initializeChartView skipped: No data provided.");
    return;
  }

  // Determine if log scale preference is set
  const savedLogPref = localStorage.getItem("logScalePref") === "true";
  const savedTimeFormatPref = localStorage.getItem("timeFormatPref") === "true";

  const totalDataCount = data.length;
  const initialVisibleCount = Math.min(
    config.DEFAULT_RESET_CANDLE_COUNT,
    totalDataCount
  );
  const initialStartIndex = Math.max(0, totalDataCount - initialVisibleCount);
  const initialEndIndex = totalDataCount;

  // Find min/max low/high in the initial visible range
  let initialMinY = Infinity,
    initialMaxY = -Infinity;
  for (let i = initialStartIndex; i < initialEndIndex; i++) {
    if (!data[i] || data[i].length < 5) continue; // Need low[1] and high[2]
    const low = data[i][1];
    const high = data[i][2];
    if (!isNaN(low) && Number.isFinite(low)) {
      initialMinY = Math.min(initialMinY, low);
    }
    if (!isNaN(high) && Number.isFinite(high)) {
      initialMaxY = Math.max(initialMaxY, high);
    }
  }

  // Handle cases where min/max couldn't be determined
  if (
    initialMinY === Infinity ||
    initialMaxY === -Infinity ||
    initialMinY <= 0
  ) {
    // Try to get a fallback from the last candle's close price if available
    const lastCandle = data[data.length - 1];
    const lastClose =
      lastCandle && lastCandle.length >= 5 && Number.isFinite(lastCandle[4])
        ? lastCandle[4]
        : 100; // Default fallback
    initialMinY = lastClose * 0.9;
    initialMaxY = lastClose * 1.1;
    console.warn(
      "Could not determine initial Y range from visible data, using fallback range.",
      { initialMinY, initialMaxY }
    );
  }
  // Ensure min is positive for log scale calculations later
  initialMinY = Math.max(MIN_LOG_VALUE, initialMinY); // Use imported constant
  if (initialMaxY <= initialMinY) {
    initialMaxY = initialMinY * 1.1; // Ensure max > min
  }

  // --- Apply Padding based on Scale Type ---
  let initialMinPrice, initialMaxPrice;

  if (savedLogPref) {
    // Log Scale: Apply multiplicative padding
    const logPadding = 1 + config.Y_AXIS_LOG_PADDING_FACTOR;
    initialMinPrice = Math.max(MIN_LOG_VALUE, initialMinY / logPadding); // Use imported constant
    initialMaxPrice = initialMaxY * logPadding; // Multiply max by (1 + factor)

    // Ensure minimum range ratio for log scale
    if (initialMaxPrice / initialMinPrice < 1.01) {
      const midLog =
        (Math.log(initialMaxPrice) + Math.log(initialMinPrice)) / 2;
      const halfRangeLog = Math.log(1.005); // ~0.5% range
      initialMinPrice = Math.max(
        MIN_LOG_VALUE,
        Math.exp(midLog - halfRangeLog)
      ); // Use imported constant
      initialMaxPrice = Math.exp(midLog + halfRangeLog);
    }
  } else {
    // Linear Scale: Apply additive padding
    const linearPadding = Math.max(
      config.MIN_PRICE_RANGE_SPAN * 0.1, // Ensure padding is at least something
      (initialMaxY - initialMinY) * config.Y_AXIS_PRICE_PADDING_FACTOR
    );
    initialMinPrice = Math.max(0, initialMinY - linearPadding); // Cannot go below 0
    initialMaxPrice = initialMaxY + linearPadding;

    // Ensure minimum linear range span
    if (initialMaxPrice - initialMinPrice < config.MIN_PRICE_RANGE_SPAN) {
      const mid = (initialMaxPrice + initialMinPrice) / 2;
      initialMinPrice = Math.max(0, mid - config.MIN_PRICE_RANGE_SPAN / 2); // Clamp at 0
      initialMaxPrice = mid + config.MIN_PRICE_RANGE_SPAN / 2;
    }
  }

  // Update the global state
  updateState({
    visibleStartIndex: initialStartIndex,
    visibleEndIndex: initialEndIndex,
    minVisiblePrice: initialMinPrice,
    maxVisiblePrice: initialMaxPrice,
    isLogScale: savedLogPref,
    is12HourFormat: savedTimeFormatPref,
  });

  // Update UI toggles to match loaded state
  if (dom.logScaleToggle) dom.logScaleToggle.checked = savedLogPref;
  if (dom.timeFormatToggle) dom.timeFormatToggle.checked = savedTimeFormatPref;

  console.log("Initialized chart view state:", {
    startIndex: initialStartIndex,
    endIndex: initialEndIndex,
    minPrice: initialMinPrice,
    maxPrice: initialMaxPrice,
    isLog: savedLogPref,
  });
}

// --- Fetch/Redraw Chart Data ---
function fetchAndRedraw(granularitySeconds) {
  updateState({ currentGranularity: granularitySeconds });
  const currentProductID = config.DEFAULT_PRODUCT_ID; // Use default for now
  const apiUrl = `http://localhost:5000/api/candles?granularity=${granularitySeconds}&product_id=${currentProductID}`;
  console.log(
    `Fetching chart data for ${currentProductID} at ${granularitySeconds}s interval from: ${apiUrl}`
  );
  if (dom.chartMessage) {
    dom.chartMessage.textContent = `Loading ${currentProductID} ${Math.round(
      granularitySeconds / 60
    )}m data...`;
    dom.chartMessage.style.display = "block";
  }
  closeWebSocket(); // Close previous connection before fetching new data

  fetch(apiUrl)
    .then((response) => {
      if (!response.ok) {
        // Try to get error details from response body
        return response
          .json()
          .catch(() => ({
            // Fallback if body isn't JSON
            error: `HTTP error ${response.status} (${response.statusText})`,
            details: response.statusText,
          }))
          .then((errData) => {
            // Throw an error object with more info
            const error = new Error(
              errData.error || `API Error ${response.status}`
            );
            error.details = errData.details || `Status: ${response.status}`;
            throw error;
          });
      }
      return response.json();
    })
    .then((data) => {
      if (!Array.isArray(data)) {
        throw new Error("Invalid data format: API response was not an array.");
      }
      if (data.length === 0) {
        console.warn(
          `No chart data returned for ${currentProductID} at ${granularitySeconds}s interval.`
        );
        updateState({ fullData: [] }); // Clear data
        if (dom.chartMessage)
          dom.chartMessage.textContent = `No data available for this interval.`;
        redrawChart(); // Redraw empty chart
        return; // Stop processing
      }

      console.log(
        `Loaded ${data.length} chart data points for ${granularitySeconds}s interval.`
      );

      // Data Format: [timestamp, low, high, open, close, volume]
      // Ensure data is sorted oldest to newest (ascending timestamp)
      let processedData = data;
      if (data.length > 1 && data[0][0] > data[data.length - 1][0]) {
        console.warn("Chart data received newest-first. Reversing array.");
        processedData = data.slice().reverse(); // Create reversed copy
      } else {
        console.log("Chart data received oldest-first (expected).");
      }

      // Update state with the new, sorted data
      updateState({ fullData: processedData });

      // Set up the initial view based on the new data and preferences
      initializeChartView(processedData); // <<< THIS NOW HANDLES PADDING

      // Hide loading message and redraw
      if (dom.chartMessage) dom.chartMessage.style.display = "none";
      requestAnimationFrame(redrawChart);

      // Reconnect WebSocket for the current product ID
      initializeWebSocket(currentProductID);
    })
    .catch((error) => {
      console.error("Chart Data Fetch Error:", error);
      if (dom.chartMessage) {
        dom.chartMessage.textContent = `Error loading chart data: ${
          error.message
        }${error.details ? ` (${error.details})` : ""}`;
        dom.chartMessage.style.display = "block";
        dom.chartMessage.style.color = "red";
      }
      updateState({ fullData: [] }); // Clear data on error
      redrawChart(); // Redraw empty chart
    });
}

// --- Main Execution ---
document.addEventListener("DOMContentLoaded", () => {
  if (!dom.checkElements()) {
    console.error("Essential DOM elements missing. Aborting initialization.");
    // Maybe display a user-facing error message here
    document.body.innerHTML =
      '<div style="padding: 20px; text-align: center; color: red; font-size: 1.2em;">Error: Application cannot start. Required HTML elements are missing. Check the console for details.</div>';
    return;
  }

  initializeTheme();
  initializeSettingsMenu();
  initializeTabs("#bottom-tab-bar", ".tab-content-area"); // This now handles order loading trigger
  initializePromptTab();
  // initializeVolumeChart(); // Initialize the volume chart module <-- COMMENTED OUT
  attachInteractionListeners();
  initializeResizer();
  checkApiStatus(); // Check backend/credentials status
  initializeBalances(); // Fetch account balances

  // Setup Granularity Controls
  if (dom.granularityControls) {
    dom.granularityControls.addEventListener("click", (event) => {
      if (event.target.tagName === "BUTTON" && !event.target.disabled) {
        const newGranularity = parseInt(event.target.dataset.granularity, 10);
        if (
          !isNaN(newGranularity) &&
          newGranularity !== state.currentGranularity
        ) {
          // Update UI
          const currentActive =
            dom.granularityControls.querySelector("button.active");
          if (currentActive) currentActive.classList.remove("active");
          event.target.classList.add("active");

          // Fetch and redraw with new granularity
          fetchAndRedraw(newGranularity);
        }
      }
    });

    // Set initial active button based on default state granularity
    const initialActiveButton = dom.granularityControls.querySelector(
      `button[data-granularity="${state.currentGranularity}"]`
    );
    if (
      initialActiveButton &&
      !initialActiveButton.classList.contains("active")
    ) {
      // Ensure only one is active if the default wasn't marked initially
      const currentActive =
        dom.granularityControls.querySelector("button.active");
      if (currentActive) currentActive.classList.remove("active");
      initialActiveButton.classList.add("active");
    } else if (!initialActiveButton) {
      console.warn(
        `No granularity button found for default: ${state.currentGranularity}`
      );
      // Optionally activate the first button as a fallback
      const firstButton = dom.granularityControls.querySelector("button");
      if (firstButton) firstButton.classList.add("active");
    }
  } else {
    console.warn(
      "Granularity controls element (#granularity-controls) not found."
    );
  }

  // Initial data fetch
  fetchAndRedraw(state.currentGranularity);

  // Add cleanup for WebSocket on page unload
  window.addEventListener("beforeunload", () => {
    closeWebSocket(); // Use the specific function, no argument needed
  });

  console.log("GeminiTrader Frontend Initialized.");
});
