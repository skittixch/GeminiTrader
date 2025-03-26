// Encapsulate chart logic in an IIFE
(function () {
  "use strict"; // Enable strict mode

  // --- Theme Handling (Run this early) ---
  const themeToggle = document.getElementById("theme-checkbox");
  const userPrefersDark =
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const currentTheme = localStorage.getItem("theme");
  let theme = "light"; // Default

  if (currentTheme) {
    theme = currentTheme;
  } else if (userPrefersDark) {
    theme = "dark";
  }

  document.documentElement.setAttribute("data-theme", theme);
  if (themeToggle && theme === "dark") {
    themeToggle.checked = true;
  }

  if (themeToggle) {
    themeToggle.addEventListener("change", function () {
      if (this.checked) {
        document.documentElement.setAttribute("data-theme", "dark");
        localStorage.setItem("theme", "dark");
      } else {
        document.documentElement.setAttribute("data-theme", "light");
        localStorage.setItem("theme", "light");
      }
      // Redrawing isn't strictly necessary as CSS handles colors, but uncomment if needed
      // requestAnimationFrame(redrawChart);
    });
  }

  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", (e) => {
      if (!localStorage.getItem("theme")) {
        const newTheme = e.matches ? "dark" : "light";
        document.documentElement.setAttribute("data-theme", newTheme);
        if (themeToggle) themeToggle.checked = newTheme === "dark";
      }
    });
  // --- End Theme Handling ---

  // --- DOM Elements ---
  const chartContainer = document.getElementById("chart-container");
  const chartWrapper = chartContainer?.querySelector(".chart-wrapper");
  const chartArea = document.getElementById("chart-area");
  const gridContainer = document.getElementById("grid-container");
  const yAxisLabelsContainer = document.getElementById("y-axis-labels");
  const xAxisLabelsContainer = document.getElementById("x-axis-labels");
  const chartMessage = document.getElementById("chart-message");

  if (
    !chartContainer ||
    !chartWrapper ||
    !chartArea ||
    !gridContainer ||
    !yAxisLabelsContainer ||
    !xAxisLabelsContainer ||
    !chartMessage
  ) {
    console.error("Chart initialization failed: DOM elements missing.");
    if (chartMessage)
      chartMessage.textContent = "Error: Chart elements missing!";
    return;
  }

  // --- Chart State ---
  let fullData = [];
  let visibleStartIndex = 0;
  let visibleEndIndex = 0;
  let minVisiblePrice = 0;
  let maxVisiblePrice = 1;
  let isPanning = false;
  let isDraggingYAxis = false;
  let isDraggingXAxis = false; // Scaling X
  let panStartX = 0;
  let panStartY = 0;
  let panStartVisibleIndex = 0;
  let panStartVisibleCount = 0;
  let panStartMinPrice = 0;
  let panStartMaxPrice = 0;
  let lastDrawTime = 0;

  // --- Constants ---
  const ZOOM_FACTOR_X = 0.1;
  const ZOOM_FACTOR_Y = 0.1;
  const MIN_VISIBLE_CANDLES = 5;
  const DEFAULT_RESET_CANDLE_COUNT = 100;
  const MIN_PRICE_RANGE_SPAN = 0.1;
  const Y_AXIS_PRICE_PADDING_FACTOR = 0.05;
  const Y_AXIS_DRAG_SENSITIVITY = 2.0;
  const X_AXIS_DRAG_SENSITIVITY = 2.0;
  const MOUSE_MOVE_THROTTLE = 16;
  const DEBOUNCE_DELAY = 100;

  // --- Utility Functions ---
  function calculateNiceStep(range, maxTicks) {
    if (range <= 0 || maxTicks <= 0) return 1;
    const roughStep = range / maxTicks;
    const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep)));
    const residual = roughStep / magnitude;
    let niceStep;
    if (residual > 5) niceStep = 10 * magnitude;
    else if (residual > 2) niceStep = 5 * magnitude;
    else if (residual > 1) niceStep = 2 * magnitude;
    else niceStep = magnitude;
    return Math.max(niceStep, Number.EPSILON * 10);
  }

  function formatTimestamp(timestamp) {
    const date = new Date(timestamp * 1000);
    const hours = date.getHours().toString().padStart(2, "0");
    const minutes = date.getMinutes().toString().padStart(2, "0");
    return `${hours}:${minutes}`;
  }

  // --- Main Drawing Function ---
  function redrawChart() {
    if (!fullData || !chartArea.offsetHeight || !chartArea.offsetWidth) {
      return;
    }
    const chartHeight = chartArea.offsetHeight;
    const chartWidth = chartArea.offsetWidth;
    const priceRange = maxVisiblePrice - minVisiblePrice;
    const visibleCount = visibleEndIndex - visibleStartIndex;

    if (priceRange <= 0 || visibleCount <= 0) {
      chartArea.innerHTML = "";
      gridContainer.innerHTML = "";
      yAxisLabelsContainer.innerHTML = "";
      xAxisLabelsContainer.innerHTML = "";
      return;
    }

    chartArea.innerHTML = "";
    gridContainer.innerHTML = "";
    yAxisLabelsContainer.innerHTML = "";
    xAxisLabelsContainer.innerHTML = "";

    const scaleY = chartHeight / priceRange;
    const totalCandleWidthRatio = 0.85;
    const candleWidth = Math.max(
      1,
      (chartWidth / visibleCount) * totalCandleWidthRatio
    );
    const candleMargin = Math.max(
      0.5,
      ((chartWidth / visibleCount) * (1 - totalCandleWidthRatio)) / 2
    );
    const candleTotalWidth = candleWidth + candleMargin * 2;

    // Draw Gridlines and Axis Labels
    try {
      const yTickDensity = Math.max(3, Math.round(chartHeight / 40));
      const yTicks = calculateNiceStep(priceRange, yTickDensity);
      const firstYTick =
        yTicks > Number.EPSILON
          ? Math.ceil(minVisiblePrice / yTicks) * yTicks
          : minVisiblePrice;
      for (
        let price = firstYTick;
        price <= maxVisiblePrice + yTicks * 0.1;
        price += yTicks
      ) {
        if (yTicks <= Number.EPSILON || price > maxVisiblePrice + priceRange)
          break;
        const y = chartHeight - (price - minVisiblePrice) * scaleY;
        if (y >= -chartHeight && y <= chartHeight * 2) {
          const hLine = document.createElement("div");
          hLine.className = "grid-line horizontal";
          hLine.style.top = `${y.toFixed(1)}px`;
          gridContainer.appendChild(hLine);
          if (y >= -5 && y <= chartHeight + 5) {
            const yLabel = document.createElement("div");
            yLabel.className = "axis-label y-axis-label";
            yLabel.style.top = `${y.toFixed(1)}px`;
            const decimals =
              priceRange < 10 ? (price < 1 ? 4 : 2) : price < 100 ? 1 : 0;
            yLabel.textContent = price.toFixed(decimals);
            yAxisLabelsContainer.appendChild(yLabel);
          }
        }
        if (price + yTicks <= price) break;
      }

      const xTickDensity = Math.max(3, Math.round(chartWidth / 70));
      const xTicks = Math.max(1, calculateNiceStep(visibleCount, xTickDensity));
      for (let i = 0; i < visibleCount; i++) {
        const dataIndex = visibleStartIndex + i;
        if (dataIndex >= 0 && dataIndex < fullData.length) {
          const isTick = (i + Math.floor(xTicks / 4)) % xTicks === 0;
          if (i === 0 || isTick || (xTicks === 1 && i % 5 === 0)) {
            const candleData = fullData[dataIndex];
            if (!candleData) continue;
            const timestamp = candleData[0];
            const x = i * candleTotalWidth + candleTotalWidth / 2;
            if (x >= -candleTotalWidth && x <= chartWidth + candleTotalWidth) {
              const xLabel = document.createElement("div");
              xLabel.className = "axis-label x-axis-label";
              xLabel.style.left = `${x.toFixed(1)}px`;
              xLabel.textContent = formatTimestamp(timestamp);
              xAxisLabelsContainer.appendChild(xLabel);
            }
          }
        }
      }
    } catch (e) {
      console.error("Error drawing axes/grid:", e);
    }

    // Draw Candles
    try {
      for (let i = 0; i < visibleCount; i++) {
        const dataIndex = visibleStartIndex + i;
        if (dataIndex >= 0 && dataIndex < fullData.length) {
          const candle = fullData[dataIndex];
          if (!candle || candle.length < 5) continue;
          const [timestamp, open, high, low, close] = candle;
          const wickHighY = chartHeight - (high - minVisiblePrice) * scaleY;
          const wickLowY = chartHeight - (low - minVisiblePrice) * scaleY;
          const bodyTopY =
            chartHeight - (Math.max(open, close) - minVisiblePrice) * scaleY;
          const bodyBottomY =
            chartHeight - (Math.min(open, close) - minVisiblePrice) * scaleY;
          const wickHeight = Math.max(1, wickLowY - wickHighY);
          const bodyHeight = Math.max(1, bodyBottomY - bodyTopY);
          const isUp = close >= open;

          const candleElement = document.createElement("div");
          candleElement.className = "candle";
          candleElement.style.width = `${candleWidth}px`;
          candleElement.style.marginLeft = `${
            i === 0 ? candleMargin : candleMargin * 2
          }px`;

          const wickElement = document.createElement("div");
          wickElement.className = "wick";
          wickElement.style.top = `${wickHighY.toFixed(1)}px`;
          wickElement.style.height = `${wickHeight.toFixed(1)}px`;

          const bodyElement = document.createElement("div");
          bodyElement.className = `body ${isUp ? "color-up" : "color-down"}`; // CSS handles color via these classes
          bodyElement.style.top = `${bodyTopY.toFixed(1)}px`;
          bodyElement.style.height = `${bodyHeight.toFixed(1)}px`;

          candleElement.appendChild(wickElement);
          candleElement.appendChild(bodyElement);
          chartArea.appendChild(candleElement);
        }
      }
    } catch (e) {
      console.error("Error drawing candles:", e);
    }
  }

  // --- Event Handlers ---
  function handleZoom(event) {
    event.preventDefault();
    const chartRect = chartArea.getBoundingClientRect();
    const mouseX = event.clientX - chartRect.left;
    const mouseY = event.clientY - chartRect.top;
    const chartHeight = chartArea.offsetHeight;
    const chartWidth = chartArea.offsetWidth;
    if (!chartHeight || !chartWidth) return;

    const priceRange = maxVisiblePrice - minVisiblePrice;
    if (priceRange <= 0) return;

    // Y-Axis Zoom
    const priceAtCursor = maxVisiblePrice - (mouseY / chartHeight) * priceRange;
    const zoomAmountY =
      event.deltaY < 0 ? 1 - ZOOM_FACTOR_Y : 1 + ZOOM_FACTOR_Y;
    let newMinVisiblePrice =
      priceAtCursor - (priceAtCursor - minVisiblePrice) * zoomAmountY;
    let newMaxVisiblePrice =
      priceAtCursor + (maxVisiblePrice - priceAtCursor) * zoomAmountY;
    if (newMaxVisiblePrice - newMinVisiblePrice < MIN_PRICE_RANGE_SPAN) {
      const mid = (newMaxVisiblePrice + newMinVisiblePrice) / 2;
      newMinVisiblePrice = mid - MIN_PRICE_RANGE_SPAN / 2;
      newMaxVisiblePrice = mid + MIN_PRICE_RANGE_SPAN / 2;
    }

    // X-Axis Zoom
    const currentVisibleCount = visibleEndIndex - visibleStartIndex;
    if (currentVisibleCount <= 0) return;
    const indexAtCursor =
      visibleStartIndex + (mouseX / chartWidth) * currentVisibleCount;
    const zoomAmountX =
      event.deltaY < 0 ? 1 - ZOOM_FACTOR_X : 1 + ZOOM_FACTOR_X;
    let newVisibleCount = Math.round(currentVisibleCount * zoomAmountX);
    newVisibleCount = Math.max(
      MIN_VISIBLE_CANDLES,
      Math.min(newVisibleCount, fullData.length * 2)
    );
    let newStartIndex = Math.round(
      indexAtCursor - (mouseX / chartWidth) * newVisibleCount
    );
    let newEndIndex = newStartIndex + newVisibleCount;

    // No clamping for infinite scroll
    visibleStartIndex = newStartIndex;
    visibleEndIndex = newEndIndex;
    minVisiblePrice = newMinVisiblePrice;
    maxVisiblePrice = newMaxVisiblePrice;

    requestAnimationFrame(redrawChart);
  }

  function handleMouseDownChart(event) {
    isPanning = true;
    isDraggingYAxis = false;
    isDraggingXAxis = false;
    panStartX = event.clientX;
    panStartY = event.clientY;
    panStartVisibleIndex = visibleStartIndex;
    panStartMinPrice = minVisiblePrice;
    panStartMaxPrice = maxVisiblePrice;
    panStartVisibleCount = visibleEndIndex - visibleStartIndex;
    chartContainer.classList.add("panning");
  }

  function handleMouseDownYAxis(event) {
    event.stopPropagation();
    isDraggingYAxis = true;
    isPanning = false;
    isDraggingXAxis = false;
    panStartY = event.clientY;
    panStartMinPrice = minVisiblePrice;
    panStartMaxPrice = maxVisiblePrice;
  }

  function handleMouseDownXAxis(event) {
    event.stopPropagation();
    isDraggingXAxis = true;
    isPanning = false;
    isDraggingYAxis = false;
    panStartX = event.clientX;
    panStartVisibleIndex = visibleStartIndex;
    panStartVisibleCount = visibleEndIndex - visibleStartIndex;
  }

  function handleMouseMove(event) {
    if (!isPanning && !isDraggingYAxis && !isDraggingXAxis) return;

    const now = Date.now();
    if (now - lastDrawTime < MOUSE_MOVE_THROTTLE) return;

    let needsRedraw = false;

    if (isDraggingYAxis) {
      const deltaY = event.clientY - panStartY;
      const chartHeight = chartArea.offsetHeight;
      if (!chartHeight) return;
      const initialRange = panStartMaxPrice - panStartMinPrice;
      if (initialRange <= 0) return;
      const midPrice = (panStartMaxPrice + panStartMinPrice) / 2;
      const scaleFactor = Math.pow(
        2,
        (deltaY / chartHeight) * Y_AXIS_DRAG_SENSITIVITY
      );
      let newRange = initialRange * scaleFactor;
      newRange = Math.max(MIN_PRICE_RANGE_SPAN, newRange);
      const newMin = midPrice - newRange / 2;
      const newMax = midPrice + newRange / 2;
      if (
        Math.abs(newMin - minVisiblePrice) > 1e-9 ||
        Math.abs(newMax - maxVisiblePrice) > 1e-9
      ) {
        minVisiblePrice = newMin;
        maxVisiblePrice = newMax;
        needsRedraw = true;
      }
    } else if (isDraggingXAxis) {
      const deltaX = event.clientX - panStartX;
      const chartWidth = chartArea.offsetWidth;
      if (!chartWidth || panStartVisibleCount <= 0) return;
      const centerIndex = panStartVisibleIndex + panStartVisibleCount / 2;
      const scaleFactor = Math.pow(
        2,
        (deltaX / chartWidth) * X_AXIS_DRAG_SENSITIVITY
      );
      let newVisibleCount = Math.round(panStartVisibleCount * scaleFactor);
      newVisibleCount = Math.max(
        MIN_VISIBLE_CANDLES,
        Math.min(newVisibleCount, fullData.length * 2)
      );
      let newStartIndex = Math.round(centerIndex - newVisibleCount / 2);
      let newEndIndex = newStartIndex + newVisibleCount;

      if (
        newStartIndex !== visibleStartIndex ||
        newEndIndex !== visibleEndIndex
      ) {
        visibleStartIndex = newStartIndex;
        visibleEndIndex = newEndIndex;
        needsRedraw = true;
      }
    } else if (isPanning) {
      const deltaX = event.clientX - panStartX;
      const deltaY = event.clientY - panStartY;
      const chartHeight = chartArea.offsetHeight;
      const chartWidth = chartArea.offsetWidth;
      if (!chartWidth || !chartHeight) return;

      let changedX = false;
      let changedY = false;

      if (panStartVisibleCount > 0) {
        const indexDelta = (deltaX / chartWidth) * panStartVisibleCount;
        let newStartIndex = panStartVisibleIndex - Math.round(indexDelta);
        if (newStartIndex !== visibleStartIndex) {
          visibleStartIndex = newStartIndex;
          visibleEndIndex = newStartIndex + panStartVisibleCount;
          changedX = true;
        }
      }

      const initialPriceRange = panStartMaxPrice - panStartMinPrice;
      if (initialPriceRange > 0) {
        const priceDelta = (deltaY / chartHeight) * initialPriceRange;
        const newMinPrice = panStartMinPrice + priceDelta;
        const newMaxPrice = panStartMaxPrice + priceDelta;
        if (
          Math.abs(newMinPrice - minVisiblePrice) > 1e-9 ||
          Math.abs(newMaxPrice - maxVisiblePrice) > 1e-9
        ) {
          minVisiblePrice = newMinPrice;
          maxVisiblePrice = newMaxPrice;
          changedY = true;
        }
      }
      needsRedraw = changedX || changedY;
    }

    if (needsRedraw) {
      lastDrawTime = now;
      requestAnimationFrame(redrawChart);
    }
  }

  function handleMouseUpOrLeave(event) {
    if (isPanning || isDraggingYAxis || isDraggingXAxis) {
      isPanning = false;
      isDraggingYAxis = false;
      isDraggingXAxis = false;
      chartContainer.classList.remove("panning");
    }
  }

  let resizeTimeout;
  function handleResize() {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      requestAnimationFrame(redrawChart);
    }, DEBOUNCE_DELAY);
  }

  function handleDoubleClick(event) {
    if (!fullData.length) return;
    const chartRect = chartArea.getBoundingClientRect();
    const mouseX = event.clientX - chartRect.left;
    const chartWidth = chartArea.offsetWidth;
    if (!chartWidth) return;

    const currentVisibleCount = visibleEndIndex - visibleStartIndex;
    const fractionalIndex =
      visibleStartIndex + (mouseX / chartWidth) * currentVisibleCount;
    let targetIndex = Math.round(fractionalIndex);
    targetIndex = Math.max(0, Math.min(targetIndex, fullData.length - 1));

    let newVisibleCount = Math.min(DEFAULT_RESET_CANDLE_COUNT, fullData.length);
    let newStartIndex = Math.round(targetIndex - newVisibleCount / 2);
    newStartIndex = Math.max(
      0,
      Math.min(newStartIndex, fullData.length - newVisibleCount)
    );
    let newEndIndex = Math.min(
      fullData.length,
      newStartIndex + newVisibleCount
    );
    newStartIndex = Math.max(0, newEndIndex - newVisibleCount);

    let newMin = Infinity,
      newMax = -Infinity;
    for (let i = newStartIndex; i < newEndIndex; i++) {
      if (!fullData[i] || fullData[i].length < 4) continue;
      newMin = Math.min(newMin, fullData[i][3]);
      newMax = Math.max(newMax, fullData[i][2]);
    }
    if (newMin === Infinity) {
      newMin = 0;
      newMax = 1;
    }

    const padding = Math.max(
      MIN_PRICE_RANGE_SPAN * 0.1,
      (newMax - newMin) * Y_AXIS_PRICE_PADDING_FACTOR
    );
    let newMinPrice = Math.max(0, newMin - padding);
    let newMaxPrice = newMax + padding;
    if (newMaxPrice - newMinPrice < MIN_PRICE_RANGE_SPAN) {
      const mid = (newMaxPrice + newMinPrice) / 2;
      newMinPrice = mid - MIN_PRICE_RANGE_SPAN / 2;
      newMaxPrice = mid + MIN_PRICE_RANGE_SPAN / 2;
    }

    visibleStartIndex = newStartIndex;
    visibleEndIndex = newEndIndex;
    minVisiblePrice = newMinPrice;
    maxVisiblePrice = newMaxPrice;

    requestAnimationFrame(redrawChart);
  }

  // --- Initialization ---
  function initializeChart(data) {
    fullData = data;
    if (!fullData.length) {
      chartMessage.textContent = "No data loaded.";
      chartMessage.style.display = "block";
      return;
    }
    const initialVisibleCount = Math.min(
      DEFAULT_RESET_CANDLE_COUNT,
      fullData.length
    );
    visibleStartIndex = Math.max(0, fullData.length - initialVisibleCount);
    visibleEndIndex = fullData.length;

    let initialMin = Infinity,
      initialMax = -Infinity;
    for (let i = visibleStartIndex; i < visibleEndIndex; i++) {
      if (!fullData[i] || fullData[i].length < 4) continue;
      initialMin = Math.min(initialMin, fullData[i][3]);
      initialMax = Math.max(initialMax, fullData[i][2]);
    }
    if (initialMin === Infinity) {
      initialMin = 0;
      initialMax = 1;
    }
    const padding = Math.max(
      MIN_PRICE_RANGE_SPAN * 0.1,
      (initialMax - initialMin) * Y_AXIS_PRICE_PADDING_FACTOR
    );
    minVisiblePrice = Math.max(0, initialMin - padding);
    maxVisiblePrice = initialMax + padding;
    if (maxVisiblePrice - minVisiblePrice < MIN_PRICE_RANGE_SPAN) {
      const mid = (maxVisiblePrice + minVisiblePrice) / 2;
      minVisiblePrice = mid - MIN_PRICE_RANGE_SPAN / 2;
      maxVisiblePrice = mid + MIN_PRICE_RANGE_SPAN / 2;
    }

    chartContainer.addEventListener("wheel", handleZoom, { passive: false });
    chartContainer.addEventListener("mousedown", handleMouseDownChart);
    yAxisLabelsContainer.addEventListener("mousedown", handleMouseDownYAxis);
    xAxisLabelsContainer.addEventListener("mousedown", handleMouseDownXAxis);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUpOrLeave);
    window.addEventListener("resize", handleResize);
    chartContainer.addEventListener("dblclick", handleDoubleClick);

    chartMessage.style.display = "none";
    requestAnimationFrame(redrawChart);
  }

  // --- Data Fetching and Startup ---
  document.addEventListener("DOMContentLoaded", () => {
    fetch("btc_data.json")
      .then((response) => {
        if (!response.ok) {
          throw new Error(
            `HTTP error ${response.status} (${response.statusText}) loading btc_data.json`
          );
        }
        return response.json();
      })
      .then((data) => {
        if (Array.isArray(data)) {
          console.log(`Loaded ${data.length} data points.`);
          initializeChart(data.slice().reverse());
        } else {
          throw new Error("Loaded data is not an array.");
        }
      })
      .catch((error) => {
        console.error("Chart Error:", error);
        chartMessage.textContent = `Error: ${error.message}. Check console & network tab. Ensure using web server.`;
        chartMessage.style.display = "block";
      });
  });
})(); // End IIFE
