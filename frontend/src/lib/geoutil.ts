// Map math that doesn't need MapLibre (so pages can use it without loading the map bundle).

/** A GeoJSON polygon approximating a circle, for the radius tool. */
export function circle(lat: number, lon: number, miles: number, steps = 72) {
	const coords: [number, number][] = [];
	const dLat = miles / 69.0;
	const dLon = miles / (69.0 * Math.cos((lat * Math.PI) / 180));
	for (let i = 0; i <= steps; i++) {
		const a = (i / steps) * 2 * Math.PI;
		coords.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
	}
	return {
		type: 'Feature' as const,
		properties: {},
		geometry: { type: 'Polygon' as const, coordinates: [coords] }
	};
}

export function milesBetween(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
	const r = Math.PI / 180;
	const dLat = (b.lat - a.lat) * r;
	const dLon = (b.lon - a.lon) * r;
	const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
	return 2 * 3958.8 * Math.asin(Math.sqrt(h));
}
