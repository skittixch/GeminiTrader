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
import { initializeVolumeChart } from "./volumeChart.js"; // Volume chart is back
import { MIN_LOG_VALUE } from "./utils.js";

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
        throw new Error(`HTTP ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      updateApiStatusIndicator(
        data.credentials_loaded,
        data.credentials_loaded ? null : "Creds Failed"
      );
    })
    .catch((error) => {
      console.error("Error checking API status:", error);
      updateApiStatusIndicator(false, "Unavailable");
    });
}

// --- Initialize Chart View State ---
function initializeChartView(data) {
  console.log("[initializeChartView] Starting."); // Log start
  if (!data || !data.length) {
    console.warn("[initializeChartView] Skipped: No data.");
    return;
  }
  const savedLogPref = localStorage.getItem("logScalePref") === "true";
  const savedTimeFormatPref = localStorage.getItem("timeFormatPref") === "true";
  const totalDataCount = data.length;
  const initialVisibleCount = Math.min(
    config.DEFAULT_RESET_CANDLE_COUNT,
    totalDataCount
  );
  const initialStartIndex = Math.max(0, totalDataCount - initialVisibleCount);
  const initialEndIndex = totalDataCount;
  let initialMinY = Infinity,
    initialMaxY = -Infinity;
  for (let i = initialStartIndex; i < initialEndIndex; i++) {
    if (!data[i] || data[i].length < 5) continue;
    initialMinY = Math.min(initialMinY, data[i][1]); // low
    initialMaxY = Math.max(initialMaxY, data[i][2]); // high
  }
  if (
    initialMinY === Infinity ||
    initialMaxY === -Infinity ||
    initialMinY <= 0
  ) {
    const lastCandle = data[data.length - 1];
    const lastClose =
      lastCandle && lastCandle.length >= 5 && Number.isFinite(lastCandle[4])
        ? lastCandle[4]
        : 100;
    initialMinY = lastClose * 0.9;
    initialMaxY = lastClose * 1.1;
    console.warn("[initializeChartView] Using fallback Y range.");
  }
  initialMinY = Math.max(MIN_LOG_VALUE, initialMinY);
  if (initialMaxY <= initialMinY) {
    initialMaxY = initialMinY * 1.1;
  }
  let initialMinPrice, initialMaxPrice;
  if (savedLogPref) {
    const logPadding = 1 + config.Y_AXIS_LOG_PADDING_FACTOR;
    initialMinPrice = Math.max(MIN_LOG_VALUE, initialMinY / logPadding);
    initialMaxPrice = initialMaxY * logPadding;
    if (initialMaxPrice / initialMinPrice < 1.01) {
      const midLog =
        (Math.log(initialMaxPrice) + Math.log(initialMinPrice)) / 2;
      const halfRangeLog = Math.log(1.005);
      initialMinPrice = Math.max(
        MIN_LOG_VALUE,
        Math.exp(midLog - halfRangeLog)
      );
      initialMaxPrice = Math.exp(midLog + halfRangeLog);
    }
  } else {
    const linearPadding = Math.max(
      config.MIN_PRICE_RANGE_SPAN * 0.1,
      (initialMaxY - initialMinY) * config.Y_AXIS_PRICE_PADDING_FACTOR
    );
    initialMinPrice = Math.max(0, initialMinY - linearPadding);
    initialMaxPrice = initialMaxY + linearPadding;
    if (initialMaxPrice - initialMinPrice < config.MIN_PRICE_RANGE_SPAN) {
      const mid = (initialMaxPrice + initialMinPrice) / 2;
      initialMinPrice = Math.max(0, mid - config.MIN_PRICE_RANGE_SPAN / 2);
      initialMaxPrice = mid + config.MIN_PRICE_RANGE_SPAN / 2;
    }
  }
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
  console.log(
    `[initializeChartView] Finished. State updated: StartIdx=${initialStartIndex}, EndIdx=${initialEndIndex}, MinPrice=${initialMinPrice.toFixed(
      2
    )}, MaxPrice=${initialMaxPrice.toFixed(2)}, Log=${savedLogPref}`
  );
}

// --- Fetch/Redraw Chart Data ---
function fetchAndRedraw(granularitySeconds) {
  console.log(
    `[fetchAndRedraw] Called with granularity: ${granularitySeconds}s`
  ); // Log entry
  try {
    updateState({ currentGranularity: granularitySeconds });
    const currentProductID = config.DEFAULT_PRODUCT_ID;
    const apiUrl = `http://localhost:5000/api/candles?granularity=${granularitySeconds}&product_id=${currentProductID}`;
    console.log(`[fetchAndRedraw] API URL: ${apiUrl}`);

    if (dom.chartMessage) {
      dom.chartMessage.textContent = `Loading ${currentProductID} ${Math.round(
        granularitySeconds / 60
      )}m data...`;
      dom.chartMessage.style.display = "block";
      console.log("[fetchAndRedraw] Loading message displayed.");
    } else {
      console.warn("[fetchAndRedraw] Chart message element not found.");
    }

    console.log("[fetchAndRedraw] Closing WebSocket before fetch...");
    closeWebSocket();

    console.log(`[fetchAndRedraw] Starting fetch from ${apiUrl}...`);
    fetch(apiUrl)
      .then((response) => {
        console.log(
          `[fetchAndRedraw] Received response status: ${response.status}`
        );
        if (!response.ok) {
          // Try to parse error JSON, otherwise use status text
          return response
            .json()
            .catch(() => ({
              error: `HTTP error ${response.status} (${response.statusText})`,
              details: response.statusText,
            }))
            .then((errData) => {
              const error = new Error(
                errData.error || `API Error ${response.status}`
              );
              error.details = errData.details || `Status: ${response.status}`;
              console.error("[fetchAndRedraw] HTTP error details:", errData); // Log error details
              throw error; // Important to re-throw
            });
        }
        return response.json();
      })
      .then((data) => {
        console.log("[fetchAndRedraw] Received JSON data.");
        if (!Array.isArray(data)) {
          throw new Error(
            "Invalid data format: API response was not an array."
          );
        }
        if (data.length === 0) {
          console.warn(
            `[fetchAndRedraw] No chart data returned for ${currentProductID} at ${granularitySeconds}s interval.`
          );
          updateState({ fullData: [] });
          if (dom.chartMessage)
            dom.chartMessage.textContent = `No data available for this interval.`;
          requestAnimationFrame(redrawChart); // Still redraw empty chart
          console.log("[fetchAndRedraw] Redrawing empty chart (no data).");
          return;
        }

        console.log(`[fetchAndRedraw] Loaded ${data.length} data points.`);
        let processedData = data;
        if (data.length > 1 && data[0][0] > data[data.length - 1][0]) {
          console.warn(
            "[fetchAndRedraw] Data received newest-first. Reversing."
          );
          processedData = data.slice().reverse();
        }
        updateState({ fullData: processedData });
        console.log("[fetchAndRedraw] Updated state with fullData.");

        initializeChartView(processedData); // Set initial view based on data

        if (dom.chartMessage) dom.chartMessage.style.display = "none";
        console.log(
          "[fetchAndRedraw] Requesting animation frame for redraw..."
        );
        requestAnimationFrame(redrawChart); // <<< THE REDRAW CALL
        console.log("[fetchAndRedraw] Requested animation frame.");

        console.log("[fetchAndRedraw] Initializing WebSocket...");
        initializeWebSocket(currentProductID); // Reconnect WebSocket AFTER processing data
      })
      .catch((error) => {
        console.error(
          "[fetchAndRedraw] Chart Data Fetch/Processing Error:",
          error
        );
        if (dom.chartMessage) {
          dom.chartMessage.textContent = `Error loading chart data: ${
            error.message
          }${error.details ? ` (${error.details})` : ""}`;
          dom.chartMessage.style.display = "block";
          dom.chartMessage.style.color = "red";
        }
        updateState({ fullData: [] });
        requestAnimationFrame(redrawChart); // Redraw empty chart on error
      });
  } catch (err) {
    console.error("[fetchAndRedraw] Synchronous error:", err);
    if (dom.chartMessage) {
      dom.chartMessage.textContent = `Error: ${err.message}`;
      dom.chartMessage.style.display = "block";
      dom.chartMessage.style.color = "red";
    }
  }
  console.log("[fetchAndRedraw] Function end."); // Log sync function exit
}

