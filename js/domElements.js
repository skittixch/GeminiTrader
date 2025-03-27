// js/domElements.js

// Centralized DOM element references
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
// Live Price Elements
export const currentPriceLine = document.getElementById("current-price-line");
export const currentPriceLabel = document.getElementById("current-price-label");
// Time Format Toggle
export const timeFormatToggle = document.getElementById("time-format-checkbox");
// Tooltip Element
export const chartTooltip = document.getElementById("chart-tooltip");

// Basic check for essential elements
export function checkElements() {
  // Ensure all needed elements are found
  if (
    !chartContainer ||
    !chartWrapper ||
    !chartArea ||
    !gridContainer ||
    !yAxisLabelsContainer ||
    !xAxisLabelsContainer ||
    !chartMessage ||
    !logScaleToggle ||
    !themeToggle ||
    !granularityControls ||
    !currentPriceLine ||
    !currentPriceLabel ||
    !timeFormatToggle ||
    !chartTooltip /* Check added */
  ) {
    console.error(
      "Chart initialization failed: Essential DOM elements missing."
    );
    if (chartMessage)
      chartMessage.textContent =
        "Error: Essential chart/control elements missing!";
    return false;
  }
  return true;
}
