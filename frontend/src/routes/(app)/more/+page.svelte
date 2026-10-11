<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { api, errorText } from '#lib/api.ts';
	import Avatar from '#lib/components/Avatar.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import Sheet from '#lib/components/Sheet.svelte';
	import ShortcutSetup from '#lib/components/ShortcutSetup.svelte';
	import LockNote from '#lib/components/LockNote.svelte';
	import ServerSettings, { type AdminSettings } from '#lib/components/ServerSettings.svelte';
	import { ago, longDate, shortDate } from '#lib/format.ts';
	import { loadConfig, loadSession, session } from '#lib/state/session.svelte.ts';
	import { setTheme, theme, type Theme } from '#lib/state/theme.svelte.ts';
	import { flash } from '#lib/state/toast.svelte.ts';
	import { onDestroy, onMount } from 'svelte';

	type Token = { id: number; name: string; prefix: string; created_at: string; last_used_at: string | null; confirm?: boolean };
	type AUser = { id: number; username: string; color: string; role: string; sightings: number; last_active_at: string | null; you: boolean; disabled: boolean };
	type Rp = { state: 'idle' | 'running' | 'paused' | 'done'; total: number; done: number; changed: number };

	const isAdmin = $derived(session.me?.role === 'admin');
	// The Shortcut only runs on Apple devices (iPadOS and macOS both report "Macintosh").
	const apple = typeof navigator !== 'undefined' && /iPhone|iPad|iPod|Macintosh/.test(navigator.userAgent);
	const shortcutReady = $derived(apple && !!session.config?.shortcut_url);
	let tab = $state<'settings' | 'admin'>(page.url.searchParams.get('tab') === 'admin' ? 'admin' : 'settings');
	let tokens = $state<Token[]>([]);
	let tname = $state('');
	let newToken = $state<string | null>(null);
	let copied = $state(false);
	let users = $state<AUser[]>([]);
	let settings = $state<AdminSettings | null>(null);
	let shortcutDraft = $state('');
	let rp = $state<Rp>({ state: 'idle', total: 0, done: 0, changed: 0 });
	let invite = $state<{ url: string; role: string } | null>(null);
	let inviteRole = $state('member');
	let pwOpen = $state(false);
	let pw = $state({ current: '', next: '' });
	let rpTimer: ReturnType<typeof setInterval> | undefined;

	const MODES: Record<string, string> = {
		auto: 'Auto: ask the AI reader only when OCR is unsure or a character looks ambiguous. Recommended.',
		always: 'Always: read every photo with both. Slower and uses more GPU, catches more look-alikes.',
		off: 'Off: OCR only. Disagreements are never shown in Review.'
	};

	onMount(() => {
		const linked = page.url.searchParams.get('linked');
		const err = page.url.searchParams.get('error');
		if (linked) flash('Pocket ID linked');
		if (err) flash(err);
		loadTokens();
		loadConfig().catch(() => {}); // the copy from before sign-in leaves out the Shortcut link
		if (isAdmin) loadAdmin();
	});
	onDestroy(() => clearInterval(rpTimer));

	async function loadTokens() {
		tokens = await api.get('/api/tokens').catch(() => []);
	}

	async function loadAdmin() {
		const [u, s, r] = await Promise.all([api.get('/api/admin/users'), api.get('/api/admin/settings'), api.get('/api/admin/reprocess')]);
		users = u;
		settings = s;
		shortcutDraft = s.shortcut_url ?? '';
		rp = r;
		if (rp.state === 'running') pollRp();
	}

	async function createToken() {
		try {
			const t = await api.post('/api/tokens', { name: tname });
			newToken = t.token;
			copied = false;
			tname = '';
			loadTokens();
		} catch (e) {
			flash(errorText(e));
		}
	}

	async function copy() {
		try {
			await navigator.clipboard.writeText(newToken!);
			copied = true;
		} catch {
			flash('Copy failed — select the token and copy it by hand');
		}
	}

	async function revoke(t: Token) {
		const r = await api.del(`/api/tokens/${t.id}`);
		flash(r.toast);
		loadTokens();
	}

	async function unlink() {
		try {
			session.me = await api.post('/api/auth/oidc/unlink');
			flash('Pocket ID unlinked');
		} catch (e) {
			flash(errorText(e));
		}
	}

	async function changePassword() {
		try {
			session.me = await api.post('/api/auth/password', { current: pw.current || null, new: pw.next });
			pwOpen = false;
			pw = { current: '', next: '' };
			flash('Password changed');
		} catch (e) {
			flash(errorText(e));
		}
	}

	async function signOut() {
		await api.post('/api/auth/logout');
		session.me = null;
		goto('/login');
	}

	async function setRole(u: AUser, role: string) {
		try {
			const r = await api.patch(`/api/admin/users/${u.id}`, { role });
			flash(r.toast);
			u.role = role;
			if (u.you) await loadSession();
		} catch (e) {
			flash(errorText(e));
			users = await api.get('/api/admin/users');
		}
	}

	async function makeInvite() {
		try {
			invite = await api.post('/api/admin/invites', { role: inviteRole });
		} catch (e) {
			flash(errorText(e));
		}
	}

	let thrTimer: ReturnType<typeof setTimeout> | undefined;
	function onThr(v: number) {
		if (!settings) return;
		settings.ocr_threshold = v;
		clearTimeout(thrTimer);
		thrTimer = setTimeout(() => saveSettings({ ocr_threshold: v }), 400);
	}

	/** Save admin settings; the sign-in page and the Shortcut button read some of them via the config. */
	async function saveSettings(patch: Record<string, unknown>, msg?: string): Promise<boolean> {
		if (!Object.keys(patch).length) return true;
		try {
			settings = await api.put('/api/admin/settings', patch);
			if (msg) flash(msg);
			loadConfig().catch(() => {});
			return true;
		} catch (e) {
			flash(errorText(e));
			if (settings) settings = await api.get('/api/admin/settings').catch(() => settings);
			return false;
		}
	}

	async function setMode(m: string) {
		await saveSettings({ vlm_mode: m });
	}

	async function saveShortcut(url: string) {
		if (await saveSettings({ shortcut_url: url }, url ? 'Shortcut link saved' : 'Shortcut link removed')) shortcutDraft = settings!.shortcut_url ?? '';
	}

	function pollRp() {
		clearInterval(rpTimer);
		rpTimer = setInterval(async () => {
			rp = await api.get('/api/admin/reprocess');
			if (rp.state !== 'running') clearInterval(rpTimer);
		}, 1500);
	}

	async function rpAction() {
		const action = rp.state === 'running' ? 'pause' : rp.state === 'paused' ? 'resume' : 'start';
		try {
			rp = await api.post('/api/admin/reprocess', { action });
			if (rp.state === 'running') pollRp();
		} catch (e) {
			flash(errorText(e));
		}
	}

	const rpPct = $derived(rp.total ? Math.round((rp.done / rp.total) * 100) : 0);
	const roleLabel = $derived(session.me ? session.me.role[0].toUpperCase() + session.me.role.slice(1) : '');
	const THEMES: [Theme, string][] = [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']];
</script>

<svelte:head><title>Platedex · More</title></svelte:head>

<div class="page">
	<header class="page-head">
		<h1>More</h1>
		{#if isAdmin}
			<div class="seg full tabsw" role="tablist">
				<button role="tab" class:on={tab === 'settings'} aria-selected={tab === 'settings'} onclick={() => (tab = 'settings')}>Settings</button>
				<button role="tab" class:on={tab === 'admin'} aria-selected={tab === 'admin'} onclick={() => ((tab = 'admin'), !users.length && loadAdmin())}>Admin</button>
			</div>
		{/if}
	</header>

	<div class="page-body body">
		{#if tab === 'settings' && session.me}
			<div class="card me">
				<Avatar user={session.me} />
				<div style="flex: 1; min-width: 0"><p style="font-weight: 800">{session.me.username}</p><p class="muted" style="font-size: 13px">{roleLabel} · {session.me.sightings} sightings logged</p></div>
				<button class="btn" onclick={signOut}>Sign out</button>
			</div>

			<section class="sec">
				<span class="lbl">Appearance</span>
				<div class="seg full">
					{#each THEMES as [k, label]}<button class:on={theme.value === k} aria-pressed={theme.value === k} onclick={() => setTheme(k)}>{label}</button>{/each}
				</div>
			</section>

			{#if session.me.role !== 'viewer'}
				<section class="sec">
					<div class="srow"><span class="lbl">API tokens</span><span class="muted" style="font-size: 12.5px">for the iOS Shortcut</span></div>
					<p class="muted" style="font-size: 13.5px; margin-top: -4px">The Shortcut uploads original photos, so location and time are kept.</p>
					{#if shortcutReady}<ShortcutSetup url={session.config!.shortcut_url!} {tokens} oncreated={loadTokens} />{/if}
					{#if newToken}
						<div class="once" role="status">
							<p style="font-weight: 800">Copy this token now. You won't see it again.</p>
							<div class="row" style="align-items: center"><code class="mono tok">{newToken}</code><button class="btn primary" onclick={copy}>{copied ? 'Copied' : 'Copy'}</button></div>
							<button class="btn" style="align-self: flex-start" onclick={() => (newToken = null)}>Done</button>
						</div>
					{/if}
					<div class="card">
						{#each tokens as t (t.id)}
							<div class="item wrap">
								<div style="flex: 1; min-width: 0">
									<p style="font-weight: 700">{t.name}</p>
									<p class="muted" style="font-size: 12.5px"><span class="mono">{t.prefix}</span> · created {shortDate(t.created_at)}</p>
									<p style="font-size: 12.5px">Last used {ago(t.last_used_at)}</p>
								</div>
								{#if !t.confirm}
									<button class="btn danger" onclick={() => (t.confirm = true)}>Revoke</button>
								{:else}
									<div class="confirm"><span style="font-size: 13px; flex: 1">Shortcuts using it will stop working.</span><button class="btn" onclick={() => (t.confirm = false)}>Cancel</button><button class="btn dangerfill" onclick={() => revoke(t)}>Revoke</button></div>
								{/if}
							</div>
						{:else}
							<p class="muted" style="padding: 14px; font-size: 14px">No tokens yet.</p>
						{/each}
					</div>
					<div class="row">
						<label style="flex: 1"><span class="sr-only">Token name</span><input class="field" placeholder="Token name, e.g. Maya's iPhone" bind:value={tname} onkeydown={(e) => e.key === 'Enter' && createToken()} /></label>
						<button class="btn primary" onclick={createToken}>Create</button>
					</div>
				</section>
			{/if}

			<section class="sec">
				<span class="lbl">Linked accounts</span>
				<div class="card">
					{#if session.config?.oidc.enabled}
						<div class="item">
							<Icon name="id" size={28} stroke={1.8} />
							<div style="flex: 1"><p style="font-weight: 700">{session.config.oidc.label}</p><p class="muted" style="font-size: 12.5px">{session.me.oidc_linked ? `Linked${session.me.oidc_linked_at ? ` · since ${longDate(session.me.oidc_linked_at)}` : ''}` : 'Not linked. Link to sign in with a passkey.'}</p></div>
							<span class="pill {session.me.oidc_linked ? 'p-ok' : 'p-mute'}">{session.me.oidc_linked ? 'Linked' : 'Not linked'}</span>
						</div>
						<div class="item" style="justify-content: flex-end; padding-top: 0; border-top: 0">
							{#if session.me.oidc_linked}
								<button class="btn danger" onclick={unlink} disabled={!session.me.has_password} title={session.me.has_password ? '' : 'Set a password first'}>Unlink {session.config.oidc.label}</button>
							{:else}
								<a class="btn primary" href="/api/auth/oidc/start?link=1" data-sveltekit-reload>Link {session.config.oidc.label}</a>
							{/if}
						</div>
					{/if}
					<div class="item">
						<Icon name="lock" size={28} stroke={1.8} />
						<div style="flex: 1"><p style="font-weight: 700">Password</p><p class="muted" style="font-size: 12.5px">{session.me.has_password ? (session.me.password_changed_at ? `Changed ${longDate(session.me.password_changed_at)}` : 'Set') : 'Not set — you sign in with Pocket ID'}</p></div>
						<button class="btn" onclick={() => (pwOpen = true)}>{session.me.has_password ? 'Change' : 'Set'}</button>
					</div>
				</div>
			</section>
		{/if}

		{#if tab === 'admin' && isAdmin}
			<section class="sec">
				<div class="srow" style="align-items: center"><span class="lbl">Users</span><button class="btn" style="min-height: 40px" onclick={makeInvite}><Icon name="plus" size={16} />Invite</button></div>
				{#if invite}
					<div class="once">
						<p style="font-weight: 800">Invite link · valid 7 days · one use</p>
						<div class="row" style="align-items: center">
							<code class="mono tok">{invite.url}</code>
							<button class="btn primary" onclick={async () => (await navigator.clipboard.writeText(invite!.url).catch(() => {}), flash('Invite link copied'))}>Copy</button>
						</div>
						<label class="row" style="align-items: center; font-size: 13px; font-weight: 600">Role for the next link
							<select class="field" style="width: 130px" bind:value={inviteRole}><option value="member">Member</option><option value="viewer">Viewer</option><option value="admin">Admin</option></select>
						</label>
					</div>
				{/if}
				<div class="card">
					{#each users as u (u.id)}
						<div class="item">
							<Avatar user={u} />
							<div style="flex: 1; min-width: 0"><p style="font-weight: 700">{u.username} <span class="muted" style="font-weight: 500">{u.you ? '(you)' : ''}</span></p><p class="muted" style="font-size: 12.5px">{u.sightings} sightings · active {ago(u.last_active_at)}</p></div>
							<label><span class="sr-only">Role for {u.username}</span>
								<select class="field" style="width: 118px" value={u.role} onchange={(e) => setRole(u, e.currentTarget.value)}>
									<option value="admin">Admin</option><option value="member">Member</option><option value="viewer">Viewer</option>
								</select>
							</label>
						</div>
					{/each}
				</div>
			</section>

			<section class="sec">
				<span class="lbl">Reprocess all photos</span>
				<div class="card pad">
					<p style="font-size: 14px">Runs OCR and the AI reader again on all {settings?.photos ?? 0} photos with the current settings. Confirmed plates are kept; changed readings go to Review.</p>
					{#if rp.state !== 'idle'}
						<div class="srow" style="font-size: 13px; font-weight: 700"><span>{rp.done} of {rp.total} photos</span><span class="muted">{rp.state === 'paused' ? 'Paused' : rp.state === 'done' ? 'Finished' : 'Running…'}</span></div>
						<div class="bar" role="progressbar" aria-valuenow={rpPct} aria-valuemin="0" aria-valuemax="100" aria-label="Reprocess progress" style="height: 8px"><span style="width: {rpPct}%"></span></div>
						<p class="muted" style="font-size: 12.5px">{rp.changed} reading{rp.changed === 1 ? '' : 's'} changed so far · they appear in Review</p>
					{/if}
					<button class="btn" class:primary={rp.state !== 'running'} onclick={rpAction}>{rp.state === 'running' ? 'Pause' : rp.state === 'paused' ? 'Resume' : 'Reprocess all photos'}</button>
				</div>
			</section>

			{#if settings}
				<ServerSettings {settings} onsave={(patch, msg) => saveSettings(patch, msg)} />

				<section class="sec">
					<span class="lbl">OCR confidence threshold</span>
					<div class="card pad">
						<div class="srow"><label for="thr" style="font-weight: 700">Send to Verify below</label><span class="mono" style="font-size: 20px; font-weight: 800">{settings.ocr_threshold}%</span></div>
						<input id="thr" type="range" min="50" max="99" value={settings.ocr_threshold} disabled={!!settings.locked.ocr_threshold} oninput={(e) => onThr(+e.currentTarget.value)} style="width: 100%; accent-color: var(--accent); min-height: 36px" />
						<div class="muted srow" style="font-size: 12px"><span>50% · fewer reviews</span><span>99% · review almost all</span></div>
						<LockNote env={settings.locked.ocr_threshold} />
						<p style="font-size: 13.5px">
							{#if settings.review_share != null}About <b>{settings.review_share}%</b> of past readings would need a human check at this level.{:else}Upload a few photos to see how many would need a human check.{/if}
						</p>
					</div>
				</section>

				<section class="sec">
					<span class="lbl">AI reader (VLM)</span>
					<div class="seg full" role="radiogroup" aria-label="VLM mode">
						{#each ['auto', 'always', 'off'] as m}<button role="radio" aria-checked={settings.vlm_mode === m} class:on={settings.vlm_mode === m} disabled={!!settings.locked.vlm_mode} onclick={() => setMode(m)}>{m[0].toUpperCase() + m.slice(1)}</button>{/each}
					</div>
					<LockNote env={settings.locked.vlm_mode} />
					<p class="muted" style="font-size: 13.5px">{MODES[settings.vlm_mode]}</p>
					{#if settings.vlm_mode !== 'off'}
						<p class="vstat" class:bad={!settings.vlm?.ready}>
							<Icon name={settings.vlm?.ready ? 'check' : 'warn'} size={16} stroke={2.2} />
							{settings.vlm?.ready ? `${settings.vlm.model} is loaded` : settings.vlm?.reachable ? `${settings.vlm?.model} is still downloading…` : 'Ollama is not reachable — OCR runs alone until it is'}
						</p>
					{/if}
				</section>

				<section class="sec">
					<span class="lbl">iPhone Shortcut</span>
					<div class="card pad">
						<label for="sc" style="font-weight: 700">iCloud link</label>
						<input id="sc" class="field mono" style="font-size: 13px" placeholder="https://www.icloud.com/shortcuts/…" bind:value={shortcutDraft} disabled={!!settings.locked.shortcut_url} onkeydown={(e) => e.key === 'Enter' && saveShortcut(shortcutDraft)} autocomplete="off" spellcheck="false" />
						<p class="muted" style="font-size: 13px">
							{settings.shortcut_url ? 'People on an iPhone, iPad or Mac see “Set up iPhone Shortcut” in their settings.' : 'Until a link is set, nobody sees the Shortcut setup button.'}
							Make the link once (README → <b>iOS Shortcut</b>).
						</p>
						<LockNote env={settings.locked.shortcut_url} />
						{#if !settings.locked.shortcut_url}
							<div class="row">
								{#if settings.shortcut_url}<button class="btn" onclick={() => saveShortcut('')}>Remove</button>{/if}
								<button class="btn primary" disabled={shortcutDraft.trim() === (settings.shortcut_url ?? '')} onclick={() => saveShortcut(shortcutDraft)}>Save link</button>
							</div>
						{/if}
					</div>
				</section>
			{/if}
		{/if}
	</div>
</div>

<Sheet bind:open={pwOpen} title={session.me?.has_password ? 'Change password' : 'Set a password'}>
	{#if session.me?.has_password}
		<label class="fl">Current password<input class="field" type="password" autocomplete="current-password" bind:value={pw.current} /></label>
	{/if}
	<label class="fl">New password<input class="field" type="password" autocomplete="new-password" minlength="8" bind:value={pw.next} /></label>
	<p class="muted" style="font-size: 13px">At least 8 characters. Other devices are signed out.</p>
	<button class="btn primary block" disabled={pw.next.length < 8} onclick={changePassword}>Save password</button>
</Sheet>

<style>
	.tabsw {
		max-width: 420px;
	}
	.body {
		gap: 22px;
		max-width: 760px;
	}
	.me {
		padding: 14px;
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.sec {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.srow {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
	}
	.row {
		display: flex;
		gap: 8px;
	}
	.item {
		display: flex;
		gap: 12px;
		align-items: center;
		padding: 12px 14px;
		border-top: 1px solid var(--line);
	}
	.item:first-child {
		border-top: 0;
	}
	.item.wrap {
		flex-wrap: wrap;
	}
	.confirm {
		width: 100%;
		display: flex;
		gap: 8px;
		align-items: center;
		justify-content: flex-end;
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
	.tok {
		flex: 1;
		min-width: 0;
		overflow-wrap: anywhere;
		background: var(--surface);
		color: var(--ink);
		border-radius: 8px;
		padding: 8px 10px;
		font-size: 13px;
		font-weight: 700;
	}
	.pad {
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.vstat {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 13px;
		font-weight: 700;
		color: var(--ok);
	}
	.vstat.bad {
		color: var(--warn);
	}
	.fl {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-weight: 600;
		font-size: 14px;
	}
</style>
