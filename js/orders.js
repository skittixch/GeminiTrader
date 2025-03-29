// js/orders.js

import * as dom from "./domElements.js";
import { formatTimestamp, formatCurrency, formatQuantity } from "./utils.js"; // Keep imports

// --- <<<< RESTORE fetchOpenOrders FUNCTION >>>> ---
/**
 * Fetches open orders from the backend API.
 * @returns {Promise<Array|null>} A promise that resolves with an array of order objects or null if an error occurs.
 */
async function fetchOpenOrders() {
  console.log("[fetchOpenOrders] Starting fetch..."); // Add simple log
  const url = "http://localhost:5000/api/open_orders";
  try {
    const response = await fetch(url);
    console.log(`[fetchOpenOrders] Response status: ${response.status}`); // Log status
    const result = await response.json(); // Read JSON regardless of status

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
      return []; // Return empty array if structure is unexpected but response was ok
    }
  } catch (error) {
    console.error(
      "[fetchOpenOrders] Failed to fetch or parse open orders:",
      error
    );
    // Display error in the UI - Keep this part
    if (dom.openOrdersContent) {
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
// --- <<<< END OF RESTORED FUNCTION >>>> ---

/**
 * Renders the fetched open orders into the UI.
 * @param {Array|null} orders - An array of order objects, or null if fetching failed.
 */
function renderOpenOrders(orders) {
  if (!dom.openOrdersContent) {
    console.error("Cannot render orders: Target DOM element not found.");
    return;
  }

  dom.openOrdersContent.innerHTML = ""; // Clear previous

  if (orders === null) return; // Error handled by fetch

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
  orders.forEach((order, orderIndex) => {
    // Add index for logging clarity
    const row = tbody.insertRow();

    // --- More Detailed Logging ---
    console.log(
      `%c--- Processing Order ${orderIndex} (ID: ${
        order.order_id || "N/A"
      }) ---`,
      "color: blue; font-weight: bold;"
    );
    console.log(`  Available keys on 'order' object:`, Object.keys(order)); // Log all keys
    const keyToCheck = "created_time"; // Define the key we expect
    const hasKeyDirect = order.hasOwnProperty(keyToCheck); // Check direct ownership
    const valueViaDot = order.create_time; // Try dot notation again for comparison
    const valueViaBracket = order[keyToCheck]; // <<<< Access using bracket notation

    console.log(
      `  Does order directly have property "${keyToCheck}"? ${hasKeyDirect}`
    );
    console.log(
      `  Value via order.create_time:`,
      valueViaDot,
      `(Type: ${typeof valueViaDot})`
    );
    console.log(
      `  Value via order["${keyToCheck}"]:`,
      valueViaBracket,
      `(Type: ${typeof valueViaBracket})`
    ); // <<<< Log bracket access result
    // --- End Detailed Logging ---

    const type = (order.order_type || "UNKNOWN").toUpperCase();
    const side = (order.side || "UNKNOWN").toUpperCase();
    const status = (order.status || "UNKNOWN").toUpperCase();
    const pair = order.product_id || "--";
    const quoteCurrency = pair.includes("-") ? pair.split("-")[1] : "Quote";
    const baseCurrency = pair.includes("-") ? pair.split("-")[0] : "Base";

    // --- Use Bracket Notation for Time Handling ---
    const rawCreateTimeValue = order[keyToCheck]; // <<<< Use bracket notation result
    let createdTime = "--"; // Default
    let dateObject = null;
    try {
      // Check the value obtained via bracket notation
      if (rawCreateTimeValue && typeof rawCreateTimeValue === "string") {
        dateObject = new Date(rawCreateTimeValue);
        if (dateObject instanceof Date && !isNaN(dateObject.getTime())) {
          createdTime = formatTimestamp(dateObject); // Pass Date object
        } else {
          console.warn(
            `Invalid Date from create_time string: "${rawCreateTimeValue}"`
          );
          createdTime = "Invalid Time"; // Show specific error if parsing failed
        }
      } else if (rawCreateTimeValue) {
        console.warn(
          `create_time exists but is not a string:`,
          rawCreateTimeValue
        );
        createdTime = "Format Error";
      } else {
        // This case should now match the log output if valueViaBracket was undefined/null
        createdTime = "Missing Time";
      }
    } catch (e) {
      console.error(`Error processing create_time "${rawCreateTimeValue}":`, e);
      createdTime = "Processing Error";
    }
    console.log(`  Final createdTime for cell = "${createdTime}"`);
    // --- End Time Handling ---

    // --- Other Fields (Using bracket notation for consistency/safety) ---
    let price = "--";
    const orderConfig = order["order_configuration"]; // Use brackets
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
    // Add STOP_LIMIT handling if needed

    let size = "--";
    if (type === "LIMIT" || type === "STOP_LIMIT") {
      const limitConfig =
        orderConfig?.limit_limit_gtd ||
        orderConfig?.limit_limit_gtc; /* || stop limit path */
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
    const filledSizeStr = order["filled_size"]; // Use bracket notation
    if (filledSizeStr) {
      const num = parseFloat(filledSizeStr);
      if (!isNaN(num)) filledSize = `${formatQuantity(num)} ${baseCurrency}`;
    }
    // --- End Other Fields ---

    // Add cells to row
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
      cell.textContent = content; // Stick with textContent for now
      // Apply Styling Classes
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

/**
 * Initializes the open orders functionality (called by tabs.js).
 */
export async function loadAndDisplayOpenOrders() {
  // Ensure target element exists before showing loading
  if (dom.openOrdersContent) {
    dom.openOrdersContent.innerHTML = `<div class="pane-placeholder"><p>Loading open orders...</p></div>`;
  } else {
    console.error(
      "[loadAndDisplayOpenOrders] Cannot show loading message, target element missing."
    );
    return; // Don't proceed if the container isn't there
  }
  // Now call fetchOpenOrders (which should be defined above)
  const orders = await fetchOpenOrders();
  // Render, even if orders is null (renderOpenOrders handles it)
  renderOpenOrders(orders);
}
