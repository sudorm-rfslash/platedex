<script lang="ts">
	// Sightings of one plate on a real map, numbered by date and joined by a dashed route.
	import { onMount } from 'svelte';
	import type { GeoJSONSource, Map as MlMap, Marker } from 'maplibre-gl';

	type Pt = { n: number; lat: number; lon: number; dup?: boolean; label: string };
	let { points, height = 230 }: { points: Pt[]; height?: number } = $props();

	let el: HTMLDivElement;
	let map: MlMap | undefined;
	let markers: Marker[] = [];
	let lib: typeof import('../map') | undefined;

	function draw() {
		if (!map || !lib) return;
		const { maplibregl, cssVar, fitPoints } = lib;
		markers.forEach((m) => m.remove());
		markers = points.map((p) => {
			const d = document.createElement('div');
			d.className = 'pdx-mk' + (p.dup ? ' dup' : '');
			d.textContent = String(p.n);
			d.title = p.label;
			return new maplibregl.Marker({ element: d }).setLngLat([p.lon, p.lat]).addTo(map!);
		});
		const line = {
			type: 'Feature' as const,
			properties: {},
			geometry: { type: 'LineString' as const, coordinates: points.map((p) => [p.lon, p.lat]) }
		};
		const src = map.getSource('route') as GeoJSONSource | undefined;
		if (src) src.setData(line);
		else {
			map.addSource('route', { type: 'geojson', data: line });
			map.addLayer({
				id: 'route',
				type: 'line',
				source: 'route',
				paint: { 'line-color': cssVar('--accent'), 'line-width': 2.5, 'line-dasharray': [2.4, 1.6] },
				layout: { 'line-cap': 'round', 'line-join': 'round' }
			});
		}
		fitPoints(map, points.map((p) => [p.lon, p.lat]), 12, 36);
	}

	onMount(() => {
		let dead = false;
		import('../map').then((mod) => {
			if (dead) return;
			lib = mod;
			map = mod.createMap(el, { zoom: 3 });
			map.on('load', draw);
		});
		return () => {
			dead = true;
			map?.remove();
		};
	});

	$effect(() => {
		JSON.stringify(points);
		if (map?.loaded()) draw();
	});
</script>

<div class="rm" style="height: {height}px" bind:this={el}></div>

<style>
	.rm {
		border-radius: 12px;
		overflow: hidden;
		border: 1px solid var(--line);
		background: var(--map-bg);
	}
	:global(.pdx-mk) {
		width: 24px;
		height: 24px;
		border-radius: 50%;
		background: var(--accent);
		color: var(--accent-ink);
		font: 800 12px 'Public Sans', sans-serif;
		display: flex;
		align-items: center;
		justify-content: center;
		border: 2px solid var(--surface);
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
	}
	:global(.pdx-mk.dup) {
		background: #b4441a;
		color: #fff;
	}
</style>
