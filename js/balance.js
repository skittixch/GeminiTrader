// js/balance.js

import * as dom from "./domElements.js";
import { formatCurrency, formatQuantity } from "./utils.js";
import { BALANCE_DUST_THRESHOLD_USD } from "./config.js"; // Import threshold
import state, { updateLatestPrice } from "./state.js"; // Import state and price update function

const DUST_SUMMARY_CLASS = "balance-list-dust-summary";
const DUST_ITEM_CLASS = "balance-list-dust-item";
const DUST_VISIBLE_CLASS = "dust-visible"; // Class added to UL when dust is shown

/**
 * Fetches the current ticker price for a single product ID from the backend.
 * @param {string} productId (e.g., "ETH-USD")
 * @returns {Promise<number|null>} Resolves with the price number or null.
 */
async function fetchTickerPrice(productId) {
  if (!productId) return null;
  const url = `http://localhost:5000/api/ticker?product_id=${productId}`;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      console.warn(
        `Ticker fetch failed for ${productId}: ${response.status} ${response.statusText}`
      );
      try {
        const errorData = await response.json();
        console.warn(
          ` -> API Error: ${errorData?.message || response.statusText}`
        );
      } catch {}
      return null;
    }
    const data = await response.json();
    const price = parseFloat(data?.price);
    return !isNaN(price) ? price : null;
  } catch (error) {
    console.error(`Network error fetching ticker for ${productId}:`, error);
    return null;
  }
}

/**
 * Renders a single balance list item.
 * Stores currency and quantity in data attributes for later updates.
 * @param {object} acc - The processed account object (with totalBalance, usdValue).
 * @param {boolean} isDustItem - Flag to add the dust item class.
 */
function renderBalanceItem(acc, isDustItem = false) {
  const { currency, totalBalance, usdValue } = acc;

  const li = document.createElement("li");
  // Store currency and quantity for easy access during live updates
  li.dataset.currency = currency;
  li.dataset.quantity = totalBalance.toString(); // Store as string
  if (isDustItem) {
    li.classList.add(DUST_ITEM_CLASS);
  }

  const codeSpan = document.createElement("span");
  codeSpan.className = "asset-code";
  codeSpan.textContent = currency;

  const qtySpan = document.createElement("span");
  qtySpan.className = "asset-qty";
  qtySpan.textContent = formatQuantity(totalBalance);

  const valueSpan = document.createElement("span");
  valueSpan.className = "asset-value";
  if (usdValue !== null && Number.isFinite(usdValue)) {
    // Check finiteness
    valueSpan.textContent = formatCurrency(usdValue);
  } else {
    valueSpan.textContent = `(?.?? USD)`;
  }

  li.appendChild(codeSpan);
  li.appendChild(qtySpan);
  li.appendChild(valueSpan);
  dom.balanceList.appendChild(li);
}

/**
 * Updates the balance pane HTML with fetched account data and prices.
 * Partitions into Main/Dust, sorts, and renders with collapsible dust section.
 * @param {Array} accounts - Array of account objects from the API.
 * @param {Map<string, number>} prices - Map of currency codes (UPPERCASE) to their initial USD prices.
 */
