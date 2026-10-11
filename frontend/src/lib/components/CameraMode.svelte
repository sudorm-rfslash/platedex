<script lang="ts">
	// In-app camera: live viewfinder plus the phone's location, so photos never lose their GPS.
	import { onMount } from 'svelte';
	import { coord } from '../format';
	import Icon from './Icon.svelte';

	type Loc = { lat: number; lon: number; accuracy: number };
	let { onshoot, onclose }: { onshoot: (file: File, loc: Loc | null) => void; onclose: () => void } = $props();

	let video: HTMLVideoElement;
	let stream: MediaStream | null = null;
	let loc = $state<Loc | null>(null);
	let locError = $state('');
	let camError = $state('');
	let flash = $state(false);
	let fallbackInput: HTMLInputElement;

	onMount(() => {
		let watch: number | undefined;
		if ('geolocation' in navigator) {
			watch = navigator.geolocation.watchPosition(
				(p) => (loc = { lat: p.coords.latitude, lon: p.coords.longitude, accuracy: Math.round(p.coords.accuracy) }),
				(e) => (locError = e.code === 1 ? 'Location blocked — allow it in your browser settings' : 'Finding your location…'),
				{ enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 }
			);
		} else locError = 'This browser has no location access';

		(async () => {
			try {
				stream = await navigator.mediaDevices.getUserMedia({
					audio: false,
					video: { facingMode: { ideal: 'environment' }, width: { ideal: 3840 }, height: { ideal: 2160 } }
				});
				video.srcObject = stream;
				await video.play();
			} catch {
				camError = 'Camera unavailable here. Use your phone’s camera app instead — your location is still attached.';
			}
		})();
		return () => {
			if (watch !== undefined) navigator.geolocation.clearWatch(watch);
			stream?.getTracks().forEach((t) => t.stop());
		};
	});

	async function shoot() {
		flash = true;
		setTimeout(() => (flash = false), 120);
		const track = stream?.getVideoTracks()[0];
		let blob: Blob | null = null;
		// Full-resolution still where the browser supports it (Chrome on Android).
		const IC = (window as any).ImageCapture;
		if (track && IC) {
			try {
				blob = await new IC(track).takePhoto();
			} catch {
				blob = null;
			}
		}
		if (!blob) {
			const c = document.createElement('canvas');
			c.width = video.videoWidth;
			c.height = video.videoHeight;
			c.getContext('2d')!.drawImage(video, 0, 0);
			blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', 0.92));
		}
		if (!blob) return;
		const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 13);
		onshoot(new File([blob], `CAM_${stamp}.jpg`, { type: 'image/jpeg', lastModified: Date.now() }), loc);
	}

	function pickFromCameraApp(e: Event) {
		const f = (e.currentTarget as HTMLInputElement).files?.[0];
		if (f) onshoot(new File([f], f.name || `CAM_${Date.now()}.jpg`, { type: f.type, lastModified: Date.now() }), loc);
	}
</script>

<div class="cam" role="dialog" aria-label="Camera mode">
	<div class="top">
		<button class="iconbtn" aria-label="Close camera" onclick={onclose} style="color: #fff"><Icon name="close" stroke={2} /></button>
		<span class="loc">
			<Icon name="pin" size={15} stroke={2.2} style="color: {loc ? '#7CE3A1' : '#F4D27E'}" />
			{#if loc}<span class="mono">{coord(loc.lat, loc.lon)}</span> ±{loc.accuracy} m{:else}{locError || 'Finding your location…'}{/if}
		</span>
		<span style="width: 44px"></span>
	</div>
	<div class="view">
		<!-- svelte-ignore a11y_media_has_caption -->
		<video bind:this={video} playsinline muted></video>
		{#if camError}
			<div class="err">
				<p>{camError}</p>
				<button class="btn primary" onclick={() => fallbackInput.click()}><Icon name="camera" />Open camera app</button>
			</div>
		{:else}
			<div class="frame"></div>
			<p class="hint">Fill the box with the plate</p>
		{/if}
		{#if flash}<div class="flash"></div>{/if}
	</div>
	<div class="bottom">
		<button class="appcam" onclick={() => fallbackInput.click()}>Camera app</button>
		<button class="shutter" aria-label="Take photo" onclick={shoot} disabled={!!camError}><span></span></button>
		<span style="width: 84px"></span>
	</div>
	<input bind:this={fallbackInput} type="file" accept="image/*" capture="environment" hidden onchange={pickFromCameraApp} />
</div>

<style>
	.cam {
		position: fixed;
		inset: 0;
		background: #050607;
		z-index: 50;
		display: flex;
		flex-direction: column;
		color: #fff;
	}
	.top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: max(12px, env(safe-area-inset-top)) 12px 8px;
	}
	.loc {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		background: rgba(255, 255, 255, 0.14);
		border-radius: 999px;
		padding: 6px 12px;
		font-size: 13px;
		font-weight: 600;
		max-width: calc(100vw - 120px);
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}
	.view {
		flex: 1;
		position: relative;
		overflow: hidden;
	}
	video {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.frame {
		position: absolute;
		left: 50%;
		top: 55%;
		width: min(62vw, 360px);
		aspect-ratio: 2 / 1;
		transform: translate(-50%, -50%);
		border: 2px solid rgba(255, 255, 255, 0.9);
		border-radius: 10px;
		box-shadow: 0 0 0 2000px rgba(0, 0, 0, 0.18);
	}
	.hint {
		position: absolute;
		left: 0;
		right: 0;
		top: 16px;
		text-align: center;
		font-size: 13px;
		font-weight: 600;
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
	}
	.err {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 14px;
		padding: 24px;
		text-align: center;
	}
	.flash {
		position: absolute;
		inset: 0;
		background: #fff;
		opacity: 0.6;
	}
	.bottom {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 22px 24px max(32px, env(safe-area-inset-bottom));
	}
	.shutter {
		width: 76px;
		height: 76px;
		border-radius: 50%;
		border: 4px solid #fff;
		background: transparent;
		padding: 5px;
		cursor: pointer;
	}
	.shutter span {
		display: block;
		width: 100%;
		height: 100%;
		border-radius: 50%;
		background: #fff;
	}
	.shutter:active span {
		transform: scale(0.92);
	}
	.appcam {
		width: 84px;
		min-height: 44px;
		background: rgba(255, 255, 255, 0.14);
		border: 0;
		border-radius: 999px;
		color: #fff;
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
	}
</style>
