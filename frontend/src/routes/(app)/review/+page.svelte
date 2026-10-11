<script lang="ts">
	import { replaceState } from '$app/navigation';
	import { page } from '$app/state';
	import { api, errorText } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import IdentifyPanel from '#lib/components/IdentifyPanel.svelte';
	import VerifyPanel, { type Item } from '#lib/components/VerifyPanel.svelte';
	import { ago } from '#lib/format.ts';
	import { counts, refreshCounts } from '#lib/state/counts.svelte.ts';
	import { canEdit, session } from '#lib/state/session.svelte.ts';
	import { flash } from '#lib/state/toast.svelte.ts';
	import { onMount } from 'svelte';

	type QItem = { id: number; title: string; state: string | null; status: string; by: { username: string; color: string }; uploaded_at: string; place: string | null };
	type Tab = 'verify' | 'identify';

	let tab = $state<Tab>(page.url.searchParams.get('tab') === 'identify' ? 'identify' : 'verify');
	let who = $state<'mine' | 'all'>('mine');
	let queue = $state<QItem[]>([]);
	let skipped = $state<number[]>([]);
	let current = $state<Item | null>(null);
	let done = $state(0);
	let loading = $state(true);
	let busy = $state(false);
	let error = $state('');
	let pollTimer: ReturnType<typeof setInterval> | undefined;

	const visible = $derived(queue.filter((q) => !skipped.includes(q.id)));
	const remaining = $derived(tab === 'verify' ? counts.verify[who] : counts.identify[who]);
	const total = $derived(done + Math.max(remaining, visible.length));
	const pos = $derived(current ? Math.max(0, visible.findIndex((q) => q.id === current!.id)) : 0);
	const meLine = $derived(
		current
			? `uploaded by ${current.by.username === session.me?.username ? 'you' : current.by.username} · ${ago(current.uploaded_at)}${current.place ? ` · near ${current.place}` : ''}`
			: ''
	);
	const reading = $derived(current?.status === 'reading');

	async function load(keepCurrent = false) {
		loading = true;
		error = '';
		try {
			const res = await api.get<{ items: QItem[] }>('/api/review/queue', { tab, who });
			queue = res.items;
			await refreshCounts();
			if (!keepCurrent || !current || !queue.some((q) => q.id === current!.id)) await open(firstOpen());
		} catch (e) {
			error = errorText(e);
		} finally {
			loading = false;
		}
	}

	function firstOpen(): number | null {
		const q = queue.find((x) => !skipped.includes(x.id));
		return q ? q.id : null;
	}

	async function open(id: number | null) {
		clearInterval(pollTimer);
		if (current && current.id !== id && canEdit()) api.post(`/api/review/items/${current.id}/release`).catch(() => {});
		if (id == null) {
			current = null;
			return;
		}
		try {
			current = canEdit() ? await api.post(`/api/review/items/${id}/claim`) : await api.get(`/api/review/items/${id}`);
			if (current?.status === 'reading') watchReading(id);
		} catch (e) {
			flash(errorText(e));
			queue = queue.filter((q) => q.id !== id);
			await open(firstOpen());
		}
	}

	/** The item after `id` in the visible queue (wrapping to the start), ignoring `id` itself. */
	function after(id: number): number | null {
		const idx = visible.findIndex((q) => q.id === id);
		const rest = visible.filter((q) => q.id !== id);
		if (!rest.length) return null;
		return (rest[idx < 0 ? 0 : idx % rest.length] ?? rest[0]).id;
	}

	function next(removedId: number) {
		const nxt = after(removedId);
		queue = queue.filter((q) => q.id !== removedId);
		done++;
		refreshCounts();
		current = null;
		open(nxt);
	}

	async function act(path: string, body?: unknown) {
		if (!current) return;
		busy = true;
		const id = current.id;
		try {
			const r = await api.post(`/api/review/items/${id}/${path}`, body);
			flash(r.toast);
			next(id);
		} catch (e) {
			flash(errorText(e));
		} finally {
			busy = false;
		}
	}

	function skip() {
		if (!current) return;
		const id = current.id;
		const nxt = after(id);
		skipped = [...skipped, id];
		open(nxt);
	}

	function watchReading(id: number) {
		clearInterval(pollTimer);
		pollTimer = setInterval(async () => {
			try {
				const it: Item = await api.get(`/api/review/items/${id}`);
				if (it.status === 'reading') return;
				clearInterval(pollTimer);
				queue = queue.map((q) => (q.id === id ? { ...q, title: it.text || 'No reading', status: it.status } : q));
				// Stay in Identify: the reading appears in the panel, ready to confirm.
				if (current?.id === id) {
					current = it;
					flash(it.text ? `Read ${it.text} — check it and confirm` : 'Couldn’t read that box. Redraw it or type the plate.');
				}
				refreshCounts();
			} catch {
				clearInterval(pollTimer);
			}
		}, 1000);
	}

	async function drawBox(bbox: number[]) {
		if (!current) return;
		busy = true;
		try {
			current = await api.post(`/api/review/items/${current.id}/box`, { bbox });
			watchReading(current!.id);
		} catch (e) {
			flash(errorText(e));
		} finally {
			busy = false;
		}
	}

	async function addPlate(bbox: number[]) {
		if (!current) return;
		busy = true;
		try {
			const it: Item = await api.post(`/api/photos/${current.photo_id}/detections`, { bbox });
			// The new plate becomes its own Identify item, opened right away; the old one stays queued.
			const at = Math.max(0, queue.findIndex((q) => q.id === current!.id));
			const q: QItem = { id: it.id, title: 'Reading…', state: it.state, status: it.status, by: it.by, uploaded_at: it.uploaded_at, place: it.place };
			queue = [...queue.slice(0, at + 1), q, ...queue.slice(at + 1)];
			if (current && canEdit()) api.post(`/api/review/items/${current.id}/release`).catch(() => {});
			current = it;
			watchReading(it.id);
			refreshCounts();
		} catch (e) {
			flash(errorText(e));
		} finally {
			busy = false;
		}
	}

	async function clearBox() {
		if (!current) return;
		busy = true;
		const id = current.id;
		const fromVerify = tab === 'verify';
		try {
			const r = await api.post(`/api/review/items/${id}/clear-box`);
			flash(r.toast);
			if (r.deleted) {
				queue = queue.filter((q) => q.id !== id);
				current = null;
				await open(firstOpen());
			} else if (fromVerify) {
				// The reading was from the wrong spot: continue in Identify to draw the right box.
				tab = 'identify';
				syncUrl();
				skipped = [];
				done = 0;
				const res = await api.get<{ items: QItem[] }>('/api/review/queue', { tab, who });
				queue = res.items;
				current = r;
			} else {
				current = r;
				queue = queue.map((q) => (q.id === id ? { ...q, title: 'No reading' } : q));
			}
			refreshCounts();
		} catch (e) {
			flash(errorText(e));
		} finally {
			busy = false;
		}
	}

	// Keep ?tab= in step so a reload or shared link opens the same tab.
	function syncUrl() {
		const url = new URL(page.url.href);
		url.searchParams.set('tab', tab);
		replaceState(url, page.state);
	}

	function setTab(t: Tab) {
		if (t === tab) return;
		tab = t;
		syncUrl();
		skipped = [];
		done = 0;
		load();
	}

	function setWho(w: 'mine' | 'all') {
		if (w === who) return;
		who = w;
		skipped = [];
		done = 0;
		load();
	}

	onMount(() => {
		load();
		return () => {
			clearInterval(pollTimer);
			if (current && canEdit()) api.post(`/api/review/items/${current.id}/release`).catch(() => {});
		};
	});
