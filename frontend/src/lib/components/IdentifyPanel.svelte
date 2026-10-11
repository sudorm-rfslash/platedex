<script lang="ts">
	import Avatar from './Avatar.svelte';
	import BlurMeter from './BlurMeter.svelte';
	import Icon from './Icon.svelte';
	import PhotoViewer from './PhotoViewer.svelte';
	import PlateEditor from './PlateEditor.svelte';
	import type { Item } from './VerifyPanel.svelte';

	let {
		item,
		n,
		total,
		meLine,
		busy,
		reading,
		onbox,
		onadd,
		ontype,
		onconfirm,
		onclear,
		onnoplate,
		onkeep,
		onskip
	}: {
		item: Item;
		n: number;
		total: number;
		meLine: string;
		busy: boolean;
		reading: boolean;
		onbox: (bbox: number[]) => void;
		onadd: (bbox: number[]) => void;
		ontype: (text: string) => void;
		onconfirm: (text: string, state: string, guess: boolean) => void;
		onclear: () => void;
		onnoplate: () => void;
		onkeep: () => void;
		onskip: () => void;
	} = $props();

	let drawing = $state(false);
	let adding = $state(false);
	let typing = $state(false);
	let typed = $state('');
	let wide = $state(false);
	// Editor state for a box that has been read
	let text = $state('');
	let st = $state('??');
	let stTouched = $state(false);

	$effect.pre(() => {
		// New item, or the same item with a fresh reading: reset everything.
		item.id;
		item.text;
		item.has_reading;
		drawing = adding = typing = false;
		typed = '';
		text = item.text;
		st = item.state ?? '??';
		stTouched = false;
	});

	$effect(() => {
		const mq = matchMedia('(min-width: 900px)');
		wide = mq.matches;
		const f = () => (wide = mq.matches);
		mq.addEventListener('change', f);
		return () => mq.removeEventListener('change', f);
	});

	const aspect = $derived(item.photo_size[0] && item.photo_size[1] ? item.photo_size[0] / item.photo_size[1] : 4 / 3);
	const mine = $derived(item.source === 'manual_box' || item.source === 'added_box');
	const boxes = $derived([
		...(item.bbox && !drawing ? [{ bbox: item.bbox, label: mine ? 'Your box' : 'Plate area' }] : []),
		...item.other_boxes.map((o, i) => ({ bbox: o.bbox, label: o.text || `Plate ${i + 2}`, dim: true }))
	]);
	const isGuess = $derived(item.state_is_guess && !stTouched && st !== '??');
	const clean = $derived(typed.toUpperCase().replace(/[^A-Z0-9? -]/g, ''));
	const locked = $derived(busy || reading);

	function drawn(bbox: number[]) {
		if (adding) {
			adding = false;
			onadd(bbox);
		} else onbox(bbox);
	}

	function startDraw(add = false) {
		drawing = true;
		adding = add;
		typing = false;
	}

	function confirm() {
		if (!text.trim() || locked) return;
		onconfirm(text, st, isGuess);
	}
</script>

