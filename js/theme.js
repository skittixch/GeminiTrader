// js/theme.js
import { themeToggle } from "./domElements.js";

export function initializeTheme() {
  const userPrefersDark =
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const currentTheme = localStorage.getItem("theme");
  let theme = "light";
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
}
