<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import Header from '$lib/components/Header/Header.svelte';
	import ChartContainer from '$lib/components/Chart/ChartContainer.svelte';
	import TabContainer from '$lib/components/BottomPane/TabContainer.svelte';
	import { isChartLoading, chartError } from '$lib/stores/chartState';
	import { isApiReady, apiCheckError } from '$lib/stores/apiState';
	import { currentGranularity } from '$lib/stores/settings';
	import { initializeWebSocket, closeWebSocket } from '$lib/utils/websocket';
	import { checkApiStatus, fetchCandles, fetchAccounts, fetchOpenOrders } from '$lib/utils/api';
	import {
		rawData,
		visibleStartIndex,
		visibleEndIndex,
		minVisiblePrice,
		maxVisiblePrice
	} from '$lib/stores/chartState';
	import { accounts, areBalancesLoading, balanceError } from '$lib/stores/balanceState';
	import { openOrders, areOrdersLoading, ordersError, ordersToPlot } from '$lib/stores/orderState';
	import { initializeChartView } from '$lib/utils/viewInitialization'; // We'll create this helper

	let unsubscribeGranularity: (() => void) | null = null;

	onMount(async () => {
		console.log('[+page.svelte] Mounted. Initializing...');
		isChartLoading.set(true);
		areBalancesLoading.set(true);
		chartError.set(null);
		balanceError.set(null);
		ordersError.set(null);
		apiCheckError.set(null);

		// --- Initial Data Fetches ---
		try {
			// 1. Check Backend API Status
			const status = await checkApiStatus();
			isApiReady.set(status.credentials_loaded);
			if (!status.credentials_loaded) {
				apiCheckError.set('Backend API credentials not loaded or client failed.');
				// Stop further authenticated fetches if creds failed
				areBalancesLoading.set(false); // Stop balance loading explicitly
				areOrdersLoading.set(false); // Stop order loading explicitly
				console.warn('Stopping authenticated fetches due to API status.');
				// Still try to fetch candles as they are public
			}

			// 2. Fetch Candles (Public - attempt even if API not fully ready)
			try {
				const candleData = await fetchCandles(get(currentProductId), get(currentGranularity));
				rawData.set(candleData);
				if (candleData.length > 0) {
					initializeChartView(candleData); // Initialize view based on fetched candles
				} else {
					chartError.set('No candle data returned from API.');
				}
			} catch (err: any) {
				console.error('Error fetching initial candles:', err);
				chartError.set(err.message || 'Failed to load chart data.');
				rawData.set([]); // Ensure data is empty on error
				initializeChartView([]); // Reset view
			} finally {
				isChartLoading.set(false);
			}

			// 3. Fetch Authenticated Data (only if API seems ready)
			if (get(isApiReady)) {
				// Fetch Balances and Orders in parallel
				const [accountResult, orderResult] = await Promise.allSettled([
					fetchAccounts(),
					fetchOpenOrders()
				]);

				// Handle Balances Result
				if (accountResult.status === 'fulfilled') {
					accounts.set(accountResult.value);
				} else {
					console.error('Error fetching initial accounts:', accountResult.reason);
					balanceError.set(accountResult.reason?.message || 'Failed to load balances.');
				}
				areBalancesLoading.set(false);

				// Handle Orders Result
				if (orderResult.status === 'fulfilled') {
					openOrders.set(orderResult.value); // Update store, triggers derivation for ordersToPlot
				} else {
					console.error('Error fetching initial open orders:', orderResult.reason);
					ordersError.set(orderResult.reason?.message || 'Failed to load open orders.');
				}
				areOrdersLoading.set(false); // Set loading false even on error
			} else {
				console.log('Skipping initial authenticated data fetch (API not ready).');
				// Ensure loading states are off if skipped
				areBalancesLoading.set(false);
				areOrdersLoading.set(false);
			}

			// 4. Initialize WebSocket (after initial data is loaded/attempted)
			console.log('[+page.svelte] Initializing WebSocket...');
			initializeWebSocket();
		} catch (err: any) {
			console.error('Critical error during initial data loading sequence:', err);
			apiCheckError.set(err.message || 'Failed to initialize application data.');
			isChartLoading.set(false);
			areBalancesLoading.set(false);
			areOrdersLoading.set(false);
		}

		// --- Subscribe to Granularity Changes ---
		// When granularity changes *externally* (e.g., via Header), refetch candles
		unsubscribeGranularity = currentGranularity.subscribe(async ($granularity, oldGranularity) => {
			// Avoid initial run and ensure it actually changed
			if (oldGranularity !== undefined && $granularity !== oldGranularity) {
				console.log(
					`[+page.svelte] Granularity changed to: ${$granularity}. Refetching candles...`
				);
				isChartLoading.set(true);
				chartError.set(null);
				try {
					const candleData = await fetchCandles(get(currentProductId), $granularity);
					rawData.set(candleData);
					if (candleData.length > 0) {
						initializeChartView(candleData); // Reset view for new granularity
					} else {
						chartError.set('No candle data returned for this interval.');
					}
					// Note: No need to fetch orders again here, only candle data changes with granularity
				} catch (err: any) {
					console.error('Error fetching candles on granularity change:', err);
					chartError.set(err.message || 'Failed to load chart data for new interval.');
					rawData.set([]);
					initializeChartView([]);
				} finally {
					isChartLoading.set(false);
					// Ensure websocket is re-initialized/subscribed correctly if needed after fetch
					initializeWebSocket();
				}
			}
		});

		return () => {
			// Cleanup function
			console.log('[+page.svelte] Unmounting. Closing WebSocket.');
			closeWebSocket();
			if (unsubscribeGranularity) {
				unsubscribeGranularity();
			}
		};
	});
