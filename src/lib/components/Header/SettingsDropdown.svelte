<!-- FILE: src/lib/components/Header/SettingsDropdown.svelte -->
<script lang="ts">
	import { theme, isLogScale, is12HourFormat } from '$lib/stores/settings';

    export let show = false; // Controlled by parent

    // Theme toggle specific helper
    function toggleTheme() {
        theme.update(current => current === 'light' ? 'dark' : 'light');
    }
</script>

{#if show}
<div id="settings-dropdown" class="dropdown-menu show" role="menu">
	<div class="dropdown-item" role="menuitem">
		<span>Dark Theme</span>
		<div class="theme-switch-wrapper">
			<label class="theme-switch" for="theme-checkbox">
				<input
                    type="checkbox"
                    id="theme-checkbox"
                    checked={$theme === 'dark'}  <!-- Use the checked ATTRIBUTE -->
                    on:change={toggleTheme}     <!-- Keep the on:change handler -->
                />
				<div class="slider"></div>
			</label>
		</div>
	</div>
	<div class="dropdown-item" role="menuitem">
         <!-- Keep bind:checked here for direct store binding -->
		<span>Log Scale (Y-Axis)</span>
		<div class="log-scale-switch-wrapper">
			<label class="theme-switch" for="log-scale-checkbox">
				<input type="checkbox" id="log-scale-checkbox" bind:checked={$isLogScale} />
				<div class="slider"></div>
			</label>
		</div>
	</div>
	<div class="dropdown-item" role="menuitem">
        <!-- Keep bind:checked here for direct store binding -->
		<span>12-Hour Time (AM/PM)</span>
		<div class="time-format-switch-wrapper">
			<label class="theme-switch" for="time-format-checkbox">
				<input type="checkbox" id="time-format-checkbox" bind:checked={$is12HourFormat} />
				<div class="slider"></div>
			</label>
		</div>
	</div>
</div>
{/if}

<!-- Styles can be in app.css or scoped here -->
<style>
    /* Styles are mostly in app.css */
	.dropdown-menu {
        position: absolute;
		top: calc(100% + 5px);
		right: 0;
		z-index: 120;
		display: block;
	}
</style>