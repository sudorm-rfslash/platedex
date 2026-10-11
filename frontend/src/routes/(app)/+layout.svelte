<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import Avatar from '#lib/components/Avatar.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import Logo from '#lib/components/Logo.svelte';
	import { counts, startCountPolling } from '#lib/state/counts.svelte.ts';
	import { loadSession, session } from '#lib/state/session.svelte.ts';
	import { api } from '#lib/api.ts';
	import { onMount } from 'svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	const NAV = [
		{ href: '/upload', label: 'Upload', icon: 'upload' },
		{ href: '/review', label: 'Review', icon: 'review' },
		{ href: '/plates', label: 'Plates', icon: 'plates' },
		{ href: '/map', label: 'Map', icon: 'map' },
		{ href: '/more', label: 'More', icon: 'more' }
	];

	onMount(() => {
		let stop: (() => void) | undefined;
		(session.loaded ? Promise.resolve(session.me) : loadSession()).then((me: unknown) => {
			if (!me) goto('/login?next=' + encodeURIComponent(page.url.pathname + page.url.search), { replaceState: true });
			else stop = startCountPolling();
		});
		return () => stop?.();
	});

	const active = (href: string) => page.url.pathname === href || page.url.pathname.startsWith(href + '/');
	const roleLabel = $derived(session.me ? session.me.role[0].toUpperCase() + session.me.role.slice(1) : '');

	async function signOut() {
		try {
			await api.post('/api/auth/logout');
		} catch {
			/* offline or already signed out: still leave */
		}
		session.me = null;
		goto('/login');
	}
</script>

{#if session.me}
	<div class="shell">
		<nav class="side" aria-label="Main">
			<a href="/upload" class="brand"><Logo width={40} /><span>Platedex</span></a>
			{#each NAV as n}
				<a class="nav" class:on={active(n.href)} href={n.href} aria-current={active(n.href) ? 'page' : undefined}>
					<Icon name={n.icon} />{n.label}
					{#if n.href === '/review' && counts.badge > 0}<span class="badge" style="margin-left: auto" aria-label="{counts.badge} pending">{counts.badge}</span>{/if}
				</a>
			{/each}
			<div class="me">
				<Avatar user={session.me} size={32} />
				<div style="flex: 1; min-width: 0">
					<p style="font-weight: 700; font-size: 14px">{session.me.username}</p>
					<p class="muted" style="font-size: 12px">{roleLabel}</p>
				</div>
				<button class="link" onclick={signOut}>Sign out</button>
			</div>
		</nav>
		<main class="main">{@render children()}</main>
		<nav class="tabbar" aria-label="Main">
			{#each NAV as n}
				<a href={n.href} class:on={active(n.href)} aria-current={active(n.href) ? 'page' : undefined}>
					<Icon name={n.icon} />{n.label}
					{#if n.href === '/review' && counts.badge > 0}<span class="badge" aria-label="{counts.badge} pending">{counts.badge}</span>{/if}
				</a>
			{/each}
		</nav>
	</div>
{/if}

<style>
	.shell {
		height: 100dvh;
		display: flex;
		flex-direction: column;
	}
	.main {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		position: relative;
	}
	.side {
		display: none;
	}
	.tabbar {
		display: grid;
		grid-template-columns: repeat(5, minmax(0, 1fr));
		border-top: 1px solid var(--line);
		background: var(--surface);
		padding-bottom: max(8px, var(--safe-bottom));
		flex: none;
		z-index: 20;
	}
	.tabbar a {
		min-height: 56px;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 3px;
		font-size: 11px;
		font-weight: 600;
		color: var(--muted);
		text-decoration: none;
		position: relative;
	}
	.tabbar a.on {
		color: var(--accent);
	}
	.tabbar .badge {
		position: absolute;
		top: 4px;
		left: calc(50% + 5px);
	}
	@media (min-width: 900px) {
		.shell {
			flex-direction: row;
		}
		.tabbar {
			display: none;
		}
		.side {
			width: 240px;
			flex: none;
			background: var(--surface);
			border-right: 1px solid var(--line);
			padding: 20px 14px;
			display: flex;
			flex-direction: column;
			gap: 4px;
			height: 100dvh;
			position: sticky;
			top: 0;
		}
		.main {
			overflow-y: auto;
		}
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 0 8px 18px;
		color: var(--ink);
		text-decoration: none;
		font-size: 20px;
		font-weight: 800;
	}
	.nav {
		display: flex;
		align-items: center;
		gap: 12px;
		min-height: 44px;
		padding: 0 12px;
		border-radius: 10px;
		color: var(--ink);
		text-decoration: none;
		font-weight: 600;
	}
	.nav:hover {
		background: var(--surface2);
	}
	.nav.on {
		background: var(--accent-soft);
		color: var(--accent);
	}
	.me {
		margin-top: auto;
		padding: 14px 8px 0;
		border-top: 1px solid var(--line);
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.link {
		border: 0;
		background: none;
		font: inherit;
		font-size: 13px;
		font-weight: 700;
		color: var(--accent);
		cursor: pointer;
		min-height: 32px;
	}
</style>