</script>

<svelte:head><title>Platedex · Review</title></svelte:head>

<div class="page">
	<header class="rhead">
		<div class="t1">
			<h1>Review</h1>
			<span class="muted" style="font-size: 13px">{who === 'mine' ? 'Showing your uploads' : 'Showing everyone'}</span>
		</div>
		<div class="t2">
			<div class="seg full whoseg" role="group" aria-label="Whose uploads">
				<button class:on={who === 'mine'} aria-pressed={who === 'mine'} onclick={() => setWho('mine')}>My uploads</button>
				<button class:on={who === 'all'} aria-pressed={who === 'all'} onclick={() => setWho('all')}>Everyone</button>
			</div>
			<div class="tabs" role="tablist">
				<button class="rtab" class:on={tab === 'verify'} role="tab" aria-selected={tab === 'verify'} onclick={() => setTab('verify')}>
					Verify <span class="badge">{counts.verify[who]}</span>
				</button>
				<button class="rtab" class:on={tab === 'identify'} role="tab" aria-selected={tab === 'identify'} onclick={() => setTab('identify')}>
					Identify <span class="badge">{counts.identify[who]}</span>
				</button>
				<span class="muted desk-only tabhelp">{tab === 'verify' ? 'OCR has a reading but isn’t sure' : 'OCR found no plate or couldn’t read it'}</span>
			</div>
		</div>
	</header>

	<div class="rbody">
		<aside class="queue desk-only" aria-label="Queue">
			<p class="lbl" style="padding: 0 4px 6px">Queue · {visible.length} {who === 'mine' ? 'of yours' : 'from everyone'}</p>
			{#each visible.slice(0, 40) as q (q.id)}
				<button class="qi" class:on={current?.id === q.id} aria-current={current?.id === q.id} onclick={() => open(q.id)}>
					<span class="qt"><span class="mono" style="font-weight: 800; font-size: 15px; letter-spacing: 0.04em">{q.title}</span><span class="muted" style="font-size: 12px; font-weight: 700">{q.state ?? ''}</span></span>
					<span class="muted qs"><Avatar user={q.by} size={18} />uploaded by {q.by.username === session.me?.username ? 'you' : q.by.username} · {ago(q.uploaded_at)}</span>
				</button>
			{/each}
			{#if visible.length > 40}<p class="muted" style="font-size: 12.5px; padding: 8px 4px">+ {visible.length - 40} more in this queue</p>{/if}
		</aside>

		<div class="content">
			{#if error}
				<p class="err">{error}</p>
			{:else if current && tab === 'verify'}
				<VerifyPanel
					item={current}
					n={Math.min(total, done + pos + 1)}
					{total}
					pct={total ? Math.round((done / total) * 100) : 0}
					{meLine}
					busy={busy || !canEdit()}
					onconfirm={(text, state, guess) => act('confirm', { text, state, state_is_guess: guess })}
					onreject={() => act('reject')}
					onskip={skip}
					onredraw={canEdit() ? clearBox : undefined}
				/>
			{:else if current && tab === 'identify'}
				<IdentifyPanel
					item={current}
					n={Math.min(total, done + pos + 1)}
					{total}
					{meLine}
					busy={busy || !canEdit()}
					{reading}
					onbox={drawBox}
					onadd={addPlate}
					ontype={(text) => act('type', { text, state: current?.state ?? null, state_is_guess: true })}
					onconfirm={(text, state, guess) => act('confirm', { text, state, state_is_guess: guess })}
					onclear={clearBox}
					onnoplate={() => act('no-plate')}
					onkeep={() => act('keep')}
					onskip={skip}
				/>
			{:else if !loading}
				<div class="empty">
					<Icon name="check" size={44} stroke={1.8} style="color: var(--ok)" />
					<p style="font-weight: 800; font-size: 17px">All caught up</p>
					<p class="muted">
						{skipped.length ? `You skipped ${skipped.length}. ` : ''}Nothing left in this tab{who === 'mine' ? ' from your uploads' : ''}.
					</p>
					{#if skipped.length}<button class="btn" onclick={() => ((skipped = []), load())}>Show skipped again</button>{/if}
					{#if who === 'mine' && (tab === 'verify' ? counts.verify.all : counts.identify.all) > 0}
						<button class="btn" onclick={() => setWho('all')}>See everyone's ({tab === 'verify' ? counts.verify.all : counts.identify.all})</button>
					{/if}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.rhead {
		flex: none;
		padding: 12px 16px 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
		background: var(--surface);
		border-bottom: 1px solid var(--line);
	}
	.t1 {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	.t1 h1 {
		font-size: 22px;
		font-weight: 800;
	}
	.t2 {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.tabs {
		display: flex;
	}
	.rtab {
		flex: 1;
		min-height: 46px;
		border: 0;
		background: none;
		font: inherit;
		font-weight: 700;
		font-size: 15px;
		color: var(--muted);
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		cursor: pointer;
		border-bottom: 3px solid transparent;
	}
	.rtab.on {
		color: var(--ink);
		border-bottom-color: var(--accent);
	}
	.rtab .badge {
		background: var(--surface2);
		color: var(--ink);
	}
	.rtab.on .badge {
		background: var(--badge);
		color: var(--badge-ink);
	}
	.tabhelp {
		margin-left: auto;
		align-self: center;
		font-size: 13px;
	}
	.rbody {
		flex: 1;
		min-height: 0;
		display: flex;
	}
	.content {
		flex: 1;
		min-width: 0;
		overflow-y: auto;
		padding: 12px 16px 16px;
	}
	.empty {
		height: 100%;
		min-height: 300px;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 10px;
		padding: 24px;
		text-align: center;
	}
	.err {
		background: var(--bad-soft);
		color: var(--bad);
		border-radius: 10px;
		padding: 10px 12px;
		font-weight: 600;
	}
	.queue {
		width: 280px;
		flex: none;
		border-right: 1px solid var(--line);
		padding: 16px 12px;
		display: flex;
		flex-direction: column;
		gap: 4px;
		background: var(--surface);
		overflow-y: auto;
	}
	.qi {
		display: flex;
		flex-direction: column;
		gap: 4px;
		text-align: left;
		padding: 10px 12px;
		border-radius: 10px;
		border: 1px solid transparent;
		background: none;
		color: var(--ink);
		font: inherit;
		cursor: pointer;
		min-height: 44px;
	}
	.qi:hover {
		background: var(--surface2);
	}
	.qi.on {
		background: var(--accent-soft);
		border-color: var(--accent);
	}
	.qt {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
	}
	.qs {
		font-size: 12.5px;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	@media (min-width: 900px) {
		.rhead {
			padding: 24px 32px 0;
		}
		.t1 h1 {
			font-size: 28px;
		}
		.t2 {
			flex-direction: row-reverse;
			justify-content: space-between;
			align-items: flex-end;
		}
		.whoseg {
			width: 300px;
			margin-bottom: 8px;
		}
		.tabs {
			flex: 1;
			max-width: 640px;
		}
		.rtab {
			flex: none;
			padding: 0 20px;
		}
		.content {
			padding: 0;
		}
	}
</style>
