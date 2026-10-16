<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, errorText } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import PlateChip from '#lib/components/PlateChip.svelte';
	import RouteMap from '#lib/components/RouteMap.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { dateTime, longDate, plural, shortDate, STATE_NAMES, STATE_SLOGANS, timeOf } from '#lib/format.ts';
	import { canEdit } from '#lib/state/session.svelte.ts';
	import { flash } from '#lib/state/toast.svelte.ts';

	type U = { username: string; color: string };
	type S = {
		id: number; read_text: string | null; seen_at: string | null; tz: string | null; lat: number | null; lon: number | null;
		place: string | null; user: U; crop_url: string | null; thumb_url: string | null; photo_id: number | null;
	};
	type Dup = { id: number; text: string; state: string | null; reason: string; n: number; diffs: [string, string][]; last: S | null };
	type Plate = {
		id: number; text: string; state: string | null; state_is_guess: boolean; state_name: string | null; partial: boolean;
		meaning: string | null; tags: string[]; notes: string | null; notes_by: U | null; first_by: U | null;
		n: number; places: number; spotters: number; first: string | null; last: string | null; sightings: S[]; duplicates: Dup[];
	};

	const id = $derived(Number(page.params.id));
	let plate = $state<Plate | null>(null);
	let error = $state('');
	let splitting = $state(false);
	let sel = $state<number[]>([]);
	let splitText = $state('');
	let splitOpen = $state(false);
	let editOpen = $state(false);
	let deleteOpen = $state(false);
	let edit = $state({ text: '', state: '', meaning: '' });
	let notesEditing = $state(false);
	let notesDraft = $state('');
	let tagAdding = $state(false);
	let tagDraft = $state('');
	let dupEl = $state<HTMLElement>();

	async function load() {
		try {
			const r = await api.get(`/api/plates/${id}`);
			if (r.redirect) return goto(`/plates/${r.redirect}`, { replaceState: true });
			plate = r;
			error = '';
		} catch (e) {
			error = errorText(e);
		}
	}

	$effect(() => {
		id;
		plate = null;
		splitting = false;
		sel = [];
		load();
	});

	const ordered = $derived(plate ? [...plate.sightings].sort((a, b) => (a.seen_at ?? '').localeCompare(b.seen_at ?? '')) : []);
	const numbered = $derived(ordered.map((s, i) => ({ ...s, n: i + 1 })));
	const newest = $derived([...numbered].reverse());
	const routePts = $derived(
		numbered.filter((s) => s.lat != null).map((s) => ({ n: s.n, lat: s.lat!, lon: s.lon!, dup: !!s.read_text && s.read_text !== plate?.text, label: `${s.n}. ${shortDate(s.seen_at, s.tz)} · ${s.place ?? ''}` }))
	);
	const slogan = $derived(plate?.state ? STATE_SLOGANS[plate.state] ?? '' : '');
	const vanity = $derived(!!plate && (plate.tags.includes('vanity') || !!plate.meaning));
	const editable = $derived(canEdit());

	async function patch(body: Record<string, unknown>, msg?: string) {
		if (!plate) return;
		try {
			plate = await api.patch(`/api/plates/${plate.id}`, body);
			if (msg) flash(msg);
		} catch (e) {
			flash(errorText(e));
		}
	}

	async function merge(d: Dup) {
		if (!plate) return;
		try {
			const r = await api.post(`/api/plates/${plate.id}/merge`, { source_id: d.id });
			flash(r.toast, async () => {
				try {
					await api.post(`/api/merges/${r.merge_id}/undo`);
				} catch (e) {
					flash(errorText(e));
				}
				load();
			});
			load();
		} catch (e) {
			flash(errorText(e));
		}
	}

	async function dismiss(d: Dup) {
		if (!plate) return;
		const pid = plate.id;
		try {
			const r = await api.post(`/api/plates/${pid}/dismiss`, { other_id: d.id });
			flash(r.toast, async () => {
				await api.post(`/api/plates/${pid}/undismiss`, { other_id: d.id }).catch((e) => flash(errorText(e)));
				load();
			});
			load();
		} catch (e) {
			flash(errorText(e));
		}
	}

	function startSplit() {
		splitting = !splitting;
		sel = [];
	}

	function openSplit() {
		if (!plate || !sel.length) return;
		const first = plate.sightings.find((s) => sel.includes(s.id));
		splitText = first?.read_text && first.read_text !== plate.text ? first.read_text : plate.text;
		splitOpen = true;
	}

	async function doSplit() {
		if (!plate) return;
		const before = plate.id;
		try {
			const r = await api.post(`/api/plates/${before}/split`, { sighting_ids: sel, text: splitText, state: plate.state });
			splitOpen = false;
			splitting = false;
			sel = [];
			flash(r.toast);
			load();
		} catch (e) {
			flash(errorText(e));
		}
	}

	async function doDelete() {
		if (!plate) return;
		try {
			const r = await api.del(`/api/plates/${plate.id}`);
			deleteOpen = false;
			flash(r.toast);
			goto('/plates');
		} catch (e) {
			flash(errorText(e));
		}
	}

	function openEdit() {
		if (!plate) return;
		edit = { text: plate.text, state: plate.state ?? '??', meaning: plate.meaning ?? '' };
		editOpen = true;
	}

	async function saveEdit() {
		await patch({ text: edit.text, state: edit.state, meaning: edit.meaning }, 'Plate updated');
		editOpen = false;
	}

	async function addTag() {
		const t = tagDraft.trim();
		if (!plate || !t) return;
		await patch({ tags: [...plate.tags, t] });
		tagDraft = '';
		tagAdding = false;
	}
