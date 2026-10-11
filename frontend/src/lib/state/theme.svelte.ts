export type Theme = 'auto' | 'light' | 'dark';

function initial(): Theme {
	try {
		const t = localStorage.getItem('platedex.theme');
		if (t === 'light' || t === 'dark') return t;
	} catch {
		/* storage blocked */
	}
	return 'auto';
}

export const theme = $state({ value: initial() as Theme });

export function setTheme(t: Theme) {
	theme.value = t;
	document.documentElement.dataset.theme = t;
	try {
		localStorage.setItem('platedex.theme', t);
	} catch {
		/* storage blocked */
	}
}

/** True when the page is currently showing dark colors. */
export function isDark(): boolean {
	if (theme.value === 'dark') return true;
	if (theme.value === 'light') return false;
	return matchMedia('(prefers-color-scheme: dark)').matches;
}
