import { api } from '../api';

type Counts = { verify: { mine: number; all: number }; identify: { mine: number; all: number }; badge: number };
export const counts = $state<Counts>({ verify: { mine: 0, all: 0 }, identify: { mine: 0, all: 0 }, badge: 0 });

let timer: ReturnType<typeof setInterval> | undefined;

export async function refreshCounts() {
	try {
		Object.assign(counts, await api.get<Counts>('/api/review/counts'));
	} catch {
		/* signed out or offline */
	}
}

export function startCountPolling() {
	refreshCounts();
	clearInterval(timer);
	timer = setInterval(refreshCounts, 20000);
	return () => clearInterval(timer);
}
