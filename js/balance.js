// js/balance.js

import * as dom from "./domElements.js";
import { formatCurrency, formatQuantity } from "./utils.js";

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
 * Updates the balance pane HTML with fetched account data and prices.
 * @param {Array} accounts - Array of account objects from the API.
 * @param {Map<string, number>} prices - Map of currency codes (UPPERCASE) to their USD prices.
 */
function updateBalancePaneUI(accounts, prices) {
  if (!dom.balanceList || !dom.balanceTotalValue || !dom.balancePartialNotice) {
    console.error("Balance pane DOM elements not found for UI update.");
    return;
  }
  dom.balanceList.innerHTML = ""; // Clear previous list items
  let totalUsdValue = 0;
  let partialTotal = false;

  if (!Array.isArray(accounts)) {
    dom.balanceList.innerHTML =
      '<li class="error">Invalid account data structure.</li>';
    accounts = [];
  }

  // Sort accounts: USD first, then others alphabetically
  accounts.sort((a, b) => {
    const currA = a?.currency?.toUpperCase();
    const currB = b?.currency?.toUpperCase();
    if (currA === "USD") return -1;
    if (currB === "USD") return 1;
    return (currA || "").localeCompare(currB || "");
  });

  accounts.forEach((acc) => {
    // *** Use AVAILABLE_BALANCE string ***
    const balanceString = acc?.available_balance?.value;
    const currency = acc?.currency?.toUpperCase();
    const balance = parseFloat(balanceString);

    // Skip if invalid data or effectively zero balance (handle potential small floating point values)
    const ZERO_THRESHOLD = 1e-9; // Define a small threshold for zero
    if (!currency || isNaN(balance) || Math.abs(balance) < ZERO_THRESHOLD) {
      return;
    }

    const li = document.createElement("li");
    const codeSpan = document.createElement("span");
    codeSpan.className = "asset-code";
    codeSpan.textContent = currency;
    const qtySpan = document.createElement("span");
    qtySpan.className = "asset-qty";
    qtySpan.textContent = formatQuantity(balance);
    const valueSpan = document.createElement("span");
    valueSpan.className = "asset-value";

    let usdValue = null;
    if (currency === "USD") {
      usdValue = balance;
    } else if (currency === "USDT") {
      usdValue = balance * 1.0; // Assume USDT price is always $1.00
    } else {
      const price = prices.get(currency);
      if (price) {
        usdValue = balance * price;
      } else {
        partialTotal = true; // Price missing or fetch failed
        console.warn(`Price unavailable for ${currency}.`);
      }
    }

    if (usdValue !== null) {
      totalUsdValue += usdValue;
      valueSpan.textContent = formatCurrency(usdValue);
    } else {
      valueSpan.textContent = `(?.?? ${currency})`; // Value unknown
    }

    li.appendChild(codeSpan);
    li.appendChild(qtySpan);
    li.appendChild(valueSpan);
    dom.balanceList.appendChild(li);
  });

  if (dom.balanceList.children.length === 0) {
    dom.balanceList.innerHTML =
      '<li class="info">No non-zero balances found.</li>';
  }

  dom.balanceTotalValue.textContent = formatCurrency(totalUsdValue);
  dom.balancePartialNotice.style.display = partialTotal ? "inline" : "none";
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

  try {
    // 1. Fetch Accounts
    const accountsResponse = await fetch("http://localhost:5000/api/accounts");
    const accountsResult = await (async () => {
      const status = accountsResponse.status;
      try {
        const data = await accountsResponse.json();
        return { ok: accountsResponse.ok, status: status, data: data };
      } catch {
        throw new Error(`Received non-JSON response (Status: ${status})`);
      }
    })();
    if (!accountsResult.ok) {
      throw new Error(
        accountsResult.data?.error ||
          `Account API Error (${accountsResult.status})`
      );
    }
    if (!accountsResult.data || !Array.isArray(accountsResult.data.accounts)) {
      throw new Error("Invalid account data format");
    }
    const accounts = accountsResult.data.accounts;

    console.log("Raw Accounts Received:", JSON.stringify(accounts, null, 2));

    // 2. Identify non-zero crypto assets needing prices (EXCLUDING USDT)
    const cryptoAssetsToPrice = new Set();
    console.log("--- Filtering accounts for pricing ---");
    const ZERO_THRESHOLD = 1e-9; // Define a small threshold for zero
    accounts.forEach((acc, index) => {
      const currency = acc?.currency?.toUpperCase();
      // *** Use AVAILABLE_BALANCE string for filtering ***
      const balanceString = acc?.available_balance?.value;
      const balance = parseFloat(balanceString);

      // Original log
      console.log(
        `Account ${index}: Currency=${currency}, BalanceString='${balanceString}', ParsedBalance=${balance}`
      );

      // Detailed condition check log
      const isCrypto = currency && currency !== "USD" && currency !== "USDT";
      const isNumber = !isNaN(balance);
      // Use threshold for non-zero check
      const isNonZero = Math.abs(balance) >= ZERO_THRESHOLD;
      console.log(
        `  -> Checks: isCrypto=${isCrypto}, isNumber=${isNumber}, isNonZero=${isNonZero} (Threshold: ${ZERO_THRESHOLD})`
      );

      if (isCrypto && isNumber && isNonZero) {
        // Use the parsed 'balance' and threshold
        console.log(`  -> Adding ${currency} to price list.`);
        cryptoAssetsToPrice.add(currency);
      } else {
        if (!currency) console.log(`  -> Skipping: Missing currency.`);
        else if (!isCrypto) console.log(`  -> Skipping: Is USD or USDT.`);
        else if (!isNumber)
          console.log(`  -> Skipping: Parsed balance is NaN.`);
        else if (!isNonZero)
          console.log(`  -> Skipping: Parsed balance is effectively zero.`);
      }
    });
    console.log("--- Finished filtering ---");
    console.log("Assets to Fetch Prices For:", Array.from(cryptoAssetsToPrice));

    // 3. Fetch prices concurrently
    const pricePromises = Array.from(cryptoAssetsToPrice).map((currency) => {
      const productId = `${currency}-USD`;
      return fetchTickerPrice(productId).then((price) => ({ currency, price }));
    });
    const priceResults = await Promise.all(pricePromises);

    // 4. Create Price Map
    const prices = new Map();
    priceResults.forEach((result) => {
      if (result.price !== null) {
        prices.set(result.currency, result.price);
      }
    });
    console.log("Fetched Prices:", Object.fromEntries(prices));

    // 5. Update UI
    updateBalancePaneUI(accounts, prices); // Call the UI update function
  } catch (error) {
    console.error("Error initializing balances:", error);
    if (dom.balanceList)
      dom.balanceList.innerHTML = `<li class="error">Error: ${error.message}</li>`;
    if (dom.balanceTotalValue)
      dom.balanceTotalValue.textContent = formatCurrency(0);
    if (dom.balancePartialNotice)
      dom.balancePartialNotice.style.display = "none";
  }
}
