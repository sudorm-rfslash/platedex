<script lang="ts">
	// Zoom/pan photo viewer with a draw-a-box mode. Boxes are [x, y, w, h] fractions of the photo.
	import Icon from './Icon.svelte';

	type Box = { bbox: number[]; label: string; dim?: boolean };
	let {
		src,
		aspect,
		boxes = [],
		drawing = $bindable(false),
		reading = false,
		blurPx = 0,
		height = 270,
		ondrawn
	}: {
		src: string;
		aspect: number;
		boxes?: Box[];
		drawing?: boolean;
		reading?: boolean;
		blurPx?: number;
		height?: number;
		ondrawn: (bbox: number[]) => void;
	} = $props();

	let frame = $state<HTMLDivElement>();
	let stage = $state<HTMLDivElement>();
	let fw = $state(0);
	let fh = $state(0);
	let zoom = $state(1);
	let px = $state(0);
	let py = $state(0);
	let drag = $state<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
	let pan: { sx: number; sy: number; px: number; py: number } | null = null;
	const pointers = new Map<number, { x: number; y: number }>();
	let pinch: { d: number; z: number } | null = null;

	// Fit the photo inside the frame (letterboxed), then zoom/pan the whole stage.
	const size = $derived.by(() => {
		if (!fw || !fh) return { w: 0, h: 0, l: 0, t: 0 };
		let w = fw;
		let h = fw / aspect;
		if (h > fh) {
			h = fh;
			w = fh * aspect;
		}
		return { w, h, l: (fw - w) / 2, t: (fh - h) / 2 };
	});

	export function reset() {
		zoom = 1;
		px = 0;
		py = 0;
	}

	function clampPan() {
		px = Math.max(fw * (1 - zoom), Math.min(0, px));
		py = Math.max(fh * (1 - zoom), Math.min(0, py));
	}

	function setZoom(z: number, cx = fw / 2, cy = fh / 2) {
		z = Math.max(1, Math.min(4, z));
		// keep the point under (cx, cy) fixed
		px = cx - ((cx - px) / zoom) * z;
		py = cy - ((cy - py) / zoom) * z;
		zoom = z;
		clampPan();
	}

	function toPhoto(e: PointerEvent) {
		const r = stage!.getBoundingClientRect();
		return {
			x: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
			y: Math.max(0, Math.min(1, (e.clientY - r.top) / r.height))
		};
	}

	function down(e: PointerEvent) {
		if (reading) return;
		frame!.setPointerCapture(e.pointerId);
		pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
		if (pointers.size === 2) {
			const [a, b] = [...pointers.values()];
			pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), z: zoom };
			drag = null;
			pan = null;
			return;
		}
		if (drawing) {
			const p = toPhoto(e);
			drag = { x0: p.x, y0: p.y, x1: p.x, y1: p.y };
		} else if (zoom > 1) pan = { sx: e.clientX, sy: e.clientY, px, py };
	}

	function move(e: PointerEvent) {
		if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
		if (pinch && pointers.size === 2) {
			const [a, b] = [...pointers.values()];
			const r = frame!.getBoundingClientRect();
			setZoom(pinch.z * (Math.hypot(a.x - b.x, a.y - b.y) / pinch.d), (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top);
			return;
		}
		if (drag) {
			const p = toPhoto(e);
			drag = { ...drag, x1: p.x, y1: p.y };
		} else if (pan) {
			px = pan.px + e.clientX - pan.sx;
			py = pan.py + e.clientY - pan.sy;
			clampPan();
		}
	}

	function up(e: PointerEvent) {
		pointers.delete(e.pointerId);
		if (pointers.size < 2) pinch = null;
		if (drag) {
			const b = norm(drag);
			drag = null;
			if (b[2] > 0.02 && b[3] > 0.01) {
				drawing = false;
				ondrawn(b);
			}
		}
		pan = null;
	}

	function norm(d: { x0: number; y0: number; x1: number; y1: number }) {
		return [Math.min(d.x0, d.x1), Math.min(d.y0, d.y1), Math.abs(d.x1 - d.x0), Math.abs(d.y1 - d.y0)];
	}

	function wheel(e: WheelEvent) {
		e.preventDefault();
		const r = frame!.getBoundingClientRect();
		setZoom(zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - r.left, e.clientY - r.top);
	}

	const live = $derived(drag ? norm(drag) : null);
	const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
</script>

<div
	class="frame"
	bind:this={frame}
	bind:clientWidth={fw}
	bind:clientHeight={fh}
	style="height: {height}px; cursor: {drawing ? 'crosshair' : zoom > 1 ? 'grab' : 'default'}"
	role="application"
	aria-label="Photo viewer. Pinch or use the zoom buttons; drag to pan."
	onpointerdown={down}
	onpointermove={move}
	onpointerup={up}
	onpointercancel={up}
	onwheel={wheel}
>
	<div class="zoomer" style="transform: translate({px}px, {py}px) scale({zoom})">
		<div class="stage" bind:this={stage} style="left: {size.l}px; top: {size.t}px; width: {size.w}px; height: {size.h}px">
			<img {src} alt="The uploaded shot" draggable="false" style="filter: blur({blurPx}px)" />
			{#each boxes as b}
				<div class="box" class:dim={b.dim} style="left: {pct(b.bbox[0])}; top: {pct(b.bbox[1])}; width: {pct(b.bbox[2])}; height: {pct(b.bbox[3])}; border-width: {2.5 / zoom}px">
					<b style="transform: scale({1 / zoom}); transform-origin: 0 100%">{b.label}</b>
				</div>
			{/each}
			{#if live}
				<div class="box dashed" style="left: {pct(live[0])}; top: {pct(live[1])}; width: {pct(live[2])}; height: {pct(live[3])}; border-width: {2.5 / zoom}px"></div>
			{/if}
		</div>
	</div>
	{#if drawing}<p class="tip">Drag a rectangle around the plate</p>{/if}
	{#if reading}
		<div class="reading"><Icon name="spinner" size={30} stroke={2.4} class="spin" />Reading…</div>
	{/if}
	<div class="zbtns">
		<button class="iconbtn" aria-label="Zoom out" onclick={() => setZoom(zoom - 0.5)} onpointerdown={(e) => e.stopPropagation()}><Icon name="minus" size={18} stroke={2.2} /></button>
		<button class="iconbtn" aria-label="Zoom in" onclick={() => setZoom(zoom + 0.5)} onpointerdown={(e) => e.stopPropagation()}><Icon name="plus" size={18} stroke={2.2} /></button>
	</div>
	<span class="zl mono">{zoom.toFixed(1)}×</span>
</div>

<style>
	.frame {
		position: relative;
		border-radius: 12px;
		overflow: hidden;
		background: #111;
		touch-action: none;
		user-select: none;
	}
	.zoomer {
		position: absolute;
		inset: 0;
		transform-origin: 0 0;
	}
	.stage {
		position: absolute;
	}
	img {
		width: 100%;
		height: 100%;
		object-fit: fill;
		pointer-events: none;
	}
	.box {
		position: absolute;
		border: 2.5px solid #ffd43b;
		border-radius: 4px;
		box-shadow: 0 0 0 2000px rgba(0, 0, 0, 0.18);
		pointer-events: none;
	}
	.box.dim {
		border-color: rgba(255, 255, 255, 0.7);
		box-shadow: none;
	}
	.box.dashed {
		border-style: dashed;
	}
	.box b {
		position: absolute;
		left: -2px;
		bottom: 100%;
		background: #ffd43b;
		color: #1a1a1a;
		font-size: 11px;
		font-weight: 800;
		padding: 2px 6px;
		border-radius: 4px 4px 4px 0;
		white-space: nowrap;
	}
	.box.dim b {
		background: rgba(255, 255, 255, 0.85);
	}
	.tip {
		position: absolute;
		left: 10px;
		right: 10px;
		top: 10px;
		background: rgba(0, 0, 0, 0.66);
		color: #fff;
		font-size: 13px;
		font-weight: 600;
		padding: 8px 10px;
		border-radius: 8px;
		text-align: center;
		pointer-events: none;
	}
	.reading {
		position: absolute;
		inset: 0;
		background: rgba(0, 0, 0, 0.55);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 10px;
		color: #fff;
		font-weight: 700;
	}
	.zbtns {
		position: absolute;
		right: 8px;
		bottom: 8px;
		display: flex;
		gap: 6px;
	}
	.zbtns .iconbtn {
		background: rgba(0, 0, 0, 0.55);
		color: #fff;
	}
	.zl {
		position: absolute;
		left: 8px;
		bottom: 8px;
		background: rgba(0, 0, 0, 0.6);
		color: #fff;
		font-size: 12px;
		font-weight: 700;
		padding: 3px 8px;
		border-radius: 6px;
	}
</style>
