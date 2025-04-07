// FILE: src/lib/stores/apiState.ts
import { writable } from 'svelte/store';

// Backend API readiness (based on credentials loading on server)
export const isApiReady = writable<boolean>(false);
export const apiCheckError = writable<string | null>(null);