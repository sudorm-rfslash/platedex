import { api } from '../api';

export type User = { id: number; username: string; name: string; color: string; role: 'admin' | 'member' | 'viewer' };
export type Me = User & {
	email: string | null;
	has_password: boolean;
	password_changed_at: string | null;
	oidc_linked: boolean;
	oidc_linked_at: string | null;
	sightings: number;
};
export type AuthConfig = {
	local_login: boolean;
	oidc: { enabled: boolean; label: string };
	needs_setup: boolean;
	map: { light: string; dark: string };
	shortcut_url: string | null;
	max_upload_mb: number;
};

export const session = $state({ me: null as Me | null, config: null as AuthConfig | null, loaded: false });

export async function loadSession(): Promise<Me | null> {
	try {
		session.me = await api.get<Me>('/api/auth/me');
	} catch {
		session.me = null;
	}
	session.loaded = true;
	return session.me;
}

export async function loadConfig(): Promise<AuthConfig> {
	session.config = await api.get<AuthConfig>('/api/auth/config');
	return session.config;
}

export function canEdit(): boolean {
	return session.me?.role === 'admin' || session.me?.role === 'member';
}