function updateBalancePaneUI(accounts, prices) {
  if (!dom.balanceList || !dom.balanceTotalValue || !dom.balancePartialNotice) {
    console.error("Balance pane DOM elements not found for UI update.");
    return;
  }
  dom.balanceList.innerHTML = ""; // Clear previous list items
  dom.balanceList.classList.remove(DUST_VISIBLE_CLASS);
  let totalUsdValue = 0;
  let partialTotal = false;

  if (!Array.isArray(accounts)) {
    dom.balanceList.innerHTML =
      '<li class="error">Invalid account data structure received.</li>';
    console.error("updateBalancePaneUI expected an array, got:", accounts);
    accounts = [];
  }

  const ZERO_THRESHOLD = 1e-9;
  const mainBalances = [];
  const dustBalances = [];

  // 1. Map accounts, calculate values, and partition into main/dust
  accounts.forEach((acc) => {
    const currency = acc?.currency?.toUpperCase();
    const availableString = acc?.available_balance?.value ?? "0";
    const holdString = acc?.hold?.value ?? "0";
    const availableBalance = parseFloat(availableString);
    const holdBalance = parseFloat(holdString);

    if (!currency || isNaN(availableBalance) || isNaN(holdBalance)) {
      return; // Skip invalid account data
    }

    const totalBalance = availableBalance + holdBalance;

    if (Math.abs(totalBalance) < ZERO_THRESHOLD) {
      return; // Skip zero balance
    }

    let usdValue = null;
    if (currency === "USD") {
      usdValue = totalBalance;
    } else if (currency === "USDT" || currency === "USDC") {
      usdValue = totalBalance * 1.0;
    } else {
      const price = prices.get(currency); // Use initial prices map here
      if (price !== undefined && price !== null && Number.isFinite(price)) {
        usdValue = totalBalance * price;
      } else {
        partialTotal = true;
      }
    }

    // Accumulate total value (do this *before* partitioning)
    if (usdValue !== null && Number.isFinite(usdValue)) {
      totalUsdValue += usdValue;
    }

    const processedAcc = {
      ...acc,
      currency,
      totalBalance,
      usdValue, // Initial USD value
    };

    // Partition based on USD value
    if (
      usdValue !== null &&
      Number.isFinite(usdValue) &&
      usdValue < BALANCE_DUST_THRESHOLD_USD
    ) {
      dustBalances.push(processedAcc);
    } else {
      mainBalances.push(processedAcc);
    }
  });

  // 2. Sort the main balances
  mainBalances.sort((a, b) => {
    if (a.currency === "USD") return -1;
    if (b.currency === "USD") return 1;
    const valueA = a.usdValue ?? -Infinity;
    const valueB = b.usdValue ?? -Infinity;
    if (valueB !== valueA) return valueB - valueA; // Desc value
    return (a.currency || "").localeCompare(b.currency || ""); // Asc currency
  });

  // 3. Sort the dust balances
  dustBalances.sort((a, b) => {
    return (a.currency || "").localeCompare(b.currency || ""); // Asc currency
  });

  // 4. Render Main Balances
  mainBalances.forEach((acc) => renderBalanceItem(acc, false));

  // 5. Render Dust Section
  if (dustBalances.length > 0) {
    const dustLi = document.createElement("li");
    dustLi.classList.add(DUST_SUMMARY_CLASS);
    dustLi.innerHTML = `
          <span class="asset-code">Dust</span>
          <span class="asset-qty">(${dustBalances.length} items)</span>
          <span class="asset-value">(click to show)</span> <!-- Initial text -->
      `;
    dom.balanceList.appendChild(dustLi);
    dustBalances.forEach((acc) => renderBalanceItem(acc, true));
  }

  // --- Final UI Updates ---
  if (dom.balanceList.children.length === 0) {
    dom.balanceList.innerHTML = '<li class="info">No balances found.</li>';
  } else if (mainBalances.length === 0 && dustBalances.length === 0) {
    dom.balanceList.innerHTML =
      '<li class="info">No non-zero balances found.</li>';
  }

  dom.balanceTotalValue.textContent = formatCurrency(totalUsdValue);
  dom.balancePartialNotice.style.display = partialTotal ? "inline" : "none";
}

/**
 * Updates ONLY the USD values and total in the already rendered balance list.
 * Reads quantities and currencies from data attributes.
 * Uses latest prices from the global state.
 */
export function updateBalanceValuesUI() {
  if (!dom.balanceList || !dom.balanceTotalValue || !dom.balancePartialNotice) {
    // console.warn("Cannot update balance values: UI elements missing.");
    return;
  }
  // console.log("Updating balance values..."); // Debug

  let newTotalUsdValue = 0;
  let partialTotal = false; // Re-evaluate if any prices are missing now

  const listItems = dom.balanceList.querySelectorAll(
    "li[data-currency][data-quantity]"
  );

  listItems.forEach((li) => {
    const currency = li.dataset.currency;
    const quantity = parseFloat(li.dataset.quantity);
    const valueSpan = li.querySelector(".asset-value");

    if (!currency || isNaN(quantity) || !valueSpan) {
      console.warn(
        "Skipping update for list item, missing data or element:",
        li
      );
      return; // Skip malformed items
    }

    let usdValue = null;
    if (currency === "USD") {
      usdValue = quantity;
    } else if (currency === "USDT" || currency === "USDC") {
      usdValue = quantity * 1.0;
    } else {
      // Get the LATEST price from global state
      const price = state.latestPrices.get(currency);

      if (price !== undefined && price !== null && Number.isFinite(price)) {
        usdValue = quantity * price;
      } else {
        // console.log(`No valid price found in state for ${currency}`); // Debug
        partialTotal = true; // If price is missing now, total is partial
      }
    }

    // Update the value span text
    if (usdValue !== null && Number.isFinite(usdValue)) {
      valueSpan.textContent = formatCurrency(usdValue);
      newTotalUsdValue += usdValue; // Add to the new total
    } else {
      valueSpan.textContent = `(?.?? USD)`; // Keep placeholder if value unknown
    }

    // Re-check dust partitioning? (More complex - maybe skip for now)
    // If an item *becomes* dust or *stops being* dust due to price changes,
    // it would require moving the element in the DOM or re-rendering.
    // For simplicity, let's just update values in place for now.
    // Re-partitioning could be added later if needed.
  });

  // Update the total value display
  dom.balanceTotalValue.textContent = formatCurrency(newTotalUsdValue);
  dom.balancePartialNotice.style.display = partialTotal ? "inline" : "none";
}

/**
 * Attaches the click listener for the dust category toggle using event delegation.
 */
function attachDustToggleListener() {
  if (!dom.balanceList) return;
  dom.balanceList.removeEventListener("click", handleDustClick);
  dom.balanceList.addEventListener("click", handleDustClick);
  console.log("Dust toggle listener attached.");
}

