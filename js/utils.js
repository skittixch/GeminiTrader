// js/utils.js
export function calculateNiceStep(range, maxTicks) {
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

export function formatTimestamp(timestamp) {
  const date = new Date(timestamp * 1000);
  const options = {
    timeZone: "America/Chicago",
    hour: "numeric",
    minute: "2-digit",
    hour12: false,
  };
  try {
    return date.toLocaleString("en-US", options);
  } catch (error) {
    console.error("Error formatting timestamp:", error);
    const h = date.getHours().toString().padStart(2, "0");
    const m = date.getMinutes().toString().padStart(2, "0");
    return `${h}:${m}`;
  }
}

export function formatDate(timestamp) {
  const date = new Date(timestamp * 1000);
  const options = {
    timeZone: "America/Chicago",
    month: "short",
    day: "numeric",
  };
  try {
    return date.toLocaleDateString("en-US", options);
  } catch (error) {
    console.error("Error formatting date:", error);
    return "";
  }
}
