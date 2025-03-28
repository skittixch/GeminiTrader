// js/volumeChart.js
import * as dom from "./domElements.js";
import state from "./state.js"; // Need state for visible range and data

let ctx = null;
let canvasWidth = 0;
let canvasHeight = 0;

/**
 * Initializes the volume chart canvas context.
 */
export function initializeVolumeChart() {
  if (!dom.volumeChartCanvas) {
    console.error("Volume chart canvas not found.");
    return;
  }
  ctx = dom.volumeChartCanvas.getContext("2d");
  if (!ctx) {
    console.error("Failed to get 2D context for volume chart canvas.");
    return;
  }
  console.log("Volume chart initialized.");
}

/**
 * Draws the volume bars based on the main chart's visible data.
 *
 * @param {object} mainChartState - The main chart's state (including fullData, visibleStartIndex, visibleEndIndex).
 * @param {number} mainChartWidth - The width of the main chart drawing area (needed for alignment).
 */
export function drawVolumeChart(mainChartState, mainChartWidth) {
  // Ensure context and canvas element exist before proceeding
  if (!ctx || !dom.volumeChartCanvas) {
    console.warn(
      "Volume chart draw skipped: Context or Canvas element missing."
    );
    return;
  }

  canvasWidth = dom.volumeChartCanvas.offsetWidth;
  canvasHeight = dom.volumeChartCanvas.offsetHeight;

  // Ensure canvas has valid dimensions to draw on
  if (canvasWidth <= 0 || canvasHeight <= 0) {
    // console.warn("Volume chart draw skipped: Invalid canvas dimensions."); // Optional log
    // Ensure canvas is clear if dimensions are invalid
    if (dom.volumeChartCanvas.width > 0 || dom.volumeChartCanvas.height > 0) {
      dom.volumeChartCanvas.width = 0; // Explicitly clear if needed
      dom.volumeChartCanvas.height = 0;
    }
    return;
  }

  // Ensure canvas internal resolution matches display size
  if (
    dom.volumeChartCanvas.width !== canvasWidth ||
    dom.volumeChartCanvas.height !== canvasHeight
  ) {
    dom.volumeChartCanvas.width = canvasWidth;
    dom.volumeChartCanvas.height = canvasHeight;
    // console.log("Resized volume canvas:", canvasWidth, canvasHeight); // Optional log
  }

  // Clear the canvas for redrawing
  ctx.clearRect(0, 0, canvasWidth, canvasHeight);

  const { fullData, visibleStartIndex, visibleEndIndex } = mainChartState;
  const visibleCount = visibleEndIndex - visibleStartIndex;

  // Ensure there is data and visible candles to process
  if (
    !fullData ||
    visibleCount <= 0 ||
    fullData.length === 0 ||
    mainChartWidth <= 0
  ) {
    // console.warn("Volume chart draw skipped: No visible data or invalid main chart width."); // Optional log
    return; // Nothing to draw
  }

  // --- Calculate Volume Scale ---
  let maxVisibleVolume = 0;
  for (let i = visibleStartIndex; i < visibleEndIndex; i++) {
    // Robust check: ensure array exists, has enough elements, and volume is a number
    if (
      fullData[i] &&
      fullData[i].length > 5 &&
      typeof fullData[i][5] === "number" &&
      !isNaN(fullData[i][5])
    ) {
      maxVisibleVolume = Math.max(maxVisibleVolume, fullData[i][5]);
    }
  }

  // Avoid division by zero if max volume is zero or less (shouldn't be <0, but safe check)
  if (maxVisibleVolume <= 0) {
    // console.warn("Volume chart draw skipped: Max visible volume is zero or negative."); // Optional log
    return;
  }

  // Calculate scale factor AFTER confirming maxVisibleVolume > 0
  const volumeScaleY = canvasHeight / maxVisibleVolume;

  // --- Calculate Bar Width and Alignment ---
  const barTotalWidth = mainChartWidth / visibleCount;
  const barWidthRatio = 0.7;
  const barWidth = Math.max(1, barTotalWidth * barWidthRatio);

  // --- Get Colors and Opacity ---
  const styles = getComputedStyle(document.documentElement);
  const colorUp = styles.getPropertyValue("--candle-up").trim();
  const colorDown = styles.getPropertyValue("--candle-down").trim();
  const barOpacity = parseFloat(
    styles.getPropertyValue("--volume-bar-opacity").trim() || 0.7
  );

  // Apply opacity once if using globalAlpha
  ctx.globalAlpha = barOpacity;

  // --- Draw Bars ---
  for (let i = 0; i < visibleCount; i++) {
    const dataIndex = visibleStartIndex + i;
    // Basic bounds check (already somewhat covered by loop condition)
    if (dataIndex < 0 || dataIndex >= fullData.length) continue;

    const candle = fullData[dataIndex];
    // More robust check for essential data points needed for coloring and volume
    if (
      !candle ||
      candle.length < 6 ||
      typeof candle[3] !== "number" ||
      isNaN(candle[3]) || // open
      typeof candle[4] !== "number" ||
      isNaN(candle[4]) || // close
      typeof candle[5] !== "number" ||
      isNaN(candle[5])
    ) {
      // volume
      // console.warn(`Skipping volume bar at index ${dataIndex}: Invalid candle data`, candle); // Debug log
      continue;
    }

    const open = candle[3];
    const close = candle[4];
    const volume = candle[5];

    // Skip drawing if volume is essentially zero
    if (volume <= 1e-9) continue;

    // Calculate height, ensuring a minimum visual height of 1px
    const barHeight = Math.max(1, volume * volumeScaleY);
    const isUp = close >= open;

    // Calculate X position
    const barCenterX = (i + 0.5) * barTotalWidth;
    const barLeft = barCenterX - barWidth / 2;

    // Set fill color
    ctx.fillStyle = isUp ? colorUp : colorDown;

    // Draw the rectangle
    // Prevent drawing outside canvas bounds (Y coordinate)
    const yPos = Math.max(0, canvasHeight - barHeight); // Ensure Y doesn't go negative
    const drawHeight = Math.min(barHeight, canvasHeight); // Ensure height doesn't exceed canvas height
    ctx.fillRect(barLeft, yPos, barWidth, drawHeight);
  }

  // Reset global alpha after drawing all bars
  ctx.globalAlpha = 1.0;
}
