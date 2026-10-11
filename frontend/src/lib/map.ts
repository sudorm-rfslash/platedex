import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// MapLibre finds its worker next to its own module by default; after bundling it lives elsewhere.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import { session } from './state/session.svelte';
import { isDark } from './state/theme.svelte';

maplibregl.setWorkerUrl(workerUrl);

export { maplibregl };

const DEFAULT_LIGHT = 'https://tiles.openfreemap.org/styles/positron';
const DEFAULT_DARK = 'https://tiles.openfreemap.org/styles/dark';

export function styleUrl(): string {
	const cfg = session.config;
	return isDark() ? cfg?.map?.dark || DEFAULT_DARK : cfg?.map?.light || DEFAULT_LIGHT;
}

export const US_CENTER: [number, number] = [-98.5, 38.5];

export function createMap(
	container: HTMLElement,
	opts: { center?: [number, number]; zoom?: number; interactive?: boolean } = {}
) {
	const map = new maplibregl.Map({
		container,
		style: styleUrl(),
		center: opts.center ?? US_CENTER,
		zoom: opts.zoom ?? 3.2,
		interactive: opts.interactive ?? true,
		attributionControl: { compact: true },
		cooperativeGestures: false
	});
	return map;
}

/** Fit the map to points ([lon, lat]) with sensible padding and a max zoom. */
export function fitPoints(map: maplibregl.Map, pts: [number, number][], maxZoom = 13, padding = 48) {
	if (!pts.length) return;
	if (pts.length === 1) {
		map.jumpTo({ center: pts[0], zoom: Math.min(maxZoom, 12) });
		return;
	}
	const b = new maplibregl.LngLatBounds(pts[0], pts[0]);
	pts.forEach((p) => b.extend(p));
	map.fitBounds(b, { padding, maxZoom, duration: 0 });
}

/** Read a CSS variable so map layers follow the light/dark tokens. */
export function cssVar(name: string, el: HTMLElement = document.documentElement) {
	return getComputedStyle(el).getPropertyValue(name).trim();
}
