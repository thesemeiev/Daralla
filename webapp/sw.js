/* PWA Service Worker - splash cache, network-first for / */
var CACHE_VERSION = 'v1';
var CACHE_NAME = 'daralla-splash-' + CACHE_VERSION;

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.add('/splash.html');
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        if (key !== CACHE_NAME) return caches.delete(key);
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.mode !== 'navigate') {
    event.respondWith(fetch(request));
    return;
  }
  var url = new URL(request.url);
  if (url.pathname !== '/' && url.pathname !== '/index.html') {
    event.respondWith(fetch(request));
    return;
  }
  event.respondWith(
    fetch(request).catch(function () {
      return caches.match('/splash.html');
    })
  );
});
