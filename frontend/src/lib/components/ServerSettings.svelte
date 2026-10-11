<script lang="ts" module>
	export type AdminSettings = {
		ocr_threshold: number;
		vlm_mode: string;
		local_login_enabled: boolean;
		oidc_issuer: string | null;
		oidc_client_id: string | null;
		oidc_client_secret_set: boolean;
		oidc_admin_group: string | null;
		oidc_auto_create: boolean;
		oidc_link_by_email: boolean;
		oidc_button_label: string | null;
		oidc_enabled: boolean;
		map_style_light: string;
		map_style_dark: string;
		max_upload_mb: number;
		shortcut_url: string | null;
		locked: Record<string, string>;
		review_share: number | null;
		vlm: any;
		photos: number;
	};
</script>

<script lang="ts">
	import { api, errorText } from '../api';
	import { session } from '../state/session.svelte';
	import LockNote from './LockNote.svelte';
	import Icon from './Icon.svelte';

	/** Sign-in (password + Pocket ID), uploads and map settings in More → Admin. */
	let { settings, onsave }: { settings: AdminSettings; onsave: (patch: Record<string, unknown>, msg: string) => Promise<boolean> } = $props();

	const TEXT = ['oidc_issuer', 'oidc_client_id', 'oidc_admin_group', 'oidc_button_label'] as const;
	const lock = $derived(settings.locked);

	function draftFrom(s: AdminSettings) {
		return {
			oidc_issuer: s.oidc_issuer ?? '',
			oidc_client_id: s.oidc_client_id ?? '',
			oidc_client_secret: '',
			oidc_admin_group: s.oidc_admin_group ?? '',
			oidc_button_label: s.oidc_button_label ?? '',
			oidc_auto_create: s.oidc_auto_create,
			oidc_link_by_email: s.oidc_link_by_email,
			max_upload_mb: s.max_upload_mb,
			map_style_light: s.map_style_light,
			map_style_dark: s.map_style_dark
		};
	}
	// svelte-ignore state_referenced_locally
	let d = $state(draftFrom(settings));
	let clearSecret = $state(false);
	let test = $state<{ ok: boolean; error?: string; callback?: string } | null>(null);
	let testing = $state(false);

	/** Only the unlocked fields that differ from what's saved. */
	function changed(keys: string[]) {
		const out: Record<string, unknown> = {};
		const cur = draftFrom(settings) as Record<string, unknown>;
		for (const k of keys) {
			if (lock[k]) continue;
			const v = (d as Record<string, unknown>)[k];
			if (k === 'oidc_client_secret') {
				if (clearSecret) out[k] = '';
				else if (v) out[k] = v;
			} else if (v !== cur[k]) out[k] = typeof v === 'string' ? v.trim() : v;
		}
		return out;
	}

	const OIDC_KEYS = [...TEXT, 'oidc_client_secret', 'oidc_auto_create', 'oidc_link_by_email'];
	const OTHER_KEYS = ['max_upload_mb', 'map_style_light', 'map_style_dark'];
	const oidcDirty = $derived(Object.keys(changed(OIDC_KEYS)).length > 0);
	const otherDirty = $derived(Object.keys(changed(OTHER_KEYS)).length > 0);
	const allOidcLocked = $derived(OIDC_KEYS.every((k) => lock[k]));
	const canDisablePasswords = $derived(settings.oidc_enabled && !!session.me?.oidc_linked);

	async function save(keys: string[], msg: string) {
		if (await onsave(changed(keys), msg)) {
			d = draftFrom(settings);
			clearSecret = false;
		}
	}

	async function togglePasswords(el: HTMLInputElement) {
		const on = el.checked;
		if (!(await onsave({ local_login_enabled: on }, on ? 'Password sign-in on' : 'Password sign-in off'))) el.checked = !on;
	}

	async function runTest() {
		testing = true;
		test = null;
		try {
			test = await api.post('/api/admin/oidc/test', { issuer: d.oidc_issuer });
		} catch (e) {
			test = { ok: false, error: errorText(e) };
		} finally {
			testing = false;
		}
	}
</script>

