// FILE: js/orders.js

import * as dom from "./domElements.js";
import { formatTimestamp, formatCurrency, formatQuantity } from "./utils.js";
import { updateState } from "./state.js";
import { redrawChart } from "./drawing.js"; // Keep import

// --- Fetch Function ---
async function fetchOpenOrders() {
  console.log("[fetchOpenOrders] Starting fetch...");
  const url = "http://localhost:5000/api/open_orders";
  try {
    const response = await fetch(url);
    console.log(`[fetchOpenOrders] Response status: ${response.status}`);
    const result = await response.json();

    if (!response.ok) {
      console.error(
        `[fetchOpenOrders] Error fetching open orders: ${response.status} ${response.statusText}`,
        result
      );
      throw new Error(
        result.error || `API Error (${response.status})`,
        result.details ? { cause: result.details } : undefined
      );
    }

    if (result && Array.isArray(result.orders)) {
      console.log(`[fetchOpenOrders] Received ${result.orders.length} orders.`);
      return result.orders;
    } else {
      console.warn(
        "[fetchOpenOrders] No 'orders' array found in the response:",
        result
      );
      return [];
    }
  } catch (error) {
    console.error(
      "[fetchOpenOrders] Failed to fetch or parse open orders:",
      error
    );
    if (
      dom.openOrdersContent &&
      dom.openOrdersContent.classList.contains("active")
    ) {
      dom.openOrdersContent.innerHTML = `
              <div class="pane-placeholder error">
                  <p>Error loading open orders.</p>
                  <small>${error.message} ${
        error.cause ? `(${error.cause})` : ""
      }</small>
              </div>`;
    }
    return null; // Indicate failure
  }
}

// --- Rendering Function ---
function renderOpenOrdersTable(orders) {
  // ... (implementation unchanged) ...
  if (!dom.openOrdersContent) {
    console.error("Cannot render orders: Target DOM element not found.");
    return;
  }
  dom.openOrdersContent.innerHTML = ""; // Clear previous
  if (orders === null) {
    if (!dom.openOrdersContent.innerHTML) {
      dom.openOrdersContent.innerHTML = `<div class="pane-placeholder error"><p>Error loading orders data.</p></div>`;
    }
    return;
  }
  if (!Array.isArray(orders) || orders.length === 0) {
    dom.openOrdersContent.innerHTML = `<div class="pane-placeholder"><p>No open orders found.</p></div>`;
    return;
  }
  const table = document.createElement("table");
  table.className = "orders-table";
  const thead = table.createTHead();
  const headerRow = thead.insertRow();
  const headers = [
    "Created",
    "Pair",
    "Type",
    "Side",
    "Price",
    "Size",
    "Filled",
    "Status",
  ];
  headers.forEach((text) => {
    const th = document.createElement("th");
    th.textContent = text;
    headerRow.appendChild(th);
  });
  const tbody = table.createTBody();
  orders.forEach((order) => {
    const row = tbody.insertRow();
    const type = (order.order_type || "UNKNOWN").toUpperCase();
    const side = (order.side || "UNKNOWN").toUpperCase();
    const status = (order.status || "UNKNOWN").toUpperCase();
    const pair = order.product_id || "--";
    const quoteCurrency = pair.includes("-") ? pair.split("-")[1] : "Quote";
    const baseCurrency = pair.includes("-") ? pair.split("-")[0] : "Base";
    const keyToCheck = "created_time";
    const rawCreateTimeValue = order[keyToCheck];
    let createdTime = "--";
    let dateObject = null;
    try {
      if (rawCreateTimeValue && typeof rawCreateTimeValue === "string") {
        dateObject = new Date(rawCreateTimeValue);
        if (dateObject instanceof Date && !isNaN(dateObject.getTime())) {
          createdTime = formatTimestamp(dateObject);
        } else {
          createdTime = "Invalid Time";
        }
      } else {
        createdTime = "Missing Time";
      }
    } catch (e) {
      createdTime = "Processing Error";
    }
    let price = "--";
    const orderConfig = order["order_configuration"];
    if (type === "LIMIT") {
      const limitConfig =
        orderConfig?.limit_limit_gtd || orderConfig?.limit_limit_gtc;
      const limitPriceStr = limitConfig?.limit_price;
      if (limitPriceStr) {
        const num = parseFloat(limitPriceStr);
        if (!isNaN(num)) price = formatCurrency(num);
      }
    } else if (type === "MARKET") {
      price = "Market";
    }
    let size = "--";
    if (type === "LIMIT" || type === "STOP_LIMIT") {
      const limitConfig =
        orderConfig?.limit_limit_gtd || orderConfig?.limit_limit_gtc;
      const sizeNumStr = limitConfig?.base_size;
      if (sizeNumStr) {
        const num = parseFloat(sizeNumStr);
        if (!isNaN(num)) size = `${formatQuantity(num)} ${baseCurrency}`;
      }
    } else if (type === "MARKET") {
      const marketConfig = orderConfig?.market_market_ioc;
      const baseSizeStr = marketConfig?.base_size;
      const quoteSizeStr = marketConfig?.quote_size;
      if (baseSizeStr) {
        const num = parseFloat(baseSizeStr);
        if (!isNaN(num)) size = `${formatQuantity(num)} ${baseCurrency}`;
      } else if (quoteSizeStr) {
        const num = parseFloat(quoteSizeStr);
        if (!isNaN(num)) size = `${formatCurrency(num, "")} ${quoteCurrency}`;
      }
    }
    let filledSize = formatQuantity(0);
    const filledSizeStr = order["filled_size"];
    if (filledSizeStr) {
      const num = parseFloat(filledSizeStr);
      if (!isNaN(num)) filledSize = `${formatQuantity(num)} ${baseCurrency}`;
    }
    const cells = [
      createdTime,
      pair,
      type,
      side,
      price,
      size,
      filledSize,
      status,
    ];
    cells.forEach((content, index) => {
      const cell = row.insertCell();
      cell.textContent = content;
      if (index === 3)
        cell.classList.add(
          side === "BUY"
            ? "side-buy"
            : side === "SELL"
            ? "side-sell"
            : "side-unknown"
        );
      if ([4, 5, 6].includes(index)) {
        cell.style.textAlign = "right";
        cell.style.fontFamily = "monospace";
      }
      if (index === 7) cell.classList.add(`status-${status.toLowerCase()}`);
    });
  });
  dom.openOrdersContent.appendChild(table);
}

