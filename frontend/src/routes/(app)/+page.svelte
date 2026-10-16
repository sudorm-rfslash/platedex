<script lang="ts">
	import { replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import { api, errorText } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import Logo from '#lib/components/Logo.svelte';
	import PlateChip from '#lib/components/PlateChip.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { dayKey, dayLabel, plural, shortDate, timeOf } from '#lib/format.ts';
	import { session, type User } from '#lib/state/session.svelte.ts';

	type Item = {
		key: string;
		at: string | null;
		tz: string | null;
		user: User;
		place: string | null;
		located: boolean;
		thumb_url: string | null;
		plate: { id: number; text: string; state: string | null; partial: boolean } | null;
		n: number;
		pending: string | null;
	};
	type Feed = { items: Item[]; total: number; plates: number; spotters: number; next_offset: number | null };
	type Sort = 'new' | 'old' | 'az' | 'most';

	const SORTS: [Sort, string][] = [
		['new', 'Newest first'],
		['old', 'Oldest first'],
		['az', 'Plate A–Z'],
		['most', 'Most-seen plates']
	];
	const RANGES: [string, string][] = [
		['all', 'All time'],
		['7', 'Last 7 days'],
		['30', 'Last 30 days'],
		['custom', 'Custom']
	];
	const PAGE = 48;

	// Sort and filters live in the URL query, so a refresh or a shared link shows the same view.
	const q = $derived(page.url.searchParams);
	const sort = $derived((SORTS.find(([k]) => k === q.get('sort'))?.[0] ?? 'new') as Sort);
	const who = $derived(q.get('who') || 'all');
	const range = $derived(RANGES.find(([k]) => k === q.get('range'))?.[0] ?? 'all');
	const from = $derived(q.get('from') || '');
	const to = $derived(q.get('to') || '');
	const states = $derived((q.get('states') || '').split(',').filter(Boolean));
	const vanity = $derived(q.get('vanity') === '1');
	const review = $derived(q.get('review') === '1');
	const missing = $derived(q.get('missing') === '1');
	const byDate = $derived(sort === 'new' || sort === 'old');
	const sheetCount = $derived((range !== 'all' ? 1 : 0) + states.length + +vanity + +review + +missing);
	const hasFilters = $derived(who !== 'all' || sheetCount > 0);

	function setQ(patch: Record<string, string | null>) {
		const url = new URL(page.url.href);
		for (const [k, v] of Object.entries(patch)) {
			if (v == null || v === '') url.searchParams.delete(k);
			else url.searchParams.set(k, v);
		}
		replaceState(url, page.state);
	}
	const flag = (on: boolean) => (on ? '1' : null);
	const toggleState = (st: string) => setQ({ states: (states.includes(st) ? states.filter((x) => x !== st) : [...states, st]).join(',') });
	const setRange = (r: string) => setQ({ range: r === 'all' ? null : r, ...(r === 'custom' ? {} : { from: null, to: null }) });
	const clearFilters = () => setQ({ who: null, range: null, from: null, to: null, states: null, vanity: null, review: null, missing: null });

	function daysAgo(n: number) {
		const d = new Date(Date.now() - n * 86400000);
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
	}

	const params = $derived({
		sort,
		who,
		from: range === '7' ? daysAgo(6) : range === '30' ? daysAgo(29) : range === 'custom' ? from : '',
		to: range === 'custom' ? to : '',
		states: states.join(','),
		vanity: vanity || undefined,
		review: review || undefined,
		missing: missing || undefined
	});

	let items = $state<Item[]>([]);
	let total = $state(0);
	let plates = $state(0);
	let spotters = $state(0);
	let next = $state<number | null>(null);
	let loading = $state(false);
	let loaded = $state(false);
	let error = $state('');
	let run = 0;

	async function fetchPage(offset: number) {
		const mine = run;
		loading = true;
		try {
			const r = await api.get<Feed>('/api/feed', { ...params, offset, limit: PAGE });
			if (mine !== run) return;
			items = offset === 0 ? r.items : [...items, ...r.items];
			({ total, plates, spotters } = r);
			next = r.next_offset;
			error = '';
		} catch (e) {
			if (mine === run) error = errorText(e);
		} finally {
			if (mine === run) {
				loading = false;
				loaded = true;
			}
		}
	}

	$effect(() => {
		JSON.stringify(params); // refetch from the top whenever sort or a filter changes
		run++;
		next = null;
		fetchPage(0);
	});

	// Load the next page when the end of the grid scrolls into view.
	let sentinel = $state<HTMLElement>();
	$effect(() => {
		if (!sentinel) return;
		const io = new IntersectionObserver(
			(entries) => {
				if (entries.some((e) => e.isIntersecting) && next != null && !loading) fetchPage(next);
			},
			{ rootMargin: '800px 0px' }
		);
		io.observe(sentinel);
		return () => io.disconnect();
	});

	let meta = $state<{ users: User[]; states: string[] } | null>(null);
	$effect(() => {
		api.get('/api/meta').then((m) => (meta = m)).catch(() => {});
	});
	const others = $derived((meta?.users ?? []).filter((u) => u.id !== session.me?.id));
	const whos = $derived([
		{ key: 'all', label: 'Everyone', user: null },
		{ key: 'mine', label: 'Mine', user: null },
		...others.map((u) => ({ key: u.username, label: u.username, user: u }))
	]);
	const stateOptions = $derived([...new Set([...(meta?.states ?? []), ...states])].sort());

	let sheet = $state(false);

	const TILE_KEY = 'platedex.home.tile';
	let tile = $state(220);
	try {
		tile = Number(localStorage.getItem(TILE_KEY)) || 220;
	} catch {
		/* storage blocked */
	}
	function setTile(v: number) {
		tile = v;
		try {
			localStorage.setItem(TILE_KEY, String(v));
		} catch {
			/* storage blocked */
		}
	}

	type Group = { key: string; items: Item[] };
	const groups = $derived.by((): Group[] => {
		if (!byDate) return [{ key: '', items }];
		const out: Group[] = [];
		for (const it of items) {
			const k = dayKey(it.at, it.tz);
			const last = out[out.length - 1];
			if (last && last.key === k) last.items.push(it);
			else out.push({ key: k, items: [it] });
		}
		return out;
	});

	const href = (it: Item) => (it.plate ? `/plates/${it.plate.id}` : it.pending === 'No plate found' ? '/review?tab=identify' : '/review');
	const when = (it: Item) => (byDate ? timeOf(it.at, it.tz) : `${shortDate(it.at, it.tz)}, ${timeOf(it.at, it.tz)}`);
	const where = (it: Item) => (it.located ? (it.place ?? 'Unknown place') : 'no location');
	const aria = (it: Item) =>
		`${it.plate ? `${it.plate.text} ${it.plate.state ?? ''}` : it.pending}, ${shortDate(it.at, it.tz)} ${timeOf(it.at, it.tz)}, ${it.located ? `near ${it.place ?? 'unknown place'}` : 'no location'}, by ${it.user.username}`;
</script>

<svelte:head><title>Platedex · Home</title></svelte:head>

{#snippet whoButtons(cls: string)}
	{#each whos as w (w.key)}
		<button class={cls} class:on={who === w.key} aria-pressed={who === w.key} onclick={() => setQ({ who: w.key === 'all' ? null : w.key })}>
			{#if w.user}<Avatar user={w.user} size={20} />{/if}{w.label}
		</button>
	{/each}
{/snippet}

{#snippet showOnly(cls: string)}
	<button class={cls} class:on={vanity} aria-pressed={vanity} onclick={() => setQ({ vanity: flag(!vanity) })}>Vanity plates</button>
	<button class={cls} class:on={review} aria-pressed={review} onclick={() => setQ({ review: flag(!review) })}>Needs review</button>
	<button class={cls} class:on={missing} aria-pressed={missing} onclick={() => setQ({ missing: flag(!missing) })}>Missing location</button>
{/snippet}

{#snippet customDates()}
	<div class="dates">
		<label>From<input class="field" type="date" value={from} max={to || undefined} onchange={(e) => setQ({ from: e.currentTarget.value })} /></label>
		<label>To<input class="field" type="date" value={to} min={from || undefined} onchange={(e) => setQ({ to: e.currentTarget.value })} /></label>
	</div>
{/snippet}

<div class="page">
	<header class="page-head home-head">
		<div class="hrow">
			<div class="title">
				<span class="mobile-only logo"><Logo width={34} /></span>
				<h1><span class="mobile-only">Latest</span><span class="desk-only">Latest sightings</span></h1>
			</div>
			<span class="muted count-l">
				{plural(total, 'photo')}<span class="desk-only">&nbsp;· {plural(plates, 'plate')} · {plural(spotters, 'spotter')}</span>
			</span>
		</div>

		<!-- Mobile: sort, Filter sheet, uploader chips -->
		<div class="mrow mobile-only">
			<label class="grow">
				<span class="sr-only">Sort</span>
				<select class="field sel" value={sort} onchange={(e) => setQ({ sort: e.currentTarget.value === 'new' ? null : e.currentTarget.value })}>
					{#each SORTS as [k, label]}<option value={k}>{label}</option>{/each}
				</select>
			</label>
			<button class="btn" onclick={() => (sheet = true)}>
				<Icon name="filter" size={18} stroke={2} />Filter
				{#if sheetCount}<span class="badge" style="background: var(--accent); color: var(--accent-ink)">{sheetCount}</span>{/if}
			</button>
		</div>
		<div class="chiprow mobile-only" role="group" aria-label="Who uploaded">
			{@render whoButtons('tog who')}
		</div>

		<!-- Desktop: everything in a toolbar -->
		<div class="trow desk-only">
			<div class="seg" role="group" aria-label="Who uploaded">{@render whoButtons('')}</div>
			<label class="inl">Date
				<select class="field" value={range} onchange={(e) => setRange(e.currentTarget.value)}>
					{#each RANGES as [k, label]}<option value={k}>{label}</option>{/each}
				</select>
			</label>
			{#if range === 'custom'}{@render customDates()}{/if}
			<label class="inl">State
				<select class="field" value={states.length === 1 ? states[0] : states.length ? '*' : ''} onchange={(e) => setQ({ states: e.currentTarget.value })}>
					<option value="">Any</option>
					{#if states.length > 1}<option value="*" disabled>{states.join(', ')}</option>{/if}
					{#each stateOptions as st}<option value={st}>{st}</option>{/each}
				</select>
			</label>
			<span class="grow"></span>
			<label class="inl">Sort
				<select class="field" style="width: 180px" value={sort} onchange={(e) => setQ({ sort: e.currentTarget.value === 'new' ? null : e.currentTarget.value })}>
					{#each SORTS as [k, label]}<option value={k}>{label}</option>{/each}
				</select>
			</label>
		</div>
		<div class="trow desk-only">
			<span class="lbl" style="margin-right: 4px">Show only</span>
			{@render showOnly('tog')}
			{#if hasFilters}<button class="btn small" onclick={clearFilters}>Clear filters</button>{/if}
			<span class="grow"></span>
			<label class="inl muted small-l">Tile size
				<input type="range" min="160" max="300" step="20" value={tile} oninput={(e) => setTile(+e.currentTarget.value)} />
			</label>
		</div>
	</header>

	<div class="page-body feed" style="--tile: {tile}px">
		{#if error}
			<p class="err">{error}</p>
		{/if}
		{#each groups as g, gi (`${gi}:${g.key}`)}
			{#if byDate}
				<div class="day">
					<h2><span class="mobile-only">{dayLabel(g.key)}</span><span class="desk-only">{dayLabel(g.key, 'long')}</span></h2>
					<span class="muted">{plural(g.items.length, 'photo')}</span>
				</div>
			{/if}
			<div class="grid">
				{#each g.items as it (it.key)}
					<a href={href(it)} class="tile" aria-label={aria(it)}>
						<div class="ph">
							{#if it.thumb_url}
								<img src={it.thumb_url} alt="" loading="lazy" decoding="async" />
							{:else}
								<span class="noimg"><Icon name="plates" size={32} /></span>
							{/if}
							{#if !it.located}<span class="ovl"><Icon name="pin-off" size={11} stroke={2.6} />No location</span>{/if}
						</div>
						{#if it.plate}
							<div class="cap">
								<PlateChip text={it.plate.text} partial={it.plate.partial} />
								{#if it.plate.state}<span class="stc">{it.plate.state}</span>{/if}
								<span class="grow"></span>
								<span class="seen desk-only">{it.n}×</span>
							</div>
						{:else}
							<div class="cap"><span class="rv">{it.pending}</span></div>
						{/if}
						<div class="meta">
							<Avatar user={it.user} size={20} />
							<span class="t"><span class="desk-only">{it.user.username} · </span>{when(it)} · {where(it)}</span>
						</div>
					</a>
				{/each}
			</div>
		{/each}

		{#if loaded && !items.length && !error}
			<div class="empty">
				{#if hasFilters}
					<p style="font-weight: 800">No photos match</p>
					<button class="btn" onclick={clearFilters}>Clear filters</button>
				{:else}
					<p style="font-weight: 800">No photos yet</p>
					<a class="btn primary" href="/upload"><Icon name="upload" size={18} />Upload photos</a>
				{/if}
			</div>
		{/if}
		<div bind:this={sentinel} class="sentinel" aria-hidden="true">
			{#if loading && items.length}<Icon name="spinner" size={20} class="spin" />{/if}
		</div>
	</div>
</div>

<Sheet bind:open={sheet} title="Filter photos">
	<div class="sheetbody">
		<section>
			<span class="lbl">Date</span>
			<div class="wrap">
				{#each RANGES as [k, label]}<button class="tog" class:on={range === k} onclick={() => setRange(k)}>{label}</button>{/each}
			</div>
			{#if range === 'custom'}{@render customDates()}{/if}
		</section>
		<section>
			<span class="lbl">State</span>
			<div class="wrap">
				{#each stateOptions as st}<button class="tog" class:on={states.includes(st)} aria-pressed={states.includes(st)} onclick={() => toggleState(st)}>{st}</button>{/each}
				{#if !stateOptions.length}<span class="muted" style="font-size: 14px">No plates yet</span>{/if}
			</div>
		</section>
		<section>
			<span class="lbl">Show only</span>
			<div class="wrap">{@render showOnly('tog')}</div>
		</section>
	</div>
	{#snippet footer()}
		<button class="btn" onclick={() => setQ({ range: null, from: null, to: null, states: null, vanity: null, review: null, missing: null })}>Clear all</button>
		<button class="btn primary" style="flex: 1" onclick={() => (sheet = false)}>Show {plural(total, 'photo')}</button>
	{/snippet}
</Sheet>

<style>
	.hrow {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
	}
	.title {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.logo {
		display: inline-flex;
	}
	.count-l {
		font-size: 13px;
	}
	.mrow {
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.grow {
		flex: 1;
		min-width: 0;
	}
	.sel {
		font-weight: 600;
		font-size: 14px;
	}
	.chiprow {
		display: flex;
		gap: 6px;
		overflow-x: auto;
		margin: 0 -16px;
		padding: 0 16px 2px;
		scrollbar-width: none;
	}
	/* The uploader chips use a solid "on" state, unlike the filter toggles. */
	.chiprow :global(.tog.who) {
		flex: none;
		white-space: nowrap;
	}
	.chiprow :global(.tog.who.on) {
		background: var(--ink);
		border-color: var(--ink);
		color: var(--bg);
	}
	.trow {
		display: flex;
		gap: 10px;
		align-items: center;
		flex-wrap: wrap;
	}
	.inl {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 14px;
		font-weight: 600;
	}
	.inl .field {
		font-weight: 600;
	}
	.small-l {
		font-size: 13.5px;
	}
	.inl input[type='range'] {
		width: 120px;
		accent-color: var(--accent);
		min-height: 32px;
	}
	.btn.small {
		min-height: 38px;
		font-size: 13.5px;
	}
	.dates {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}
	.dates label {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 13.5px;
		font-weight: 600;
	}
	.dates .field {
		width: auto;
	}

	.feed {
		gap: 0;
	}
	.day {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		padding: 14px 0 8px;
	}
	.day h2 {
		font-size: 15px;
		font-weight: 800;
	}
	.day .muted {
		font-size: 12.5px;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 14px 10px;
	}
	.grid:first-child {
		margin-top: 14px;
	}
	.tile {
		display: flex;
		flex-direction: column;
		gap: 6px;
		text-decoration: none;
		color: var(--ink);
		border-radius: 12px;
		min-width: 0;
	}
	.tile:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.ph {
		position: relative;
		aspect-ratio: 4 / 3;
		border-radius: 10px;
		overflow: hidden;
		background: var(--surface2);
	}
	.ph img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.noimg {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--muted);
		opacity: 0.6;
	}
	/* Fixed colors: the label sits on a photo, so it doesn't follow the theme. */
	.ovl {
		position: absolute;
		left: 6px;
		top: 6px;
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-size: 11px;
		font-weight: 800;
		padding: 2px 7px;
		border-radius: 6px;
		background: #fef3c7;
		color: #6e4300;
	}
	.cap {
		display: flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
	}
	.seen {
		font-size: 12px;
		font-weight: 700;
		color: var(--muted);
	}
	.rv {
		font-size: 12px;
		font-weight: 800;
		padding: 2px 8px;
		border-radius: 999px;
		background: var(--amber-bg);
		color: var(--amber-ink);
		border: 1px solid var(--amber-line);
		white-space: nowrap;
	}
	.meta {
		display: flex;
		align-items: center;
		gap: 5px;
		font-size: 12px;
		color: var(--muted);
		min-width: 0;
	}
	.meta .t {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.empty {
		padding: 48px 12px;
		text-align: center;
		display: flex;
		flex-direction: column;
		gap: 8px;
		align-items: center;
	}
	.sentinel {
		min-height: 48px;
		display: flex;
		justify-content: center;
		align-items: center;
		color: var(--muted);
	}
	.err {
		color: var(--bad);
		font-weight: 600;
	}

	.sheetbody {
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.sheetbody section {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.wrap {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}

	@media (min-width: 900px) {
		.home-head {
			gap: 14px;
			padding-bottom: 12px;
			border-bottom: 1px solid var(--line);
			margin: 0 32px;
			padding-left: 0;
			padding-right: 0;
		}
		.hrow {
			align-items: baseline;
		}
		.count-l {
			font-size: 15px;
		}
		.grid {
			grid-template-columns: repeat(auto-fill, minmax(var(--tile), 1fr));
			gap: 18px 16px;
		}
		.grid:first-child {
			margin-top: 18px;
		}
		.day {
			justify-content: flex-start;
			gap: 10px;
			padding: 22px 0 10px;
		}
		.day h2 {
			font-size: 17px;
		}
		.day .muted {
			font-size: 13px;
		}
		.tile {
			gap: 7px;
			padding: 6px;
			margin: -6px;
		}
		.tile:hover {
			background: var(--surface);
		}
		.tile:hover .ph {
			box-shadow: var(--shadow);
		}
		.ovl {
			left: 8px;
			top: 8px;
			font-size: 11.5px;
			padding: 2px 8px;
		}
		.meta {
			font-size: 12.5px;
			gap: 6px;
		}
		.rv {
			font-size: 12.5px;
			padding: 2px 9px;
		}
	}
</style>
