<script lang="ts">
	let { width = 34, label = false }: { width?: number; label?: boolean } = $props();
</script>

<svg
	{width}
	height={Math.round((width * 52) / 84)}
	viewBox="0 0 84 52"
	role={label ? 'img' : undefined}
	aria-label={label ? 'Platedex logo' : undefined}
	aria-hidden={label ? undefined : 'true'}
>
	<rect x="2.5" y="2.5" width="79" height="47" rx="8" fill="none" stroke="currentColor" stroke-width={width > 60 ? 3 : 4.5} />
	{#if width > 60}
		<circle cx="13" cy="11" r="2.5" fill="currentColor" /><circle cx="71" cy="11" r="2.5" fill="currentColor" />
	{/if}
	<text
		x="42"
		y="35"
		text-anchor="middle"
		font-family="JetBrains Mono, monospace"
		font-weight="800"
		font-size="21"
		letter-spacing="3"
		fill="currentColor">PDX</text
	>
</svg>
