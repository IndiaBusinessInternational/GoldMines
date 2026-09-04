/* ═══════════════════════════════════════════════════════════════════════════
   IBI Gold Mines — service worker (v1.0.1)

   • Navigations (HTML shell): NETWORK FIRST — a price app must never boot from
     a stale shell; the cache is only the offline lifeboat.
   • Same-origin static assets (icons, images, manifest): STALE-WHILE-REVALIDATE.
   • data/history.json: NETWORK FIRST with cache fallback, so offline still
     shows the last known history (the page also keeps a localStorage copy).
   • Cross-origin (gold-api, frankfurter, geocoder, fonts): NOT TOUCHED.

   ⚠ PRECACHE USES cache:'reload' — a plain cache.addAll() goes through the
   browser HTTP cache and can ship the PREVIOUS build under a new badge.
   ═══════════════════════════════════════════════════════════════════════════ */
const VERSION     = 'v1.0.1';
const SHELL_CACHE = 'ibigold-shell-' + VERSION;
const ASSET_CACHE = 'ibigold-assets-' + VERSION;
const OFFLINE_URL = './index.html';
const PRECACHE = ['./', './index.html', './manifest.json', './icon-192.png', './icon-512.png', './data/history.json'];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    await Promise.all(PRECACHE.map(async (url) => {
      try {
        const resp = await fetch(new Request(url, { cache: 'reload' }));
        if (resp && resp.ok) await cache.put(url, resp);
      } catch (e) { /* optional asset — never fail the install */ }
    }));
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k.startsWith('ibigold-') && k !== SHELL_CACHE && k !== ASSET_CACHE).map(k => caches.delete(k)));
    if (self.registration.navigationPreload) { try { await self.registration.navigationPreload.enable(); } catch (e) {} }
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const preload = await event.preloadResponse;
        if (preload) { (await caches.open(SHELL_CACHE)).put(OFFLINE_URL, preload.clone()); return preload; }
        const fresh = await fetch(req);
        (await caches.open(SHELL_CACHE)).put(OFFLINE_URL, fresh.clone());
        return fresh;
      } catch (e) {
        return (await caches.match(OFFLINE_URL)) || Response.error();
      }
    })());
    return;
  }

  if (url.pathname.endsWith('/data/history.json')) {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        if (fresh && fresh.ok) (await caches.open(SHELL_CACHE)).put(req, fresh.clone());
        return fresh;
      } catch (e) {
        return (await caches.match(req)) || Response.error();
      }
    })());
    return;
  }

  event.respondWith((async () => {
    const cache = await caches.open(ASSET_CACHE);
    const cached = await cache.match(req);
    const network = fetch(req).then(resp => { if (resp && resp.ok) cache.put(req, resp.clone()); return resp; }).catch(() => null);
    return cached || (await network) || Response.error();
  })());
});
