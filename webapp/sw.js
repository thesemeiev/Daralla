/* PWA Service Worker: cache static assets, offline fallback */
var CACHE_VERSION = 'daralla-static-v1';
var STATIC_URLS = [
  '/',
  '/index.html',
  '/style.css',
  '/app.js',
  '/manifest.json',
  '/offline.html',
  '/icons/icon-128.png',
  '/icons/icon-192.png',
  '/icons/icon-256.png',
  '/icons/icon-512.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_VERSION).then(function (cache) {
      return cache.addAll(STATIC_URLS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        if (key !== CACHE_VERSION && key.startsWith('daralla-static-')) {
          return caches.delete(key);
        }
      }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (event) {
  var url = new URL(event.request.url);
  if (url.origin !== self.location.origin) {
    return;
  }
  var path = url.pathname;
  var isNav = event.request.mode === 'navigate';
  var isStatic = /^\/(style\.css|app\.js|manifest\.json|icons\/icon-\d+\.png)$/.test(path) || path === '/' || path === '/index.html';

  if (isStatic && !isNav) {
    event.respondWith(
      caches.match(event.request).then(function (cached) {
        return cached || fetch(event.request).then(function (response) {
          var clone = response.clone();
          caches.open(CACHE_VERSION).then(function (cache) {
            cache.put(event.request, clone);
          });
          return response;
        });
      })
    );
    return;
  }

  if (isNav) {
    event.respondWith(
      fetch(event.request).then(function (response) {
        var clone = response.clone();
        caches.open(CACHE_VERSION).then(function (cache) {
          cache.put(event.request, clone);
        });
        return response;
      }).catch(function () {
        return caches.match('/offline.html').then(function (offline) {
          return offline || caches.match(event.request).then(function (cached) {
            return cached || new Response(
              '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width"><title>Нет соединения</title></head><body style="font-family:sans-serif;background:#1a1a2e;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:24px;text-align:center"><h1>Нет соединения</h1><p>Проверьте сеть и обновите страницу.</p><button onclick="location.reload()" style="padding:12px 24px;margin-top:16px;background:#4a9eff;color:#fff;border:none;border-radius:8px;cursor:pointer">Обновить</button></body></html>',
              { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
            );
          });
        });
      })
    );
    return;
  }

  event.respondWith(fetch(event.request));
});
