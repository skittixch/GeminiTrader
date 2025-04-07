// FILE: src/lib/types/index.ts

// Raw candle data from backend (timestamp, low, high, open, close, volume)
export type RawCandleData = [number, number, number, number, number, number];

// Processed candle data (e.g., with Date object) - Optional if needed
export interface Candle {
	time: number; // Unix timestamp (seconds)
	low: number;
	high: number;
	open: number;
	close: number;
	volume: number;
}

// Account data structure (based on Coinbase SDK response)
export interface BalanceValue {
	value: string;
	currency: string;
}

export interface Account {
	uuid: string;
	name: string;
	currency: string;
	available_balance: BalanceValue;
	default: boolean;
	active: boolean;
	created_at: string; // ISO timestamp
	updated_at: string; // ISO timestamp
	deleted_at: string | null;
	type: string;
	ready: boolean;
	hold: BalanceValue;
	// Calculated fields added in frontend
	totalBalance?: number;
	usdValue?: number | null;
}

// Order data structure (based on Coinbase SDK response)
// Note: This is complex, adjust based on actual API fields needed
export interface OrderConfiguration {
	limit_limit_gtd?: { // Example for Limit GTD
		base_size: string;
		limit_price: string;
		post_only: boolean;
		end_time?: string;
	};
	limit_limit_gtc?: { // Example for Limit GTC
		base_size: string;
		limit_price: string;
		post_only: boolean;
	};
	market_market_ioc?: { // Example for Market IOC
		base_size?: string; // Either base or quote
		quote_size?: string;
	};
	// Add other order types (STOP_LIMIT, etc.) if needed
	[key: string]: any; // Allow other potential config types
}

export interface Order {
	order_id: string;
	product_id: string;
	user_id?: string; // May not be present depending on API/context
	order_configuration: OrderConfiguration;
	side: 'BUY' | 'SELL' | string; // Allow for unknown string values initially
	client_order_id: string;
	status: 'OPEN' | 'FILLED' | 'CANCELLED' | 'EXPIRED' | 'FAILED' | 'PENDING' | string;
	time_in_force: 'GOOD_UNTIL_DATE_TIME' | 'GOOD_UNTIL_CANCELLED' | 'IMMEDIATE_OR_CANCEL' | 'FILL_OR_KILL' | string;
	created_time: string; // ISO timestamp
	completion_percentage: string; // e.g., "50.00"
	filled_size: string; // Base currency amount filled
	average_filled_price: string;
	fee: string; // Fees paid for this order
	number_of_fills: string;
	filled_value: string; // Quote currency amount filled
	pending_cancel: boolean;
	size_in_quote: boolean;
	total_fees: string;
	size_inclusive_of_fees: boolean;
	total_value_after_fees: string;
	trigger_status: string; // e.g., "INVALID_ORDER_TYPE"
	order_type: 'MARKET' | 'LIMIT' | 'STOP' | 'STOP_LIMIT' | string;
	reject_reason: string;
	settled: boolean;
	product_type: 'SPOT' | string;
	reject_message: string;
	cancel_message: string;
	// Calculated field for plotting
	plotTime?: number; // Unix timestamp (seconds)
	plotPrice?: number;
}

// Simplified structure for plotting orders on chart
export interface PlotOrder {
	id: string;
	time: number; // Unix timestamp (seconds)
	price: number;
	side: 'BUY' | 'SELL';
}

// Generic API Error structure
export interface ApiError {
	message: string;
	details?: string | object | null;
}

// Theme type
export type Theme = 'light' | 'dark';

// Granularity structure
export interface GranularityOption {
    label: string;
    value: number; // seconds
}