/* ============================================================
   SERVICE WORKER — Caché offline (app-shell) + PWA instalable
   Estrategia: cache-first para estáticos, network-first para /api/*
   ============================================================ */
const CACHE_NAME = "noirgold-cache-v1";
const APP_SHELL = [
  "/",
  "/manifest.json",
  "/static/css/style.css",
  "/static/js/audio.js",
  "/static/js/realtime.js",
  "/static/js/viewer3d.js",
  "/static/js/faceshape.js",
  "/static/js/pos.js",
  "/static/js/dashboard.js",
  "/static/js/app.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Nunca cachear WebSocket / socket.io ni el webhook
  if (url.pathname.startsWith("/socket.io") || url.pathname.startsWith("/webhook")) return;

  // API: network-first, cae a caché si no hay conexión (lectura offline degradada)
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Estáticos / shell: cache-first
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((res) => {
      const clone = res.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
      return res;
    }).catch(() => cached))
  );
});
