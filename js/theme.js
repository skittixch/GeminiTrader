// js/theme.js
import * as dom from "./domElements.js"; // Import domElements
import * as config from "./config.js"; // Import config for colors

/**
 * Applies the selected theme (light/dark) to the application.
 * Sets the data-theme attribute and directly styles the body background.
 * @param {string} theme - The theme to apply ('light' or 'dark').
 */
function applyTheme(theme) {
  if (theme !== "light" && theme !== "dark") {
    console.warn(`Invalid theme specified: ${theme}. Defaulting to light.`);
    theme = "light";
  }

  // 1. Set data-theme attribute for CSS variable switching
  document.documentElement.setAttribute("data-theme", theme);

  // 2. Directly set body background color from config
  const bgColor =
    theme === "dark" ? config.DARK_MODE_BG_COLOR : config.LIGHT_MODE_BG_COLOR;
  document.body.style.backgroundColor = bgColor;

  // 3. Update toggle state if it exists
  if (dom.themeToggle) {
    dom.themeToggle.checked = theme === "dark";
  }

  console.log(`Theme applied: ${theme}, Background set to: ${bgColor}`);
}

/**
 * Initializes the theme based on saved preference, system preference, or default.
 * Attaches event listeners for theme changes.
 */
export function initializeTheme() {
  const userPrefersDark =
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const savedTheme = localStorage.getItem("theme"); // Could be 'light' or 'dark'

  let initialTheme = "light"; // Default

  if (savedTheme === "light" || savedTheme === "dark") {
    initialTheme = savedTheme;
    console.log(`Using saved theme preference: ${initialTheme}`);
  } else if (userPrefersDark) {
    initialTheme = "dark";
    console.log(`Using system theme preference: ${initialTheme}`);
  } else {
    console.log(`Using default theme: ${initialTheme}`);
  }

  applyTheme(initialTheme); // Apply the determined initial theme

  // Listener for the theme toggle checkbox
  if (dom.themeToggle) {
    dom.themeToggle.addEventListener("change", function () {
      const newTheme = this.checked ? "dark" : "light";
      applyTheme(newTheme);
      try {
        localStorage.setItem("theme", newTheme); // Save preference
      } catch (e) {
        console.error("Could not save theme preference to localStorage:", e);
      }
    });
  } else {
    console.warn("Theme toggle checkbox not found.");
  }

  // Listener for changes in system preference (if no user preference is saved)
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", (e) => {
      // Only apply system change if the user hasn't explicitly set a theme via toggle
      if (!localStorage.getItem("theme")) {
        const newSystemTheme = e.matches ? "dark" : "light";
        console.log(`System theme changed to: ${newSystemTheme}. Applying...`);
        applyTheme(newSystemTheme);
      } else {
        console.log(
          "System theme changed, but user preference is set. Ignoring system change."
        );
      }
    });
}
