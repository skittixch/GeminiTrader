// js/liveUpdate.js

import state, { updateState, updateLatestPrice } from "./state.js"; // Import state functions
import { redrawChart } from "./drawing.js";
import { updateBalanceValuesUI } from "./balance.js"; // Import the new balance update function
import * as config from "./config.js";
import { getYCoordinate } from "./utils.js"; // Import shared utility
import * as dom from "./domElements.js"; // Import DOM elements

let ws = null;
let chartRedrawTimeout = null;
let balanceUpdateTimeout = null; // <<<--- ADDED: Timeout ID for balance updates
const CHART_REDRAW_THROTTLE_MS = 250;
const BALANCE_UPDATE_THROTTLE_MS = 1500; // <<<--- ADDED: Throttle delay for balances (e.g., 1.5 seconds)

const WEBSOCKET_URL = "wss://ws-feed.exchange.coinbase.com";
let currentProductId = config.DEFAULT_PRODUCT_ID; // Track main chart product ID

/**
 * Updates the UI for the live price indicator.
 * @param {number} price - The current price.
 */
function updateLivePriceIndicatorUI(price) {
  if (!dom.currentPriceLabel || !dom.currentPriceLine || isNaN(price)) {
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
    return;
  }
  const chartHeight = dom.chartArea?.offsetHeight; // Use optional chaining
  if (!chartHeight) return;
  const y = getYCoordinate(price, chartHeight); // Use utility

  if (y !== null && !isNaN(y)) {
    const decimals = price < 1 ? 4 : price < 100 ? 2 : price < 10000 ? 1 : 0;
    dom.currentPriceLabel.textContent = price.toFixed(decimals);
    dom.currentPriceLabel.style.top = `${y.toFixed(1)}px`;
    dom.currentPriceLine.style.top = `${y.toFixed(1)}px`;
    dom.currentPriceLabel.style.display = "block";
    dom.currentPriceLine.style.display = "block";
  } else {
    dom.currentPriceLabel.style.display = "none";
    dom.currentPriceLine.style.display = "none";
  }
}

function connectWebSocket() {
  // Use the product ID currently shown on the chart for the primary WS subscription
  const productIdToSubscribe =
    state.currentProductId || config.DEFAULT_PRODUCT_ID; // Use state or fallback
  console.log(
    `Attempting WS connect: ${WEBSOCKET_URL} for ${productIdToSubscribe}`
  );

  if (
    ws &&
    ws.readyState !== WebSocket.CLOSED &&
    ws.readyState !== WebSocket.CLOSING
  ) {
    console.log("Closing existing WebSocket connection.");
    ws.close(1000, "Reconnecting");
  }
  ws = null; // Clear previous instance

  // Clear any pending timeouts
  if (chartRedrawTimeout) clearTimeout(chartRedrawTimeout);
  if (balanceUpdateTimeout) clearTimeout(balanceUpdateTimeout);
  chartRedrawTimeout = null;
  balanceUpdateTimeout = null;

  ws = new WebSocket(WEBSOCKET_URL);

  ws.onopen = () => {
    console.log(`WS connected for ${productIdToSubscribe}. Subscribing...`);
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "subscribe",
          product_ids: [productIdToSubscribe], // Subscribe only to the main chart's product ID
          channels: ["ticker"], // Only need ticker for live updates
        })
      );
    } else {
      console.warn("WS opened but readyState is not OPEN. Cannot subscribe.");
    }
  };

  ws.onmessage = (event) => {
    // console.log("WS Raw:", event.data); // Uncomment for intense debugging
    try {
      const message = JSON.parse(event.data);

      if (message.type === "ticker" && message.price) {
        const price = parseFloat(message.price);
        const productId = message.product_id; // e.g., "BTC-USD"
        const currencyCode = productId ? productId.split("-")[0] : null; // e.g., "BTC"
        const tickerTime = message.time
          ? new Date(message.time).getTime() / 1000
          : null;

        // --- Update Global Price State ---
        if (currencyCode && !isNaN(price)) {
          updateLatestPrice(currencyCode, price); // Update the price in our global state map

          // --- Trigger Throttled Balance UI Update ---
          if (!balanceUpdateTimeout) {
            balanceUpdateTimeout = setTimeout(() => {
              updateBalanceValuesUI(); // Call the specific UI update function
              balanceUpdateTimeout = null; // Clear timeout ID
            }, BALANCE_UPDATE_THROTTLE_MS);
          }
        }

        // --- Update Chart (Only if message matches the chart's product ID) ---
        if (productId === productIdToSubscribe && !isNaN(price)) {
          updateState({ lastTickerPrice: price }); // Update chart-specific last ticker price
          updateLivePriceIndicatorUI(price); // Update indicator immediately

          // Update last candle logic (if applicable)
          if (tickerTime && state.fullData.length > 0) {
            const lastCandleIndex = state.fullData.length - 1;
            const lastCandle = state.fullData[lastCandleIndex];
            if (lastCandle && lastCandle.length >= 5) {
              // Need at least timestamp and prices
              const candleStartTime = lastCandle[0];
              const candleEndTime = candleStartTime + state.currentGranularity;

              if (tickerTime >= candleStartTime && tickerTime < candleEndTime) {
                let changed = false;
                // Update close price
                if (lastCandle[4] !== price) {
                  lastCandle[4] = price;
                  changed = true;
                }
                // Update high price
                if (price > lastCandle[2]) {
                  lastCandle[2] = price;
                  changed = true;
                }
                // Update low price
                if (price < lastCandle[1]) {
                  lastCandle[1] = price;
                  changed = true;
                }

                // Trigger throttled chart redraw if data changed
                if (changed && !chartRedrawTimeout) {
                  chartRedrawTimeout = setTimeout(() => {
                    requestAnimationFrame(redrawChart);
                    chartRedrawTimeout = null;
                  }, CHART_REDRAW_THROTTLE_MS);
                }
              }
            }
          }
        }
      } else if (message.type === "subscriptions") {
        console.log("WS Subscriptions:", message.channels);
      } else if (message.type === "error") {
        console.error("WS Error Msg:", message.message);
      }
    } catch (error) {
      console.error("Error processing WS msg:", error, event.data);
    }
  };

  ws.onerror = (error) => {
    console.error("WS Error Event:", error);
  };

  ws.onclose = (event) => {
    console.log(
      `WS closed. Code: ${event.code}, Reason: ${
        event.reason || "(No reason provided)"
      }, Clean: ${event.wasClean}`
    );
    ws = null;
    // Clear any pending timeouts on close
    if (chartRedrawTimeout) clearTimeout(chartRedrawTimeout);
    if (balanceUpdateTimeout) clearTimeout(balanceUpdateTimeout);
    chartRedrawTimeout = null;
    balanceUpdateTimeout = null;

    // Hide price indicator
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
    updateState({ lastTickerPrice: null });

    // Optional: Reconnect logic (only if not closed intentionally)
    if (event.code !== 1000) {
      // 1000 = Normal closure
      console.log("Attempting WS reconnect in 5s...");
      setTimeout(connectWebSocket, 5000);
    }
  };
}

