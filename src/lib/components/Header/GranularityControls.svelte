<script lang="ts">
	import { currentGranularity, granularityOptions } from '$lib/stores/settings';
	// No need to dispatch events, just update the store
</script>

<div class="granularity-controls" id="granularity-controls">
	<span>Interval:</span>
	{#each granularityOptions as g}
		<button
			data-granularity={g.value}
			class:active={$currentGranularity === g.value}
			on:click={() => currentGranularity.set(g.value)}
		>
			{g.label}
		</button>
	{/each}
</div>

<!-- Styles in app.css -->
<style>
	/* Styles are in app.css */
</style>
