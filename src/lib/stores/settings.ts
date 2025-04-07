// FILE: src/lib/stores/settings.ts
import { writable } from 'svelte/store';
import type { Theme, GranularityOption } from '$lib/types';
import { DEFAULT_GRANULARITY, DEFAULT_PRODUCT_ID } from '$lib/utils/constants';

// Helper to get initial value from localStorage or default
function getLocalStorageItem<T>(key: string, defaultValue: T, validator?: (value: any) => boolean): T {
	if (typeof localStorage === 'undefined') {
		return defaultValue;
	}
	try {
		const storedValue = localStorage.getItem(key);
		if (storedValue !== null) {
			const parsedValue = JSON.parse(storedValue);
			if (validator ? validator(parsedValue) : true) {
				return parsedValue as T;
			}
		}
	} catch (e) {
		console.error(`Error reading localStorage key “${key}”:`, e);
		localStorage.removeItem(key); // Remove corrupted item
	}
	return defaultValue;
}

// Theme Store
const initialTheme = getLocalStorageItem<Theme>(
	'theme',
	(typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light',
	(value) => value === 'light' || value === 'dark'
);
export const theme = writable<Theme>(initialTheme);
theme.subscribe((value) => {
	if (typeof document !== 'undefined') {
		document.documentElement.setAttribute('data-theme', value);
	}
	if (typeof localStorage !== 'undefined') {
		try {
			localStorage.setItem('theme', JSON.stringify(value));
		} catch (e) {
			console.error("Failed to save theme preference:", e);
		}
	}
});

// Log Scale Store
const initialLogScale = getLocalStorageItem<boolean>('logScalePref', false, (v) => typeof v === 'boolean');
export const isLogScale = writable<boolean>(initialLogScale);
isLogScale.subscribe((value) => {
	if (typeof localStorage !== 'undefined') {
		try {
			localStorage.setItem('logScalePref', JSON.stringify(value));
		} catch (e) {
			console.error("Failed to save log scale preference:", e);
		}
	}
});

// Time Format Store
const initialTimeFormat = getLocalStorageItem<boolean>('timeFormatPref', false, (v) => typeof v === 'boolean');
export const is12HourFormat = writable<boolean>(initialTimeFormat);
is12HourFormat.subscribe((value) => {
	if (typeof localStorage !== 'undefined') {
		try {
			localStorage.setItem('timeFormatPref', JSON.stringify(value));
		} catch (e) {
			console.error("Failed to save time format preference:", e);
		}
	}
});

// Current Product ID Store
export const currentProductId = writable<string>(DEFAULT_PRODUCT_ID);

// Granularity Store
export const currentGranularity = writable<number>(DEFAULT_GRANULARITY);

export const granularityOptions: GranularityOption[] = [
    { label: '5m', value: 300 },
    { label: '15m', value: 900 },
    { label: '1h', value: 3600 },
    { label: '6h', value: 21600 },
    { label: '1d', value: 86400 },
];