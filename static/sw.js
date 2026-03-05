// sw.js — Service Worker Genesi PWA
// Strategia: Network First con fallback cache
// Non cacha le API calls — solo asset statici

const CACHE_NAME = 'genesi-v5';
const CACHE_TIMEOUT = 8000; // ms prima di usare cache (aumentato per immagini su mobile)

// Asset da precachare al primo install
const PRECACHE_ASSETS = [
    '/',
    '/static/style.css',
    '/static/app.v2.js',
    '/static/manifest.json',
    '/static/icon.png'
];

// Route API: mai cachate, sempre network
const API_ROUTES = [
    '/api/',
    '/auth/',
    '/coding/',
];

// Pagine informative: sempre network (evita brochure stale)
const NO_CACHE_ROUTES = [
    '/brochure',
    '/guida-icloud',
];

// ── Install: precache asset statici ─────────────────────────
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] Precaching assets');
            return cache.addAll(PRECACHE_ASSETS);
        })
    );
    self.skipWaiting();
});

// ── Activate: rimuovi cache vecchie ─────────────────────────
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => {
                        console.log('[SW] Rimozione cache obsoleta:', key);
                        return caches.delete(key);
                    })
            )
        )
    );
    self.clients.claim();
});

// ── Fetch: Network First per tutto tranne API ────────────────
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // API e auth: sempre network, mai cache
    const isAPI = API_ROUTES.some((route) => url.pathname.startsWith(route));
    const isNoCachePage = NO_CACHE_ROUTES.some((route) => url.pathname === route || url.pathname.startsWith(route + '/'));
    if (isAPI || isNoCachePage || event.request.method !== 'GET') return;

    // Asset statici: Network First con fallback cache
    event.respondWith(
        Promise.race([
            fetch(event.request).then((response) => {
                // Aggiorna cache con la risposta fresca
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                }
                return response;
            }),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('timeout')), CACHE_TIMEOUT)
            ),
        ]).catch(() => {
            // Fallback cache se network lento o offline
            return caches.match(event.request).then((cached) => {
                if (cached) {
                    console.log('[SW] Serving from cache:', url.pathname);
                    return cached;
                }
                // Fallback finale: pagina principale dalla cache
                return caches.match('/');
            });
        })
    );
});

// ── Push notifications ───────────────────────────────────────
self.addEventListener('push', (event) => {
    if (!event.data) return;

    let payload;
    try {
        payload = event.data.json();
    } catch {
        payload = { title: 'Genesi', body: event.data.text() };
    }

    const options = {
        body: payload.body || '',
        icon: payload.icon || '/static/icon.png',
        badge: payload.badge || '/static/icon.png',
        tag: payload.tag || 'genesi-notification',
        renotify: payload.renotify || false,
        data: payload.data || {},
        actions: [
            { action: 'open', title: 'Apri Genesi' },
            { action: 'dismiss', title: 'Chiudi' },
        ],
    };

    event.waitUntil(
        self.registration.showNotification(payload.title || 'Genesi', options)
    );
});

// Click sulla notifica: apre l'app
self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    if (event.action === 'dismiss') return;

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                // Se l'app è già aperta, porta in primo piano
                for (const client of clientList) {
                    if (client.url.includes(self.location.origin) && 'focus' in client) {
                        return client.focus();
                    }
                }
                // Altrimenti apri una nuova finestra
                return clients.openWindow('/');
            })
    );
});
