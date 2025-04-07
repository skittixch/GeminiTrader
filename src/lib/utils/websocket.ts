// FILE: src/lib/utils/websocket.ts
import { get } from 'svelte/store';
import { currentProductId, lastTickerPrice, rawData } from '$lib/stores/chartState';
import { latestPrices, updatePrice } from '$lib/stores/balanceState';
import { currentGranularity } from '$lib/stores/settings';
import { WEBSOCKET_URL, WS_LIVE_UPDATE_THROTTLE_MS, WS_BALANCE_UPDATE_THROTTLE_MS } from './constants';
// We need redrawChart, import it carefully or rethink the update mechanism
// Option: Emit a custom event or rely purely on store reactivity?
// For now, let's try relying on store reactivity triggered by rawData update.

let ws: WebSocket | null = null;
let reconnectTimeoutId: ReturnType<typeof setTimeout> | null = null;
let chartRedrawTimeoutId: ReturnType<typeof setTimeout> | null = null;
let balanceUpdateTimeoutId: ReturnType<typeof setTimeout> | null = null;
let currentSubscribedProductId: string | null = null;
let isConnecting = false;
let intentionalClose = false;

// --- Throttled Update Functions ---
// We won't call redrawChart directly. Instead, updating rawData should trigger redraws elsewhere.
const throttledChartUpdate = () => {
	if (chartRedrawTimeoutId) return;
	chartRedrawTimeoutId = setTimeout(() => {
		// console.log('WS: Throttled chart update triggered (rawData change should cause redraw)');
		chartRedrawTimeoutId = null;
		// The actual redraw should happen reactively in ChartContainer/ChartArea
		// due to the change in the 'rawData' store.
        // No direct call to redrawChart() here.
	}, WS_LIVE_UPDATE_THROTTLE_MS);
};

// Balance updates need a function to be called. Let's create a store listener elsewhere.
// For now, just manage the timeout.
const scheduleBalanceUpdate = () => {
    if (balanceUpdateTimeoutId) return;
    balanceUpdateTimeoutId = setTimeout(() => {
        // console.log('WS: Throttled balance update triggered');
        // Need a way to signal BalanceList component to re-render with new prices.
        // Directly calling updateBalanceValuesUI is not ideal Svelte pattern.
        // WORKAROUND: Trigger reactivity by slightly modifying the prices map
        latestPrices.update(map => new Map(map)); // Create a new map instance
        balanceUpdateTimeoutId = null;
    }, WS_BALANCE_UPDATE_THROTTLE_MS);
};


