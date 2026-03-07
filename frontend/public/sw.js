const CACHE_NAME = "jokers-edge-v2";

// Install — skip waiting to activate immediately
self.addEventListener("install", (event) => {
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch strategy:
// - API calls: always network (no SW interception)
// - Navigation (HTML): network-first (prevents stale index.html after deploys)
// - Assets (JS/CSS/images): cache-first (hashed filenames handle versioning)
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls — always go to network
  if (url.pathname.startsWith("/api")) {
    return;
  }

  // Skip non-http(s) schemes (chrome-extension, etc.)
  if (!url.protocol.startsWith("http")) {
    return;
  }

  // Navigation requests (HTML pages) — network-first to always get latest index.html
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Static assets — cache-first (Vite hashed filenames ensure freshness)
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const fetchPromise = fetch(event.request)
        .then((response) => {
          if (response.ok && event.request.method === "GET") {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => cached);

      return cached || fetchPromise;
    })
  );
});
