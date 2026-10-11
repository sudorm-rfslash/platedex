<script lang="ts">
	let {
		text,
		partial = false,
		size = 14,
		highlight = -1
	}: { text: string; partial?: boolean; size?: number; highlight?: number } = $props();
</script>

<span class="plate" class:partial style="font-size: {size}px">
	{#if highlight >= 0}
		{text.slice(0, highlight)}<span class="hl">{text[highlight]}</span>{text.slice(highlight + 1)}
	{:else}
		{text}
	{/if}
</span>

<style>
	.hl {
		background: var(--amber-bg);
		color: var(--amber-ink);
		border-bottom: 2px solid var(--amber-ink);
	}
</style>
