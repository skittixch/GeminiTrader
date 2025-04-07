// FILE: src/lib/utils/api.ts
import { API_BASE_URL } from './constants';
import type { RawCandleData, Account, Order, ApiError } from '$lib/types';

// Helper to handle fetch responses and potential errors
async function handleApiResponse<T>(response: Response, context: string): Promise<T> {
    const status = response.status;
    let data;
    try {
        data = await response.json();
    } catch (e) {
        // Handle cases where response is not JSON (e.g., 502 Bad Gateway HTML)
        const textResponse = await response.text();
        console.error(`[API Fetch Error - ${context}] Non-JSON response (Status: ${status}):`, textResponse);
        throw new Error(`Server returned non-JSON response (${status}) during ${context}`);
    }

    if (!response.ok) {
        const errorMsg = data?.error || `API Error (${status}) during ${context}`;
        const errorDetails = data?.details || '(No details provided)';
        console.error(`[API Fetch Error - ${context}] Status: ${status}`, errorMsg, errorDetails);
        const error: Error & { details?: any } = new Error(errorMsg);
        error.details = errorDetails;
        throw error;
    }
    return data as T;
}

// --- API Fetch Functions ---

export async function checkApiStatus(): Promise<{ credentials_loaded: boolean }> {
    try {
        const response = await fetch(`${API_BASE_URL}/status`);
        // Don't use handleApiResponse here as we expect specific boolean field
        if (!response.ok) {
             throw new Error(`Failed to check API status: ${response.status} ${response.statusText}`);
        }
        const data = await response.json();
        if (typeof data.credentials_loaded !== 'boolean') {
             throw new Error('Invalid response format from /api/status');
        }
        return data;
    } catch (error) {
        console.error("Error in checkApiStatus:", error);
        return { credentials_loaded: false }; // Assume false on error
    }
}


export async function fetchCandles(productId: string, granularity: number): Promise<RawCandleData[]> {
    const url = `${API_BASE_URL}/candles?product_id=${productId}&granularity=${granularity}`;
    console.log(`[API] Fetching candles: ${url}`);
    const response = await fetch(url);
    const data = await handleApiResponse<{ candles: RawCandleData[] } | RawCandleData[] >(response, 'fetchCandles');

    // Backend might return { candles: [...] } or just [...]
    if (Array.isArray(data)) {
        return data;
    } else if (data && Array.isArray(data.candles)) {
        return data.candles;
    } else {
        console.warn("[API] Unexpected candle data format:", data);
        return [];
    }
}

export async function fetchAccounts(): Promise<Account[]> {
    const url = `${API_BASE_URL}/accounts`;
    console.log(`[API] Fetching accounts: ${url}`);
    const response = await fetch(url);
    const data = await handleApiResponse<{ accounts: Account[] }>(response, 'fetchAccounts');
    return data?.accounts || [];
}

export async function fetchOpenOrders(): Promise<Order[]> {
    const url = `${API_BASE_URL}/open_orders`;
    console.log(`[API] Fetching open orders: ${url}`);
    const response = await fetch(url);
    const data = await handleApiResponse<{ orders: Order[] }>(response, 'fetchOpenOrders');
    return data?.orders || [];
}


export async function fetchTickerPrice(productId: string): Promise<number | null> {
    const url = `${API_BASE_URL}/ticker?product_id=${productId}`;
    try {
        const response = await fetch(url);
        const data = await handleApiResponse<{ product_id: string, price: string }>(response, `fetchTickerPrice (${productId})`);
        const price = parseFloat(data.price);
        return !isNaN(price) ? price : null;
    } catch (error) {
        console.warn(`[API] Failed to fetch ticker for ${productId}:`, error);
        return null; // Don't throw, just return null on failure
    }
}