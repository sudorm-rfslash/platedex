<script lang="ts">
	import '../app.css';
	import Toast from '#lib/components/Toast.svelte';
	import { loadConfig } from '#lib/state/session.svelte.ts';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
	loadConfig().catch(() => {});
	if ('serviceWorker' in navigator && location.protocol === 'https:') {
		navigator.serviceWorker.register('/sw.js').catch(() => {});
	}
</script>

{@render children()}
<Toast />