</script>

<svelte:head><title>Platedex · {plate?.text ?? 'Plate'}</title></svelte:head>

<div class="page">
	<header class="topbar">
		<a href="/plates" class="btn ghost back"><Icon name="back" size={20} stroke={2.2} /><span class="mobile-only">Plates</span><span class="desk-only crumbs">Plates <span class="muted">/</span> <span class="mono">{plate?.text ?? ''}</span></span></a>
		{#if editable && plate}
			<div class="acts">
				<button class="btn ghost" onclick={openEdit}><Icon name="edit" size={18} /><span class="desk-only">Edit</span></button>
				<button class="btn ghost" onclick={startSplit}><Icon name="split" size={18} />{splitting ? 'Cancel' : 'Split'}</button>
				<button class="btn ghost" onclick={() => (plate?.duplicates.length ? dupEl?.scrollIntoView({ behavior: 'smooth', block: 'center' }) : flash('No likely duplicates for this plate'))}><Icon name="merge" size={18} />Merge</button>
				<button class="btn ghost" style="color: var(--bad)" onclick={() => (deleteOpen = true)}><Icon name="trash" size={18} />Delete</button>
			</div>
		{/if}
	</header>

	{#if error}
		<p class="err">{error}</p>
	{:else if plate}
		<div class="body">
			<div class="left">
				<div class="hero">
					<div class="lp" role="img" aria-label="{plate.state_name ?? ''} plate {plate.text}">
						<span class="bolt l"></span><span class="bolt r"></span>
						<span class="stname">{(plate.state_name ?? 'UNKNOWN STATE').toUpperCase()}</span>
						<span class="mono ptext" style="--fsm: {Math.min(66, 400 / Math.max(plate.text.length, 6))}px; --fsd: {Math.min(92, 640 / Math.max(plate.text.length, 6))}px">{plate.text}</span>
						<span class="slogan">{slogan}</span>
					</div>
					<div class="cap">
						{#if plate.meaning}
							<p class="mean"><span class="mono" style="font-weight: 800">{plate.text}</span> <span class="muted">→</span> <b>“{plate.meaning}”</b></p>
						{/if}
						<p class="muted" style="font-size: 13px">
							{vanity ? 'Vanity plate' : plate.partial ? 'Partial plate' : 'Plate'}{plate.state_name ? ` · ${plate.state_name}` : ''}{plate.state_is_guess && plate.state ? ' (guess)' : ''}{plate.first_by ? ` · first logged by ${plate.first_by.username}` : ''}
						</p>
					</div>
				</div>

				<div class="stats">
					<div class="card st"><p>{plate.n}</p><span class="muted">sightings</span></div>
					<div class="card st"><p>{plate.places}</p><span class="muted">places</span></div>
					<div class="card st"><p>{plate.spotters}</p><span class="muted">spotters</span></div>
				</div>
				<p class="muted seen">First seen {longDate(plate.first)} · Last seen {longDate(plate.last)}</p>

				<section class="sec">
					<span class="lbl">Tags</span>
					<div class="tags">
						{#each plate.tags as t}
							<span class="tag">#{t}{#if editable}<button class="tx" aria-label="Remove tag {t}" onclick={() => patch({ tags: plate!.tags.filter((x) => x !== t) })}>×</button>{/if}</span>
						{/each}
						{#if editable}
							{#if tagAdding}
								<input class="field tagin" placeholder="tag" bind:value={tagDraft} onkeydown={(e) => (e.key === 'Enter' ? addTag() : e.key === 'Escape' && ((tagDraft = ''), (tagAdding = false)))} onblur={addTag} />
							{:else}
								<button class="btn addtag" onclick={() => (tagAdding = true)}>+ Add tag</button>
							{/if}
						{/if}
					</div>
				</section>

				<section class="sec">
					<div class="srow"><span class="lbl">Notes</span>{#if editable && !notesEditing}<button class="btn ghost link" onclick={() => ((notesDraft = plate!.notes ?? ''), (notesEditing = true))}>{plate.notes ? 'Edit' : 'Add'}</button>{/if}</div>
					{#if notesEditing}
						<textarea class="field" bind:value={notesDraft} placeholder="Car, stickers, where it parks…"></textarea>
						<div class="row"><button class="btn" onclick={() => (notesEditing = false)}>Cancel</button><button class="btn primary" onclick={async () => (await patch({ notes: notesDraft }, 'Notes saved'), (notesEditing = false))}>Save</button></div>
					{:else if plate.notes}
						<p class="notes">{plate.notes} {#if plate.notes_by}<span class="muted">— {plate.notes_by.username}</span>{/if}</p>
					{:else}
						<p class="muted" style="font-size: 14px">No notes yet.</p>
					{/if}
				</section>

				<div class="dups" bind:this={dupEl}>
				{#each plate.duplicates as d}
					<section class="dup" aria-label="Possible duplicate">
						<div class="dh"><Icon name="warn" size={18} stroke={2} style="color: var(--amber-ink)" /><span>Possible duplicates — merge?</span></div>
						<div class="row" style="align-items: center; flex-wrap: wrap">
							<PlateChip text={plate.text} partial={plate.partial} />
							<span class="muted" style="font-size: 13px">vs</span>
							<a href="/plates/{d.id}" style="text-decoration: none"><PlateChip text={d.text} highlight={d.diffs.length === 1 ? [...d.text].findIndex((c, i) => c !== plate!.text[i]) : -1} /></a>
						</div>
						<p style="font-size: 13.5px">
							{d.text} has {plural(d.n, 'sighting')}{#if d.last}{' '}({shortDate(d.last.seen_at, d.last.tz)}{d.last.place ? `, near ${d.last.place}` : ''}, by {d.last.user.username}){/if}. It {d.reason}.
						</p>
						{#if editable}
							<div class="row"><button class="btn" onclick={() => dismiss(d)}>Not the same</button><button class="btn primary grow" onclick={() => merge(d)}>Merge into {plate.text}</button></div>
						{/if}
					</section>
				{/each}
				</div>
			</div>

			<div class="right">
				{#if routePts.length}
					<section class="sec">
						<div class="srow"><span class="lbl">Route</span><span class="muted" style="font-size: 12.5px">numbered by date</span></div>
						<RouteMap points={routePts} height={260} />
					</section>
				{/if}

				<section class="sec">
					<div class="srow"><span class="lbl">Sightings</span><span class="muted" style="font-size: 12.5px">newest first</span></div>
					{#if splitting}<p class="splithint">Select the sightings that belong to a different plate.</p>{/if}
					{#each newest as s (s.id)}
						<label class="tl" class:sel={sel.includes(s.id)}>
							{#if splitting}
								<input type="checkbox" class="ck" checked={sel.includes(s.id)} onchange={() => (sel = sel.includes(s.id) ? sel.filter((x) => x !== s.id) : [...sel, s.id])} aria-label="Select sighting {s.n}" />
							{/if}
							<div class="crop">
								{#if s.crop_url}<img src={s.crop_url} alt="Plate as photographed" loading="lazy" />{:else}<span class="mono chip">{s.read_text ?? plate.text}</span>{/if}
							</div>
							<div class="tinfo">
								<div class="row" style="align-items: center; gap: 6px"><span class="num" class:dupn={!!s.read_text && s.read_text !== plate.text}>{s.n}</span><b style="font-size: 14px">{longDate(s.seen_at, s.tz)}</b></div>
								<span class="muted" style="font-size: 13px">{timeOf(s.seen_at, s.tz)} · {s.place ? `near ${s.place}` : 'no location'}</span>
								<span class="who"><Avatar user={s.user} size={20} />{s.user.username}{#if s.read_text && s.read_text !== plate.text}<span class="muted">· read as {s.read_text}</span>{/if}</span>
							</div>
							{#if s.photo_id && !splitting}<a class="open" href="/api/photos/{s.photo_id}/display" target="_blank" rel="noopener" aria-label="Open photo from {dateTime(s.seen_at, s.tz)}"><Icon name="chevron" size={18} /></a>{/if}
						</label>
					{/each}
					{#if splitting}
						<button class="btn primary" disabled={!sel.length} onclick={openSplit}>{sel.length ? `Split ${plural(sel.length, 'sighting')} into a new plate` : 'Select sightings to split'}</button>
					{/if}
				</section>
			</div>
		</div>
	{/if}
</div>

<Sheet bind:open={splitOpen} title="Split into a new plate">
	<p class="muted" style="font-size: 14px">{plural(sel.length, 'sighting')} will move to the plate below. If that plate already exists, they join it.</p>
	<label class="fl">New plate text<input class="field mono" style="font-size: 20px; font-weight: 700; letter-spacing: 0.08em" bind:value={splitText} oninput={(e) => (splitText = e.currentTarget.value.toUpperCase())} /></label>
	<button class="btn primary block" onclick={doSplit} disabled={!splitText.trim()}>Split</button>
</Sheet>

<Sheet bind:open={deleteOpen} title="Delete {plate?.text ?? 'plate'}?">
	<p class="muted" style="font-size: 14px">This removes the plate and its {plural(plate?.n ?? 0, 'sighting')} for everyone. The photos stay but won't be read as this plate again. This can't be undone.</p>
	<div class="row"><button class="btn grow" onclick={() => (deleteOpen = false)}>Cancel</button><button class="btn dangerfill grow" onclick={doDelete}>Delete plate</button></div>
</Sheet>

<Sheet bind:open={editOpen} title="Edit plate">
	<label class="fl">Plate text<input class="field mono" style="font-size: 18px; font-weight: 700" value={edit.text} oninput={(e) => (edit.text = e.currentTarget.value.toUpperCase())} /></label>
	<label class="fl">State
		<select class="field" bind:value={edit.state}>
			{#each Object.entries(STATE_NAMES) as [c, n]}<option value={c}>{c} · {n}</option>{/each}
			<option value="??">Unknown</option>
		</select>
	</label>
	<label class="fl">Meaning <span class="muted" style="font-weight: 500">(for vanity plates)</span><input class="field" placeholder="grateful" bind:value={edit.meaning} /></label>
	<button class="btn primary block" onclick={saveEdit}>Save</button>
</Sheet>

<style>
	.topbar {
		flex: none;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 6px 8px;
		background: var(--surface);
		border-bottom: 1px solid var(--line);
	}
	.back {
		padding: 0 8px;
		color: var(--accent);
	}
	.crumbs {
		font-size: 14px;
		font-weight: 600;
	}
	.acts {
		display: flex;
		gap: 2px;
	}
	.acts .btn {
		padding: 0 10px;
	}
	.body {
		flex: 1;
		overflow-y: auto;
		padding: 16px 16px 24px;
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.left,
	.right {
		display: flex;
		flex-direction: column;
		gap: 18px;
		min-width: 0;
	}
	.hero {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 12px;
	}
	.lp {
		width: min(320px, 100%);
		aspect-ratio: 2 / 1;
		border-radius: 14px;
		background: #fbfbf8;
		border: 2px solid #9aa0a6;
		box-shadow: var(--shadow);
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: space-between;
		padding: 12px 18px 10px;
		overflow: hidden;
	}
	.bolt {
		position: absolute;
		top: 12px;
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: #c9cdd1;
		box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.35);
	}
	.bolt.l {
		left: 22px;
	}
	.bolt.r {
		right: 22px;
	}
	.stname {
		font-size: 20px;
		font-weight: 800;
		letter-spacing: 0.3em;
		color: #13204a;
		line-height: 1;
		white-space: nowrap;
	}
	.ptext {
		font-size: var(--fsm);
		font-weight: 800;
		color: #111827;
		letter-spacing: 0.04em;
		line-height: 1;
	}
	.slogan {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.22em;
		color: #13204a;
		min-height: 12px;
	}
	.cap {
		text-align: center;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.mean {
		font-size: 18px;
	}
	.stats {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 8px;
	}
	.st {
		padding: 10px;
		text-align: center;
	}
	.st p {
		font-size: 22px;
		font-weight: 800;
	}
	.st span {
		font-size: 12px;
	}
	.seen {
		font-size: 13px;
		text-align: center;
		margin-top: -8px;
	}
	.sec {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.srow {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
	}
	.tags {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		align-items: center;
	}
	.tx {
		border: 0;
		background: none;
		color: inherit;
		font: inherit;
		cursor: pointer;
		padding: 0 0 0 4px;
	}
	.addtag {
		min-height: 34px;
		padding: 0 10px;
		font-size: 13px;
		border-style: dashed;
	}
	.tagin {
		width: 140px;
		min-height: 34px;
	}
	.link {
		min-height: 36px;
		padding: 0 6px;
		color: var(--accent);
	}
	.notes {
		font-size: 14.5px;
		white-space: pre-wrap;
	}
	.row {
		display: flex;
		gap: 8px;
	}
	.grow {
		flex: 1;
	}
	.dups {
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.dups:empty {
		display: none;
	}
	.dup {
		background: var(--amber-bg);
		border: 1px solid var(--amber-line);
		border-radius: 12px;
		padding: 12px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		color: var(--ink);
	}
	.dh {
		display: flex;
		align-items: center;
		gap: 8px;
		font-weight: 800;
		color: var(--amber-ink);
	}
	.splithint {
		font-size: 13.5px;
		font-weight: 600;
		color: var(--accent);
	}
	.tl {
		display: flex;
		gap: 12px;
		align-items: center;
		padding: 10px;
		border-radius: 12px;
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.tl.sel {
		border-color: var(--accent);
		background: var(--accent-soft);
	}
	.ck {
		width: 22px;
		height: 22px;
		accent-color: var(--accent);
		flex: none;
	}
	.crop {
		width: 88px;
		height: 56px;
		border-radius: 8px;
		flex: none;
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
		background: #2a2f35;
	}
	.crop img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.chip {
		background: #f4f4ef;
		color: #13204a;
		border: 2px solid #13204a;
		border-radius: 4px;
		font-weight: 800;
		font-size: 12px;
		padding: 3px 6px;
		letter-spacing: 0.04em;
	}
	.tinfo {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.num {
		width: 24px;
		height: 24px;
		border-radius: 50%;
		background: var(--accent);
		color: var(--accent-ink);
		font-size: 12px;
		font-weight: 800;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex: none;
	}
	.num.dupn {
		background: #b4441a;
		color: #fff;
	}
	.who {
		font-size: 13px;
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
	}
	.open {
		color: var(--muted);
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 44px;
	}
	.fl {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-weight: 600;
		font-size: 14px;
	}
	.err {
		margin: 16px;
		background: var(--bad-soft);
		color: var(--bad);
		border-radius: 10px;
		padding: 10px 12px;
		font-weight: 600;
	}
	@media (min-width: 900px) {
		.topbar {
			background: transparent;
			border: 0;
			padding: 20px 32px 0;
		}
		.body {
			flex-direction: row;
			align-items: flex-start;
			gap: 28px;
			padding: 16px 32px 48px;
			overflow: visible;
		}
		.left {
			flex: 1 1 400px;
			max-width: 520px;
		}
		.right {
			flex: 1 1 460px;
		}
		.hero {
			align-items: flex-start;
		}
		.cap {
			text-align: left;
		}
		.lp {
			width: 100%;
			max-width: 460px;
			border-radius: 18px;
			padding: 18px 24px 14px;
		}
		.stname {
			font-size: 28px;
		}
		.ptext {
			font-size: var(--fsd);
		}
		.slogan {
			font-size: 13px;
		}
		.mean {
			font-size: 24px;
		}
		.seen {
			text-align: left;
		}
		.st {
			text-align: left;
			padding: 12px;
		}
		.st p {
			font-size: 26px;
		}
	}
</style>
