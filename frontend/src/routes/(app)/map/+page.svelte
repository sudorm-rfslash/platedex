<script lang="ts">
	import { page } from '$app/state';
	import { api, errorText } from '#lib/api.ts';
	import FilterPanel from '#lib/components/FilterPanel.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import PlateChip from '#lib/components/PlateChip.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { plural } from '#lib/format.ts';
	import { chips, filterParams, filters, saveFilters } from '#lib/state/filters.svelte.ts';
	import { flash } from '#lib/state/toast.svelte.ts';
	import { circle, milesBetween } from '#lib/geoutil.ts';
	import type { GeoJSONSource, Map as MlMap } from 'maplibre-gl';
	import { onMount } from 'svelte';

	type Feat = { type: 'Feature'; geometry: { type: 'Point'; coordinates: [number, number] }; properties: { sid: number; pid: number; text: string; state: string; partial: boolean; seen: string; user: string } };
	type Result = { pid: number; text: string; state: string; partial: boolean; n: number; last: string };

	const MILES = [1, 2, 5, 10, 25, 50, 100, 250, 500];
	let el: HTMLDivElement;
	let map: MlMap | undefined;
	let lib: typeof import('#lib/map.ts') | undefined;
	let feats = $state.raw<Feat[]>([]);
	let heat = $state(false);
	let radius = $state(!!filters.area || page.url.searchParams.get('radius') === '1');
	let center = $state<{ lat: number; lon: number }>(filters.area ? { lat: filters.area.lat, lon: filters.area.lon } : { lat: 39.5, lon: -98.35 });
	let mi = $state(filters.area?.mi ?? 25);
	let selected = $state<{ title: string; pids: Set<number>; sids: Set<number> } | null>(null);
	let inView = $state<Set<number>>(new Set());
	let fOpen = $state(false);
	let meta = $state<any>(null);
	let snap = $state(1);
	let error = $state('');
	let fitted = false;
	let ready = $state(false);

	const SNAP = [{ h: 150, name: 'peek' }, { h: 370, name: 'half' }, { h: 640, name: 'full' }];
	const mapFilterChips = $derived(chips({ ...filters, area: null }));

	// The map shows every sighting that passes the shared filters except the area; the area drives the list.
	async function fetchPoints() {
		try {
			const params = { ...filterParams({ ...filters, area: null, missing: false }) };
			const fc = await api.get<{ features: Feat[] }>('/api/map/points', params);
			feats = fc.features;
			error = '';
		} catch (e) {
			error = errorText(e);
		}
	}

	$effect(() => {
		JSON.stringify({ ...filters, area: null });
		const t = setTimeout(fetchPoints, 150);
		return () => clearTimeout(t);
	});

	function setData() {
		if (!map || !ready) return;
		const data = { type: 'FeatureCollection' as const, features: feats };
		(map.getSource('pts') as GeoJSONSource)?.setData(data);
		(map.getSource('heatsrc') as GeoJSONSource)?.setData(data);
		if (!fitted && feats.length && !radius && lib) {
			lib.fitPoints(map, feats.map((f) => f.geometry.coordinates), 11, 60);
			fitted = true;
		}
		updateInView();
	}

	$effect(() => {
		feats;
		ready;
		setData();
	});

	function ring() {
		if (!map || !ready) return;
		const src = map.getSource('ring') as GeoJSONSource | undefined;
		const empty = { type: 'FeatureCollection' as const, features: [] };
		src?.setData(radius ? circle(center.lat, center.lon, mi) : empty);
		(map.getSource('ctr') as GeoJSONSource | undefined)?.setData(
			radius ? { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [center.lon, center.lat] } } : empty
		);
	}

	$effect(() => {
		radius;
		center;
		mi;
		ready;
		ring();
	});

	// Keep the shared area filter in step with the radius tool so the Plates list matches.
	let labelSeq = 0;
	$effect(() => {
		if (!radius) {
			if (filters.area) {
				filters.area = null;
				saveFilters();
			}
			return;
		}
		const c = { ...center };
		const m = mi;
		const my = ++labelSeq;
		const t = setTimeout(async () => {
			let label = `${c.lat.toFixed(2)}, ${c.lon.toFixed(2)}`;
			try {
				label = (await api.get('/api/geo/reverse', { lat: c.lat, lon: c.lon })).place;
			} catch {
				/* keep coordinates */
			}
			if (my !== labelSeq) return;
			filters.area = { lat: +c.lat.toFixed(5), lon: +c.lon.toFixed(5), mi: m, label };
			saveFilters();
		}, 300);
		return () => clearTimeout(t);
	});

	$effect(() => {
		if (map && ready) {
			map.setLayoutProperty('heat', 'visibility', heat ? 'visible' : 'none');
			for (const id of ['clusters', 'cluster-count', 'point']) map.setLayoutProperty(id, 'visibility', heat ? 'none' : 'visible');
		}
	});

	function updateInView() {
		if (!map) return;
		const b = map.getBounds();
		inView = new Set(feats.filter((f) => b.contains(f.geometry.coordinates)).map((f) => f.properties.sid));
	}

	const pool = $derived.by(() => {
		if (radius) return feats.filter((f) => milesBetween(center, { lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] }) <= mi);
		if (selected) return feats.filter((f) => selected!.sids.has(f.properties.sid));
		return feats.filter((f) => inView.has(f.properties.sid));
	});

	const results = $derived.by(() => {
		const by = new Map<number, Result>();
		for (const f of pool) {
			const p = f.properties;
			const r = by.get(p.pid) ?? { pid: p.pid, text: p.text, state: p.state, partial: p.partial, n: 0, last: '' };
			r.n++;
			if (p.seen > r.last) r.last = p.seen;
			by.set(p.pid, r);
		}
		return [...by.values()].sort((a, b) => b.n - a.n || b.last.localeCompare(a.last));
	});

	const title = $derived(
		radius ? `Within ${mi} mi of ${filters.area?.label ?? `${center.lat.toFixed(2)}, ${center.lon.toFixed(2)}`}` : selected ? selected.title : 'In view'
	);
	const sub = $derived(`${plural(results.length, 'plate')} · ${plural(pool.length, 'sighting')}`);

	onMount(() => {
		api.get('/api/meta').then((m) => (meta = m)).catch(() => {});
		let dead = false;
		import('#lib/map.ts').then((mod) => {
			if (dead) return;
			lib = mod;
			setup(mod);
		});
		return () => {
			dead = true;
			map?.remove();
		};
	});

	function setup({ createMap, cssVar, maplibregl }: typeof import('#lib/map.ts')) {
		map = createMap(el, { center: [center.lon, center.lat], zoom: filters.area ? 8 : 3.4 });
		map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
		map.on('load', () => {
			const accent = cssVar('--accent');
			const accentInk = cssVar('--accent-ink');
			const surface = cssVar('--surface');
			const empty = { type: 'FeatureCollection' as const, features: [] };
			map!.addSource('pts', { type: 'geojson', data: empty, cluster: true, clusterRadius: 48, clusterMaxZoom: 14 });
			map!.addSource('heatsrc', { type: 'geojson', data: empty });
			map!.addSource('ring', { type: 'geojson', data: empty });
			map!.addSource('ctr', { type: 'geojson', data: empty });
			map!.addLayer({
				id: 'heat',
				type: 'heatmap',
				source: 'heatsrc',
				layout: { visibility: 'none' },
				paint: {
					'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 2, 18, 10, 40],
					'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 2, 0.8, 10, 2],
					'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(250,204,21,0)', 0.3, 'rgba(250,204,21,.45)', 0.6, 'rgba(245,158,11,.7)', 1, 'rgba(220,38,38,.85)']
				}
			});
			map!.addLayer({ id: 'ring-fill', type: 'fill', source: 'ring', paint: { 'fill-color': accent, 'fill-opacity': 0.08 } });
			map!.addLayer({ id: 'ring-line', type: 'line', source: 'ring', paint: { 'line-color': accent, 'line-width': 2.5, 'line-dasharray': [2, 1.5] } });
			map!.addLayer({ id: 'ctr', type: 'circle', source: 'ctr', paint: { 'circle-radius': 6, 'circle-color': surface, 'circle-stroke-color': accent, 'circle-stroke-width': 3 } });
			map!.addLayer({
				id: 'clusters',
				type: 'circle',
				source: 'pts',
				filter: ['has', 'point_count'],
				paint: {
					'circle-color': accent,
					'circle-radius': ['interpolate', ['linear'], ['get', 'point_count'], 2, 17, 25, 26, 100, 34],
					'circle-stroke-width': 3,
					'circle-stroke-color': surface
				}
			});
			map!.addLayer({
				id: 'cluster-count',
				type: 'symbol',
				source: 'pts',
				filter: ['has', 'point_count'],
				layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 14, 'text-font': ['Noto Sans Bold'] },
				paint: { 'text-color': accentInk }
			});
			map!.addLayer({
				id: 'point',
				type: 'circle',
				source: 'pts',
				filter: ['!', ['has', 'point_count']],
				paint: { 'circle-color': accent, 'circle-radius': 8, 'circle-stroke-width': 2.5, 'circle-stroke-color': surface }
			});
			ready = true;
		});

		map.on('click', 'clusters', async (e) => {
			e.preventDefault();
			const f = e.features![0];
			const src = map!.getSource('pts') as GeoJSONSource;
			const leaves = (await src.getClusterLeaves(f.properties!.cluster_id, 1000, 0)) as unknown as Feat[];
			const [lon, lat] = (f.geometry as any).coordinates;
			let near = 'here';
			try {
				near = (await api.get('/api/geo/reverse', { lat, lon })).place;
			} catch {
				/* coords */
			}
			selected = { title: `Near ${near}`, pids: new Set(leaves.map((l) => l.properties.pid)), sids: new Set(leaves.map((l) => l.properties.sid)) };
			snap = Math.max(1, snap);
		});
		map.on('click', 'point', (e) => {
			e.preventDefault();
			const p = e.features![0].properties as Feat['properties'];
			selected = { title: `${p.text}${p.state ? ' · ' + p.state : ''}`, pids: new Set([p.pid]), sids: new Set([p.sid]) };
			snap = Math.max(1, snap);
		});
		map.on('click', (e) => {
			if ((e as any).defaultPrevented) return;
			if (radius) center = { lat: e.lngLat.lat, lon: e.lngLat.lng };
			else selected = null;
		});
		for (const id of ['clusters', 'point']) {
			map.on('mouseenter', id, () => (map!.getCanvas().style.cursor = 'pointer'));
			map.on('mouseleave', id, () => (map!.getCanvas().style.cursor = radius ? 'crosshair' : ''));
		}
		map.on('moveend', updateInView);
	}

	$effect(() => {
		if (map) map.getCanvas().style.cursor = radius ? 'crosshair' : '';
	});

	function toggleRadius() {
		radius = !radius;
		selected = null;
		if (radius && map) {
			const c = map.getCenter();
			center = { lat: c.lat, lon: c.lng };
		}
	}

	function locate() {
		if (!('geolocation' in navigator)) return flash('This browser has no location access');
		navigator.geolocation.getCurrentPosition(
			(p) => {
				const c = { lat: p.coords.latitude, lon: p.coords.longitude };
				map?.flyTo({ center: [c.lon, c.lat], zoom: Math.max(map.getZoom(), 10) });
				if (radius) center = c;
			},
			() => flash('Allow location to center the map on you'),
			{ timeout: 8000, maximumAge: 120000 }
		);
	}

	let y0: number | null = null;
	function hUp(e: PointerEvent) {
		const dy = y0 == null ? 0 : e.clientY - y0;
		y0 = null;
		if (dy < -30) snap = Math.min(2, snap + 1);
		else if (dy > 30) snap = Math.max(0, snap - 1);
		else snap = (snap + 1) % 3;
	}
	const milesIdx = $derived(Math.max(0, MILES.findIndex((m) => m >= mi)));
