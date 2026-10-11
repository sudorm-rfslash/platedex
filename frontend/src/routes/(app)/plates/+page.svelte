<script lang="ts">
	import { api, errorText } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import FilterPanel from '#lib/components/FilterPanel.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import MiniMap from '#lib/components/MiniMap.svelte';
	import PlateChip from '#lib/components/PlateChip.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { coord, dateTime, plural, shortDate } from '#lib/format.ts';
	import { chips, filterParams, filters, resetFilters, saveFilters } from '#lib/state/filters.svelte.ts';
	import { flash } from '#lib/state/toast.svelte.ts';
	import { toQuery } from '#lib/api.ts';
	import { onMount } from 'svelte';

	type PlateRow = {
		id: number; text: string; state: string | null; partial: boolean; meaning: string | null; tags: string[];
		n: number; places: string[]; spotters: number; first: string; last: string; dist_mi: number | null; points: [number, number][];
	};
	type Sight = {
		id: number; plate_id: number | null; plate: { id: number; text: string; state: string | null; partial: boolean } | null;
		seen_at: string | null; tz: string | null; place: string | null; lat: number | null; lon: number | null; user: { username: string; color: string };
	};

	const VIEW_KEY = 'platedex.platesView';
	function saved() {
		try {
			return JSON.parse(sessionStorage.getItem(VIEW_KEY) || '{}');
		} catch {
			return {};
		}
	}
	const s0 = saved();
	let q = $state<string>(s0.q ?? '');
	let sort = $state<string>(s0.sort ?? 'last');
	let view = $state<'stacked' | 'flat'>(s0.view ?? 'stacked');
	let help = $state(false);
	let sheet = $state(false);
	let origin = $state<{ lat: number; lon: number } | null>(null);
	let plates = $state<PlateRow[]>([]);
	let sightings = $state<Sight[]>([]);
	let totalSightings = $state(0);
	let meta = $state<any>(null);
	let loading = $state(true);
	let error = $state('');
	let searchEl = $state<HTMLInputElement>();

	// "/" jumps to the search box from anywhere on the page (unless you're already typing).
	function hotkey(e: KeyboardEvent) {
		if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
		const t = e.target as HTMLElement;
		if (t.isContentEditable || /^(input|textarea|select)$/i.test(t.tagName)) return;
		e.preventDefault();
		searchEl?.focus();
		searchEl?.select();
	}

	const activeChips = $derived(chips(filters));

	$effect(() => {
		try {
			sessionStorage.setItem(VIEW_KEY, JSON.stringify({ q, sort, view }));
		} catch {
			/* storage blocked */
		}
	});

	function params() {
		const o = origin ?? (filters.area ? { lat: filters.area.lat, lon: filters.area.lon } : null);
		return { ...filterParams(filters), q, sort, origin: sort === 'dist' && o ? `${o.lat},${o.lon}` : undefined };
	}

	let seq = 0;
	async function fetchList() {
		const my = ++seq;
		error = '';
		try {
			const p = params();
			if (view === 'stacked') {
				const r = await api.get('/api/plates', p);
				if (my !== seq) return;
				plates = r.plates;
				totalSightings = r.sightings;
			} else {
				const [r, pr] = await Promise.all([api.get('/api/sightings', p), api.get('/api/plates', p)]);
				if (my !== seq) return;
				sightings = r.sightings;
				totalSightings = r.total;
				plates = pr.plates;
			}
		} catch (e) {
			error = errorText(e);
		} finally {
			if (my === seq) loading = false;
		}
	}

	// Refetch whenever the search, sort, view or any shared filter changes.
	$effect(() => {
		JSON.stringify(filters);
		q;
		sort;
		view;
		origin;
		const t = setTimeout(fetchList, 220);
		return () => clearTimeout(t);
	});

	onMount(async () => {
		meta = await api.get('/api/meta').catch(() => null);
	});

	function onSort(v: string) {
		sort = v;
		if (v === 'dist' && !origin && !filters.area && 'geolocation' in navigator) {
			navigator.geolocation.getCurrentPosition(
				(p) => (origin = { lat: p.coords.latitude, lon: p.coords.longitude }),
				() => flash('Allow location to sort by distance from you'),
				{ timeout: 8000, maximumAge: 300000 }
			);
		}
	}

	function setQ(v: string) {
		q = v;
		help = false;
	}

	function clearAll() {
		q = '';
		resetFilters();
	}

	const headline = $derived(`${plural(plates.length, 'plate')} · ${plural(totalSightings, 'sighting')}`);
	const exportHref = $derived('/api/export.csv?' + toQuery(params()));
