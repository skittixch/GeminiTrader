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
// Import the balance initialization function from the new module
import { initializeBalances } from "./balance.js";
// Utilities are likely still needed by other parts, keep the import if so
// import { formatCurrency, formatQuantity } from './utils.js';

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
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      return response.json();
    })
    .then((data) => {
      updateApiStatusIndicator(data.credentials_loaded);
    })
    .catch((error) => {
      console.error("Error checking API status:", error);
      updateApiStatusIndicator(false, "Unavailable");
    });
}

// --- Balance Pane functions moved to balance.js ---
// REMOVED: fetchTickerPrice, updateBalancePaneUI, fetchAccountDataAndPrices

// --- Initialize Chart, Fetch/Redraw Chart Data functions ---
// These functions remain unchanged for now
function initializeChart(data) {
  updateState({ fullData: data });
  if (!state.fullData.length) {
    dom.chartMessage.textContent = `No data returned.`;
    dom.chartMessage.style.display = "block";
    return;
  }
  const initialVisibleCount = Math.min(
    config.DEFAULT_RESET_CANDLE_COUNT,
    state.fullData.length
  );
  const initialStartIndex = Math.max(
    0,
    state.fullData.length - initialVisibleCount
  );
  const initialEndIndex = state.fullData.length;
  let initialMin = Infinity,
    initialMax = -Infinity;
  for (let i = initialStartIndex; i < initialEndIndex; i++) {
    if (!state.fullData[i] || state.fullData[i].length < 5) continue;
    initialMin = Math.min(initialMin, state.fullData[i][1]);
    initialMax = Math.max(initialMax, state.fullData[i][2]);
  }
  if (initialMin === Infinity) {
    initialMin = 0;
    initialMax = 1;
  }
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
    initialMinPrice = Math.max(0, initialMinPrice);
  }
  const savedLogPref = localStorage.getItem("logScalePref") === "true";
  const savedTimeFormatPref = localStorage.getItem("timeFormatPref") === "true";
  updateState({
    visibleStartIndex: initialStartIndex,
    visibleEndIndex: initialEndIndex,
    minVisiblePrice: initialMinPrice,
    maxVisiblePrice: initialMaxPrice,
    isLogScale: savedLogPref,
    is12HourFormat: savedTimeFormatPref,
  });
  if (dom.logScaleToggle) dom.logScaleToggle.checked = savedLogPref;
  if (dom.timeFormatToggle) dom.timeFormatToggle.checked = savedTimeFormatPref;
  updateWebSocketSubscription(config.DEFAULT_PRODUCT_ID);
  dom.chartMessage.style.display = "none";
  requestAnimationFrame(redrawChart);
}
function fetchAndRedraw(granularitySeconds) {
  updateState({ currentGranularity: granularitySeconds });
  const currentProductID = config.DEFAULT_PRODUCT_ID;
  const apiUrl = `http://localhost:5000/api/candles?granularity=${granularitySeconds}&product_id=${currentProductID}`;
  console.log(
    `Fetching chart data for ${currentProductID} at ${granularitySeconds}s interval from: ${apiUrl}`
  );
  dom.chartMessage.textContent = `Loading ${currentProductID} ${granularitySeconds}s data...`;
  dom.chartMessage.style.display = "block";
  closeWebSocket();
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
      if (!Array.isArray(data)) {
        throw new Error("API response was not an array.");
      }
      console.log(
        `Loaded ${data.length} chart data points for ${granularitySeconds}s interval.`
      );
      if (data.length > 0 && data[0][0] > data[data.length - 1][0]) {
        console.warn("Chart data RECEIVED newest-first. Reversing.");
        initializeChart(data.slice().reverse());
      } else {
        console.log("Chart data RECEIVED oldest-first. Passing directly.");
        initializeChart(data);
      }
    })
    .catch((error) => {
      console.error("Chart Error:", error);
      dom.chartMessage.textContent = `Error loading chart data: ${error.message}`;
      dom.chartMessage.style.display = "block";
    });
}

// --- Main Execution ---
document.addEventListener("DOMContentLoaded", () => {
  if (!dom.checkElements()) return;
  initializeTheme();
  attachInteractionListeners();

  checkApiStatus(); // Check backend credential status
  initializeBalances(); // Initialize balances using the new module

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
  // Initial chart data fetch
  fetchAndRedraw(state.currentGranularity);
  // WS Cleanup
  window.addEventListener("beforeunload", () => {
    closeWebSocket();
  });
});