</script>

<div class="main-layout">
	<Header />

	<div class="content-area" id="content-area">
		<!-- Top Pane -->
		<div class="chart-pane" id="chart-pane">
			{#if $isChartLoading}
				<div id="chart-message">Loading chart data...</div>
			{:else if $chartError}
				<div id="chart-message" style="color: var(--candle-down);">Error: {$chartError}</div>
			{:else if $rawData.length === 0 && !$isChartLoading}
				<div id="chart-message">No chart data available.</div>
			{:else}
				<ChartContainer />
			{/if}
		</div>

		<!-- Resizer -->
		<div class="resizer" id="resizer"></div>
		<!-- TODO: Add Resizer component later -->

		<!-- Bottom Pane -->
		<TabContainer />
	</div>
</div>

<style>
	/* Ensure main layout takes full height */
	.main-layout {
		display: flex;
		flex-direction: column;
		height: 100vh; /* Use viewport height */
		width: 100%;
		overflow: hidden; /* Prevent body scroll */
	}

	.content-area {
		flex-grow: 1;
		display: flex;
		flex-direction: column;
		overflow: hidden; /* Important */
		/* Background is handled by body + theme */
	}

	.chart-pane {
		flex-basis: 67%; /* Initial height percentage */
		flex-grow: 1; /* Allow growing */
		flex-shrink: 1; /* Allow shrinking */
		overflow: hidden; /* Hide overflow */
		position: relative;
		min-height: var(--min-pane-height, 150px); /* Minimum height */
		display: flex; /* Use flex for message centering */
		flex-direction: column; /* Stack chart content */
	}

	/* Keep chart message centered if chart container fails */
	#chart-message {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		/* Styles are in app.css */
		z-index: 100; /* Ensure it's above other chart elements if they render partially */
	}

	.resizer {
		flex-shrink: 0;
		height: var(--resizer-height, 6px);
		background-color: var(--resizer-color, #ccc);
		cursor: row-resize;
		width: 100%;
	}

	/* TabContainer itself will be styled internally or in app.css */
</style>
