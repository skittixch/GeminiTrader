// js/domElements.js

// Layout Structure
export const mainLayout = document.querySelector(".main-layout");
export const headerArea = document.querySelector(".header-area");
export const contentArea = document.getElementById("content-area");
export const chartPane = document.getElementById("chart-pane");
export const resizer = document.getElementById("resizer");
export const bottomPane = document.getElementById("bottom-pane");

// Chart Specific
export const chartContainer = document.getElementById("chart-container");
export const chartWrapper = chartContainer?.querySelector(".chart-wrapper");
export const chartArea = document.getElementById("chart-area");
export const gridContainer = document.getElementById("grid-container");
export const yAxisLabelsContainer = document.getElementById("y-axis-labels");
export const xAxisLabelsContainer = document.getElementById("x-axis-labels");
export const chartMessage = document.getElementById("chart-message");
export const currentPriceLine = document.getElementById("current-price-line");
export const currentPriceLabel = document.getElementById("current-price-label");
export const chartTooltip = document.getElementById("chart-tooltip");
export const crosshairLineX = document.getElementById("crosshair-line-x");
export const crosshairLabelY = document.getElementById("crosshair-label-y");

// Volume/Depth elements REMOVED

// Controls (Header / Settings Menu)
export const headerControls = document.querySelector(".header-controls");
export const granularityControls = document.getElementById(
  "granularity-controls"
);
export const settingsButton = document.getElementById("settings-button");
export const settingsDropdown = document.getElementById("settings-dropdown");

// Switches (Now potentially inside dropdown)
export const themeToggle = document.getElementById("theme-checkbox");
export const logScaleToggle = document.getElementById("log-scale-checkbox");
export const timeFormatToggle = document.getElementById("time-format-checkbox");

// Other UI
export const apiStatusIndicator = document.getElementById(
  "api-status-indicator"
);

// Bottom Pane Tabs
export const bottomTabBar = document.getElementById("bottom-tab-bar");
export const positionsContent = document.getElementById("positions-content");
export const openOrdersContent = document.getElementById("open-orders-content"); // <<< Keep this reference
export const orderHistoryContent = document.getElementById(
  "order-history-content"
);
export const promptContent = document.getElementById("prompt-content");
export const promptTextarea = document.getElementById("prompt-textarea");

// Balance Pane Specific (Now inside positionsContent)
export const balanceList = document.getElementById("balance-list");
export const balanceTotalValue = document.getElementById("total-usd-value");
export const balancePartialNotice = document.getElementById(
  "total-usd-partial-notice"
);

// Exported map for checkElements to get names
const elementMap = {
  mainLayout,
  headerArea,
  contentArea,
  chartPane,
  resizer,
  bottomPane, // Layout
  chartContainer,
  chartWrapper,
  chartArea,
  gridContainer,
  yAxisLabelsContainer, // Chart Core
  xAxisLabelsContainer,
  chartMessage,
  currentPriceLine,
  currentPriceLabel,
  chartTooltip,
  crosshairLineX,
  crosshairLabelY,
  // volumeChartContainer, volumeChartCanvas, // REMOVED
  headerControls,
  granularityControls,
  settingsButton,
  settingsDropdown, // Header/Settings
  themeToggle,
  logScaleToggle,
  timeFormatToggle, // Switches
  apiStatusIndicator, // Other UI
  bottomTabBar,
  positionsContent,
  openOrdersContent, // <<< Ensure this is included
  orderHistoryContent,
  promptContent, // Tabs
  promptTextarea, // Prompt Input
  balanceList,
  balanceTotalValue,
  balancePartialNotice, // Balance List (nested)
};

export function checkElements() {
  const missingElements = Object.entries(elementMap)
    .filter(([name, el]) => !el)
    .map(([name]) => name);

  if (missingElements.length > 0) {
    const missingNames = missingElements.join(", ");
    console.error(
      `Initialization failed: Essential DOM elements missing: ${missingNames}`
    );
    if (chartMessage) {
      chartMessage.textContent = `Error: Missing DOM elements! (${missingNames})`;
      chartMessage.style.display = "block";
      chartMessage.style.color = "red";
    } else {
      alert(
        `Error: Critical DOM elements missing: ${missingNames}! Cannot initialize app. Check console.`
      );
    }
    return false;
  }
  console.log("All essential DOM elements found.");
  return true;
}