</script>

<svelte:head><title>Platedex · Plates</title></svelte:head>
<svelte:window onkeydown={hotkey} />

<div class="page">
	<header class="page-head">
		<div class="hrow">
			<h1>Plates</h1>
			<span class="muted" style="font-size: 13px">{headline}</span>
		</div>
		<div class="tools">
			<div class="search">
				<label class="sl">
					<span class="sr-only">Search plates</span>
					<Icon name="search" size={18} stroke={2} class="sicon" />
					<input bind:this={searchEl} class="field mono" style="padding-left: 38px; padding-right: {q ? 40 : 12}px; font-size: 15px" onkeydown={(e) => e.key === 'Escape' && q && ((q = ''), e.stopPropagation())} placeholder="GR8FUL · 7AB* · 7A?12 · ~LUVU2 · grateful" value={q} oninput={(e) => (q = e.currentTarget.value)} autocapitalize="characters" autocomplete="off" spellcheck="false" />
				</label>
				{#if q}<button class="clr" aria-label="Clear search" onclick={() => ((q = ''), searchEl?.focus())}><Icon name="x" size={18} stroke={2.2} /></button>{/if}
				<button class="iconbtn hbtn" aria-label="Search syntax help" aria-expanded={help} onclick={() => (help = !help)}><Icon name="help" size={20} /></button>
				{#if help}
					<div class="pop" role="dialog" aria-label="Search syntax">
						<div class="ph"><span class="lbl">Search syntax · tap to try</span><button class="iconbtn" style="width: 36px; height: 36px" aria-label="Close help" onclick={() => (help = false)}><Icon name="close" size={16} stroke={2.2} /></button></div>
						<button class="ex" onclick={() => setQ('7AB*')}><code>7AB*</code><span>Starts with 7AB</span></button>
						<button class="ex" onclick={() => setQ('7A?12')}><code>7A?12</code><span><span class="mono" style="font-weight: 800">?</span> is one unknown character</span></button>
						<button class="ex" onclick={() => setQ('~LUVU2')}><code>~LUVU2</code><span>Fuzzy · also finds look-alikes like LUVV2, 1UVU2</span></button>
						<button class="ex" onclick={() => setQ('vanity')}><code style="font-family: 'Public Sans', sans-serif">vanity</code><span>Plain words search meaning, notes and tags</span></button>
					</div>
				{/if}
			</div>
			<div class="ctrls">
				<div class="seg" role="group" aria-label="View">
					<button class:on={view === 'stacked'} aria-pressed={view === 'stacked'} onclick={() => (view = 'stacked')}><span class="mobile-only">Plates</span><span class="desk-only">Stacked by plate</span></button>
					<button class:on={view === 'flat'} aria-pressed={view === 'flat'} onclick={() => (view = 'flat')}><span class="mobile-only">Sightings</span><span class="desk-only">All sightings</span></button>
				</div>
				<label class="sortl">
					<span class="desk-only">Sort</span><span class="sr-only">Sort</span>
					<select class="field" value={sort} onchange={(e) => onSort(e.currentTarget.value)}>
						<option value="last">Last seen</option>
						<option value="first">First seen</option>
						<option value="most">Most sightings</option>
						<option value="places">Most places</option>
						<option value="dist">Distance{origin ? ' from you' : filters.area ? ` from ${filters.area.label}` : ''}</option>
						<option value="az">A–Z</option>
					</select>
				</label>
				<button class="btn mobile-only fbtn" onclick={() => ((sheet = true), (help = false))} aria-label="Filters">
					<Icon name="filter" size={18} stroke={2} />
					{#if activeChips.length}<span class="badge" style="background: var(--accent); color: var(--accent-ink)">{activeChips.length}</span>{/if}
				</button>
				<a class="btn desk-only" href={exportHref} download><Icon name="download" size={18} />CSV</a>
			</div>
		</div>
		{#if activeChips.length}
			<div class="chips">
				{#each activeChips as c}
					<button class="fchip" onclick={c.clear} aria-label="Remove filter {c.label}">{c.label}<Icon name="x" size={20} stroke={2.2} /></button>
				{/each}
				<a href="/map" class="sync"><Icon name="link" size={14} stroke={2.2} />Synced with Map</a>
			</div>
		{/if}
	</header>

	<div class="page-body layout">
		<aside class="card fside desk-only" aria-label="Filters">
			<div class="fh"><h2>Filters</h2><a href="/map" class="sync"><Icon name="link" size={14} stroke={2.2} />Synced with Map</a></div>
			<FilterPanel {meta} onMissing={() => (view = 'flat')} />
			{#if activeChips.length}<button class="btn" onclick={resetFilters}>Clear all</button>{/if}
		</aside>

		<section class="results" aria-label="Results">
			{#if meta?.missing_location > 0 && !filters.missing}
				<button class="missing mobile-only" onclick={() => ((filters.missing = true), saveFilters(), (view = 'flat'))}>
					<Icon name="pin-off" size={18} stroke={2} /><span style="flex: 1">{plural(meta.missing_location, 'sighting')} missing location</span><Icon name="chevron" size={18} stroke={2} />
				</button>
			{/if}
			{#if error}<p class="err">{error}</p>{/if}

			{#if view === 'stacked'}
				<div class="thead desk-only"><span>Plate</span><span>Sightings</span><span>First seen</span><span>Last seen</span><span>Where</span></div>
				{#each plates as p (p.id)}
					<a href="/plates/{p.id}" class="prow">
						<div class="pmain">
							<div class="pl1">
								<PlateChip text={p.text} partial={p.partial} />
								<span class="stc">{p.state ?? ''}</span>
								{#if p.partial}<span class="tag partial">partial</span>{/if}
								{#if p.meaning}<span class="muted mean">“{p.meaning}”</span>{/if}
							</div>
							<div class="mobile-only"><span class="count">{plural(p.n, 'sighting')} · {plural(p.places.length, 'place')}</span></div>
							<div class="muted mobile-only" style="font-size: 12.5px">First {shortDate(p.first)} · Last {shortDate(p.last)}{p.dist_mi != null && sort === 'dist' ? ` · ${Math.round(p.dist_mi)} mi` : ''}</div>
						</div>
						<div class="desk-only"><span class="count">{plural(p.n, 'sighting')} · {plural(p.places.length, 'place')}</span></div>
						<span class="desk-only cell">{shortDate(p.first)}</span>
						<span class="desk-only cell">{shortDate(p.last)}</span>
						<MiniMap points={p.points} label={p.places.length ? 'Seen in ' + p.places.join(', ') : 'No locations'} />
					</a>
				{/each}
			{:else}
				<div class="fhead desk-only"><span>Plate</span><span>When</span><span>Where</span><span>Logged by</span></div>
				{#each sightings as s (s.id)}
					<a href={s.plate_id ? `/plates/${s.plate_id}` : '/review?tab=identify'} class="frow">
						<div class="fl1">
							{#if s.plate}<PlateChip text={s.plate.text} partial={s.plate.partial} /><span class="stc">{s.plate.state ?? ''}</span>{/if}
						</div>
						<div class="fl2">
							<span>{dateTime(s.seen_at, s.tz)}</span>
							<span class="muted mobile-only">·</span>
							{#if s.lat != null}<span class="muted">{s.place ? `near ${s.place}` : coord(s.lat, s.lon ?? 0)}</span>{:else}<span class="noloc">No location</span>{/if}
						</div>
						<span class="who"><Avatar user={s.user} size={24} /><span class="desk-only">{s.user.username}</span></span>
					</a>
				{/each}
			{/if}

			{#if !loading && (view === 'stacked' ? !plates.length : !sightings.length)}
				<div class="none">
					<p style="font-weight: 800">{q || activeChips.length ? 'No plates match' : 'No plates yet'}</p>
					<p class="muted" style="font-size: 14px">{q || activeChips.length ? 'Try a fuzzy search with ~ or clear filters.' : 'Upload a few photos and they show up here.'}</p>
					{#if q || activeChips.length}<button class="btn" onclick={clearAll}>Clear search and filters</button>{/if}
				</div>
			{/if}
		</section>
	</div>
</div>

<Sheet bind:open={sheet} title="Filters">
	<p class="sync" style="margin-top: -10px">Shared with Map</p>
	<FilterPanel {meta} onMissing={() => ((view = 'flat'), (sheet = false))} />
	{#snippet footer()}
		<button class="btn" onclick={resetFilters}>Clear all</button>
		<button class="btn primary" style="flex: 1" onclick={() => (sheet = false)}>Show {plural(plates.length, 'plate')}</button>
	{/snippet}
</Sheet>

<style>
	.hrow {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 12px;
	}
	.tools {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.search {
		position: relative;
		display: flex;
		gap: 6px;
		align-items: center;
	}
	.sl {
		flex: 1;
		position: relative;
		display: block;
	}
	.sl :global(.sicon) {
		position: absolute;
		left: 12px;
		top: 13px;
		color: var(--muted);
	}
	.clr {
		position: absolute;
		right: 54px;
		top: 50%;
		transform: translateY(-50%);
		width: 32px;
		height: 32px;
		display: flex;
		align-items: center;
		justify-content: center;
		border: 0;
		border-radius: 8px;
		background: none;
		color: var(--muted);
		cursor: pointer;
	}
	.clr:hover {
		color: var(--ink);
	}
	.hbtn {
		border: 1px solid var(--line);
		background: var(--surface);
	}
	.pop {
		position: absolute;
		z-index: 12;
		top: 52px;
		left: 0;
		right: 0;
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: 12px;
		box-shadow: var(--shadow);
		padding: 12px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.ph {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.ex {
		display: flex;
		gap: 10px;
		align-items: center;
		min-height: 44px;
		padding: 4px 8px;
		border-radius: 8px;
		border: 0;
		background: none;
		color: var(--ink);
		font: inherit;
		font-size: 14px;
		text-align: left;
		cursor: pointer;
		width: 100%;
	}
	.ex:hover {
		background: var(--surface2);
	}
	.ex code {
		font-family: 'JetBrains Mono', monospace;
		font-feature-settings: 'zero' 1;
		font-weight: 800;
		font-size: 14px;
		min-width: 78px;
		color: var(--accent);
	}
	.ctrls {
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.sortl {
		flex: 1;
		min-width: 0;
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 14px;
		font-weight: 600;
	}
	.sortl select {
		padding: 0 8px;
		font-size: 14px;
		font-weight: 600;
	}
	.fbtn {
		padding: 0 12px;
	}
	.chips {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		align-items: center;
	}
	.layout {
		gap: 10px;
	}
	.results {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-width: 0;
	}
	.prow {
		display: flex;
		gap: 12px;
		align-items: stretch;
		padding: 12px;
		border-radius: 12px;
		background: var(--surface);
		border: 1px solid var(--line);
		text-decoration: none;
		color: var(--ink);
	}
	.prow:hover {
		border-color: var(--muted);
	}
	.pmain {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.pl1 {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}
	.mean {
		font-size: 13px;
		font-style: italic;
	}
	.frow {
		display: flex;
		gap: 10px;
		align-items: center;
		flex-wrap: wrap;
		padding: 10px 12px;
		border-radius: 12px;
		background: var(--surface);
		border: 1px solid var(--line);
		text-decoration: none;
		color: var(--ink);
	}
	.fl1 {
		display: flex;
		gap: 8px;
		align-items: center;
		width: 100%;
	}
	.fl2 {
		font-size: 13px;
		display: flex;
		gap: 6px;
		align-items: center;
		flex-wrap: wrap;
		flex: 1;
		min-width: 0;
	}
	.who {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 14px;
	}
	.noloc {
		font-weight: 700;
		color: var(--amber-ink);
		background: var(--amber-bg);
		padding: 0 6px;
		border-radius: 5px;
	}
	.none {
		padding: 40px 12px;
		text-align: center;
		display: flex;
		flex-direction: column;
		gap: 8px;
		align-items: center;
	}
	.err {
		background: var(--bad-soft);
		color: var(--bad);
		border-radius: 10px;
		padding: 10px 12px;
		font-weight: 600;
	}
	@media (max-width: 899.98px) {
		.frow {
			flex-wrap: nowrap;
		}
		.frow .fl1 {
			width: auto;
		}
		.frow {
			display: grid;
			grid-template-columns: 1fr auto;
			grid-template-areas: 'a c' 'b c';
			row-gap: 4px;
		}
		.fl1 {
			grid-area: a;
		}
		.fl2 {
			grid-area: b;
		}
		.who {
			grid-area: c;
		}
	}
	@media (min-width: 900px) {
		.tools {
			flex-direction: row;
			flex-wrap: wrap;
			align-items: center;
			gap: 10px;
		}
		.search {
			flex: 1 1 380px;
		}
		.pop {
			left: auto;
			width: 420px;
		}
		.ctrls {
			flex: none;
		}
		.sortl select {
			width: 190px;
		}
		.layout {
			flex-direction: row;
			align-items: flex-start;
			gap: 24px;
		}
		.fside {
			flex: 0 0 280px;
			padding: 16px;
			display: flex;
			flex-direction: column;
			gap: 18px;
			position: sticky;
			top: 12px;
		}
		.fh {
			display: flex;
			justify-content: space-between;
			align-items: center;
		}
		.fh h2 {
			font-size: 16px;
			font-weight: 800;
		}
		.results {
			flex: 1;
			gap: 0;
			background: var(--surface);
			border: 1px solid var(--line);
			border-radius: 12px;
			overflow: hidden;
		}
		.thead,
		.prow {
			display: grid;
			grid-template-columns: minmax(0, 2.2fr) minmax(0, 1.4fr) 110px 110px 84px;
			gap: 16px;
			align-items: center;
			padding: 12px 18px;
			border: 0;
			border-top: 1px solid var(--line);
			border-radius: 0;
			min-height: 72px;
		}
		.thead,
		.fhead {
			border-top: 0;
			min-height: 40px;
			font-size: 12px;
			font-weight: 800;
			letter-spacing: 0.06em;
			text-transform: uppercase;
			color: var(--muted);
		}
		.prow:hover,
		.frow:hover {
			background: var(--surface2);
		}
		.cell {
			font-size: 14px;
		}
		.fhead,
		.frow {
			display: grid;
			grid-template-columns: minmax(0, 1.4fr) minmax(0, 1.2fr) minmax(0, 1.4fr) 160px;
			gap: 16px;
			align-items: center;
			padding: 12px 18px;
			border: 0;
			border-top: 1px solid var(--line);
			border-radius: 0;
		}
		.fhead {
			border-top: 0;
		}
		.fl2 {
			display: contents;
			font-size: 14px;
		}
		.fl1 {
			width: auto;
		}
		.missing.mobile-only {
			display: none;
		}
		.none,
		.err {
			margin: 16px;
		}
	}
</style>
