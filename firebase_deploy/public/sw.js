// Service Worker mínimo para PWA (solo cachea el shell)
const CACHE = 'deriv-spike-v1';
const ASSETS = ['/', '/index.html', '/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
});

self.addEventListener('fetch', e => {
  // Nunca cachear el WebSocket de Deriv
  if (e.request.url.includes('binaryws.com')) return;
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});
