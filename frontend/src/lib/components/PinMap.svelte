<script lang="ts">
	import { onMount } from 'svelte';

	let {
		lat = $bindable<number | null>(null),
		lon = $bindable<number | null>(null),
		height = 230
	}: { lat?: number | null; lon?: number | null; height?: number } = $props();

	let el: HTMLDivElement;

	onMount(() => {
		let map: import('maplibre-gl').Map | undefined;
		let dead = false;
		import('../map').then(({ createMap, maplibregl }) => {
			if (dead) return;
			const start: [number, number] | undefined = lat != null && lon != null ? [lon, lat] : undefined;
			map = createMap(el, { center: start, zoom: start ? 14 : 3.2 });
			const m = map;
			const dot = document.createElement('div');
			dot.className = 'pdx-pin';
			dot.innerHTML =
				'<svg width="34" height="34" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12z" fill="currentColor" stroke="#fff" stroke-width="1.5"/><circle cx="12" cy="10" r="2.6" fill="#fff"/></svg>';
			const marker = new maplibregl.Marker({ element: dot, anchor: 'bottom', draggable: true });
			if (start) marker.setLngLat(start).addTo(m);
			m.on('click', (e) => {
				marker.setLngLat(e.lngLat).addTo(m);
				lat = +e.lngLat.lat.toFixed(6);
				lon = +e.lngLat.lng.toFixed(6);
			});
			marker.on('dragend', () => {
				const p = marker.getLngLat();
				lat = +p.lat.toFixed(6);
				lon = +p.lng.toFixed(6);
			});
			if (!start && 'geolocation' in navigator) {
				navigator.geolocation.getCurrentPosition(
					(p) => m.jumpTo({ center: [p.coords.longitude, p.coords.latitude], zoom: 13 }),
					() => {},
					{ timeout: 4000, maximumAge: 600000 }
				);
			}
		});
		return () => {
			dead = true;
			map?.remove();
		};
	});
</script>

<div class="pm" style="height: {height}px" bind:this={el} aria-label="Map. Tap to place the pin; drag the pin to adjust."></div>

<style>
	.pm {
		border-radius: 12px;
		overflow: hidden;
		border: 1px solid var(--line);
		background: var(--map-bg);
		cursor: crosshair;
	}
	:global(.pdx-pin) {
		color: var(--accent);
		cursor: grab;
	}
</style>
