<script lang="ts">
	import { api } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import CameraMode from '#lib/components/CameraMode.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import Logo from '#lib/components/Logo.svelte';
	import PinMap from '#lib/components/PinMap.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import { coord, dateTime } from '#lib/format.ts';
	import { canEdit, session } from '#lib/state/session.svelte.ts';
	import { flash } from '#lib/state/toast.svelte.ts';
	import { addedText, addFiles, blocked, clearFinished, isPhoto, PHOTO_ACCEPT, loadRecent, pin, remove, removable, retry, setTime, statusLabel, takeShared, uploads, type Row } from '#lib/state/uploads.svelte.ts';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';

	const BANNER_KEY = 'platedex.locBannerDismissed';
	let banner = $state(true);
	let help = $state(false);
	let camera = $state(false);
	let over = $state(false);
	let input = $state<HTMLInputElement>();

	let pinFor = $state<Row | null>(null);
	let pinLat = $state<number | null>(null);
	let pinLon = $state<number | null>(null);
	let pinPlace = $state('');
	let timeFor = $state<Row | null>(null);
	let timeValue = $state('');

	onMount(() => {
		try {
			const t = Number(localStorage.getItem(BANNER_KEY) || 0);
			banner = Date.now() - t > 30 * 864e5;
		} catch {
			banner = true;
		}
		if (page.url.searchParams.has('shared')) {
			takeShared().then((n) => {
				if (n) flash(`${n} shared photo${n === 1 ? '' : 's'} added`);
				goto('/upload', { replaceState: true });
			});
		} else loadRecent();
	});

	function dismiss() {
		banner = false;
		try {
			localStorage.setItem(BANNER_KEY, String(Date.now()));
		} catch {
			/* storage blocked */
		}
	}

	const done = $derived(uploads.rows.filter((r) => r.status === 'done').length);
	const finished = $derived(uploads.rows.some((r) => r.status === 'done' || r.status === 'review'));
	const summary = $derived(`${uploads.rows.length} file${uploads.rows.length === 1 ? '' : 's'} · ${done} done`);

	/** Add picked, pasted or dropped files, skipping anything that isn't a supported photo. */
	function take(files: File[], verb = 'added') {
		if (!files.length) return;
		const ok = files.filter(isPhoto);
		if (ok.length) addFiles(ok);
		flash(addedText(ok.length, files.length - ok.length, verb));
	}

	function picked(e: Event) {
		take(Array.from((e.currentTarget as HTMLInputElement).files ?? []));
		(e.currentTarget as HTMLInputElement).value = '';
	}

	// Desktop: paste screenshots or copied image files straight into the batch.
	function pasted(e: ClipboardEvent) {
		if (!canEdit() || camera || pinFor || timeFor) return;
		const t = e.target as HTMLElement;
		if (t.isContentEditable || /^(input|textarea)$/i.test(t.tagName)) return;
		const files = Array.from(e.clipboardData?.files ?? []);
		if (!files.length) return;
		e.preventDefault();
		take(files, 'pasted');
	}

	const hasFiles = (e: DragEvent) => !!e.dataTransfer?.types.includes('Files');

	// Files dropped anywhere on the page go into the batch. Without this, a drop that misses the
	// drop zone makes the browser open the image and leave the page (and the batch) behind.
	function windowDragOver(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		if (e.dataTransfer) e.dataTransfer.dropEffect = canEdit() ? 'copy' : 'none';
	}

	function dropped(e: DragEvent) {
		if (!hasFiles(e)) return;
		e.preventDefault();
		over = false;
		if (canEdit()) take(Array.from(e.dataTransfer?.files ?? []));
	}

	function dragLeave(e: DragEvent) {
		// dragleave also fires when moving onto the zone's own icon and text; ignore those.
		if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node | null)) over = false;
	}

	function shot(file: File, loc: { lat: number; lon: number; accuracy: number } | null) {
		camera = false;
		addFiles([file], { captureMode: 'camera', device: loc });
		flash(loc ? 'Photo added with your location' : 'Photo added — drop a pin for its location');
	}

	function openPin(r: Row) {
		pinFor = r;
		pinLat = r.pinned?.lat ?? null;
		pinLon = r.pinned?.lon ?? null;
		pinPlace = r.pinned?.label ?? '';
	}

	$effect(() => {
		if (pinLat == null || pinLon == null) return;
		const [la, lo] = [pinLat, pinLon];
		const t = setTimeout(async () => {
			try {
				const g = await api.get('/api/geo/reverse', { lat: la, lon: lo });
				pinPlace = g.place;
			} catch {
				pinPlace = '';
			}
		}, 250);
		return () => clearTimeout(t);
	});

	function confirmPin() {
		if (!pinFor || pinLat == null || pinLon == null) return;
		pin(pinFor.key, pinLat, pinLon, pinPlace ? `near ${pinPlace}` : coord(pinLat, pinLon));
		pinFor = null;
		flash('Location added');
	}

	function local(d: Date) {
		const p = (n: number) => String(n).padStart(2, '0');
		return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
	}

	function openTime(r: Row) {
		timeFor = r;
		timeValue = local(new Date(r.lastModified ?? Date.now()));
	}

	function confirmTime() {
		if (!timeFor || !timeValue) return;
		const d = new Date(timeValue);
		setTime(timeFor.key, d.toISOString(), dateTime(d.toISOString()));
		timeFor = null;
		flash('Capture time set');
	}
