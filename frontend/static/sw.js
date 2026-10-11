// Platedex service worker: Android "share to Platedex" + offline-friendly app assets.
// API requests are never cached.
const ASSETS = 'pdx-assets-v1';
const SHARED = 'pdx-shared';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (event) => {
	const url = new URL(event.request.url);
	if (url.origin !== self.location.origin) return;

	// Web Share Target: photos shared from the Android share sheet arrive here as a POST.
	if (url.pathname === '/share-target' && event.request.method === 'POST') {
		event.respondWith(
			(async () => {
				const form = await event.request.formData();
				const files = form.getAll('photos').filter((f) => typeof f !== 'string');
				const cache = await caches.open(SHARED);
				let i = 0;
				for (const f of files) {
					await cache.put(
						`/shared/${Date.now()}-${i++}`,
						new Response(f, { headers: { 'content-type': f.type || 'image/jpeg', 'x-name': encodeURIComponent(f.name || 'shared.jpg'), 'x-modified': String(f.lastModified || Date.now()) } })
					);
				}
				return Response.redirect(`/upload?shared=${files.length}`, 303);
			})()
		);
		return;
	}

	if (event.request.method !== 'GET' || url.pathname.startsWith('/api/')) return;

	// Hashed build assets never change: cache first.
	if (url.pathname.startsWith('/_app/immutable/')) {
		event.respondWith(
			caches.open(ASSETS).then(async (cache) => {
				const hit = await cache.match(event.request);
				if (hit) return hit;
				const res = await fetch(event.request);
				if (res.ok) cache.put(event.request, res.clone());
				return res;
			})
		);
		return;
	}

	// Pages: network first, fall back to the cached shell when offline.
	if (event.request.mode === 'navigate') {
		event.respondWith(
			fetch(event.request)
				.then((res) => {
					const copy = res.clone();
					caches.open(ASSETS).then((c) => c.put('/__shell', copy));
					return res;
				})
				.catch(async () => (await caches.match('/__shell')) || Response.error())
		);
	}
});
