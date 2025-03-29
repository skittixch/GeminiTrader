// js/volumeChart.js
import * as dom from "./domElements.js";
// No need to import state directly if passed into drawVolumeChart

let ctx = null;
let canvasWidth = 0;
let canvasHeight = 0;

/**
 * Initializes the volume chart canvas context.
 */
export function initializeVolumeChart() {
  if (!dom.volumeChartCanvas) {
    console.error("Volume chart canvas not found. Cannot initialize.");
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
 * @param {number} mainDrawingAreaWidth - The width of the main chart's drawing area (needed for alignment).
 */
export function drawVolumeChart(mainChartState, mainDrawingAreaWidth) {
  // Ensure context and canvas element exist before proceeding
  if (!ctx || !dom.volumeChartCanvas || !dom.volumeChartContainer) {
    // console.warn("Volume chart draw skipped: Context or Canvas element missing."); // Less noise
    return;
  }

  canvasWidth =
    dom.volumeChartContainer.offsetWidth -
    dom.volumeChartContainer.style.paddingLeft -
    dom.volumeChartContainer.style.paddingRight -
    55; // Calculate usable width (consider padding/axis)
  canvasHeight = dom.volumeChartContainer.offsetHeight; // Use container height

  // Ensure canvas has valid dimensions to draw on
  if (canvasWidth <= 0 || canvasHeight <= 0) {
    if (dom.volumeChartCanvas.width > 0 || dom.volumeChartCanvas.height > 0) {
      dom.volumeChartCanvas.width = 0;
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
    mainDrawingAreaWidth <= 0
  ) {
    return; // Nothing to draw
  }

  // --- Calculate Volume Scale ---
  let maxVisibleVolume = 0;
  for (let i = visibleStartIndex; i < visibleEndIndex; i++) {
    if (
      fullData[i] &&
      fullData[i].length > 5 &&
      typeof fullData[i][5] === "number" &&
      !isNaN(fullData[i][5])
    ) {
      maxVisibleVolume = Math.max(maxVisibleVolume, fullData[i][5]);
    }
  }

  // Avoid division by zero
  if (maxVisibleVolume <= 0) {
    return;
  }
  const volumeScaleY = canvasHeight / maxVisibleVolume; // Scale based on canvas height

  // --- Calculate Bar Width and Alignment ---
  // Use the main chart's drawing area width for alignment calculation
  const barTotalWidth = mainDrawingAreaWidth / visibleCount;
  const barWidthRatio = 0.7;
  const barWidth = Math.max(1, barTotalWidth * barWidthRatio);

  // --- Get Colors and Opacity ---
  const styles = getComputedStyle(document.documentElement);
  const colorUp = styles.getPropertyValue("--candle-up").trim();
  const colorDown = styles.getPropertyValue("--candle-down").trim();
  const barOpacity = parseFloat(
    styles.getPropertyValue("--volume-bar-opacity").trim() || 0.6
  ); // Adjusted default

  ctx.globalAlpha = barOpacity;

  // --- Draw Bars ---
  for (let i = 0; i < visibleCount; i++) {
    const dataIndex = visibleStartIndex + i;
    if (dataIndex < 0 || dataIndex >= fullData.length) continue;

    const candle = fullData[dataIndex];
    // Need open[3], close[4], volume[5]
    if (
      !candle ||
      candle.length < 6 ||
      typeof candle[3] !== "number" ||
      isNaN(candle[3]) ||
      typeof candle[4] !== "number" ||
      isNaN(candle[4]) ||
      typeof candle[5] !== "number" ||
      isNaN(candle[5]) ||
      candle[5] <= 0
    ) {
      continue; // Skip invalid or zero volume candles
    }

    const open = candle[3];
    const close = candle[4];
    const volume = candle[5];
    const barHeight = Math.max(1, volume * volumeScaleY);
    const isUp = close >= open;

    // Calculate X position based on the main chart's drawing area width
    const barCenterX = (i + 0.5) * barTotalWidth;
    const barLeft = barCenterX - barWidth / 2;

    ctx.fillStyle = isUp ? colorUp : colorDown;

    const yPos = Math.max(0, canvasHeight - barHeight);
    const drawHeight = Math.min(barHeight, canvasHeight - yPos); // Prevent drawing past bottom
    ctx.fillRect(barLeft, yPos, barWidth, drawHeight);
  }

  ctx.globalAlpha = 1.0;

  // Optional: Draw Y-Axis Labels for Volume (Simple Example)
  if (dom.volumeYAxisLabels) {
    dom.volumeYAxisLabels.innerHTML = ""; // Clear old labels
    const maxVolFormatted = formatVolumeLabel(maxVisibleVolume);
    const midVolFormatted = formatVolumeLabel(maxVisibleVolume / 2);

    // Max Label (Top)
    const maxLabel = document.createElement("div");
    maxLabel.className = "axis-label y-axis-label";
    maxLabel.style.top = "2px"; // Position near top
    maxLabel.textContent = maxVolFormatted;
    dom.volumeYAxisLabels.appendChild(maxLabel);

    // Mid Label (Approx Middle)
    const midLabel = document.createElement("div");
    midLabel.className = "axis-label y-axis-label";
    midLabel.style.top = `${(canvasHeight / 2).toFixed(0)}px`;
    midLabel.style.transform = "translateY(-50%)"; // Center vertically
    midLabel.textContent = midVolFormatted;
    dom.volumeYAxisLabels.appendChild(midLabel);

    // Zero label is implicitly at the bottom
  }
}

// Helper to format volume labels nicely (e.g., 1.23M, 543K)
function formatVolumeLabel(volume) {
  if (volume >= 1e6) {
    return (volume / 1e6).toFixed(2) + "M";
  } else if (volume >= 1e3) {
    return (volume / 1e3).toFixed(1) + "K";
  } else {
    return volume.toFixed(0); // Show whole numbers for small volumes
  }
}
