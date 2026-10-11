<script lang="ts">
	import { api, errorText } from '../api';
	import { flash } from '../state/toast.svelte';
	import Icon from './Icon.svelte';
	import Sheet from './Sheet.svelte';

	let { url, tokens, oncreated }: { url: string; tokens: { name: string }[]; oncreated: () => void } = $props();

	const PREFIX = 'Shortcut · ';
	let open = $state(false);
	let device = $state('iPhone');
	let busy = $state(false);
	let code = $state<string | null>(null);
	let copied = $state(false);

	// iPadOS also says "Macintosh"; a touch screen tells them apart.
	const isMac = typeof navigator !== 'undefined' && /Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints < 2;
	const older = $derived(tokens.filter((t) => t.name.startsWith(PREFIX)).length);

	function start() {
		code = null;
		copied = false;
		device = 'iPhone';
		open = true;
	}

	async function create() {
		if (busy) return;
		busy = true;
		// The setup code is the server address and the token. The Shortcut splits it at "#".
		const pending = api
			.post<{ token: string }>('/api/tokens', { name: PREFIX + (device.trim() || 'iPhone') })
			.then((t) => `${location.origin}#${t.token}`);
		// Safari only allows clipboard writes during the tap, so hand it the pending text right away.
		const copying =
			typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write
				? navigator.clipboard.write([new ClipboardItem({ 'text/plain': pending.then((s) => new Blob([s], { type: 'text/plain' })) })])
				: pending.then((s) => navigator.clipboard.writeText(s));
		try {
			code = await pending;
			oncreated();
		} catch (e) {
			flash(errorText(e));
			busy = false;
			return;
		}
		copied = await copying.then(
			() => true,
			() => false
		);
		busy = false;
	}

	async function copy() {
		try {
			await navigator.clipboard.writeText(code!);
			copied = true;
		} catch {
			flash('Copy failed — select the code and copy it by hand');
		}
	}
</script>

<button class="card setup" onclick={start}>
	<Icon name="download" size={26} stroke={1.9} style="color: var(--accent); flex: none" />
	<span style="flex: 1; min-width: 0">
		<span class="t">Set up iPhone Shortcut</span>
		<span class="muted s">Share photos from Photos straight to Platedex. Location and time are kept.</span>
	</span>
	<Icon name="chevron" size={18} stroke={2} />
</button>

<Sheet bind:open title="iPhone Shortcut" onclose={() => (code = null)}>
	{#if !code}
		<p style="font-size: 14px">This creates a new API token just for the Shortcut and copies a <b>setup code</b> for you to paste once.</p>
		<p class="muted small">
			Existing tokens can't be reused: Platedex only keeps a fingerprint of each token, so it can't show one again. You can revoke the Shortcut's token any time in API tokens.
		</p>
		<label class="fl">Which device is this for?<input class="field" bind:value={device} maxlength="60" placeholder="iPhone" onkeydown={(e) => e.key === 'Enter' && create()} /></label>
		{#if older}
			<p class="muted small">You already have {older === 1 ? 'a Shortcut token' : `${older} Shortcut tokens`}. If this replaces an old phone, revoke the old token afterwards.</p>
		{/if}
		<button class="btn primary block" onclick={create} disabled={busy}>{busy ? 'Creating…' : 'Create token and setup code'}</button>
	{:else}
		<div class="once" role="status">
			<p style="font-weight: 800">{copied ? 'Setup code copied.' : 'Copy your setup code.'} You won't see it again.</p>
			<div class="row" style="align-items: center"><code class="mono tok">{code}</code><button class="btn primary" onclick={copy}>{copied ? 'Copied' : 'Copy'}</button></div>
			<p class="small">Anyone with this code can upload as you. Don't share it.</p>
		</div>
		<ol class="steps">
			<li>
				<a class="btn primary" href={url} target="_blank" rel="noopener"><Icon name="download" size={18} />Get the Shortcut</a>
				{#if isMac}<span class="muted small">This adds it to Shortcuts on this Mac. For your iPhone, open this page on the iPhone instead.</span>{/if}
			</li>
			<li>Tap <b>Set Up Shortcut</b> (or <b>Add Shortcut</b>) and paste the setup code when asked.</li>
			<li>In Photos, select plates → Share → <b>Platedex</b>. The originals upload with their location.</li>
		</ol>
		<button class="btn block" onclick={() => ((open = false), (code = null))}>Done</button>
	{/if}
</Sheet>

<style>
	.setup {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 14px;
		width: 100%;
		text-align: left;
		font: inherit;
		color: inherit;
		cursor: pointer;
	}
	.setup:hover {
		border-color: var(--accent);
	}
	.t {
		display: block;
		font-weight: 800;
		font-size: 15px;
	}
	.s {
		display: block;
		font-size: 13px;
	}
	.small {
		font-size: 13px;
	}
	.fl {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 13.5px;
		font-weight: 700;
	}
	.once {
		background: var(--amber-bg);
		border: 1px solid var(--amber-line);
		border-radius: 12px;
		padding: 12px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		color: var(--amber-ink);
	}
	.row {
		display: flex;
		gap: 8px;
	}
	.tok {
		flex: 1;
		min-width: 0;
		overflow-wrap: anywhere;
		background: var(--surface);
		color: var(--ink);
		border-radius: 8px;
		padding: 8px 10px;
		font-size: 12.5px;
		font-weight: 700;
		user-select: all;
	}
	.steps {
		padding-left: 20px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		font-size: 14px;
	}
	.steps li > :global(.btn) {
		display: inline-flex;
		margin-bottom: 4px;
	}
	.steps li > .small {
		display: block;
	}
</style>
