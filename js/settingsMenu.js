// js/settingsMenu.js
import * as dom from "./domElements.js";

/**
 * Initializes the settings dropdown menu functionality.
 */
export function initializeSettingsMenu() {
  // Check if elements exist right at the start
  if (!dom.settingsButton) {
    console.error("Settings Button (#settings-button) not found!");
    return;
  }
  if (!dom.settingsDropdown) {
    console.error("Settings Dropdown (#settings-dropdown) not found!");
    return;
  }
  console.log(
    "Settings menu elements found:",
    dom.settingsButton,
    dom.settingsDropdown
  ); // Log found elements

  // --- Toggle Dropdown on Button Click ---
  dom.settingsButton.addEventListener("click", (event) => {
    console.log("Settings button clicked."); // Log click
    event.stopPropagation(); // Prevent the window click listener from closing it immediately

    const isCurrentlyShown = dom.settingsDropdown.classList.contains("show");
    console.log(`Dropdown 'show' class before toggle: ${isCurrentlyShown}`);

    dom.settingsDropdown.classList.toggle("show");

    const isNowShown = dom.settingsDropdown.classList.contains("show");
    console.log(`Dropdown 'show' class after toggle: ${isNowShown}`); // Log state after toggle
  });

  // --- Close Dropdown on Click Outside ---
  window.addEventListener("click", (event) => {
    // Only run if the dropdown is currently shown
    if (dom.settingsDropdown.classList.contains("show")) {
      // Check if the click was outside the dropdown AND outside the button
      const clickedOutside =
        !dom.settingsDropdown.contains(event.target) &&
        !dom.settingsButton.contains(event.target);

      // console.log("Window clicked while dropdown is shown. Clicked outside:", clickedOutside); // Debug log

      if (clickedOutside) {
        console.log("Clicked outside, removing 'show' class."); // Log closing action
        dom.settingsDropdown.classList.remove("show");
      }
    }
  });

  console.log("Settings menu event listeners attached.");
}
