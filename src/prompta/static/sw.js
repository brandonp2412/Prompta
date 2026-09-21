const BUILD_ID = "__PROMPTA_UI_HEAD__";
const CACHE_NAME = "prompta-shell-" + (BUILD_ID || "dev");
const assetUrl = (path) => new URL(path, self.location.href).toString();
const SHELL = ["./", "./app.css", "./app.js", "./manifest.webmanifest", "./icon.svg"]
  .map(assetUrl);

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    const replacingShell = keys.some(
      (key) => key.startsWith("prompta-shell-") && key !== CACHE_NAME,
    );
    await Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)));
    await self.clients.claim();
    if (!replacingShell) return;
    const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of clients) {
      if ("navigate" in client) await client.navigate(client.url);
    }
  })());
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