<section class="panel">
	<div class="col main">
		<div class="meta">
			<div class="mrow">
				<span class="pos">{n} of {total}</span>
				<span class="lockn"><Icon name="lock" size={13} stroke={2.2} />You're reviewing this</span>
			</div>
			<p class="muted by"><Avatar user={item.by} size={22} />{meLine}</p>
			<p class="why">{reading ? 'Reading the box you drew…' : (item.reason ?? 'OCR found no plate.')}</p>
		</div>
		<PhotoViewer src={item.photo_url} {aspect} {boxes} bind:drawing {reading} height={wide ? 520 : 270} ondrawn={drawn} />
		{#if drawing}
			<div class="drawbar">
				<span>{adding ? 'Drag a box around the other plate' : item.bbox ? 'Drag a new box — it replaces the old one' : 'Drag a box around the plate'}</span>
				<button class="btn" onclick={() => ((drawing = false), (adding = false))}>Cancel</button>
			</div>
		{:else if item.bbox && !reading && !item.has_reading}
			<div class="drawbar">
				<span>{mine ? 'Box in the wrong place?' : 'Not the plate?'}</span>
				<button class="btn" disabled={locked} onclick={() => startDraw()}>Redraw</button>
				<button class="btn danger" disabled={locked} onclick={onclear}>Remove box</button>
			</div>
		{/if}
		<BlurMeter value={item.photo_blur} />
	</div>

	<div class="col side">
		{#if item.has_reading && !drawing}
			<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
			<div
				class="card result"
				role="group"
				aria-label="Reading from your box"
				onkeydown={(e) => e.key === 'Enter' && (e.target as HTMLElement).tagName === 'INPUT' && confirm()}
			>
				<div class="rhead">
					<span class="lbl">Read from your box</span>
					{#if item.text && item.confidence != null}<span class="muted" style="font-size: 12.5px">{Math.round(item.confidence * 100)}% sure</span>{/if}
				</div>
				{#if item.crop_url}
					<div class="crop"><img src={item.crop_url} alt="Plate area you drew" /></div>
				{/if}
				{#if item.disagree && item.ocr && item.vlm?.text}
					<div class="two">
						<button class="vs" class:on={text === item.ocr.text} onclick={() => (text = item.ocr!.text)}>
							<span class="lbl" style="font-size: 11px">OCR · {item.ocr.conf}%</span><span class="mono big">{item.ocr.text}</span>
						</button>
						<button class="vs" class:on={text === item.vlm.text} onclick={() => (text = item.vlm!.text!)}>
							<span class="lbl" style="font-size: 11px">AI · {item.vlm.conf}%</span><span class="mono big">{item.vlm.text}</span>
						</button>
					</div>
				{/if}
				<PlateEditor {item} bind:text bind:st bind:stTouched compact />
				<button class="btn primary block" disabled={locked || !text.trim()} onclick={confirm}>
					<Icon name="check" size={18} stroke={2.4} />Confirm {text || 'plate'}
				</button>
				<div class="row">
					<button class="btn grow" disabled={locked} onclick={() => startDraw()}><Icon name="box" size={18} stroke={2} />Redraw box</button>
					<button class="btn danger grow" disabled={locked} onclick={onclear}><Icon name="trash" size={18} stroke={2} />Remove box</button>
				</div>
			</div>
		{/if}

		{#if typing}
			<div class="card typer">
				<label class="tl"
					>Type the plate
					<input
						class="field mono plateinput"
						placeholder="7A?123"
						bind:value={typed}
						autocapitalize="characters"
						autocomplete="off"
						spellcheck="false"
						onkeydown={(e) => e.key === 'Enter' && clean && ontype(clean)}
					/>
				</label>
				<p class="muted" style="font-size: 13px">
					Use <span class="mono" style="font-weight: 800; color: var(--ink)">?</span> for each character you can't read. It's saved as a partial plate.
				</p>
				<div class="row">
					<button class="btn" onclick={() => ((typing = false), (typed = ''))}>Cancel</button>
					<button class="btn primary grow" disabled={!clean || busy} onclick={() => ontype(clean)}>{clean.includes('?') ? 'Save as partial plate' : 'Save plate'}</button>
				</div>
			</div>
		{/if}

		<div class="acts">
			{#if !item.has_reading}
				<button class="btn primary block" disabled={locked} onclick={() => startDraw()}>
					<Icon name="box" size={18} stroke={2} />{item.bbox ? 'Redraw box around plate' : 'Draw box around plate'}
				</button>
			{/if}
			<div class="row">
				<button class="btn grow" disabled={locked} onclick={() => ((typing = true), (drawing = false))}><Icon name="type" size={18} stroke={2} />Type plate</button>
				<button class="btn grow" disabled={locked} onclick={() => startDraw(true)}><Icon name="plus" size={18} stroke={2} />Add another plate</button>
			</div>
			<div class="row">
				<button class="btn danger grow" disabled={locked} onclick={onnoplate}>No plate in photo</button>
				<button class="btn grow2" disabled={locked} onclick={onkeep}>Can't read — keep sighting</button>
			</div>
			<button class="btn dashed" disabled={busy} onclick={onskip}>Skip for now</button>
		</div>
		<p class="muted desk-only" style="font-size: 13px">
			Draw a box to read just that area. The reading shows up here to confirm. "Keep sighting" saves the time and place as an unidentified sighting you can name later.
		</p>
	</div>
</section>

<style>
	.panel {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.col {
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 0;
	}
	.meta {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.mrow {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.pos {
		font-weight: 800;
		font-size: 15px;
	}
	.by {
		font-size: 13px;
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
	}
	.why {
		font-size: 13px;
		font-weight: 600;
	}
	.lockn {
		display: inline-flex;
		gap: 6px;
		align-items: center;
		font-size: 12px;
		font-weight: 600;
		color: var(--muted);
		background: var(--surface2);
		border-radius: 999px;
		padding: 3px 10px 3px 8px;
	}
	.drawbar {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
		font-size: 13.5px;
		font-weight: 600;
	}
	.drawbar span {
		flex: 1;
		min-width: 140px;
	}
	.drawbar .btn {
		min-height: 38px;
		padding: 0 12px;
	}
	.result {
		padding: 12px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		border-color: var(--accent);
	}
	.rhead {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
	}
	.crop {
		height: 96px;
		border-radius: 10px;
		background: #1c2025;
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
	}
	.crop img {
		max-width: 100%;
		max-height: 100%;
		object-fit: contain;
	}
	.two {
		display: flex;
		gap: 8px;
	}
	.vs {
		flex: 1;
		min-width: 0;
		border: 1px solid var(--line);
		border-radius: 10px;
		padding: 8px 10px;
		background: var(--surface);
		color: var(--ink);
		font: inherit;
		text-align: left;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-height: 44px;
	}
	.vs.on {
		border-color: var(--accent);
		background: var(--accent-soft);
	}
	.big {
		font-size: 17px;
		font-weight: 800;
	}
	.typer {
		padding: 12px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.tl {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-weight: 700;
		font-size: 14px;
	}
	.plateinput {
		font-size: 20px;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.acts {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.row {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}
	.grow {
		flex: 1 1 140px;
	}
	.grow2 {
		flex: 1.3 1 160px;
		white-space: normal;
		line-height: 1.2;
	}
	.dashed {
		border-style: dashed;
	}
	@media (min-width: 900px) {
		.panel {
			flex-direction: row;
			gap: 28px;
			padding: 24px 32px 32px;
			align-items: flex-start;
		}
		.main {
			flex: 1 1 560px;
		}
		.side {
			flex: 0 1 360px;
			padding-top: 70px;
		}
	}
</style>
