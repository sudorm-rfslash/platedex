<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, errorText } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import Logo from '#lib/components/Logo.svelte';
	import { loadConfig, loadSession, session } from '#lib/state/session.svelte.ts';
	import { onMount } from 'svelte';

	let username = $state('');
	let password = $state('');
	let error = $state(page.url.searchParams.get('error') || '');
	let busy = $state(false);

	// Only same-site paths: "//host" or "/\\host" would leave the app after sign-in.
	const next = $derived.by(() => {
		const n = page.url.searchParams.get('next') || '/';
		return n.startsWith('/') && !n.startsWith('//') && !n.startsWith('/\\') ? n : '/';
	});
	const cfg = $derived(session.config);
	const setup = $derived(!!cfg?.needs_setup);

	onMount(async () => {
		await loadConfig().catch(() => {});
		if (await loadSession()) goto(next, { replaceState: true });
	});

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			session.me = await api.post(setup ? '/api/auth/setup' : '/api/auth/login', { username, password });
			goto(next, { replaceState: true });
		} catch (err) {
			error = errorText(err);
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Platedex · Sign in</title></svelte:head>

<div class="wrap">
	<section class="panel desk-only">
		<div class="brand"><Logo width={64} label /><span>Platedex</span></div>
		<div class="pitch">
			<h1>Spot it. Snap it. See where it shows up next.</h1>
			<p>One shared pool of plate sightings for the whole crew. Every sighting keeps its time, place and who logged it.</p>
		</div>
		<div class="deco" aria-hidden="true">
			<span class="lp" style="transform: rotate(-3deg)">GR8FUL</span>
			<span class="lp" style="transform: rotate(2deg)">7ABC123</span>
			<span class="lp" style="transform: rotate(-1deg)">NOTMYCAR</span>
			<span class="lp" style="transform: rotate(3deg)">LUVU2</span>
			<span class="lp" style="transform: rotate(-2deg)">TX2CALI</span>
		</div>
	</section>

	<main>
		<div class="box">
			<div class="mobile-only hero">
				<Logo width={84} label />
				<h1>Platedex</h1>
				<p class="muted">Every plate the crew has spotted, in one shared pool.</p>
			</div>
			<div class="desk-only" style="display: flex; flex-direction: column; gap: 6px">
				<h2 class="title">{setup ? 'Set up Platedex' : 'Sign in'}</h2>
				<p class="muted">{setup ? 'Create the first account. It becomes the admin.' : 'Use the passkey on your home server, or a password.'}</p>
			</div>
			{#if setup}
				<p class="mobile-only note">Create the first account. It becomes the admin.</p>
			{/if}

			{#if error}<p class="err" role="alert">{error}</p>{/if}

			{#if cfg?.oidc.enabled}
				<a href="/api/auth/oidc/start" class="btn primary block big" data-sveltekit-reload>
					<Icon name="id" size={22} stroke={1.8} />Sign in with {cfg.oidc.label}
				</a>
				<p class="muted small center mobile-only">Passkey sign-in through your home server</p>
			{/if}

			{#if cfg && (cfg.local_login || setup)}
				{#if cfg.oidc.enabled}
					<div class="or"><span></span>or use a password<span></span></div>
				{/if}
				<form onsubmit={submit}>
					<label>Username<input class="field" autocomplete="username" placeholder="alex" bind:value={username} required autocapitalize="none" /></label>
					<label
						>Password<input
							class="field"
							type="password"
							autocomplete={setup ? 'new-password' : 'current-password'}
							placeholder="••••••••"
							bind:value={password}
							required
							minlength={setup ? 8 : undefined}
						/></label
					>
					<button class="btn block" class:primary={!cfg.oidc.enabled} disabled={busy} style="margin-top: 4px">
						{busy ? 'One moment…' : setup ? 'Create admin account' : 'Sign in'}
					</button>
				</form>
			{/if}
			<p class="muted small center">Self-hosted · invite only<span class="desk-only"> · install as an app from your browser menu</span></p>
		</div>
	</main>
</div>

<style>
	.wrap {
		min-height: 100dvh;
		display: flex;
	}
	.panel {
		flex: 1 1 520px;
		background: var(--panel);
		color: var(--panel-ink);
		padding: 56px 64px;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		gap: 40px;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 14px;
		font-size: 26px;
		font-weight: 800;
	}
	.pitch {
		display: flex;
		flex-direction: column;
		gap: 18px;
		max-width: 520px;
	}
	.pitch h1 {
		font-size: 44px;
		font-weight: 800;
		line-height: 1.08;
		letter-spacing: -0.01em;
	}
	.pitch p {
		color: var(--panel-muted);
		font-size: 17px;
	}
	.deco {
		display: flex;
		flex-wrap: wrap;
		gap: 14px;
	}
	.lp {
		display: inline-flex;
		background: #f4f4ef;
		color: #13204a;
		border: 2px solid #c8cedc;
		border-radius: 8px;
		padding: 8px 14px;
		font-family: 'JetBrains Mono', monospace;
		font-feature-settings: 'zero' 1;
		font-weight: 800;
		font-size: 24px;
		letter-spacing: 0.06em;
		box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
	}
	main {
		flex: 1 1 480px;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 32px 24px;
	}
	.box {
		width: 100%;
		max-width: 400px;
		display: flex;
		flex-direction: column;
		gap: 22px;
	}
	.hero {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 14px;
		text-align: center;
	}
	.hero h1 {
		font-size: 30px;
		font-weight: 800;
	}
	.hero p {
		max-width: 280px;
	}
	.title {
		font-size: 28px;
		font-weight: 800;
	}
	.big {
		min-height: 54px;
		font-size: 16px;
	}
	.or {
		display: flex;
		align-items: center;
		gap: 12px;
		font-size: 13px;
		color: var(--muted);
	}
	.or span {
		flex: 1;
		height: 1px;
		background: var(--line);
	}
	form {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-weight: 600;
		font-size: 14px;
	}
	.small {
		font-size: 12.5px;
	}
	.center {
		text-align: center;
	}
	.err {
		background: var(--bad-soft);
		color: var(--bad);
		border-radius: 10px;
		padding: 10px 12px;
		font-weight: 600;
		font-size: 14px;
	}
	.note {
		text-align: center;
		font-weight: 600;
	}
	@media (max-width: 899.98px) {
		.panel {
			display: none;
		}
	}
</style>