// --- Store Plot Data Function ---
// This function ONLY updates the state. It does NOT trigger redraw.
function storeOrdersForPlotting(orders) {
  let ordersToPlot = []; // Default to empty
  if (Array.isArray(orders)) {
    ordersToPlot = orders
      .map((order) => {
        try {
          const side = (order.side || "").toUpperCase();
          if (side !== "BUY") {
            return null;
          }
          const rawTime = order["created_time"];
          let timestamp = null;
          if (rawTime && typeof rawTime === "string") {
            const dateObj = new Date(rawTime);
            if (dateObj instanceof Date && !isNaN(dateObj.getTime())) {
              timestamp = dateObj.getTime() / 1000;
            }
          }
          if (timestamp === null) return null;
          let price = null;
          const type = (order.order_type || "").toUpperCase();
          const orderConfig = order["order_configuration"];
          if (type === "LIMIT") {
            const limitConfig =
              orderConfig?.limit_limit_gtd || orderConfig?.limit_limit_gtc;
            const limitPriceStr = limitConfig?.limit_price;
            if (limitPriceStr) {
              price = parseFloat(limitPriceStr);
              if (isNaN(price)) price = null;
            }
          }
          if (price === null) return null;
          return {
            time: timestamp,
            price: price,
            side: side,
            id: order.order_id,
          };
        } catch (error) {
          console.error("Error processing order for plotting:", order, error);
          return null;
        }
      })
      .filter((order) => order !== null);
  }

  console.log(
    `[storeOrdersForPlotting] Storing ${ordersToPlot.length} BUY orders in state.`
  );
  updateState({ ordersToPlot: ordersToPlot }); // Update the state

  // *** NO redraw trigger here ***
}

// --- Function for initial fetch & store ---
export async function fetchAndStorePlotOrders() {
  console.log("[fetchAndStorePlotOrders] Fetching orders for initial plot...");
  const orders = await fetchOpenOrders();
  // Process and store data in state. Redraw will happen later in main.js
  storeOrdersForPlotting(orders);
  console.log("[fetchAndStorePlotOrders] Order data stored in state.");
  return orders !== null; // Return success based on fetch result
}

// --- Load/Display Function (for Tab Click) ---
export async function loadAndDisplayOpenOrders() {
  if (dom.openOrdersContent && !dom.openOrdersContent.hasChildNodes()) {
    dom.openOrdersContent.innerHTML = `<div class="pane-placeholder"><p>Loading open orders...</p></div>`;
  } else if (!dom.openOrdersContent) {
    console.error(
      "[loadAndDisplayOpenOrders] Cannot show loading message, target element missing."
    );
    return;
  }

  const orders = await fetchOpenOrders();

  // 1. Render the table in the "Open Orders" tab
  renderOpenOrdersTable(orders);

  // 2. Process and store/update data for plotting
  storeOrdersForPlotting(orders);

  // 3. Explicitly trigger redraw AFTER tab data is processed
  console.log("[loadAndDisplayOpenOrders] Requesting redraw after tab update.");
  requestAnimationFrame(redrawChart);
}
