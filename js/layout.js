// js/layout.js
import * as dom from "./domElements.js";
import { redrawChart } from "./drawing.js"; // To redraw chart after pane resize

let isResizing = false;
let startY, startChartHeight, startBottomHeight;

// Constants from CSS (or define here)
const MIN_PANE_HEIGHT_PX = 100;
const RESIZER_HEIGHT_PX = 6;
const INITIAL_CHART_FLEX_BASIS = "67%"; // Keep initial percentages
const INITIAL_BOTTOM_FLEX_BASIS = "33%"; // Keep initial percentages

/**
 * Resets the pane heights to their initial percentage basis.
 */
function resetPaneHeights() {
  if (dom.chartPane && dom.bottomPane) {
    console.log("Resetting pane heights to initial percentages.");
    dom.chartPane.style.flexBasis = INITIAL_CHART_FLEX_BASIS;
    dom.bottomPane.style.flexBasis = INITIAL_BOTTOM_FLEX_BASIS;

    // We need to redraw the chart after the layout adjusts
    // Use a short timeout to allow the browser to recalculate layout first
    setTimeout(() => {
      requestAnimationFrame(redrawChart);
    }, 0);
  } else {
    console.error("Cannot reset pane heights: Pane elements not found.");
  }
}

function handleMouseDownResize(event) {
  event.preventDefault();
  isResizing = true;
  startY = event.clientY;

  // Get initial heights in pixels at the start of the drag
  startChartHeight = dom.chartPane.offsetHeight;
  startBottomHeight = dom.bottomPane.offsetHeight;

  document.body.classList.add("resizing");

  window.addEventListener("mousemove", handleMouseMoveResize);
  window.addEventListener("mouseup", handleMouseUpResize);
}

function handleMouseMoveResize(event) {
  if (!isResizing) return;

  const deltaY = event.clientY - startY;

  let newChartHeight = startChartHeight + deltaY;
  let newBottomHeight = startBottomHeight - deltaY;

  const totalPaneHeight = startChartHeight + startBottomHeight;

  // Enforce minimum heights
  if (newChartHeight < MIN_PANE_HEIGHT_PX) {
    newChartHeight = MIN_PANE_HEIGHT_PX;
    newBottomHeight = totalPaneHeight - newChartHeight;
  }
  if (newBottomHeight < MIN_PANE_HEIGHT_PX) {
    newBottomHeight = MIN_PANE_HEIGHT_PX;
    newChartHeight = totalPaneHeight - newBottomHeight;
  }
  if (newChartHeight < MIN_PANE_HEIGHT_PX) newChartHeight = MIN_PANE_HEIGHT_PX;

  // Apply new heights using flex-basis (pixels provide stability during drag)
  dom.chartPane.style.flexBasis = `${newChartHeight}px`;
  dom.bottomPane.style.flexBasis = `${newBottomHeight}px`;

  requestAnimationFrame(redrawChart);
}

function handleMouseUpResize() {
  if (isResizing) {
    isResizing = false;
    document.body.classList.remove("resizing");

    window.removeEventListener("mousemove", handleMouseMoveResize);
    window.removeEventListener("mouseup", handleMouseUpResize);
  }
}

/**
 * Handles the double-click event on the resizer.
 */
function handleDoubleClickResize(event) {
  event.preventDefault(); // Prevent any default dblclick behavior
  resetPaneHeights();
}

export function initializeResizer() {
  // Use the dom reference directly
  const resizer = dom.resizer;

  if (resizer && dom.chartPane && dom.bottomPane && dom.contentArea) {
    // Set initial heights using percentages
    dom.chartPane.style.flexBasis = INITIAL_CHART_FLEX_BASIS;
    dom.bottomPane.style.flexBasis = INITIAL_BOTTOM_FLEX_BASIS;
    console.log(
      `Initial flex-basis set to approx ${INITIAL_CHART_FLEX_BASIS}/${INITIAL_BOTTOM_FLEX_BASIS}`
    );

    // Attach mousedown listener for dragging
    resizer.addEventListener("mousedown", handleMouseDownResize);

    // Attach dblclick listener for resetting *** NEW ***
    resizer.addEventListener("dblclick", handleDoubleClickResize);

    console.log("Resizer initialized with drag and double-click reset.");

    // Removed the optional pixel update timeout as resetting to percentage works well
  } else {
    console.error(
      "Resizer initialization failed: Resizer, chartPane, or bottomPane not found in DOM."
    );
    if (!resizer) console.error("- Resizer missing");
    if (!dom.chartPane) console.error("- Chart Pane missing");
    if (!dom.bottomPane) console.error("- Bottom Pane missing");
    if (!dom.contentArea) console.error("- Content Area missing");
  }
}
