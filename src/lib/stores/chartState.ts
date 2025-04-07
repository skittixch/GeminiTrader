// FILE: src/lib/stores/chartState.ts
import { writable, derived } from 'svelte/store';
import type { RawCandleData, PlotOrder } from '$lib/types';
import { MIN_LOG_VALUE } from '$lib/utils/constants';

// Raw candle data fetched from API
export const rawData = writable<RawCandleData[]>([]);

// Viewport state
export const visibleStartIndex = writable<number>(0);
export const visibleEndIndex = writable<number>(0);
export const minVisiblePrice = writable<number>(0);
export const maxVisiblePrice = writable<number>(1);

// Derived: Actual candles currently visible based on indices
export const visibleData = derived<[typeof rawData, typeof visibleStartIndex, typeof visibleEndIndex], RawCandleData[]>(
	[rawData, visibleStartIndex, visibleEndIndex],
	([$rawData, $startIndex, $endIndex]) => {
        if (!$rawData || $rawData.length === 0 || $startIndex >= $endIndex || $startIndex < 0) {
            return [];
        }
		// Ensure indices are within bounds
        const start = Math.max(0, $startIndex);
        const end = Math.min($rawData.length, $endIndex);
		return $rawData.slice(start, end);
	}
);

// Derived: Number of visible candles
export const visibleCandleCount = derived<[typeof visibleStartIndex, typeof visibleEndIndex], number>(
    [visibleStartIndex, visibleEndIndex],
    ([$startIndex, $endIndex]) => Math.max(0, $endIndex - $startIndex)
);

// Last known ticker price from WebSocket
export const lastTickerPrice = writable<number | null>(null);

// Panning/Dragging state
export const isPanning = writable<boolean>(false);
export const isDraggingYAxis = writable<boolean>(false);
export const isDraggingXAxis = writable<boolean>(false);

// Chart loading/error state
export const isChartLoading = writable<boolean>(true);
export const chartError = writable<string | null>(null);

// Interaction state (e.g., for tooltip/crosshair)
export interface InteractionState {
    mouseX: number | null;
    mouseY: number | null;
    hoveredCandleIndex: number | null; // Index relative to full rawData array
	hoveredCandleData: RawCandleData | null;
    priceAtCursor: number | null;
}
export const interactionState = writable<InteractionState>({
    mouseX: null,
    mouseY: null,
    hoveredCandleIndex: null,
	hoveredCandleData: null,
    priceAtCursor: null,
});

// Derived safe min price for log calculations
export const safeMinVisiblePrice = derived(minVisiblePrice, ($min) => Math.max(MIN_LOG_VALUE, $min));