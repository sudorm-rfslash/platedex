<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, errorText } from '#lib/api.ts';
	import Icon from '#lib/components/Icon.svelte';
	import Logo from '#lib/components/Logo.svelte';
	import { session } from '#lib/state/session.svelte.ts';
	import { onMount } from 'svelte';

	const token = $derived(page.params.token ?? '');
	let info = $state<{ valid: boolean; role: string | null } | null>(null);
	let username = $state('');
	let password = $state('');
	let error = $state('');
	let busy = $state(false);

	onMount(async () => {
		info = await api.get(`/api/auth/invite/${token}`).catch(() => ({ valid: false, role: null }));
	});

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			session.me = await api.post('/api/auth/register', { token, username, password });
			goto('/upload', { replaceState: true });
		} catch (err) {
			error = errorText(err);
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Platedex · Join</title></svelte:head>

<main>
	<div class="box">
		<div class="hero">
			<Logo width={84} label />
			<h1>Join Platedex</h1>
		</div>
		{#if info === null}
			<p class="muted center">Checking your invite…</p>
		{:else if !info.valid}
			<p class="err">This invite link is invalid or has expired. Ask your admin for a new one.</p>
			<a href="/login" class="btn block">Go to sign in</a>
		{:else}
			<p class="muted center">You're invited as a <b>{info.role}</b>.</p>
			{#if error}<p class="err" role="alert">{error}</p>{/if}
			{#if session.config?.oidc.enabled}
				<a href="/api/auth/oidc/start?invite={token}" class="btn primary block" data-sveltekit-reload style="min-height: 54px">
					<Icon name="id" size={22} stroke={1.8} />Join with {session.config.oidc.label}
				</a>
			{/if}
			{#if session.config?.local_login}
				<form onsubmit={submit}>
					<label>Pick a username<input class="field" autocomplete="username" bind:value={username} required autocapitalize="none" /></label>
					<label>Password<input class="field" type="password" autocomplete="new-password" minlength="8" bind:value={password} required /></label>
					<button class="btn block" class:primary={!session.config?.oidc.enabled} disabled={busy}>{busy ? 'One moment…' : 'Create account'}</button>
				</form>
			{/if}
		{/if}
	</div>
</main>

<style>
	main {
		min-height: 100dvh;
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
		gap: 20px;
	}
	.hero {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 12px;
	}
	h1 {
		font-size: 28px;
		font-weight: 800;
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
</style>
