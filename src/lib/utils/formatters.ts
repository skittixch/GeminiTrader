// FILE: src/lib/utils/formatters.ts
import { get } from 'svelte/store';
import { is12HourFormat } from '$lib/stores/settings'; // Import store

// Date/Time Formatting
export function formatTimestamp(timestampOrDate: number | Date): string {
	try {
		let date: Date;
		if (timestampOrDate instanceof Date) {
			date = timestampOrDate;
		} else if (typeof timestampOrDate === 'number' && Number.isFinite(timestampOrDate)) {
			date = new Date(timestampOrDate * 1000); // Assume seconds -> ms
		} else {
			throw new Error("Invalid input type: Expected number (Unix timestamp) or Date object.");
		}

		if (isNaN(date.getTime())) {
			throw new Error("Invalid Date object produced");
		}

		const use12Hour = get(is12HourFormat); // Get current store value

		const options: Intl.DateTimeFormatOptions = {
			// timeZone: 'America/Chicago', // Example: Use user's local time by default or make configurable
			month: 'numeric',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
			hour12: use12Hour,
		};
		return date.toLocaleString(undefined, options); // Use browser's default locale
	} catch (error) {
		console.error("Error formatting timestamp/date:", error, timestampOrDate);
		return "Time Error";
	}
}

export function formatDate(timestamp: number): string {
	try {
		const date = new Date(timestamp * 1000); // Assume Unix seconds
		const options: Intl.DateTimeFormatOptions = {
			// timeZone: 'America/Chicago', // Or use local
			month: 'short',
			day: 'numeric',
		};
		if (isNaN(date.getTime())) {
			throw new Error("Invalid timestamp resulted in Invalid Date");
		}
		return date.toLocaleDateString(undefined, options); // Use browser locale
	} catch (error) {
		console.error("Error formatting date:", error, timestamp);
		return "Date Err";
	}
}

// Currency and Quantity Formatting
export function formatCurrency(value: number | string | null | undefined, currencySymbol = "$", defaultDecimals = 2): string {
	const numValue = typeof value === 'string' ? parseFloat(value) : value;

	if (numValue === null || numValue === undefined || isNaN(numValue) || !Number.isFinite(numValue)) {
		return `?`;
	}
	try {
		let dynamicDecimals: number;
        const absValue = Math.abs(numValue);

		if (absValue === 0) dynamicDecimals = defaultDecimals;
        else if (absValue < 0.0001) dynamicDecimals = 8;
		else if (absValue < 0.1) dynamicDecimals = 6;
		else if (absValue < 10) dynamicDecimals = 4;
		else if (absValue < 1000) dynamicDecimals = 2;
		else dynamicDecimals = 2;

        const finalDecimals = Math.max(defaultDecimals, dynamicDecimals);

		return numValue.toLocaleString(undefined, { // Use browser locale
			style: 'currency',
			currency: 'USD', // Use 'USD' for formatting engine, replace symbol later
			minimumFractionDigits: finalDecimals,
			maximumFractionDigits: finalDecimals,
		}).replace('USD', currencySymbol).replace(/^\$/, currencySymbol); // Replace symbol

	} catch (e) {
		console.error("Currency formatting error:", e, { value, defaultDecimals });
		const safeDecimals = Math.max(0, Math.floor(defaultDecimals));
		return `${currencySymbol}${numValue.toFixed(safeDecimals)}`;
	}
}

export function formatQuantity(value: number | string | null | undefined): string {
	const numValue = typeof value === 'string' ? parseFloat(value) : value;

	if (numValue === null || numValue === undefined || isNaN(numValue) || !Number.isFinite(numValue)) {
        return "--";
    }

	const absValue = Math.abs(numValue);
	let decimals: number;

	if (absValue === 0) decimals = 2;
	else if (absValue < 0.00000001) decimals = 10;
	else if (absValue < 0.00001) decimals = 8;
	else if (absValue < 0.01) decimals = 6;
	else if (absValue < 1) decimals = 5;
	else if (absValue < 100) decimals = 4;
	else if (absValue < 10000) decimals = 3;
	else decimals = 2;

	try {
		return numValue.toLocaleString(undefined, { // Use browser locale
			minimumFractionDigits: 2, // Ensure at least 2 for consistency
			maximumFractionDigits: decimals,
		});
	} catch (e) {
		console.error("Quantity formatting error:", e, { value, decimals });
		return numValue.toFixed(decimals);
	}
}

export function formatVolumeLabel(volume: number): string {
  if (volume >= 1e6) {
    return (volume / 1e6).toFixed(2) + "M";
  } else if (volume >= 1e3) {
    return (volume / 1e3).toFixed(1) + "K";
  } else {
    return volume.toFixed(0);
  }
}