</script>

<svelte:head><title>Platedex · Upload</title></svelte:head>
<svelte:window onpaste={pasted} ondragover={windowDragOver} ondrop={dropped} />

<div class="page">
	<header class="head">
		<div class="mobile-only" style="display: flex; align-items: center; gap: 10px">
			<Logo width={34} />
			<h1>Upload</h1>
		</div>
		<div class="desk-only">
			<h1>Upload</h1>
			<p class="muted">Plates are read on the server. Location and time come from each photo.</p>
		</div>
		<a href="/more" class="mobile-only" aria-label="Account: {session.me?.username}" style="text-decoration: none"><Avatar user={session.me} /></a>
		{#if canEdit()}
			<button class="btn primary desk-only camdesk" onclick={() => (camera = true)}><Icon name="camera" />Camera mode</button>
		{/if}
	</header>

	<div class="body">
		{#if !canEdit()}
			<p class="card" style="padding: 14px">You have view-only access. Ask an admin to make you a member to upload photos.</p>
		{:else}
			<div class="left">
				{#if banner}
					<div class="amber banner mobile-only" role="note">
						<Icon name="pin-off" size={20} stroke={1.9} style="flex: none; margin-top: 2px" />
						<p>
							Phones remove location from photos picked in a browser. Use Camera mode, the Files app, or the Shortcut.
							<button class="how" onclick={() => (help = true)}>How?</button>
						</p>
						<button class="iconbtn" aria-label="Dismiss" onclick={dismiss} style="margin-top: -8px"><Icon name="close" size={18} stroke={2} /></button>
					</div>
				{/if}
				<button class="btn primary block cam mobile-only" onclick={() => (camera = true)}>
					<span style="display: flex; align-items: center; gap: 10px"><Icon name="camera" size={24} />Camera mode</span>
					<span class="camsub">Shoot in the app · your location is attached</span>
				</button>
				<button
					class="drop"
					class:over
					onclick={() => input?.click()}
					ondragover={(e) => (e.preventDefault(), (over = true))}
					ondragleave={dragLeave}
				>
					<Icon name="upload" size={34} stroke={1.7} style="color: var(--accent)" />
					<span class="mobile-only dt">Tap to pick photos</span>
					<span class="desk-only dt">Drop photos here</span>
					<span class="muted" style="font-size: 13px"><span class="desk-only">or click to browse, or paste · </span>JPG, HEIC, PNG, WebP, AVIF · up to {session.config?.max_upload_mb ?? 25} MB each</span>
				</button>
				<input bind:this={input} type="file" accept={PHOTO_ACCEPT} multiple hidden onchange={picked} />
				<div class="card tips desk-only">
					<p style="font-weight: 800">Keeping location and time</p>
					<div class="tip"><span class="num">1</span><p>Upload originals. Files copied from a phone over cable, AirDrop or a NAS keep their GPS.</p></div>
					<div class="tip"><span class="num">2</span><p>Edited copies, screenshots and messenger downloads often lose it. Platedex flags those before upload.</p></div>
					<div class="tip"><span class="num">3</span><p>On iPhone, the Shortcut uploads originals directly. <a href="/more">Create a token</a></p></div>
				</div>
			</div>

			<section class="batch" aria-label="Upload queue">
				<div class="bh">
					<h2>This batch</h2>
					<span class="bsum">
						<span class="muted" style="font-size: 13px">{summary}</span>
						{#if finished}<button class="act" onclick={clearFinished}>Clear finished</button>{/if}
					</span>
				</div>
				<p class="muted" style="font-size: 12.5px; margin-top: -6px">Every file is checked for location and time before it goes up.</p>
				{#if !uploads.rows.length}
					<p class="muted empty">Nothing uploaded yet. Pick a few photos or open Camera mode.</p>
				{/if}
				{#each uploads.rows as f (f.key)}
					{@const [label, pill] = statusLabel(f.status)}
					<div class="card row">
						<div class="top">
							{#if f.thumb || f.preview}
								<img src={f.preview ?? f.thumb} alt="" class="thumb" />
							{:else}
								<div class="thumb ph"><Icon name="camera" size={20} /></div>
							{/if}
							<div class="info">
								<div class="l1">
									<span class="mono name">{f.name}</span>
									<span class="pills">
										<span class="pill {pill}">{label}</span>
										{#if removable(f)}<button class="rm" aria-label="Remove {f.name} from this batch" title="Remove from batch" onclick={() => remove(f.key)}><Icon name="x" size={16} stroke={2.2} /></button>{/if}
									</span>
								</div>
								<div class="bar" class:done={f.status === 'done'} class:failed={f.status === 'failed'} role="progressbar" aria-label="{f.name} progress" aria-valuenow={f.pct} aria-valuemin="0" aria-valuemax="100">
									<span style="width: {f.pct}%"></span>
								</div>
								<div class="l3">
									<span class="muted" style="font-size: 12.5px">{f.sub}</span>
									{#if f.status === 'review'}<a href="/review" class="act">Review</a>{/if}
									{#if f.status === 'failed'}<button class="act" onclick={() => retry(f.key)}>Retry</button>{/if}
								</div>
							</div>
						</div>
						{#if f.needGps && !f.pinned && f.status !== 'checking'}
							<button class="chipb" onclick={() => openPin(f)}><Icon name="pin" size={18} stroke={2} style="flex: none" /><span style="flex: 1">No location in this file — drop a pin or re-upload the original</span></button>
						{/if}
						{#if f.pinned && f.status === 'queued'}
							<div class="chipok"><Icon name="check" size={16} stroke={2.2} />Pinned · {f.pinned.label}</div>
						{/if}
						{#if f.needTime && !f.timed && f.status !== 'checking'}
							<button class="chipb" onclick={() => openTime(f)}><Icon name="clock" size={18} stroke={2} style="flex: none" /><span style="flex: 1">No capture time in this file — set when it was taken</span></button>
						{/if}
						{#if f.timed && f.needTime && f.status === 'queued'}
							<div class="chipok"><Icon name="check" size={16} stroke={2.2} />Time set · {f.timed.label}</div>
						{/if}
						{#if f.status === 'queued' && !blocked(f) && f.file}
							<span class="muted" style="font-size: 12px">Starting…</span>
						{/if}
					</div>
				{/each}
			</section>
		{/if}
	</div>
</div>

<Sheet bind:open={help} title="Keep the location">
	<p class="muted" style="font-size: 14px; margin-top: -8px">Browsers strip GPS from photos you pick from the library. Any of these keeps it:</p>
	<div class="opt"><span class="num">1</span><div><p style="font-weight: 700">Camera mode</p><p class="muted small">Take the photo inside Platedex. Your phone's location is attached.</p></div></div>
	<div class="opt"><span class="num">2</span><div><p style="font-weight: 700">Files app</p><p class="muted small">Save photos to Files first, then choose Browse when picking. The original keeps its location.</p></div></div>
	<div class="opt"><span class="num">3</span><div><p style="font-weight: 700">iOS Shortcut</p><p class="muted small">Share photos to the Platedex shortcut. It uploads the originals with your API token. <a href="/more">Get a token</a></p></div></div>
	<button class="btn primary block" onclick={() => ((help = false), (camera = true))}>Open Camera mode</button>
</Sheet>

<Sheet open={!!pinFor} title="Where was this taken?" subtitle={pinFor?.name} onclose={() => (pinFor = null)}>
	{#if pinFor}
		<PinMap bind:lat={pinLat} bind:lon={pinLon} />
		<p style="font-size: 14px">
			{#if pinLat != null && pinLon != null}
				<span class="mono">{coord(pinLat, pinLon)}</span>{#if pinPlace}<span class="muted"> · near {pinPlace}</span>{/if}
			{:else}
				<span class="muted">Tap the map to place the pin.</span>
			{/if}
		</p>
		<button class="btn primary block" disabled={pinLat == null} onclick={confirmPin}>Use this location</button>
		<button class="btn ghost block" onclick={() => (pinFor && remove(pinFor.key), (pinFor = null))}>Skip this file · I'll re-upload the original</button>
	{/if}
</Sheet>

<Sheet open={!!timeFor} title="When was this taken?" subtitle={timeFor?.name} onclose={() => (timeFor = null)}>
	{#if timeFor}
		<label class="tl">Date and time<input class="field" type="datetime-local" bind:value={timeValue} /></label>
		<p class="muted" style="font-size: 13px">The file was last changed {dateTime(new Date(timeFor.lastModified ?? Date.now()).toISOString())}. Screenshots and edited copies often lose their time.</p>
		<button class="btn primary block" onclick={confirmTime}>Use this time</button>
		<button class="btn ghost block" onclick={() => (timeFor = null)}>Cancel</button>
	{/if}
</Sheet>

{#if camera}
	<CameraMode onshoot={shot} onclose={() => (camera = false)} />
{/if}

<style>
	.head {
		flex: none;
		padding: 14px 16px 10px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}
	.head h1 {
		font-size: 22px;
		font-weight: 800;
	}
	.body {
		flex: 1;
		overflow-y: auto;
		padding: 0 16px 20px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.left {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.banner {
		border-radius: 12px;
		padding: 10px 6px 10px 12px;
		display: flex;
		gap: 10px;
		align-items: flex-start;
	}
	.banner p {
		flex: 1;
		font-size: 13.5px;
		font-weight: 500;
		line-height: 1.45;
	}
	.how {
		border: 0;
		background: none;
		padding: 0;
		font: inherit;
		font-weight: 800;
		color: inherit;
		text-decoration: underline;
		cursor: pointer;
	}
	.cam {
		min-height: 64px;
		font-size: 17px;
		border-radius: 14px;
		flex-direction: column;
		gap: 2px;
	}
	.camsub {
		font-size: 12.5px;
		font-weight: 500;
		opacity: 0.85;
	}
	.drop {
		width: 100%;
		border: 2px dashed var(--line);
		border-radius: 14px;
		background: var(--surface);
		color: var(--ink);
		font: inherit;
		cursor: pointer;
		padding: 22px 16px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
	}
	.drop:hover,
	.drop.over {
		border-color: var(--accent);
		background: var(--accent-soft);
	}
	.dt {
		font-weight: 700;
		font-size: 16px;
	}
	.tips {
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.tip {
		display: flex;
		gap: 10px;
		align-items: flex-start;
		font-size: 14px;
	}
	.num {
		width: 28px;
		height: 28px;
		border-radius: 50%;
		background: var(--accent-soft);
		color: var(--accent);
		font-weight: 800;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex: none;
		font-size: 13px;
	}
	.batch {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.bh {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		margin-top: 4px;
	}
	.bh h2 {
		font-size: 15px;
		font-weight: 800;
	}
	.empty {
		padding: 16px 0;
		font-size: 14px;
	}
	.row {
		padding: 10px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.top {
		display: flex;
		gap: 12px;
		align-items: center;
	}
	.thumb {
		width: 52px;
		height: 52px;
		border-radius: 8px;
		object-fit: cover;
		flex: none;
		background: var(--surface2);
	}
	.ph {
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--muted);
	}
	.info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.l1,
	.l3 {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		align-items: center;
	}
	.l3 {
		min-height: 18px;
	}
	.name {
		font-size: 13px;
		font-weight: 500;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.bsum {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.pills {
		display: flex;
		align-items: center;
		gap: 2px;
		flex: none;
	}
	.rm {
		width: 28px;
		height: 28px;
		display: flex;
		align-items: center;
		justify-content: center;
		border: 0;
		border-radius: 6px;
		background: none;
		color: var(--muted);
		cursor: pointer;
	}
	.rm:hover {
		color: var(--ink);
		background: var(--surface2);
	}
	.act {
		border: 0;
		background: none;
		font: inherit;
		font-size: 13px;
		font-weight: 700;
		color: var(--accent);
		cursor: pointer;
		min-height: 32px;
		display: inline-flex;
		align-items: center;
		text-decoration: none;
		flex: none;
	}
	.opt {
		display: flex;
		gap: 12px;
		align-items: flex-start;
		padding: 12px;
		border: 1px solid var(--line);
		border-radius: 12px;
	}
	.small {
		font-size: 13.5px;
	}
	.tl {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-weight: 600;
		font-size: 14px;
	}
	@media (min-width: 900px) {
		.head {
			padding: 32px 40px 8px;
			align-items: flex-end;
		}
		.head h1 {
			font-size: 28px;
		}
		.camdesk {
			min-height: 52px;
			font-size: 16px;
			padding: 0 22px;
		}
		.body {
			padding: 16px 40px 48px;
			flex-direction: row;
			align-items: flex-start;
			gap: 24px;
		}
		.left {
			flex: 0 1 380px;
			position: sticky;
			top: 0;
		}
		.drop {
			padding: 40px 16px;
		}
		.batch {
			flex: 1;
			min-width: 0;
		}
	}
</style>