// Initialize or Reconnect WebSocket for the main chart product
export function initializeWebSocket(productId = config.DEFAULT_PRODUCT_ID) {
  currentProductId = productId; // Update the tracked product ID
  connectWebSocket(); // Connect/reconnect using the current product ID
}

// Close WebSocket connection manually
export function closeWebSocket() {
  if (ws) {
    console.log("Closing WS manually.");
    // Clear timeouts before closing
    if (chartRedrawTimeout) clearTimeout(chartRedrawTimeout);
    if (balanceUpdateTimeout) clearTimeout(balanceUpdateTimeout);
    chartRedrawTimeout = null;
    balanceUpdateTimeout = null;
    ws.close(1000, "Client initiated closure"); // Use code 1000 for normal closure
    ws = null;
  }
  // UI cleanup might already happen in onclose, but can be done here too
  if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
  if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
  updateState({ lastTickerPrice: null });
}

// Function to update subscription if product ID changes (e.g., if user could select pairs later)
// NOTE: Currently we only subscribe to one product ID (the main chart's).
// If we needed live prices for ALL balances, we'd need to subscribe to multiple product_ids.
export function updateWebSocketSubscription(
  newProductId = config.DEFAULT_PRODUCT_ID
) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.log(`WS not open or ready, reconnecting for ${newProductId}.`);
    initializeWebSocket(newProductId); // Reconnect with the new product ID
    return;
  }

  if (newProductId !== currentProductId) {
    console.log(
      `Product change detected. Resubscribing from ${currentProductId} to ${newProductId}.`
    );
    // Unsubscribe from the old product ID
    ws.send(
      JSON.stringify({
        type: "unsubscribe",
        product_ids: [currentProductId],
        channels: ["ticker"],
      })
    );
    // Subscribe to the new product ID
    ws.send(
      JSON.stringify({
        type: "subscribe",
        product_ids: [newProductId],
        channels: ["ticker"],
      })
    );
    currentProductId = newProductId; // Update the tracked product ID
    updateState({ currentProductId: newProductId }); // Update state if needed elsewhere
  }
}
