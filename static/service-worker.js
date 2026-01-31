const CACHE_NAME = 'cache-v1';
const ASSETS = [
    '/',
    '/offline.html'
];

self.addEventListener('install', (e) => {
    self.skipWaiting();
    e.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        })
    );
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                    return null;
                })
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (e) => {
    if (e.request.method !== 'GET') return;
    e.respondWith(
        caches.match(e.request).then((response) => {
            if (response) return response;
            return fetch(e.request).then((networkResponse) => {
                // Cache same-origin GET responses for future use
                if (e.request.url.startsWith(self.location.origin)) {
                    const clone = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(e.request, clone));
                }
                return networkResponse;
            }).catch(() => {
                // Offline fallback for navigation/HTML requests
                if (e.request.mode === 'navigate' || (e.request.headers.get('accept') || '').includes('text/html')) {
                    return caches.match('/offline.html');
                }
            });
        })
    );
});