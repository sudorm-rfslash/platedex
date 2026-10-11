/** Filters shared by the Plates list and the Map, so both always show the same slice. */
export type Area = { lat: number; lon: number; mi: number; label: string };
export type Range = 'all' | '30' | '90' | 'year' | 'custom';
export type Filters = {
	range: Range;
	from: string;
	to: string;
	states: string[];
	users: string[];
	tags: string[];
	minN: number;
	area: Area | null;
	missing: boolean;
};

const KEY = 'platedex.filters';
export const EMPTY: Filters = {
	range: 'all', from: '', to: '', states: [], users: [], tags: [], minN: 1, area: null, missing: false
};

function load(): Filters {
	try {
		const raw = sessionStorage.getItem(KEY);
		if (raw) return { ...EMPTY, ...JSON.parse(raw) };
	} catch {
		/* storage blocked */
	}
	return { ...EMPTY };
}

export const filters = $state<Filters>(load());

export function saveFilters() {
	try {
		sessionStorage.setItem(KEY, JSON.stringify(filters));
	} catch {
		/* storage blocked */
	}
}

export function resetFilters() {
	Object.assign(filters, { ...EMPTY, states: [], users: [], tags: [] });
	saveFilters();
}

export function toggleIn(key: 'states' | 'users' | 'tags', v: string) {
	const a = filters[key];
	filters[key] = a.includes(v) ? a.filter((x) => x !== v) : [...a, v];
	saveFilters();
}

export const RANGES: [Range, string][] = [
	['all', 'All time'],
	['30', 'Last 30 days'],
	['90', 'Last 90 days'],
	['year', 'This year']
];

function iso(d: Date) {
	return d.toISOString().slice(0, 10);
}

export function dateBounds(f: Filters): { from?: string; to?: string } {
	const now = new Date();
	if (f.range === '30') return { from: iso(new Date(now.getTime() - 30 * 864e5)) };
	if (f.range === '90') return { from: iso(new Date(now.getTime() - 90 * 864e5)) };
	if (f.range === 'year') return { from: `${now.getFullYear()}-01-01` };
	if (f.range === 'custom') return { from: f.from || undefined, to: f.to || undefined };
	return {};
}

/** Query params for /api/plates, /api/sightings and /api/map/points. */
export function filterParams(f: Filters) {
	return {
		...dateBounds(f),
		states: f.states,
		users: f.users,
		tags: f.tags,
		min_n: f.minN > 1 ? f.minN : undefined,
		near: f.area ? `${f.area.lat},${f.area.lon}` : undefined,
		radius: f.area?.mi,
		missing: f.missing || undefined
	};
}

export function chips(f: Filters) {
	const out: { label: string; clear: () => void }[] = [];
	const save = saveFilters;
	if (f.range !== 'all') {
		const label =
			f.range === 'custom' ? `${f.from || '…'} – ${f.to || '…'}` : RANGES.find((r) => r[0] === f.range)![1];
		out.push({ label, clear: () => ((filters.range = 'all'), save()) });
	}
	f.states.forEach((v) => out.push({ label: v, clear: () => toggleIn('states', v) }));
	f.users.forEach((v) => out.push({ label: v, clear: () => toggleIn('users', v) }));
	f.tags.forEach((v) => out.push({ label: '#' + v, clear: () => toggleIn('tags', v) }));
	if (f.minN > 1) out.push({ label: `Seen ≥ ${f.minN}`, clear: () => ((filters.minN = 1), save()) });
	if (f.area) out.push({ label: `${f.area.mi} mi of ${f.area.label}`, clear: () => ((filters.area = null), save()) });
	if (f.missing) out.push({ label: 'Missing location', clear: () => ((filters.missing = false), save()) });
	return out;
}
