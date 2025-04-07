// FILE: src/lib/utils/viewInitialization.ts
import { get } from 'svelte/store';
import { visibleStartIndex, visibleEndIndex, minVisiblePrice, maxVisiblePrice, rawData } from '$lib/stores/chartState';
import { isLogScale } from '$lib/stores/settings';
import { DEFAULT_RESET_CANDLE_COUNT, MIN_LOG_VALUE, Y_AXIS_LOG_PADDING_FACTOR, Y_AXIS_PRICE_PADDING_FACTOR, MIN_PRICE_RANGE_SPAN } from './constants';
import type { RawCandleData } from '$lib/types';

export function initializeChartView(data: RawCandleData[]) {
	if (!data || data.length === 0) {
		console.warn("[initializeChartView] No data provided, resetting to default empty view.");
        visibleStartIndex.set(0);
        visibleEndIndex.set(0);
        minVisiblePrice.set(0);
        maxVisiblePrice.set(1); // Avoid zero range
		return;
	}

	const totalDataCount = data.length;
	const initialVisibleCount = Math.min(DEFAULT_RESET_CANDLE_COUNT, totalDataCount);
	const startIndex = Math.max(0, totalDataCount - initialVisibleCount);
	const endIndex = totalDataCount; // Show up to the last candle

	let minY = Infinity;
	let maxY = -Infinity;

	for (let i = startIndex; i < endIndex; i++) {
		if (!data[i] || data[i].length < 5) continue;
		const low = data[i][1];
		const high = data[i][2];
		if (!isNaN(low) && Number.isFinite(low)) minY = Math.min(minY, low);
		if (!isNaN(high) && Number.isFinite(high)) maxY = Math.max(maxY, high);
	}

    // Fallback range calculation if needed
	if (minY === Infinity || maxY === -Infinity || minY <= 0) {
        console.warn("[initializeChartView] Could not determine valid price range, using fallback based on last close.");
		const lastCandle = data[data.length - 1];
		const lastClose = (lastCandle && lastCandle.length >= 5 && Number.isFinite(lastCandle[4]))
            ? lastCandle[4] : 100; // Default center if last close invalid
		minY = Math.max(MIN_LOG_VALUE, lastClose * 0.9); // Ensure positive
		maxY = Math.max(minY * 1.1, lastClose * 1.1); // Ensure max > min & positive
	}

    // Ensure positive min/max after fallback
    minY = Math.max(MIN_LOG_VALUE, minY);
	maxY = Math.max(minY + MIN_PRICE_RANGE_SPAN, maxY); // Ensure max > min


	// Calculate final padded view range based on scale type
	let finalMinPrice: number;
	let finalMaxPrice: number;
	const useLogScale = get(isLogScale);

	if (useLogScale) {
		const logPadding = 1 + Y_AXIS_LOG_PADDING_FACTOR;
		finalMinPrice = Math.max(MIN_LOG_VALUE, minY / logPadding);
		finalMaxPrice = maxY * logPadding;
		// Prevent extreme collapse on log scale
		if (finalMaxPrice / finalMinPrice < 1.01) {
			const midLog = (Math.log(finalMaxPrice) + Math.log(finalMinPrice)) / 2;
			const halfRangeLog = Math.log(1.005); // ~0.5% range
			finalMinPrice = Math.max(MIN_LOG_VALUE, Math.exp(midLog - halfRangeLog));
			finalMaxPrice = Math.exp(midLog + halfRangeLog);
		}
	} else {
		// Linear scale padding
		const linearPadding = Math.max(
			MIN_PRICE_RANGE_SPAN * 0.1, // Ensure some padding even if range is tiny
			(maxY - minY) * Y_AXIS_PRICE_PADDING_FACTOR
		);
		finalMinPrice = Math.max(0, minY - linearPadding); // Clamp linear min at 0
		finalMaxPrice = maxY + linearPadding;
		// Prevent extreme collapse on linear scale
		if (finalMaxPrice - finalMinPrice < MIN_PRICE_RANGE_SPAN) {
			const mid = (finalMaxPrice + finalMinPrice) / 2;
			finalMinPrice = Math.max(0, mid - MIN_PRICE_RANGE_SPAN / 2);
			finalMaxPrice = mid + MIN_PRICE_RANGE_SPAN / 2;
		}
	}

	// Update the stores
	visibleStartIndex.set(startIndex);
	visibleEndIndex.set(endIndex);
	minVisiblePrice.set(finalMinPrice);
	maxVisiblePrice.set(finalMaxPrice);

	console.log(`[initializeChartView] View set: Idx [${startIndex}-${endIndex}], Price [${finalMinPrice.toFixed(4)}-${finalMaxPrice.toFixed(4)}], Log=${useLogScale}`);
}