// --- Main Execution ---
document.addEventListener("DOMContentLoaded", () => {
  console.log("[DOMContentLoaded] Starting initialization..."); // Log start

  if (!dom.checkElements()) {
    console.error("[DOMContentLoaded] Aborting due to missing elements.");
    return; // Stop if elements are missing
  }
  console.log("[DOMContentLoaded] Element check passed.");

  try {
    // Wrap initialization steps in try-catch for safety
    initializeTheme();
    console.log("[DOMContentLoaded] Theme initialized.");
    initializeSettingsMenu();
    console.log("[DOMContentLoaded] Settings menu initialized.");
    initializeTabs("#bottom-tab-bar", ".tab-content-area");
    console.log("[DOMContentLoaded] Tabs initialized.");
    initializePromptTab();
    console.log("[DOMContentLoaded] Prompt tab initialized.");
    initializeVolumeChart();
    console.log("[DOMContentLoaded] Volume chart initialized.");
    attachInteractionListeners();
    console.log("[DOMContentLoaded] Interactions attached.");
    initializeResizer();
    console.log("[DOMContentLoaded] Resizer initialized.");
    checkApiStatus(); // Async
    console.log("[DOMContentLoaded] API status check initiated.");
    initializeBalances(); // Async
    console.log("[DOMContentLoaded] Balance initialization initiated.");

    // Setup Granularity Controls
    if (dom.granularityControls) {
      dom.granularityControls.addEventListener("click", (event) => {
        if (event.target.tagName === "BUTTON" && !event.target.disabled) {
          const newGranularity = parseInt(event.target.dataset.granularity, 10);
          if (
            !isNaN(newGranularity) &&
            newGranularity !== state.currentGranularity
          ) {
            console.log(
              `[Granularity] New selection: ${newGranularity}. Fetching...`
            );
            const currentActive =
              dom.granularityControls.querySelector("button.active");
            if (currentActive) currentActive.classList.remove("active");
            event.target.classList.add("active");
            fetchAndRedraw(newGranularity); // Fetch on click
          }
        }
      });
      // Set initial active button
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
      } else if (!initialActiveButton) {
        console.warn(
          `No granularity button found for default: ${state.currentGranularity}`
        );
        const firstButton = dom.granularityControls.querySelector("button");
        if (firstButton) firstButton.classList.add("active");
      }
      console.log("[DOMContentLoaded] Granularity controls set up.");
    } else {
      console.warn(
        "[DOMContentLoaded] Granularity controls element not found."
      );
    }

    // --- Initial data fetch ---
    console.log("[DOMContentLoaded] Performing initial data fetch..."); // Log before call
    fetchAndRedraw(state.currentGranularity); // <<< THE INITIAL CALL SITE
    console.log("[DOMContentLoaded] Initial data fetch function called."); // Log right after call

    window.addEventListener("beforeunload", () => {
      closeWebSocket();
    });

    console.log(
      "[DOMContentLoaded] GeminiTrader Frontend Initialization Sequence Complete."
    ); // Final log
  } catch (initError) {
    console.error(
      "[DOMContentLoaded] CRITICAL ERROR during initialization:",
      initError
    );
    // Display a user-facing error if possible
    if (dom.chartMessage) {
      dom.chartMessage.textContent = `Initialization Error: ${initError.message}`;
      dom.chartMessage.style.display = "block";
      dom.chartMessage.style.color = "red";
    } else {
      alert(`Application Initialization Error: ${initError.message}`);
    }
  }
});
