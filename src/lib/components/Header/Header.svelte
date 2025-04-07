<script lang="ts">
	import { onMount } from 'svelte';
	import GranularityControls from './GranularityControls.svelte';
	import SettingsDropdown from './SettingsDropdown.svelte';
	import { isApiReady, apiCheckError } from '$lib/stores/apiState';

	let showSettings = false;

	function toggleSettings() {
		showSettings = !showSettings;
	}

	function handleClickOutside(event: MouseEvent) {
		const settingsButton = document.getElementById('settings-button');
		const settingsDropdown = document.getElementById('settings-dropdown');

		if (
			showSettings &&
			settingsButton &&
			!settingsButton.contains(event.target as Node) &&
			settingsDropdown &&
			!settingsDropdown.contains(event.target as Node)
		) {
			showSettings = false;
		}
	}

	onMount(() => {
		window.addEventListener('click', handleClickOutside);
		return () => {
			window.removeEventListener('click', handleClickOutside);
		};
	});
</script>

<div class="header-area">
	<!-- Status Indicator (Positioned via CSS) -->
	<div class="top-left-info">
		<div class="status-indicator">
			API Status:
			{#if $apiCheckError}
				<span id="api-status-indicator" class="error" title={$apiCheckError}>Error</span>
			{:else if $isApiReady}
				<span id="api-status-indicator" class="loaded">Loaded</span>
			{:else}
				<span id="api-status-indicator" class="loading">Checking...</span>
			{/if}
		</div>
	</div>

	<!-- Centered Content -->
	<div class="header-content">
		<h1>Interactive BTC/USD Chart</h1>
		<p class="instructions">
			Scroll=Zoom | Drag Chart=Pan | Drag Axes=Scale | Dbl-Click=Reset | Hover=Info/Crosshair
		</p>
	</div>

	<!-- Right Aligned Controls -->
	<div class="header-controls">
		<GranularityControls />
		<div class="settings-group">
			<button
				id="settings-button"
				class="icon-button"
				title="Chart Settings"
				on:click|stopPropagation={toggleSettings}>⚙️</button
			>
			<SettingsDropdown bind:show={showSettings} />
		</div>
	</div>
</div>

<!-- Styles in app.css -->
<style>
	/* Styles are in app.css */
	.settings-group {
		position: relative; /* Needed for absolute positioning of dropdown */
	}
</style>
