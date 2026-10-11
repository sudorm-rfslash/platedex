<script lang="ts">
	import Icon from './Icon.svelte';

	/** Shown under a setting that an environment variable controls (services/appsettings.py). */
	let { env }: { env?: string } = $props();
</script>

{#if env}
	<p class="lock"><Icon name="lock" size={14} stroke={2.2} style="flex: none" /><span>Set by <code class="mono">{env}</code> in the server environment. Remove it there to change it here.</span></p>
{/if}

<style>
	.lock {
		display: flex;
		gap: 6px;
		align-items: flex-start;
		font-size: 12.5px;
		color: var(--muted);
	}
	.lock :global(svg) {
		margin-top: 2px;
	}
	code {
		background: var(--surface2);
		padding: 0 4px;
		border-radius: 4px;
		font-size: 12px;
		color: var(--ink);
	}
</style>
