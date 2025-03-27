// js/liveUpdate.js

import state, { updateState } from "./state.js";
import { redrawChart } from "./drawing.js";
import * as config from "./config.js";
import { getYCoordinate } from "./utils.js"; // Import shared utility
import * as dom from "./domElements.js"; // Import DOM elements

let ws = null;
let redrawTimeout = null;
const REDRAW_THROTTLE_MS = 250;

const WEBSOCKET_URL = "wss://ws-feed.exchange.coinbase.com";
let currentProductId = config.DEFAULT_PRODUCT_ID;

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
  const chartHeight = dom.chartArea.offsetHeight;
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
  console.log(
    `Attempting WS connect: ${WEBSOCKET_URL} for ${currentProductId}`
  );
  if (
    ws &&
    ws.readyState !== WebSocket.CLOSED &&
    ws.readyState !== WebSocket.CLOSING
  ) {
    ws.close(1000, "Reconnecting");
  }
  ws = null;

  ws = new WebSocket(WEBSOCKET_URL);

  ws.onopen = () => {
    console.log(`WS connected for ${currentProductId}. Subscribing...`);
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "subscribe",
          product_ids: [currentProductId],
          channels: ["ticker"],
        })
      );
    } else {
      console.warn("WS opened but not OPEN state.");
    }
  };

  ws.onmessage = (event) => {
    // console.log("WS Raw:", event.data); // Uncomment for intense debugging
    try {
      const message = JSON.parse(event.data);
      if (
        message.type === "ticker" &&
        message.product_id === currentProductId &&
        message.price
      ) {
        const price = parseFloat(message.price);
        const tickerTime = message.time
          ? new Date(message.time).getTime() / 1000
          : null;

        if (!isNaN(price) && tickerTime && state.fullData.length > 0) {
          updateState({ lastTickerPrice: price }); // Update state immediately
          updateLivePriceIndicatorUI(price); // Update UI immediately

          const lastCandleIndex = state.fullData.length - 1;
          const lastCandle = state.fullData[lastCandleIndex];
          if (!lastCandle || lastCandle.length < 6) {
            return;
          }
          const candleStartTime = lastCandle[0];
          const candleEndTime = candleStartTime + state.currentGranularity;

          if (tickerTime >= candleStartTime && tickerTime < candleEndTime) {
            let changed = false;
            if (lastCandle[4] !== price) {
              lastCandle[4] = price;
              changed = true;
            }
            if (price > lastCandle[2]) {
              lastCandle[2] = price;
              changed = true;
            }
            if (price < lastCandle[1]) {
              lastCandle[1] = price;
              changed = true;
            }
            if (changed && !redrawTimeout) {
              redrawTimeout = setTimeout(() => {
                requestAnimationFrame(redrawChart);
                redrawTimeout = null;
              }, REDRAW_THROTTLE_MS);
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
    console.log(`WS closed. Code: ${event.code}, Clean: ${event.wasClean}`);
    ws = null;
    if (redrawTimeout) {
      clearTimeout(redrawTimeout);
      redrawTimeout = null;
    }
    if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
    if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
    updateState({ lastTickerPrice: null });
    if (event.code !== 1000) {
      console.log("Attempting WS reconnect in 5s...");
      setTimeout(connectWebSocket, 5000);
    }
  };
}

export function initializeWebSocket(productId = config.DEFAULT_PRODUCT_ID) {
  currentProductId = productId;
  connectWebSocket();
}
export function closeWebSocket() {
  if (ws) {
    console.log("Closing WS manually.");
    ws.close(1000, "Client closure");
    ws = null;
  }
  if (redrawTimeout) {
    clearTimeout(redrawTimeout);
    redrawTimeout = null;
  }
  if (dom.currentPriceLabel) dom.currentPriceLabel.style.display = "none";
  if (dom.currentPriceLine) dom.currentPriceLine.style.display = "none";
  updateState({ lastTickerPrice: null });
}
export function updateWebSocketSubscription(
  newProductId = config.DEFAULT_PRODUCT_ID
) {
  if (
    newProductId !== currentProductId ||
    !ws ||
    ws.readyState === WebSocket.CLOSED ||
    ws.readyState === WebSocket.CLOSING
  ) {
    console.log(
      `Product change/WS issue. Reconnecting WS for ${newProductId}.`
    );
    currentProductId = newProductId;
    connectWebSocket();
  }
}
