<script lang="ts">
	// Stroke icons lifted from the design prototype.
	const P: Record<string, string> = {
		upload: '<path d="M12 15V4M7 9l5-5 5 5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
		review: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 12l3 3 5-6"/>',
		plates: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6.5 12h3M12 12h5.5"/>',
		map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>',
		camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
		pin: '<path d="M12 21s-6-5.5-6-11a6 6 0 0 1 12 0c0 5.5-6 11-6 11z"/><circle cx="12" cy="10" r="2.2"/>',
		'pin-off': '<path d="M12 21s-6-5.5-6-11a6 6 0 0 1 12 0c0 5.5-6 11-6 11z"/><path d="M4 4l16 16"/>',
		close: '<path d="M6 6l12 12M18 6 6 18"/>',
		x: '<path d="M8 8l8 8M16 8l-8 8"/>',
		check: '<path d="m5 12 5 5 9-10"/>',
		search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
		help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/><path d="M12 17.5h.01"/>',
		filter: '<path d="M4 6h16M7 12h10M10 18h4"/>',
		link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
		heat: '<path d="M12 3c2 3 5 5 5 9a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-8z"/>',
		radius: '<circle cx="12" cy="12" r="8" stroke-dasharray="3 3"/><circle cx="12" cy="12" r="1.5"/><path d="M12 12h8"/>',
		locate: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/><circle cx="12" cy="12" r="7"/>',
		lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
		clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
		plus: '<path d="M12 5v14M5 12h14"/>',
		minus: '<path d="M5 12h14"/>',
		type: '<path d="M5 7V5h14v2M12 5v14M9 19h6"/>',
		box: '<path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4"/>',
		back: '<path d="m15 6-6 6 6 6"/>',
		chevron: '<path d="m9 6 6 6-6 6"/>',
		merge: '<path d="M7 4v5a5 5 0 0 0 5 5h0a5 5 0 0 1 5 5v1M17 4v5a5 5 0 0 1-5 5"/>',
		split: '<path d="M12 20v-6M12 14 6 8M12 14l6-6M6 4v4h4M18 4v4h-4"/>',
		warn: '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/>',
		spinner: '<path d="M12 3a9 9 0 1 0 9 9"/>',
		id: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2.2"/><path d="M5.8 16.5a3.4 3.4 0 0 1 6.4 0M14.5 10h4M14.5 13.5h3"/>',
		download: '<path d="M12 4v11M7 10l5 5 5-5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
		edit: '<path d="M4 20h4L19 9l-4-4L4 16v4z"/>',
		trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
		refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>'
	};
	let {
		name,
		size = 22,
		stroke = 1.9,
		class: cls = '',
		style = ''
	}: { name: string; size?: number; stroke?: number; class?: string; style?: string } = $props();
</script>

{#if name === 'more'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" class={cls} {style}>
		<circle cx="5" cy="12" r="1.7" /><circle cx="12" cy="12" r="1.7" /><circle cx="19" cy="12" r="1.7" />
	</svg>
{:else}
	<svg
		width={size}
		height={size}
		viewBox="0 0 24 24"
		fill="none"
		stroke="currentColor"
		stroke-width={stroke}
		stroke-linecap="round"
		stroke-linejoin="round"
		aria-hidden="true"
		class={cls}
		{style}
	>
		{@html P[name] ?? ''}
	</svg>
{/if}
