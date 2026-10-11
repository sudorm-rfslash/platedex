<script lang="ts">
	import Avatar from './Avatar.svelte';
	import BlurMeter from './BlurMeter.svelte';
	import Icon from './Icon.svelte';
	import PlateEditor from './PlateEditor.svelte';

	export type Item = {
		id: number;
		photo_id: number;
		status: string;
		reason: string | null;
		by: { username: string; color: string };
		uploaded_at: string;
		place: string | null;
		text: string;
		char_conf: number[];
		candidates: [string, number][];
		ocr: { text: string; conf: number } | null;
		vlm: { text?: string; conf?: number; state?: string; error?: string } | null;
		disagree: boolean;
		state: string | null;
		state_is_guess: boolean;
		blur: number | null;
		photo_blur: number | null;
		bbox: number[] | null;
		other_boxes: { id: number; bbox: number[]; text: string | null; status: string }[];
		crop_url: string | null;
		photo_url: string;
		thumb_url: string;
		photo_size: [number, number];
		prior: string | null;
		source: string;
		has_reading: boolean;
		confidence: number | null;
	};

	let {
		item,
		n,
		total,
		pct,
		meLine,
		busy,
		onconfirm,
		onreject,
		onskip,
		onredraw
	}: {
		item: Item;
		n: number;
		total: number;
		pct: number;
		meLine: string;
		busy: boolean;
		onconfirm: (text: string, state: string, guess: boolean) => void;
		onreject: () => void;
		onskip: () => void;
		onredraw?: () => void;
	} = $props();

	let text = $state('');
	let st = $state('??');
	let stTouched = $state(false);
	let panel = $state<HTMLElement>();

	$effect.pre(() => {
		// New item: reset the editor.
		item.id;
		text = item.text;
		st = item.state ?? '??';
		stTouched = false;
	});

	const isGuess = $derived(item.state_is_guess && !stTouched && st !== '??');

	function confirm() {
		if (!text.trim() || busy) return;
		onconfirm(text, st, isGuess);
	}

	function key(e: KeyboardEvent) {
		const tag = (e.target as HTMLElement).tagName.toLowerCase();
		if (tag === 'input' || tag === 'select') {
			if (e.key === 'Enter' && tag === 'input') {
				e.preventDefault();
				confirm();
			}
			return;
		}
		if (e.metaKey || e.ctrlKey || e.altKey) return;
		if (e.key === 'Enter') (e.preventDefault(), confirm());
		else if (/^[1-3]$/.test(e.key) && item.candidates[+e.key - 1]) text = item.candidates[+e.key - 1][0];
		else if (e.key.toLowerCase() === 'x') onreject();
		else if (e.key.toLowerCase() === 's') onskip();
	}

	$effect(() => {
		item.id;
		if (matchMedia('(min-width: 900px)').matches) panel?.focus();
	});

	const thumbBox = $derived(item.bbox);
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<section class="panel" tabindex="-1" bind:this={panel} onkeydown={key} aria-label="Verify item. Keyboard: Enter confirm, 1 to 3 pick a reading, X reject, S skip.">
	<div class="col main">
		<div class="meta">
			<div class="mrow">
				<span class="pos">{n} of {total}</span>
				<span class="lockn"><Icon name="lock" size={13} stroke={2.2} />You're reviewing this</span>
			</div>
			<div class="meter thin"><span style="width: {pct}%; background: var(--accent)"></span></div>
			<p class="muted by"><Avatar user={item.by} size={22} />{meLine}</p>
		</div>

		<div class="crop">
			{#if item.crop_url}
				<img src={item.crop_url} alt="Plate crop" class="cropimg" />
			{:else}
				<span class="muted">No crop</span>
			{/if}
			<a class="thumb" href={item.photo_url} target="_blank" rel="noopener" aria-label="Open full photo">
				<img src={item.thumb_url} alt="Whole scene" />
				{#if thumbBox}
					<span class="tb" style="left: {thumbBox[0] * 100}%; top: {thumbBox[1] * 100}%; width: {thumbBox[2] * 100}%; height: {thumbBox[3] * 100}%"></span>
				{/if}
			</a>
			<span class="tagl">Plate crop</span>
		</div>

		<BlurMeter value={item.blur} />
		{#if onredraw && !busy}
			<button class="redraw" onclick={onredraw}><Icon name="box" size={16} stroke={2} />Wrong spot? Redraw the box</button>
		{/if}

		{#if item.disagree && item.ocr && item.vlm?.text}
			<div class="stack">
				<span class="lbl">Readers disagree</span>
				<div class="two">
					<button class="vs" class:on={text === item.ocr.text} onclick={() => (text = item.ocr!.text)}>
						<span class="lbl" style="font-size: 11px">OCR · {item.ocr.conf}%</span>
						<span class="mono big">{item.ocr.text}</span>
					</button>
					<button class="vs" class:on={text === item.vlm.text} onclick={() => (text = item.vlm!.text!)}>
						<span class="lbl" style="font-size: 11px">AI (VLM) · {item.vlm.conf}%</span>
						<span class="mono big">{item.vlm.text}</span>
					</button>
				</div>
			</div>
		{:else if item.reason}
			<p class="reason">{item.reason}</p>
		{/if}
	</div>

	<div class="col side">
		<PlateEditor {item} bind:text bind:st bind:stTouched />
		{#if item.prior}<p class="muted" style="font-size: 13px">{item.prior}</p>{/if}

		<div class="actions">
			<button class="btn danger" onclick={onreject} disabled={busy} aria-label="Reject: not a plate"><span class="kbd desk-only">X</span><Icon name="close" size={18} stroke={2.2} class="mobile-only" />Not a plate</button>
			<button class="btn" onclick={onskip} disabled={busy}><span class="kbd desk-only">S</span>Skip</button>
			<button class="btn primary grow" onclick={confirm} disabled={busy || !text.trim()}><Icon name="check" size={18} stroke={2.4} />Confirm<span class="kbd desk-only">Enter</span></button>
		</div>
		<p class="muted keys desk-only">Shortcuts work while this panel has focus: <span class="kbd">Enter</span> confirm · <span class="kbd">1</span>–<span class="kbd">3</span> pick a reading · <span class="kbd">X</span> reject · <span class="kbd">S</span> skip</p>
	</div>
</section>

<style>
	.panel {
		display: flex;
		flex-direction: column;
		gap: 14px;
		outline: none;
		padding-bottom: 76px;
	}
	.col {
		display: flex;
		flex-direction: column;
		gap: 14px;
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
	.thin {
		height: 4px;
		flex: none;
	}
	.by {
		font-size: 13px;
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
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
	.crop {
		position: relative;
		border-radius: 12px;
		overflow: hidden;
		height: 150px;
		background: #1c2025;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.cropimg {
		max-width: 100%;
		max-height: 100%;
		object-fit: contain;
	}
	.thumb {
		position: absolute;
		right: 8px;
		bottom: 8px;
		width: 84px;
		height: 63px;
		border-radius: 6px;
		border: 2px solid #fff;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
		overflow: hidden;
		background: #333;
	}
	.thumb img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.tb {
		position: absolute;
		border: 2px solid #ffd43b;
	}
	.tagl {
		position: absolute;
		left: 8px;
		top: 8px;
		background: rgba(0, 0, 0, 0.55);
		color: #fff;
		font-size: 11px;
		font-weight: 700;
		padding: 2px 8px;
		border-radius: 6px;
	}
	.stack {
		display: flex;
		flex-direction: column;
		gap: 8px;
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
		padding: 10px;
		background: var(--surface);
		color: var(--ink);
		font: inherit;
		text-align: left;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-height: 44px;
	}
	.vs.on {
		border-color: var(--accent);
		background: var(--accent-soft);
	}
	.big {
		font-size: 19px;
		font-weight: 800;
	}
	.redraw {
		align-self: flex-start;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 36px;
		border: 0;
		background: none;
		padding: 0;
		font: inherit;
		font-size: 13.5px;
		font-weight: 700;
		color: var(--accent);
		cursor: pointer;
	}
	.reason {
		font-size: 13.5px;
		font-weight: 600;
		color: var(--amber-ink);
		background: var(--amber-bg);
		border-radius: 8px;
		padding: 6px 10px;
		align-self: flex-start;
	}
	.actions {
		display: flex;
		gap: 8px;
		position: fixed;
		left: 0;
		right: 0;
		bottom: calc(64px + max(8px, var(--safe-bottom)));
		padding: 10px 16px;
		border-top: 1px solid var(--line);
		background: var(--surface);
		z-index: 10;
	}
	.grow {
		flex: 1;
	}
	.keys {
		font-size: 12.5px;
	}
	@media (min-width: 900px) {
		.panel {
			flex-direction: row;
			flex-wrap: wrap;
			gap: 28px;
			padding: 24px 32px 32px;
			align-content: flex-start;
		}
		.main {
			flex: 1 1 420px;
		}
		.side {
			flex: 1 1 340px;
		}
		.crop {
			height: 230px;
		}
		.thumb {
			width: 120px;
			height: 90px;
		}
		.actions {
			position: static;
			padding: 0;
			border: 0;
			background: none;
			flex-wrap: wrap;
		}
	}
</style>
