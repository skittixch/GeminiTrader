// FILE: src/lib/stores/balanceState.ts
import { writable, derived } from 'svelte/store';
import type { Account } from '$lib/types';

// Full list of accounts from API
export const accounts = writable<Account[]>([]);

// Map of latest prices { 'BTC': 65000.12, 'ETH': 3400.50 }
export const latestPrices = writable<Map<string, number>>(new Map());

// Loading/Error state for balances
export const areBalancesLoading = writable<boolean>(true);
export const balanceError = writable<string | null>(null);

// Derived: Total Portfolio Value (Approx USD)
export const totalUsdValue = derived<[typeof accounts, typeof latestPrices], number>(
	[accounts, latestPrices],
	([$accounts, $prices]) => {
		let total = 0;
		$accounts.forEach(acc => {
			const currency = acc.currency.toUpperCase();
			const available = parseFloat(acc.available_balance?.value ?? '0');
			const hold = parseFloat(acc.hold?.value ?? '0');
			const totalBalance = available + hold;

			if (isNaN(totalBalance) || totalBalance === 0) return;

			let usdValue = 0;
			if (currency === 'USD') {
				usdValue = totalBalance;
			} else if (currency === 'USDT' || currency === 'USDC') {
				usdValue = totalBalance * 1.0; // Assume stablecoins are $1
			} else {
				const price = $prices.get(currency);
				if (price !== undefined && price !== null && Number.isFinite(price)) {
					usdValue = totalBalance * price;
				} else {
					// Cannot calculate value if price is missing for non-stablecoin
					return; // Skip this asset in total calculation
				}
			}
			total += usdValue;
		});
		return total;
	}
);

// Derived: Flag indicating if total value is partial due to missing prices
export const isTotalValuePartial = derived<[typeof accounts, typeof latestPrices], boolean>(
    [accounts, latestPrices],
    ([$accounts, $prices]) => {
        return $accounts.some(acc => {
            const currency = acc.currency.toUpperCase();
            const available = parseFloat(acc.available_balance?.value ?? '0');
            const hold = parseFloat(acc.hold?.value ?? '0');
            const totalBalance = available + hold;

            if (isNaN(totalBalance) || totalBalance === 0) return false; // Ignore zero balance

            // Is it a crypto we NEED a price for?
            const needsPrice = currency !== 'USD' && currency !== 'USDT' && currency !== 'USDC';
            if (!needsPrice) return false; // Doesn't need price, doesn't make total partial

            // Do we HAVE a valid price?
            const price = $prices.get(currency);
            const hasValidPrice = price !== undefined && price !== null && Number.isFinite(price);

            return !hasValidPrice; // If it needs a price but doesn't have one, total is partial
        });
    }
);

// Add helper function to update a single price - avoids direct map manipulation elsewhere
export function updatePrice(currencyCode: string, price: number) {
	if (currencyCode && typeof currencyCode === 'string' && price !== null && Number.isFinite(price)) {
		latestPrices.update(map => {
			map.set(currencyCode.toUpperCase(), price);
			return map; // Required by Svelte: return the updated value
		});
	}
}