<section class="sec">
	<span class="lbl">Sign-in</span>
	<div class="card pad">
		<label class="sw">
			<input type="checkbox" checked={settings.local_login_enabled} disabled={!!lock.local_login_enabled || (settings.local_login_enabled && !canDisablePasswords)} onchange={(e) => togglePasswords(e.currentTarget)} />
			<span><b>Password sign-in</b><span class="muted hint">Usernames and passwords. Turn off to use only Pocket ID.</span></span>
		</label>
		<LockNote env={lock.local_login_enabled} />
		{#if settings.local_login_enabled && !canDisablePasswords && !lock.local_login_enabled}
			<p class="muted hint">To turn this off, set up Pocket ID below and link your own account to it (Settings → Linked accounts), so you can't get locked out.</p>
		{/if}
	</div>

	<div class="card pad">
		<div class="srow" style="align-items: center"><b>Pocket ID (OIDC)</b><span class="pill {settings.oidc_enabled ? 'p-ok' : 'p-mute'}">{settings.oidc_enabled ? 'On' : 'Off'}</span></div>
		<p class="muted hint">In Pocket ID, create an OIDC client with the callback URL <code class="mono">{location.origin}/api/auth/oidc/callback</code>.</p>
		<label class="fl">Issuer URL<input class="field mono" placeholder="https://id.example.com" bind:value={d.oidc_issuer} disabled={!!lock.oidc_issuer} autocomplete="off" spellcheck="false" /></label>
		<LockNote env={lock.oidc_issuer} />
		<div class="row">
			<button class="btn" onclick={runTest} disabled={!d.oidc_issuer.trim() || testing}>{testing ? 'Testing…' : 'Test'}</button>
			{#if test}
				<p class="tres" class:bad={!test.ok}><Icon name={test.ok ? 'check' : 'warn'} size={16} stroke={2.2} style="flex: none" />{test.ok ? 'Pocket ID answered. Issuer looks right.' : test.error}</p>
			{/if}
		</div>
		<label class="fl">Client ID<input class="field mono" bind:value={d.oidc_client_id} disabled={!!lock.oidc_client_id} autocomplete="off" spellcheck="false" /></label>
		<LockNote env={lock.oidc_client_id} />
		<label class="fl">Client secret
			<input class="field mono" type="password" placeholder={settings.oidc_client_secret_set && !clearSecret ? '•••••••• saved · type to replace' : 'Leave empty for a public client'} bind:value={d.oidc_client_secret} disabled={!!lock.oidc_client_secret || clearSecret} autocomplete="new-password" />
		</label>
		{#if settings.oidc_client_secret_set && !lock.oidc_client_secret}
			<label class="ck"><input type="checkbox" bind:checked={clearSecret} />Remove the saved secret</label>
		{/if}
		<LockNote env={lock.oidc_client_secret} />
		<label class="fl">Admin group <span class="muted opt">optional · its members become admins</span><input class="field mono" placeholder="platedex_admins" bind:value={d.oidc_admin_group} disabled={!!lock.oidc_admin_group} autocomplete="off" spellcheck="false" /></label>
		<LockNote env={lock.oidc_admin_group} />
		<label class="fl">Button label<input class="field" placeholder="Pocket ID" bind:value={d.oidc_button_label} disabled={!!lock.oidc_button_label} maxlength="40" /></label>
		<LockNote env={lock.oidc_button_label} />
		<label class="ck"><input type="checkbox" bind:checked={d.oidc_auto_create} disabled={!!lock.oidc_auto_create} />Create accounts for anyone Pocket ID lets in</label>
		<LockNote env={lock.oidc_auto_create} />
		<label class="ck"><input type="checkbox" bind:checked={d.oidc_link_by_email} disabled={!!lock.oidc_link_by_email} />Link to an existing account with the same verified email</label>
		<LockNote env={lock.oidc_link_by_email} />
		{#if !allOidcLocked}
			<button class="btn primary" disabled={!oidcDirty} onclick={() => save(OIDC_KEYS, 'Pocket ID settings saved')}>Save Pocket ID settings</button>
		{/if}
	</div>
</section>

<section class="sec">
	<span class="lbl">Uploads and map</span>
	<div class="card pad">
		<label class="fl">Largest photo (MB)<input class="field" type="number" min="1" max="500" style="width: 120px" bind:value={d.max_upload_mb} disabled={!!lock.max_upload_mb} /></label>
		<LockNote env={lock.max_upload_mb} />
		<label class="fl">Map style, light theme<input class="field mono" style="font-size: 13px" bind:value={d.map_style_light} disabled={!!lock.map_style_light} spellcheck="false" /></label>
		<LockNote env={lock.map_style_light} />
		<label class="fl">Map style, dark theme<input class="field mono" style="font-size: 13px" bind:value={d.map_style_dark} disabled={!!lock.map_style_dark} spellcheck="false" /></label>
		<LockNote env={lock.map_style_dark} />
		<p class="muted hint">MapLibre style URLs. Point these at your own tile server for a fully offline setup.</p>
		{#if !OTHER_KEYS.every((k) => lock[k])}
			<button class="btn primary" disabled={!otherDirty || !(d.max_upload_mb >= 1)} onclick={() => save(OTHER_KEYS, 'Saved')}>Save</button>
		{/if}
	</div>
</section>

<style>
	.sec {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.pad {
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.fl {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-weight: 600;
		font-size: 14px;
	}
	.opt {
		font-weight: 500;
		font-size: 12.5px;
	}
	.hint {
		font-size: 13px;
		display: block;
	}
	.sw,
	.ck {
		display: flex;
		gap: 10px;
		align-items: flex-start;
		font-size: 14px;
		cursor: pointer;
	}
	.sw input,
	.ck input {
		width: 20px;
		height: 20px;
		margin-top: 1px;
		accent-color: var(--accent);
		flex: none;
	}
	.sw > span {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.row {
		display: flex;
		gap: 10px;
		align-items: center;
		flex-wrap: wrap;
	}
	.tres {
		display: flex;
		gap: 6px;
		align-items: center;
		font-size: 13px;
		color: var(--ok);
		flex: 1;
		min-width: 0;
	}
	.tres.bad {
		color: var(--bad);
	}
	code {
		background: var(--surface2);
		padding: 0 4px;
		border-radius: 4px;
		font-size: 12px;
		overflow-wrap: anywhere;
	}
	.srow {
		display: flex;
		justify-content: space-between;
		gap: 8px;
	}
</style>
