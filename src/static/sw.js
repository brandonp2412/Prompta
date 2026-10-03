const BUILD_ID = "__PROMPTA_UI_HEAD__";
const CACHE_NAME = "prompta-jobs-shell-" + (BUILD_ID || "dev");
const assetUrl = (path) => new URL(path, self.location.href).toString();
const SHELL = [
  "./",
  "./app.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icon.svg",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png",
  "./apple-touch-icon.png",
].map(assetUrl);

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const scopeUrl = new URL(self.registration.scope);
  const apiPrefix = scopeUrl.pathname + "api/";

  if (
    event.request.method !== "GET"
    || url.origin !== scopeUrl.origin
    || url.pathname.startsWith(apiPrefix)
  ) {
    return;
  }

  event.respondWith((async () => {
    try {
      const response = await fetch(event.request);
      if (response.ok) {
        const cache = await caches.open(CACHE_NAME);
        await cache.put(event.request, response.clone());
      }
      return response;
    } catch {
      const cached = await caches.match(event.request);
      if (cached) return cached;
      if (event.request.mode === "navigate") {
        const shell = await caches.match(assetUrl("./"));
        if (shell) return shell;
      }
      return Response.error();
    }
  })());
});