/**
 * Handles clicks on the balance list, specifically toggling dust visibility.
 * @param {Event} event - The click event object.
 */
function handleDustClick(event) {
  const summaryItem = event.target.closest(`.${DUST_SUMMARY_CLASS}`);
  if (summaryItem) {
    dom.balanceList.classList.toggle(DUST_VISIBLE_CLASS);
    // console.log("Dust visibility toggled:", dom.balanceList.classList.contains(DUST_VISIBLE_CLASS));
    const valueSpan = summaryItem.querySelector(".asset-value");
    if (valueSpan) {
      valueSpan.textContent = dom.balanceList.classList.contains(
        DUST_VISIBLE_CLASS
      )
        ? "(click to hide)"
        : "(click to show)";
    }
  }
}

/**
 * Main function to orchestrate fetching account data AND necessary ticker prices,
 * then updating the balance pane UI. Exported for use in main.js.
 */
export async function initializeBalances() {
  console.log("Initializing balances...");
  if (dom.balanceList)
    dom.balanceList.innerHTML = '<li class="loading">Loading balances...</li>';
  if (dom.balanceTotalValue) dom.balanceTotalValue.textContent = "--.--";
  if (dom.balancePartialNotice) dom.balancePartialNotice.style.display = "none";

  attachDustToggleListener();

  try {
    // 1. Fetch Accounts
    const accountsResponse = await fetch("http://localhost:5000/api/accounts");
    const accountsResult = await (async () => {
      const status = accountsResponse.status;
      try {
        const data = await accountsResponse.json();
        if (data && data.accounts && Array.isArray(data.accounts)) {
          return {
            ok: accountsResponse.ok,
            status: status,
            data: data.accounts,
          };
        } else if (Array.isArray(data)) {
          return { ok: accountsResponse.ok, status: status, data: data };
        } else {
          throw new Error("API response does not contain an accounts array.");
        }
      } catch (e) {
        console.error(
          "Failed to parse accounts response or invalid format:",
          e
        );
        let textResponse = "(Could not read text)";
        try {
          textResponse = await accountsResponse.text();
        } catch {}
        throw new Error(
          `Received non-JSON or invalid response (Status: ${status}). Body: ${textResponse}`
        );
      }
    })();

    if (!accountsResult.ok) {
      throw new Error(
        accountsResult.data?.error ||
          `Account API Error (${accountsResult.status})`
      );
    }
    const accounts = accountsResult.data;

    // 2. Identify non-zero crypto assets needing prices
    const cryptoAssetsToPrice = new Set();
    const ZERO_THRESHOLD = 1e-9;
    const stablecoins = new Set(["USD", "USDT", "USDC", "EUR", "GBP"]);

    accounts.forEach((acc) => {
      const currency = acc?.currency?.toUpperCase();
      const availableString = acc?.available_balance?.value ?? "0";
      const holdString = acc?.hold?.value ?? "0";
      const availableBalance = parseFloat(availableString);
      const holdBalance = parseFloat(holdString);

      if (isNaN(availableBalance) || isNaN(holdBalance)) return;
      const totalBalance = availableBalance + holdBalance;

      const isPricableCrypto = currency && !stablecoins.has(currency);
      const isNonZero = Math.abs(totalBalance) >= ZERO_THRESHOLD;

      if (isPricableCrypto && isNonZero) {
        cryptoAssetsToPrice.add(currency);
      }
    });
    console.log("Assets to Fetch Prices For:", Array.from(cryptoAssetsToPrice));

    // 3. Fetch prices concurrently
    const pricePromises = Array.from(cryptoAssetsToPrice).map((currency) => {
      const productId = `${currency}-USD`;
      return fetchTickerPrice(productId).then((price) => ({ currency, price }));
    });
    const priceResults = await Promise.all(pricePromises);

    // 4. Create Price Map AND Update Global State
    const initialPrices = new Map();
    priceResults.forEach((result) => {
      if (result.price !== null && Number.isFinite(result.price)) {
        initialPrices.set(result.currency, result.price);
        // ---> Populate global state with initial prices <---
        updateLatestPrice(result.currency, result.price);
      }
    });
    // Add stablecoins to global state map (price is 1.0)
    updateLatestPrice("USD", 1.0);
    updateLatestPrice("USDC", 1.0);
    updateLatestPrice("USDT", 1.0);
    // Add others if needed

    console.log("Fetched Valid Prices:", Object.fromEntries(initialPrices));
    console.log(
      "Initial Global Prices State:",
      Object.fromEntries(state.latestPrices)
    );

    // 5. Update UI using the initial prices map
    updateBalancePaneUI(accounts, initialPrices);
  } catch (error) {
    console.error("Error initializing balances:", error);
    if (dom.balanceList)
      dom.balanceList.innerHTML = `<li class="error">Error loading balances: ${error.message}</li>`;
    if (dom.balanceTotalValue)
      dom.balanceTotalValue.textContent = formatCurrency(0);
    if (dom.balancePartialNotice)
      dom.balancePartialNotice.style.display = "none";
  }
}
