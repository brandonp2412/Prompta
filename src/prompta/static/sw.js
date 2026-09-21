const CACHE_NAME = "prompta-shell-v5";
const assetUrl = (path) => new URL(path, self.location.href).toString();
const SHELL = ["./", "./app.css", "./app.js", "./manifest.webmanifest", "./icon.svg"]
  .map(assetUrl);

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
    )),
  );
  self.clients.claim();
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "./", self.registration.scope).toString();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(async (clients) => {
      for (const client of clients) {
        if (client.url.startsWith(self.registration.scope)) {
          await client.focus();
          if ("navigate" in client) await client.navigate(target);
          return;
        }
      }
      await self.clients.openWindow(target);
    }),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const scopeUrl = new URL(self.registration.scope);
  const apiPrefix = `${scopeUrl.pathname}api/`;
  if (
    event.request.method !== "GET"
    || url.origin !== scopeUrl.origin
    || url.pathname.startsWith(apiPrefix)
  ) {
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(async () => (
        await caches.match(event.request)
        || await caches.match(assetUrl("./"))
        || Response.error()
      )),
    );
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cached) => {
      const refresh = fetch(event.request).then(async (response) => {
        if (response.ok) {
          const cache = await caches.open(CACHE_NAME);
          await cache.put(event.request, response.clone());
        }
        return response;
      });
      if (cached) {
        event.waitUntil(refresh.catch(() => undefined));
        return cached;
      }
      return refresh.catch(() => Response.error());
    }),
  );
});
