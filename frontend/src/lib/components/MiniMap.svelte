<script lang="ts">
	// Tiny schematic map for list rows: a rough outline of the contiguous US with a dot per place.
	let { points, label }: { points: [number, number][]; label: string } = $props();

	const US: [number, number][] = [
		[-124.7, 48.4], [-123, 49], [-95.2, 49], [-94.8, 49.4], [-89.6, 48], [-84.8, 46.5], [-82.5, 45.3],
		[-82.4, 43], [-83.1, 42], [-79, 42.8], [-76.3, 44.2], [-75, 45], [-71.5, 45], [-70, 46.7], [-69.2, 47.4],
		[-67.8, 47.1], [-67, 44.8], [-70.6, 43], [-70, 41.8], [-71.9, 41.3], [-74, 40.6], [-74, 39], [-75.6, 38],
		[-76, 36.9], [-75.5, 35.2], [-77.9, 34], [-79.2, 33.2], [-81, 31.7], [-81.3, 30], [-80, 26.7], [-80.4, 25.2],
		[-81.1, 25.1], [-82, 26.5], [-82.8, 28], [-83, 29.1], [-84.3, 30], [-86, 30.4], [-88, 30.4], [-89.6, 30.2],
		[-89.4, 29], [-91, 29.2], [-93.8, 29.7], [-95, 29], [-97.2, 27.6], [-97.4, 26], [-99.1, 26.4], [-100.3, 28],
		[-101.4, 29.8], [-102.4, 29.8], [-103.2, 29], [-104.5, 29.6], [-106.5, 31.8], [-108.2, 31.8], [-108.2, 31.3],
		[-111, 31.3], [-114.8, 32.5], [-117.1, 32.5], [-118.5, 34], [-120.6, 34.6], [-121.9, 36.6], [-122.5, 37.8],
		[-123.8, 39.8], [-124.4, 42], [-124, 46.3]
	];
	const K = Math.cos((38 * Math.PI) / 180);

	const view = $derived.by(() => {
		const inUS = points.every(([lat, lon]) => lat > 24 && lat < 50 && lon > -125 && lon < -66);
		let minLon = -125.5, maxLon = -66, minLat = 24, maxLat = 49.8;
		if (!inUS && points.length) {
			minLon = Math.min(...points.map((p) => p[1])) - 2;
			maxLon = Math.max(...points.map((p) => p[1])) + 2;
			minLat = Math.min(...points.map((p) => p[0])) - 2;
			maxLat = Math.max(...points.map((p) => p[0])) + 2;
		}
		const w = (maxLon - minLon) * K;
		const h = maxLat - minLat;
		const x = (lon: number) => (((lon - minLon) * K) / w) * 100;
		const y = (lat: number) => ((maxLat - lat) / h) * 64;
		const seen = new Set<string>();
		const dots = points
			.map(([lat, lon]) => ({ x: x(lon), y: y(lat) }))
			.filter((d) => {
				const k = `${Math.round(d.x)}:${Math.round(d.y)}`;
				if (seen.has(k)) return false;
				seen.add(k);
				return true;
			});
		const outline = inUS ? 'M' + US.map(([lo, la]) => `${x(lo).toFixed(1)} ${y(la).toFixed(1)}`).join('L') + 'Z' : '';
		return { dots, outline };
	});
</script>

<div class="mini" role="img" aria-label={label}>
	<svg viewBox="0 0 100 64" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
		{#if view.outline}<path d={view.outline} class="land" />{/if}
		{#each view.dots as d}<circle cx={d.x} cy={d.y} r="4.2" class="dot" />{/each}
	</svg>
</div>

<style>
	.mini {
		width: 80px;
		height: 54px;
		border-radius: 8px;
		overflow: hidden;
		flex: none;
		background: var(--map-bg);
		border: 1px solid var(--line);
	}
	svg {
		width: 100%;
		height: 100%;
		display: block;
	}
	.land {
		fill: var(--surface);
		stroke: var(--line);
		stroke-width: 1;
		opacity: 0.9;
	}
	.dot {
		fill: var(--accent);
		stroke: var(--surface);
		stroke-width: 1.5;
	}
</style>