</script>

<svelte:head><title>Platedex · Map</title></svelte:head>

<div class="wrap">
	<div class="mapbox">
		<div class="map" bind:this={el}></div>

		<div class="overlay top">
			<div class="row">
				<button class="btn mobile-only shadow" onclick={() => (fOpen = true)}>
					<Icon name="filter" size={18} stroke={2} />Filters
					{#if mapFilterChips.length}<span class="badge" style="background: var(--accent); color: var(--accent-ink)">{mapFilterChips.length}</span>{/if}
				</button>
				<a href="/plates" class="syncpill" aria-label="Filters are synced with the Plates list"><Icon name="link" size={14} stroke={2.2} />Synced with Plates list</a>
			</div>
			{#if mapFilterChips.length}
				<div class="row wrapr">{#each mapFilterChips as c}<span class="mchip">{c.label}</span>{/each}</div>
			{/if}
			{#if error}<p class="err">{error}</p>{/if}
		</div>

		<div class="overlay fabs">
			<button class="fab" class:on={heat} aria-pressed={heat} aria-label="Heatmap" title="Heatmap" onclick={() => (heat = !heat)}><Icon name="heat" /></button>
			<button class="fab" class:on={radius} aria-pressed={radius} aria-label="Draw a radius" title="Radius" onclick={toggleRadius}><Icon name="radius" /></button>
			<button class="fab" aria-label="Center on me" title="Center on me" onclick={locate}><Icon name="locate" /></button>
		</div>

		{#if radius}
			<div class="overlay rpanel">
				<span style="font-size: 12.5px; font-weight: 700">Tap the map to move the center</span>
				<label class="rl">Radius · {mi} mi
					<input type="range" min="0" max={MILES.length - 1} step="1" value={milesIdx} oninput={(e) => (mi = MILES[+e.currentTarget.value])} />
				</label>
			</div>
		{/if}

		<div class="sheet mobile-only" style="height: {SNAP[snap].h}px" aria-label="Results">
			<button class="handle" onpointerdown={(e) => (y0 = e.clientY)} onpointerup={hUp} onkeydown={(e) => (e.key === 'ArrowUp' ? (snap = Math.min(2, snap + 1)) : e.key === 'ArrowDown' && (snap = Math.max(0, snap - 1)))} aria-label="Resize results sheet: {SNAP[snap].name}"><span></span></button>
			<div class="shead"><h2>{title}</h2><span class="muted">{sub}</span></div>
			<div class="slist">
				{#each results as r (r.pid)}
					<a href="/plates/{r.pid}" class="rrow"><PlateChip text={r.text} partial={r.partial} /><span class="stc">{r.state}</span><span style="flex: 1"></span><span class="count">{plural(r.n, 'sighting')}</span></a>
				{/each}
				{#if !results.length}<p class="muted none">{feats.length ? 'No sightings here. Zoom out or move the map.' : 'No located sightings yet.'}</p>{/if}
			</div>
		</div>
	</div>

	<aside class="side desk-only" aria-label="Results and filters">
		<div class="shead d"><h1>{title}</h1><p class="muted">{sub}</p></div>
		<div class="slist d">
			{#each results as r (r.pid)}
				<a href="/plates/{r.pid}" class="rrow"><PlateChip text={r.text} partial={r.partial} /><span class="stc">{r.state}</span><span style="flex: 1"></span><span class="count">{plural(r.n, 'sighting')}</span></a>
			{/each}
			{#if !results.length}<p class="muted none">{feats.length ? 'No sightings here. Zoom out or move the map.' : 'No located sightings yet.'}</p>{/if}
		</div>
		<section class="dfilters">
			<div class="row" style="justify-content: space-between"><b>Filters</b><a href="/plates" class="sync"><Icon name="link" size={14} stroke={2.2} />Synced with Plates</a></div>
			<FilterPanel {meta} compact />
		</section>
	</aside>
</div>

<Sheet bind:open={fOpen} title="Filters">
	<p class="sync" style="margin-top: -10px">Also applied to the Plates list</p>
	<FilterPanel {meta} compact />
	{#snippet footer()}
		<button class="btn primary" style="flex: 1" onclick={() => (fOpen = false)}>Show {plural(feats.length, 'sighting')}</button>
	{/snippet}
</Sheet>

<style>
	.wrap {
		flex: 1;
		min-height: 0;
		display: flex;
	}
	.mapbox {
		flex: 1;
		position: relative;
		overflow: hidden;
		background: var(--map-bg);
	}
	.map {
		position: absolute;
		inset: 0;
	}
	.overlay {
		position: absolute;
		z-index: 3;
	}
	.top {
		left: 12px;
		right: 12px;
		top: 12px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		pointer-events: none;
	}
	.top > * {
		pointer-events: auto;
	}
	.row {
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.wrapr {
		flex-wrap: wrap;
	}
	.shadow {
		box-shadow: var(--shadow);
	}
	.syncpill {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 12px;
		font-weight: 800;
		color: var(--accent);
		background: var(--surface);
		border-radius: 999px;
		padding: 0 10px;
		min-height: 32px;
		box-shadow: var(--shadow);
		border: 1px solid var(--line);
		white-space: nowrap;
		text-decoration: none;
	}
	.mchip {
		display: inline-flex;
		align-items: center;
		min-height: 32px;
		padding: 0 10px;
		border-radius: 999px;
		background: var(--surface);
		color: var(--ink);
		font-size: 13px;
		font-weight: 700;
		box-shadow: var(--shadow);
		border: 1px solid var(--line);
		white-space: nowrap;
	}
	.fabs {
		right: 12px;
		top: 116px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.fab {
		width: 48px;
		height: 48px;
		border-radius: 12px;
		border: 1px solid var(--line);
		background: var(--surface);
		color: var(--ink);
		box-shadow: var(--shadow);
		display: inline-flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}
	.fab.on {
		background: var(--accent);
		color: var(--accent-ink);
		border-color: var(--accent);
	}
	.rpanel {
		left: 12px;
		top: 116px;
		background: var(--surface);
		border-radius: 12px;
		box-shadow: var(--shadow);
		padding: 8px 10px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		width: 210px;
		border: 1px solid var(--line);
	}
	.rl {
		display: flex;
		flex-direction: column;
		gap: 2px;
		font-size: 12.5px;
		font-weight: 700;
	}
	.rl input {
		width: 100%;
		accent-color: var(--accent);
		min-height: 32px;
	}
	.err {
		background: var(--bad-soft);
		color: var(--bad);
		border-radius: 10px;
		padding: 8px 10px;
		font-weight: 600;
	}
	.sheet {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		background: var(--surface);
		border-radius: 18px 18px 0 0;
		box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.14);
		z-index: 5;
		display: flex;
		flex-direction: column;
		transition: height 0.22s ease;
		max-height: calc(100% - 24px);
	}
	.handle {
		width: 100%;
		min-height: 36px;
		border: 0;
		background: none;
		cursor: grab;
		display: flex;
		align-items: center;
		justify-content: center;
		touch-action: none;
		flex: none;
	}
	.handle span {
		width: 44px;
		height: 5px;
		border-radius: 3px;
		background: var(--line);
	}
	.shead {
		padding: 0 16px 4px;
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
	}
	.shead h2 {
		font-size: 17px;
		font-weight: 800;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.shead span {
		font-size: 13px;
		white-space: nowrap;
	}
	.slist {
		flex: 1;
		overflow-y: auto;
		padding: 0 16px 16px;
	}
	.rrow {
		display: flex;
		gap: 10px;
		align-items: center;
		padding: 10px 0;
		border-bottom: 1px solid var(--line);
		text-decoration: none;
		color: var(--ink);
		min-height: 52px;
	}
	.none {
		padding: 16px 0;
		font-size: 14px;
	}
	.side {
		width: 360px;
		flex: none;
		background: var(--surface);
		border-left: 1px solid var(--line);
		display: flex;
		flex-direction: column;
		min-height: 0;
	}
	.shead.d {
		flex-direction: column;
		gap: 4px;
		padding: 20px 20px 12px;
		border-bottom: 1px solid var(--line);
	}
	.shead.d h1 {
		font-size: 20px;
		font-weight: 800;
	}
	.slist.d {
		padding: 4px 16px 12px;
	}
	.dfilters {
		padding: 16px 20px 24px;
		border-top: 1px solid var(--line);
		display: flex;
		flex-direction: column;
		gap: 14px;
		background: var(--bg);
		max-height: 46%;
		overflow-y: auto;
	}
	@media (min-width: 900px) {
		.wrap {
			height: 100dvh;
		}
		.fabs,
		.rpanel {
			top: 60px;
		}
	}
	:global(.maplibregl-ctrl-bottom-right) {
		bottom: 160px;
	}
	@media (min-width: 900px) {
		:global(.maplibregl-ctrl-bottom-right) {
			bottom: 0;
		}
	}
</style>
