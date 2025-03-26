// js/main.js

import * as dom from "./domElements.js";
import state, { updateState } from "./state.js";
import * as config from "./config.js";
import { initializeTheme } from "./theme.js";
import { redrawChart } from "./drawing.js";
import { attachInteractionListeners } from "./interactions.js";

/**
 * Initializes the chart state based on loaded data.
 * @param {Array} data - The chart data (MUST be chronological, oldest first).
 */
function initializeChart(data) {
  updateState({ fullData: data }); // Store potentially reversed data

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
  // Start index is calculated from the end of the chronological array
  const initialStartIndex = Math.max(
    0,
    state.fullData.length - initialVisibleCount
  );
  const initialEndIndex = state.fullData.length; // End at the actual end of data

  // Calculate initial Y range based on the initial visible slice
  let initialMin = Infinity,
    initialMax = -Infinity;
  for (let i = initialStartIndex; i < initialEndIndex; i++) {
    if (!state.fullData[i] || state.fullData[i].length < 5) continue;
    initialMin = Math.min(initialMin, state.fullData[i][1]); // low (index 1)
    initialMax = Math.max(initialMax, state.fullData[i][2]); // high (index 2)
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

  // Set initial state
  const savedLogPref = localStorage.getItem("logScalePref") === "true";
  updateState({
    visibleStartIndex: initialStartIndex,
    visibleEndIndex: initialEndIndex,
    minVisiblePrice: initialMinPrice,
    maxVisiblePrice: initialMaxPrice,
    isLogScale: savedLogPref,
  });
  if (dom.logScaleToggle && savedLogPref) {
    dom.logScaleToggle.checked = true;
  }

  // Listeners attached once in DOMContentLoaded
  // attachInteractionListeners();

  dom.chartMessage.style.display = "none";
  requestAnimationFrame(redrawChart);
}

/**
 * Fetches data for a specific granularity and redraws the chart.
 * @param {number} granularitySeconds - The desired granularity in seconds.
 */
function fetchAndRedraw(granularitySeconds) {
  updateState({ currentGranularity: granularitySeconds });

  // Fetch latest ~300 candles by omitting start/end
  const apiUrl = `http://localhost:5000/api/candles?granularity=${granularitySeconds}&product_id=${config.DEFAULT_PRODUCT_ID}`;

  console.log(
    `Fetching chart data for ${granularitySeconds}s interval from: ${apiUrl}`
  );
  dom.chartMessage.textContent = `Loading ${granularitySeconds}s data...`;
  dom.chartMessage.style.display = "block";

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

        // *** DEBUGGING: Check received data order ***
        if (data.length > 0) {
          const firstTimestamp = data[0][0];
          const lastTimestamp = data[data.length - 1][0];
          console.log(
            `  DEBUG (main.js): First candle time RECEIVED: ${firstTimestamp} (${new Date(
              firstTimestamp * 1000
            ).toISOString()})`
          );
          console.log(
            `  DEBUG (main.js): Last candle time RECEIVED:  ${lastTimestamp} (${new Date(
              lastTimestamp * 1000
            ).toISOString()})`
          );

          // Decide whether to reverse based on the received order
          if (firstTimestamp > lastTimestamp) {
            console.warn(
              "  DEBUG (main.js): Data RECEIVED is newest-first. Reversing before init."
            );
            initializeChart(data.slice().reverse()); // Reverse if received newest-first
          } else {
            console.log(
              "  DEBUG (main.js): Data RECEIVED is oldest-first. Passing directly."
            );
            initializeChart(data); // Pass directly if received oldest-first
          }
        } else {
          // Handle empty data case
          console.log("API returned an empty array.");
          initializeChart([]); // Initialize with empty array
        }
        // *** END DEBUGGING ***
      } else {
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
  if (!dom.checkElements()) return; // Check elements exist

  initializeTheme(); // Set theme

  attachInteractionListeners(); // Attach all interaction listeners ONCE

  // Add listener for granularity buttons
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
          fetchAndRedraw(newGranularity); // Fetch new data
        }
      }
    });
    // Ensure initial active button matches default state
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
});
