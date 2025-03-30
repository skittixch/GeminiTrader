// FILE: js/tabs.js
import { loadAndDisplayOpenOrders } from "./orders.js"; // Keep the import

/**
 * Initializes tab switching functionality for a given container.
 * @param {string} tabBarSelector - CSS selector for the tab bar container (e.g., '#bottom-tab-bar').
 * @param {string} contentAreaSelector - CSS selector for the area containing the tab content panes (e.g., '.tab-content-area').
 */
export function initializeTabs(tabBarSelector, contentAreaSelector) {
  const tabBar = document.querySelector(tabBarSelector);
  const contentArea = document.querySelector(contentAreaSelector);

  if (!tabBar) {
    console.error(
      `Tab initialization failed: Tab bar not found with selector "${tabBarSelector}"`
    );
    return;
  }
  if (!contentArea) {
    console.error(
      `Tab initialization failed: Content area not found with selector "${contentAreaSelector}"`
    );
    return;
  }

  const tabButtons = tabBar.querySelectorAll(".tab-button");
  const contentPanes = contentArea.querySelectorAll(".tab-content");

  if (tabButtons.length === 0 || contentPanes.length === 0) {
    console.warn(
      "Tab initialization: No tab buttons or content panes found within the specified containers."
    );
    return;
  }

  // Add click listener to the tab bar (event delegation)
  tabBar.addEventListener("click", (event) => {
    const clickedButton = event.target.closest(".tab-button");
    if (!clickedButton) {
      return; // Click was not on a button
    }

    // Prevent unnecessary work if clicking the already active tab
    if (clickedButton.classList.contains("active")) {
      return;
    }

    const targetId = clickedButton.dataset.target;
    if (!targetId) {
      console.warn("Clicked tab button is missing 'data-target' attribute.");
      return;
    }

    const targetPane = contentArea.querySelector(`#${targetId}`);
    if (!targetPane) {
      console.warn(`Target content pane with ID "${targetId}" not found.`);
      return;
    }

    // --- Deactivate currently active elements ---
    const currentActiveButton = tabBar.querySelector(".tab-button.active");
    const currentActivePane = contentArea.querySelector(".tab-content.active");

    if (currentActiveButton) {
      currentActiveButton.classList.remove("active");
    }
    if (currentActivePane) {
      currentActivePane.classList.remove("active");
    }

    // --- Activate the new elements ---
    clickedButton.classList.add("active");
    targetPane.classList.add("active");

    console.log(`Switched tab to: ${targetId}`);

    // --- Trigger data refresh logic when specific tabs become active ---
    if (targetId === "open-orders-content") {
      // Fetch/update orders when tab is clicked (good for refresh)
      // loadAndDisplayOpenOrders will handle rendering the table
      // and updating the plot state, then trigger a redraw.
      console.log("Open Orders tab activated, refreshing data...");
      loadAndDisplayOpenOrders(); // Keep this call for refresh
    }
    // Example for future:
    // else if (targetId === 'order-history-content') {
    //   loadAndDisplayOrderHistory();
    // }
    // else if (targetId === 'positions-content') {
    // Optional: Re-fetch balances if needed
    // initializeBalances();
    // }
  });

  console.log(`Tabs initialized for container: ${tabBarSelector}`);

  // No initial load trigger from here - main.js handles that
}
