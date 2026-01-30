/* PWA Service Worker - minimal install, network-first fetch */
self.addEventListener('install', function (event) {
  self.skipWaiting();
});

self.addEventListener('fetch', function (event) {
  event.respondWith(fetch(event.request));
});