// --- WebSocket Logic ---
function connect() {
	if (ws || isConnecting) {
		// console.log('WS: Connection attempt skipped (already connected or connecting).');
		return;
	}

	const productIdToSubscribe = get(currentProductId);
	if (!productIdToSubscribe) {
		console.error('WS: Cannot connect, no product ID available.');
		return;
	}

	isConnecting = true;
	intentionalClose = false;
	console.log(`WS: Attempting connection to ${WEBSOCKET_URL} for ${productIdToSubscribe}...`);

	// Clear any pending reconnect timeout
	if (reconnectTimeoutId) {
		clearTimeout(reconnectTimeoutId);
		reconnectTimeoutId = null;
	}

	ws = new WebSocket(WEBSOCKET_URL);
	currentSubscribedProductId = productIdToSubscribe; // Tentatively set

	ws.onopen = () => {
		isConnecting = false;
		console.log(`WS: Connection opened for ${productIdToSubscribe}. Subscribing...`);
		if (ws?.readyState === WebSocket.OPEN) {
			ws.send(JSON.stringify({
				type: 'subscribe',
				product_ids: [productIdToSubscribe],
				channels: ['ticker'] // Only need ticker
			}));
		} else {
			console.warn('WS: Opened but readyState not OPEN. Cannot subscribe.');
		}
	};

	ws.onmessage = (event) => {
		try {
			const message = JSON.parse(event.data);

			if (message.type === 'ticker' && message.price && message.product_id) {
				const price = parseFloat(message.price);
				const productId = message.product_id;
				const currencyCode = productId.split('-')[0];
				const tickerTime = message.time ? new Date(message.time).getTime() / 1000 : null;

				// 1. Update global price state (for balances)
				if (currencyCode && !isNaN(price)) {
					updatePrice(currencyCode, price); // Use the helper function
                    scheduleBalanceUpdate(); // Schedule UI update
				}

				// 2. Update chart state (if message matches subscribed product)
				if (productId === currentSubscribedProductId && !isNaN(price)) {
					lastTickerPrice.set(price);

					// Update last candle in rawData store
					if (tickerTime) {
						rawData.update($data => {
							if ($data.length === 0) return $data; // No data to update

							const lastCandleIndex = $data.length - 1;
							const lastCandle = $data[lastCandleIndex]; // [time, l, h, o, c, v]
							const gran = get(currentGranularity);

							if (lastCandle && lastCandle.length >= 5 && gran > 0) {
								const candleStartTime = lastCandle[0];
								const candleEndTime = candleStartTime + gran;

								if (tickerTime >= candleStartTime && tickerTime < candleEndTime) {
									let changed = false;
									// Update close price
									if (lastCandle[4] !== price) {
										lastCandle[4] = price;
										changed = true;
									}
									// Update high price
									if (price > lastCandle[2]) {
										lastCandle[2] = price;
										changed = true;
									}
									// Update low price
									if (price < lastCandle[1]) {
										lastCandle[1] = price;
										changed = true;
									}

									if (changed) {
										// console.log(`WS: Updating last candle for ${productId}`, lastCandle);
                                        // Svelte reactivity: returning a *new* array reference if changed,
                                        // otherwise the old one to prevent unnecessary updates.
                                        // Modifying in place AND returning $data works for top-level array changes.
                                        // For nested changes, return [...$data] might be safer, but check perf.
                                        return $data;
									}
								}
							}
                            return $data; // Return unchanged data if no update needed
						});
                        // If rawData was updated, trigger throttled redraw (indirectly)
                        // This relies on components reacting to rawData changes.
                        // throttledChartUpdate(); // Maybe not needed if rawData update triggers reaction
					}
				}
			} else if (message.type === 'subscriptions') {
				console.log('WS: Subscriptions confirmed:', message.channels);
			} else if (message.type === 'error') {
				console.error('WS: Error message received:', message.message, message.reason);
			}

		} catch (error) {
			console.error('WS: Error processing message:', error, event.data);
		}
	};

	ws.onerror = (error) => {
		console.error('WS: WebSocket error event:', error);
		isConnecting = false; // Reset flag on error
		// onclose will handle reconnect logic
	};

	ws.onclose = (event) => {
		console.log(`WS: Connection closed. Code: ${event.code}, Reason: "${event.reason || 'N/A'}", Clean: ${event.wasClean}`);
		isConnecting = false;
		ws = null;
		currentSubscribedProductId = null;
		lastTickerPrice.set(null); // Clear live price

		// Clear timeouts
		if (reconnectTimeoutId) clearTimeout(reconnectTimeoutId);
		if (chartRedrawTimeoutId) clearTimeout(chartRedrawTimeoutId);
        if (balanceUpdateTimeoutId) clearTimeout(balanceUpdateTimeoutId);
		reconnectTimeoutId = null;
		chartRedrawTimeoutId = null;
        balanceUpdateTimeoutId = null;


		if (!intentionalClose) {
			console.log('WS: Attempting reconnect in 5 seconds...');
			reconnectTimeoutId = setTimeout(connect, 5000);
		} else {
			console.log('WS: Intentional close, not reconnecting.');
		}
	};
}

export function initializeWebSocket() {
	connect();
}

export function closeWebSocket() {
	if (reconnectTimeoutId) {
		clearTimeout(reconnectTimeoutId);
		reconnectTimeoutId = null;
	}
	if (ws) {
		console.log('WS: Closing connection intentionally.');
		intentionalClose = true;
		ws.close(1000, 'Client initiated close');
		ws = null; // Ensure ws is nullified immediately
        currentSubscribedProductId = null;
        lastTickerPrice.set(null);
	}
}

// Call this if the product ID changes in the UI
export function updateWebSocketSubscription(newProductId: string) {
    if (!newProductId || newProductId === currentSubscribedProductId) {
        return; // No change or invalid new ID
    }

    console.log(`WS: Product ID changed to ${newProductId}. Reconnecting websocket.`);
    closeWebSocket(); // Close existing connection cleanly
    // Set the new product ID in the store, which connect() will read
    currentProductId.set(newProductId);
    // Short delay before reconnecting to allow full closure
    setTimeout(connect, 200);
}