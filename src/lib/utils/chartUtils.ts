// FILE: src/lib/utils/chartUtils.ts
import { get } from 'svelte/store';
import { isLogScale } from '$lib/stores/settings';
import { minVisiblePrice, maxVisiblePrice, safeMinVisiblePrice } from '$lib/stores/chartState';
import { MIN_LOG_VALUE } from './constants';

const MIN_LINEAR_RANGE_EPSILON = 1e-9;
const MIN_LOG_RANGE_EPSILON = 1e-9;

/**
 * Calculates the Y pixel coordinate for a given price.
 * Reads required state directly from stores.
 * @param price The price value.
 * @param chartHeight The current height of the chart drawing area in pixels.
 * @returns The Y coordinate (pixels from top) or null if invalid.
 */
export function getYCoordinate(price: number, chartHeight: number): number | null {
	if (isNaN(price) || isNaN(chartHeight) || chartHeight <= 0 || price < 0) {
		return null;
	}

	const minPrice = get(minVisiblePrice);
	const maxPrice = get(maxVisiblePrice);
	const logScale = get(isLogScale);
    const safeMinPriceForLog = get(safeMinVisiblePrice); // Use derived store

	if (isNaN(minPrice) || isNaN(maxPrice) || !Number.isFinite(minPrice) || !Number.isFinite(maxPrice) || maxPrice <= minPrice) {
		return null;
	}

	if (logScale) {
		const safeMaxVisiblePrice = Math.max(MIN_LOG_VALUE, maxPrice);
		const safePrice = Math.max(MIN_LOG_VALUE, price);

		if (safeMaxVisiblePrice <= safeMinPriceForLog) return null;

		const logMin = Math.log(safeMinPriceForLog);
		const logMax = Math.log(safeMaxVisiblePrice);
		const logPrice = Math.log(safePrice);

		if (!Number.isFinite(logMin) || !Number.isFinite(logMax) || !Number.isFinite(logPrice)) {
			return null;
		}

		const logRange = logMax - logMin;
		if (!Number.isFinite(logRange) || logRange < MIN_LOG_RANGE_EPSILON) {
            // Handle zero range
            if (logPrice <= logMin) return chartHeight;
            if (logPrice >= logMax) return 0;
            return chartHeight / 2;
		}

		const logScaleY = chartHeight / logRange;
		const yPos = chartHeight - (logPrice - logMin) * logScaleY;

		return Number.isFinite(yPos) ? yPos : null;

	} else {
		// Linear Scale
		const priceRange = maxPrice - minPrice;
		if (!Number.isFinite(priceRange) || priceRange < MIN_LINEAR_RANGE_EPSILON) {
            // Handle zero range
            if (price <= minPrice) return chartHeight;
            if (price >= maxPrice) return 0;
            return chartHeight / 2;
		}

		const scaleY = chartHeight / priceRange;
		const yPos = chartHeight - (price - minPrice) * scaleY;

		return Number.isFinite(yPos) ? yPos : null;
	}
}

/**
 * Calculates the price corresponding to a Y pixel coordinate.
 * Reads required state directly from stores.
 * @param yPos Y coordinate (pixels from top).
 * @param chartHeight The current height of the chart drawing area in pixels.
 * @returns The price value or null if invalid.
 */
export function getPriceFromYCoordinate(yPos: number, chartHeight: number): number | null {
	if (isNaN(yPos) || isNaN(chartHeight) || chartHeight <= 0) return null;

    const minPrice = get(minVisiblePrice);
	const maxPrice = get(maxVisiblePrice);
	const logScale = get(isLogScale);
    const safeMinPriceForLog = get(safeMinVisiblePrice); // Use derived store

	if (isNaN(minPrice) || isNaN(maxPrice) || !Number.isFinite(minPrice) || !Number.isFinite(maxPrice) || maxPrice <= minPrice) {
		return null;
	}

	const clampedYPos = Math.max(0, Math.min(yPos, chartHeight));
	const fraction = (chartHeight - clampedYPos) / chartHeight; // 0 (bottom) to 1 (top)

	if (logScale) {
		const safeMaxVisiblePrice = Math.max(MIN_LOG_VALUE, maxPrice);
		if (safeMaxVisiblePrice <= safeMinPriceForLog) return safeMinPriceForLog;

		const logMin = Math.log(safeMinPriceForLog);
		const logMax = Math.log(safeMaxVisiblePrice);
		if (!Number.isFinite(logMin) || !Number.isFinite(logMax)) return null;

		const logRange = logMax - logMin;
		if (!Number.isFinite(logRange) || logRange < MIN_LOG_RANGE_EPSILON) {
			return safeMinPriceForLog; // Negligible range
		}

		const logPrice = logMin + fraction * logRange;
		const priceResult = Math.exp(logPrice);
		return Number.isFinite(priceResult) ? priceResult : null;

	} else {
		// Linear Scale
		const priceRange = maxPrice - minPrice;
		if (!Number.isFinite(priceRange) || priceRange < MIN_LINEAR_RANGE_EPSILON) {
			return minPrice; // Negligible range
		}

		const priceResult = minPrice + fraction * priceRange;
		return Number.isFinite(priceResult) ? Math.max(0, priceResult) : null;
	}
}


/**
 * Calculates a "nice" step value for axis ticks.
 * @param range The total range of the axis (max - min).
 * @param maxTicks The desired maximum number of ticks.
 * @returns A nicely rounded step value.
 */
export function calculateNiceStep(range: number, maxTicks: number): number {
	if (isNaN(range) || range <= 0 || isNaN(maxTicks) || maxTicks <= 0 || !Number.isFinite(range)) {
		return 1;
	}

	const roughStep = range / Math.max(1, maxTicks);
	if (roughStep <= 0 || isNaN(roughStep) || !Number.isFinite(roughStep)) {
		return 1;
	}
	if (roughStep < Number.EPSILON) {
		return Number.EPSILON * 10;
	}

	const magnitude = Math.pow(10, Math.floor(Math.log10(roughStep)));
	if (magnitude <= 0 || !Number.isFinite(magnitude)) {
		return roughStep > 1 ? roughStep : 1;
	}

	const residual = roughStep / magnitude;
	let niceStep: number;
	if (residual > 5) niceStep = 10 * magnitude;
	else if (residual > 2) niceStep = 5 * magnitude;
	else if (residual > 1) niceStep = 2 * magnitude;
	else niceStep = magnitude;

	const minStep = Math.max(Number.EPSILON * 10, range * 1e-9);
	return Number.isFinite(niceStep) ? Math.max(niceStep, minStep) : minStep;
}

// Add other chart-specific calculation helpers here if needed
// e.g., timeToX, xToTime, findCandleIndexFromX, etc.