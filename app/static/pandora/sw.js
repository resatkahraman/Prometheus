const CACHE_NAME = "pandora-shell-v4";
const SHELL_RESOURCES = [
  "/pandora",
  "/static/pandora/app.css",
  "/static/pandora/app.js",
  "/static/pandora/manifest.webmanifest",
  "/static/pandora/icon.svg",
];
const STATIC_RESOURCES = new Set(SHELL_RESOURCES.slice(1));

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_RESOURCES)).catch(() => undefined)
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) => Promise.all(
      names
        .filter((name) => name.startsWith("pandora-shell-") && name !== CACHE_NAME)
        .map((name) => caches.delete(name))
    )).catch(() => undefined)
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || request.headers.has("Authorization")) return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/v1/")) return;

  if (url.pathname === "/pandora") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  if (STATIC_RESOURCES.has(url.pathname)) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request)).catch(() => fetch(request))
    );
  }
});
