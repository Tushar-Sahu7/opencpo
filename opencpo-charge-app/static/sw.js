const CACHE = 'opencpo-charge-v2';
const PRECACHE = ['/', '/skin/style.css', '/static/home.js', '/static/favicon.svg', '/static/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API calls: network only (no caching stale data)
  if (url.pathname.startsWith('/api/')) return;

  // Static: cache first
  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/skin/')) {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(res => {
      const clone = res.clone();
      caches.open(CACHE).then(c => c.put(e.request, clone));
      return res;
    })));
    return;
  }

  // HTML: network first, cache fallback
  e.respondWith(fetch(e.request).then(res => {
    const clone = res.clone();
    caches.open(CACHE).then(c => c.put(e.request, clone));
    return res;
  }).catch(() => caches.match(e.request)));
});

// ── Push notifications ────────────────────────────────────────────────────

self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : {};
  e.waitUntil(self.registration.showNotification(
    data.title || '⚡ Charging update',
    {
      body: data.body || 'Laden voltooid',
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      vibrate: [200, 100, 200],
      data: data,
    }
  ));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = e.notification.data && e.notification.data.url ? e.notification.data.url : '/';
  e.waitUntil(clients.openWindow(url));
});
