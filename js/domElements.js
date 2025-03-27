// js/domElements.js

export const chartContainer = document.getElementById("chart-container");
export const chartWrapper = chartContainer?.querySelector(".chart-wrapper");
export const chartArea = document.getElementById("chart-area");
export const gridContainer = document.getElementById("grid-container");
export const yAxisLabelsContainer = document.getElementById("y-axis-labels");
export const xAxisLabelsContainer = document.getElementById("x-axis-labels");
export const chartMessage = document.getElementById("chart-message");
export const themeToggle = document.getElementById("theme-checkbox");
export const logScaleToggle = document.getElementById("log-scale-checkbox");
export const granularityControls = document.getElementById(
  "granularity-controls"
);
export const currentPriceLine = document.getElementById("current-price-line");
export const currentPriceLabel = document.getElementById("current-price-label");
export const timeFormatToggle = document.getElementById("time-format-checkbox");
export const chartTooltip = document.getElementById("chart-tooltip");
export const crosshairLineX = document.getElementById("crosshair-line-x");
export const crosshairLabelY = document.getElementById("crosshair-label-y");
export const apiStatusIndicator = document.getElementById(
  "api-status-indicator"
);

// *** START: Re-add Balance Pane Elements ***
export const balancePane = document.getElementById("balance-pane");
export const balanceList = document.getElementById("balance-list");
export const balanceTotalValue = document.getElementById("total-usd-value");
export const balancePartialNotice = document.getElementById(
  "total-usd-partial-notice"
);
// export const refreshBalancesBtn = document.getElementById('refresh-balances-btn'); // Keep commented if no button yet
// *** END: Balance Pane Elements ***

// REMOVED: btcBalanceValue reference

export function checkElements() {
  const requiredElements = [
    chartContainer,
    chartWrapper,
    chartArea,
    gridContainer,
    yAxisLabelsContainer,
    xAxisLabelsContainer,
    chartMessage,
    themeToggle,
    logScaleToggle,
    granularityControls,
    currentPriceLine,
    currentPriceLabel,
    timeFormatToggle,
    chartTooltip,
    crosshairLineX,
    crosshairLabelY,
    apiStatusIndicator,
    // Add new checks
    balancePane,
    balanceList,
    balanceTotalValue,
    balancePartialNotice,
  ];

  if (requiredElements.some((el) => !el)) {
    console.error(
      "Chart initialization failed: Essential DOM elements missing."
    );
    const missing = requiredElements
      .filter((el) => !el)
      .map((el) => el?.id || "Unknown");
    if (chartMessage) {
      chartMessage.textContent = `Error: Missing DOM elements! (${missing.join(
        ", "
      )})`;
      chartMessage.style.display = "block";
    }
    return false;
  }
  return true;
}
