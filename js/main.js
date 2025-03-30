// FILE: js/main.js

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
import { initializeVolumeChart } from "./volumeChart.js";
import { MIN_LOG_VALUE } from "./utils.js";
// Import fetchers directly
import { fetchAndStorePlotOrders } from "./orders.js";

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
    initialMinY <= 0 // Check if non-positive before potential log
  ) {
    const lastCandle = data[data.length - 1];
    const lastClose =
      lastCandle && lastCandle.length >= 5 && Number.isFinite(lastCandle[4])
        ? lastCandle[4]
        : 100;
    // Ensure fallback values are positive
    initialMinY = Math.max(MIN_LOG_VALUE, lastClose * 0.9);
    initialMaxY = Math.max(MIN_LOG_VALUE * 1.1, lastClose * 1.1);
    console.warn("[initializeChartView] Using fallback Y range.");
  }
  initialMinY = Math.max(MIN_LOG_VALUE, initialMinY); // Ensure min is positive for log
  if (initialMaxY <= initialMinY) {
    initialMaxY = initialMinY * 1.1; // Ensure max > min
  }
  let initialMinPrice, initialMaxPrice;
  if (savedLogPref) {
    const logPadding = 1 + config.Y_AXIS_LOG_PADDING_FACTOR;
    initialMinPrice = Math.max(MIN_LOG_VALUE, initialMinY / logPadding);
    initialMaxPrice = initialMaxY * logPadding;
    if (initialMaxPrice / initialMinPrice < 1.01) {
      // Prevent extreme collapse on log
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
    initialMinPrice = Math.max(0, initialMinY - linearPadding); // Clamp linear min at 0
    initialMaxPrice = initialMaxY + linearPadding;
    if (initialMaxPrice - initialMinPrice < config.MIN_PRICE_RANGE_SPAN) {
      // Prevent extreme collapse on linear
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

// --- Function to fetch ONLY candle data and update state ---
async function fetchCandleDataAndUpdateState(granularitySeconds) {
  console.log(
    `[fetchCandleDataAndUpdateState] Called with granularity: ${granularitySeconds}s`
  );
  try {
    updateState({ currentGranularity: granularitySeconds });
    const currentProductID = config.DEFAULT_PRODUCT_ID;
    const apiUrl = `http://localhost:5000/api/candles?granularity=${granularitySeconds}&product_id=${currentProductID}`;
    console.log(`[fetchCandleDataAndUpdateState] API URL: ${apiUrl}`);

    if (dom.chartMessage) {
      dom.chartMessage.textContent = `Loading ${currentProductID} ${Math.round(
        granularitySeconds / 60
      )}m data...`;
      dom.chartMessage.style.display = "block";
    }

    console.log(
      "[fetchCandleDataAndUpdateState] Closing WebSocket before fetch..."
    );
    closeWebSocket();

    console.log(
      `[fetchCandleDataAndUpdateState] Starting fetch from ${apiUrl}...`
    );
    const response = await fetch(apiUrl);
    console.log(
      `[fetchCandleDataAndUpdateState] Received response status: ${response.status}`
    );
    if (!response.ok) {
      const errData = await response.json().catch(() => ({
        error: `HTTP error ${response.status} (${response.statusText})`,
        details: response.statusText,
      }));
      const error = new Error(errData.error || `API Error ${response.status}`);
      error.details = errData.details || `Status: ${response.status}`;
      console.error(
        "[fetchCandleDataAndUpdateState] HTTP error details:",
        errData
      );
      throw error;
    }

    const data = await response.json();
    console.log("[fetchCandleDataAndUpdateState] Received JSON data.");
    if (!Array.isArray(data)) {
      throw new Error("Invalid data format: API response was not an array.");
    }

    if (data.length === 0) {
      console.warn(
        `[fetchCandleDataAndUpdateState] No chart data returned for ${currentProductID} at ${granularitySeconds}s interval.`
      );
      updateState({ fullData: [] });
      if (dom.chartMessage)
        dom.chartMessage.textContent = `No data available for this interval.`;
      return true; // Still success, but with empty data
    }

    console.log(
      `[fetchCandleDataAndUpdateState] Loaded ${data.length} data points.`
    );
    let processedData = data;
    if (data.length > 1 && data[0][0] > data[data.length - 1][0]) {
      console.warn(
        "[fetchCandleDataAndUpdateState] Data received newest-first. Reversing."
      );
      processedData = data.slice().reverse();
    }
    updateState({ fullData: processedData });
    console.log("[fetchCandleDataAndUpdateState] Updated state with fullData.");

    initializeChartView(processedData); // Set initial view based on data

    if (dom.chartMessage) dom.chartMessage.style.display = "none";

    console.log("[fetchCandleDataAndUpdateState] Initializing WebSocket...");
    initializeWebSocket(currentProductID); // Reconnect WebSocket
    return true; // Indicate success
  } catch (error) {
    console.error(
      "[fetchCandleDataAndUpdateState] Chart Data Fetch/Processing Error:",
      error
    );
    if (dom.chartMessage) {
      dom.chartMessage.textContent = `Error loading chart data: ${
        error.message
      }${error.details ? ` (${error.details})` : ""}`;
      dom.chartMessage.style.display = "block";
      dom.chartMessage.style.color = "red";
    }
    updateState({ fullData: [] }); // Clear data on error
    return false; // Indicate failure
  } finally {
    console.log("[fetchCandleDataAndUpdateState] Function end.");
  }
}

// --- Main Execution (Async) ---
document.addEventListener("DOMContentLoaded", async () => {
  console.log("[DOMContentLoaded] Starting initialization...");

  if (!dom.checkElements()) {
    console.error("[DOMContentLoaded] Aborting due to missing elements.");
    return;
  }
  console.log("[DOMContentLoaded] Element check passed.");

  try {
    // Initialize synchronous parts
    initializeTheme();
    initializeSettingsMenu();
    initializeTabs("#bottom-tab-bar", ".tab-content-area");
    initializePromptTab();
    initializeVolumeChart();
    attachInteractionListeners();
    initializeResizer();

    // Asynchronous Initializations (Fire and forget where appropriate)
    checkApiStatus();
    initializeBalances().catch((err) =>
      console.error("Error initializing balances:", err)
    );

    // Setup Granularity Controls
    if (dom.granularityControls) {
      dom.granularityControls.addEventListener("click", async (event) => {
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

            // Fetch candles FIRST, then fetch orders (which triggers redraw)
            await fetchCandleDataAndUpdateState(newGranularity);
            await fetchAndStorePlotOrders(); // This will trigger the redraw
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

    // --- Initial Data Fetch Sequence ---
    console.log(
      "[DOMContentLoaded] Performing initial data fetch (Candles & Orders)..."
    );

    // Fetch both in parallel, wait for both to finish
    const [candleResult, orderResult] = await Promise.all([
      fetchCandleDataAndUpdateState(state.currentGranularity),
      fetchAndStorePlotOrders(), // This triggers its own redraw internally now
    ]);

    console.log(
      `[DOMContentLoaded] Initial fetches complete. Candle success: ${candleResult}, Order success: ${orderResult}.`
    );

    // If the order fetch failed OR if the candle fetch failed,
    // we might need an explicit redraw here just to be safe,
    // as the redraw triggered by fetchAndStorePlotOrders might not have run.
    if (!orderResult || !candleResult) {
      console.log(
        "[DOMContentLoaded] Triggering safety redraw due to fetch failure."
      );
      requestAnimationFrame(redrawChart);
    }

    // --- WebSocket and Unload Listener ---
    window.addEventListener("beforeunload", () => {
      closeWebSocket();
    });

    console.log(
      "[DOMContentLoaded] GeminiTrader Frontend Initialization Sequence Complete."
    );
  } catch (initError) {
    console.error(
      "[DOMContentLoaded] CRITICAL ERROR during initialization:",
      initError
    );
    if (dom.chartMessage) {
      dom.chartMessage.textContent = `Initialization Error: ${initError.message}`;
      dom.chartMessage.style.display = "block";
      dom.chartMessage.style.color = "red";
    } else {
      alert(`Application Initialization Error: ${initError.message}`);
    }
  }
});
