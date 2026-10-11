const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function parts(iso: string, tz?: string | null) {
	const d = new Date(iso);
	try {
		const f = new Intl.DateTimeFormat('en-US', {
			timeZone: tz || undefined,
			year: 'numeric',
			month: 'numeric',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
			hour12: true
		}).formatToParts(d);
		const get = (t: string) => f.find((p) => p.type === t)?.value || '';
		return {
			y: +get('year'),
			m: +get('month') - 1,
			d: +get('day'),
			time: `${get('hour')}:${get('minute')} ${get('dayPeriod').toUpperCase()}`
		};
	} catch {
		return { y: d.getFullYear(), m: d.getMonth(), d: d.getDate(), time: d.toLocaleTimeString() };
	}
}

/** "Mar 2" (same year) or "Mar 2, 2025". Times show in the sighting's own time zone. */
export function shortDate(iso: string | null | undefined, tz?: string | null): string {
	if (!iso) return '—';
	const p = parts(iso, tz);
	const thisYear = new Date().getFullYear();
	return `${MON[p.m]} ${p.d}${p.y !== thisYear ? `, ${p.y}` : ''}`;
}

export function longDate(iso: string | null | undefined, tz?: string | null): string {
	if (!iso) return '—';
	const p = parts(iso, tz);
	return `${MON[p.m]} ${p.d}, ${p.y}`;
}

export function timeOf(iso: string | null | undefined, tz?: string | null): string {
	if (!iso) return '';
	return parts(iso, tz).time;
}

export function dateTime(iso: string | null | undefined, tz?: string | null): string {
	if (!iso) return '—';
	return `${shortDate(iso, tz)}, ${timeOf(iso, tz)}`;
}

export function ago(iso: string | null | undefined): string {
	if (!iso) return 'never';
	const s = (Date.now() - new Date(iso).getTime()) / 1000;
	if (s < 60) return 'just now';
	if (s < 3600) return `${Math.floor(s / 60)} min ago`;
	if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
	if (s < 172800) return 'yesterday';
	if (s < 86400 * 30) return `${Math.floor(s / 86400)}d ago`;
	return shortDate(iso);
}

export function plural(n: number, word: string, many = word + 's'): string {
	return `${n} ${n === 1 ? word : many}`;
}

export function coord(lat: number, lon: number): string {
	return `${lat.toFixed(4)}, ${lon.toFixed(4)}`.replace(/-/g, '−');
}

export function blurInfo(b: number | null | undefined) {
	const v = b ?? 0;
	return {
		word: v >= 0.7 ? 'Blurry' : v >= 0.4 ? 'Soft' : 'Sharp',
		color: v >= 0.7 ? 'var(--bad)' : v >= 0.4 ? 'var(--warn)' : 'var(--ok)',
		pct: Math.round(v * 100),
		value: v.toFixed(2)
	};
}

export const STATE_NAMES: Record<string, string> = {
	AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado',
	CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia', FL: 'Florida', GA: 'Georgia',
	HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky',
	LA: 'Louisiana', ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota',
	MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire',
	NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota',
	OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island',
	SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont',
	VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming',
	PR: 'Puerto Rico', GU: 'Guam', VI: 'U.S. Virgin Islands'
};

/** Slogans for the big plate rendering on the Plate page. */
export const STATE_SLOGANS: Record<string, string> = {
	TX: 'THE LONE STAR STATE', CA: '', CO: 'COLORFUL', NM: 'LAND OF ENCHANTMENT', AZ: 'GRAND CANYON STATE',
	NY: 'EMPIRE STATE', WA: 'EVERGREEN STATE', FL: 'SUNSHINE STATE', NV: 'THE SILVER STATE', UT: 'LIFE ELEVATED',
	OR: 'PACIFIC WONDERLAND', IL: 'LAND OF LINCOLN', NH: 'LIVE FREE OR DIE', NJ: 'GARDEN STATE',
	PA: 'VISITPA.COM', MI: 'PURE MICHIGAN', OK: 'NATIVE AMERICA', LA: 'SPORTSMANS PARADISE', ID: 'FAMOUS POTATOES'
};
