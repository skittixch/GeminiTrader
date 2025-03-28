// js/promptTab.js
import * as dom from "./domElements.js";

const STORAGE_KEY = "geminiTraderPromptText"; // Key for localStorage
const DEBOUNCE_DELAY = 300; // ms delay before saving after user stops typing

let saveTimeout = null;

/**
 * Saves the current content of the prompt textarea to localStorage.
 */
function savePromptText() {
  if (dom.promptTextarea) {
    try {
      localStorage.setItem(STORAGE_KEY, dom.promptTextarea.value);
      // console.log("Prompt text saved."); // Optional: for debugging
    } catch (error) {
      console.error("Error saving prompt text to localStorage:", error);
      // Handle potential storage errors (e.g., quota exceeded)
    }
  }
}

/**
 * Debounced version of the save function.
 */
function debouncedSavePromptText() {
  clearTimeout(saveTimeout);
  saveTimeout = setTimeout(savePromptText, DEBOUNCE_DELAY);
}

/**
 * Loads saved prompt text from localStorage on initialization.
 */
function loadPromptText() {
  if (dom.promptTextarea) {
    try {
      const savedText = localStorage.getItem(STORAGE_KEY);
      if (savedText !== null) {
        // Check for null, empty string is valid
        dom.promptTextarea.value = savedText;
        console.log("Prompt text loaded from localStorage.");
      } else {
        console.log("No saved prompt text found in localStorage.");
      }
    } catch (error) {
      console.error("Error loading prompt text from localStorage:", error);
    }
  }
}

/**
 * Initializes the prompt tab functionality: loads saved text and sets up auto-saving.
 */
export function initializePromptTab() {
  if (!dom.promptTextarea) {
    console.warn(
      "Prompt textarea not found. Skipping prompt tab initialization."
    );
    return;
  }

  // Load any previously saved text
  loadPromptText();

  // Add event listener to save text on input (debounced)
  dom.promptTextarea.addEventListener("input", debouncedSavePromptText);

  console.log("Prompt tab initialized.");
}
