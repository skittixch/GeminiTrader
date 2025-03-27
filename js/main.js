// js/main.js

import * as dom from "./domElements.js";
import state, { updateState } from "./state.js";
import * as config from "./config.js";
import { initializeTheme } from "./theme.js";
import { redrawChart } from "./drawing.js";
import { attachInteractionListeners } from "./interactions.js"; // Import the attach function
import {
  initializeWebSocket,
  closeWebSocket,
  updateWebSocketSubscription,
} from "./liveUpdate.js";

/**
 * Initializes the chart state based on loaded data.
 * @param {Array} data - The chart data (MUST be chronological, oldest first).
 */
function initializeChart(data) {
  // console.log("DEBUG (main.js): initializeChart called with data length:", data.length);
  updateState({ fullData: data }); // Store data assumed to be oldest first

  if (!state.fullData.length) {
    dom.chartMessage.textContent = `No data returned for ${config.DEFAULT_PRODUCT_ID} at ${state.currentGranularity}s interval.`;
    dom.chartMessage.style.display = "block";
    return;
  }

  // Calculate initial view (show the most recent data on the right)
  const initialVisibleCount = Math.min(
    config.DEFAULT_RESET_CANDLE_COUNT,
    state.fullData.length
  );
  const initialStartIndex = Math.max(
    0,
    state.fullData.length - initialVisibleCount
  );
  const initialEndIndex = state.fullData.length;

  // Calculate initial Y range
  let initialMin = Infinity,
    initialMax = -Infinity;
  for (let i = initialStartIndex; i < initialEndIndex; i++) {
    if (!state.fullData[i] || state.fullData[i].length < 5) continue;
    initialMin = Math.min(initialMin, state.fullData[i][1]); // low
    initialMax = Math.max(initialMax, state.fullData[i][2]); // high
  }
  if (initialMin === Infinity) {
    initialMin = 0;
    initialMax = 1;
  } // Fallback

  const padding = Math.max(
    config.MIN_PRICE_RANGE_SPAN * 0.1,
    (initialMax - initialMin) * config.Y_AXIS_PRICE_PADDING_FACTOR
  );
  let initialMinPrice = Math.max(0, initialMin - padding);
  let initialMaxPrice = initialMax + padding;
  if (initialMaxPrice - initialMinPrice < config.MIN_PRICE_RANGE_SPAN) {
    const mid = (initialMaxPrice + initialMinPrice) / 2;
    initialMinPrice = mid - config.MIN_PRICE_RANGE_SPAN / 2;
    initialMaxPrice = mid + config.MIN_PRICE_RANGE_SPAN / 2;
  }

  // Set initial state (load log scale and time format prefs)
  const savedLogPref = localStorage.getItem("logScalePref") === "true";
  const savedTimeFormatPref = localStorage.getItem("timeFormatPref") === "true"; // Load time pref

  updateState({
    visibleStartIndex: initialStartIndex,
    visibleEndIndex: initialEndIndex,
    minVisiblePrice: initialMinPrice,
    maxVisiblePrice: initialMaxPrice,
    isLogScale: savedLogPref,
    is12HourFormat: savedTimeFormatPref, // Set initial state
  });

  // Sync checkboxes to loaded state
  if (dom.logScaleToggle) dom.logScaleToggle.checked = savedLogPref;
  if (dom.timeFormatToggle) dom.timeFormatToggle.checked = savedTimeFormatPref; // Sync time checkbox

  // Initialize or update WebSocket AFTER data is loaded
  updateWebSocketSubscription(config.DEFAULT_PRODUCT_ID);

  dom.chartMessage.style.display = "none";
  requestAnimationFrame(redrawChart);
  // console.log("DEBUG (main.js): Initial redraw requested.");
}

/**
 * Fetches data for a specific granularity and re-initializes the chart.
 * @param {number} granularitySeconds - The desired granularity in seconds.
 */
function fetchAndRedraw(granularitySeconds) {
  updateState({ currentGranularity: granularitySeconds });

  const apiUrl = `http://localhost:5000/api/candles?granularity=${granularitySeconds}&product_id=${config.DEFAULT_PRODUCT_ID}`;

  console.log(
    `Fetching chart data for ${granularitySeconds}s interval from: ${apiUrl}`
  );
  dom.chartMessage.textContent = `Loading ${granularitySeconds}s data...`;
  dom.chartMessage.style.display = "block";

  closeWebSocket(); // Close WS before fetch

  fetch(apiUrl)
    .then((response) => {
      if (!response.ok) {
        return response
          .json()
          .catch(() => {
            throw new Error(
              `HTTP error ${response.status} (${response.statusText})`
            );
          })
          .then((errData) => {
            throw new Error(errData.error || `HTTP error ${response.status}`);
          });
      }
      return response.json();
    })
    .then((data) => {
      if (Array.isArray(data)) {
        console.log(
          `Loaded ${data.length} data points for ${granularitySeconds}s interval FROM SERVER.`
        );

        // Debugging data order check (can be removed if confident)
        if (data.length > 0) {
          const firstTimestamp = data[0][0];
          const lastTimestamp = data[data.length - 1][0];
          // console.log(`  DEBUG (main.js): First TS RECEIVED: ${firstTimestamp}`);
          // console.log(`  DEBUG (main.js): Last TS RECEIVED:  ${lastTimestamp}`);
          if (firstTimestamp > lastTimestamp) {
            console.warn(
              "  DEBUG (main.js): Data RECEIVED newest-first. Reversing."
            );
            initializeChart(data.slice().reverse());
          } else {
            console.log(
              "  DEBUG (main.js): Data RECEIVED oldest-first. Passing directly."
            );
            initializeChart(data); // Use data directly
          }
        } else {
          initializeChart([]);
        }
      } else {
        console.error("Received data is not an array:", data);
        throw new Error("API response was not an array.");
      }
    })
    .catch((error) => {
      console.error("Chart Error:", error);
      dom.chartMessage.textContent = `Error loading data: ${error.message}`;
      dom.chartMessage.style.display = "block";
    });
}

// --- Main Execution ---
document.addEventListener("DOMContentLoaded", () => {
  if (!dom.checkElements()) return;
  initializeTheme();
  attachInteractionListeners(); // Attach ALL listeners ONCE

  // Granularity Button Listener
  if (dom.granularityControls) {
    dom.granularityControls.addEventListener("click", (event) => {
      if (event.target.tagName === "BUTTON") {
        const newGranularity = parseInt(event.target.dataset.granularity, 10);
        if (
          !isNaN(newGranularity) &&
          newGranularity !== state.currentGranularity
        ) {
          const currentActive =
            dom.granularityControls.querySelector("button.active");
          if (currentActive) currentActive.classList.remove("active");
          event.target.classList.add("active");
          fetchAndRedraw(newGranularity);
        }
      }
    });
    const initialActiveButton = dom.granularityControls.querySelector(
      `button[data-granularity="${state.currentGranularity}"]`
    );
    if (
      initialActiveButton &&
      !initialActiveButton.classList.contains("active")
    ) {
      const currentActive =
        dom.granularityControls.querySelector("button.active");
      if (currentActive) currentActive.classList.remove("active");
      initialActiveButton.classList.add("active");
    }
  }

  // Initial data fetch on page load
  fetchAndRedraw(state.currentGranularity);

  // Optional: Clean up WebSocket on page unload
  window.addEventListener("beforeunload", () => {
    closeWebSocket();
  });
});
