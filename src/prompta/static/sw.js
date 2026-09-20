const CACHE_NAME = "prompta-shell-v3";
const assetUrl = (path) => new URL(path, self.location.href).toString();
const SHELL = ["./", "./app.css", "./app.js", "./manifest.json", "./icon.svg"]
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

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request).then(
        (cached) => cached || caches.match(assetUrl("./")),
      )),
  );
});
