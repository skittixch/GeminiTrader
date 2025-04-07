// FILE: src/lib/stores/orderState.ts
import { writable, derived } from 'svelte/store';
import type { Order, PlotOrder } from '$lib/types';
import { formatTimestamp } from '$lib/utils/formatters'; // Assuming formatters exist

// Raw open orders fetched from the API
export const openOrders = writable<Order[]>([]);

// Loading/Error state for open orders
export const areOrdersLoading = writable<boolean>(false); // Initially false, set true when loading
export const ordersError = writable<string | null>(null);

// Derived: Orders formatted specifically for plotting on the chart
export const ordersToPlot = derived<typeof openOrders, PlotOrder[]>(
	openOrders,
	($openOrders) => {
		if (!$openOrders || $openOrders.length === 0) {
			return [];
		}
		return $openOrders
			.map((order): PlotOrder | null => {
				try {
					// Only plot open BUY limit orders for now
					const side = (order.side || "").toUpperCase();
					const type = (order.order_type || "").toUpperCase();
					const status = (order.status || "").toUpperCase();

					if (side !== 'BUY' || type !== 'LIMIT' || status !== 'OPEN') {
						return null;
					}

					const rawTime = order["created_time"];
					let timestamp: number | null = null;
					if (rawTime && typeof rawTime === 'string') {
						const dateObj = new Date(rawTime);
						if (dateObj instanceof Date && !isNaN(dateObj.getTime())) {
							timestamp = dateObj.getTime() / 1000; // Convert ms to seconds
						}
					}
					if (timestamp === null) return null; // Need time

					let price: number | null = null;
					const orderConfig = order["order_configuration"];
					const limitConfig = orderConfig?.limit_limit_gtd || orderConfig?.limit_limit_gtc;
					const limitPriceStr = limitConfig?.limit_price;
					if (limitPriceStr) {
						price = parseFloat(limitPriceStr);
						if (isNaN(price)) price = null;
					}
					if (price === null) return null; // Need price

					return {
						id: order.order_id,
						time: timestamp,
						price: price,
						side: side as 'BUY' | 'SELL', // We already filtered for BUY
					};
				} catch (error) {
					console.error("Error processing order for plotting:", order, error);
					return null;
				}
			})
			.filter((order): order is PlotOrder => order !== null); // Type guard to filter out nulls
	}
);