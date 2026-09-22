export function createDeploymentMonitor({
  shouldDeferReload = () => false,
  deferRetryMs = 250,
}: {
  shouldDeferReload?: () => boolean;
  deferRetryMs?: number;
} = {}) {
  let head = "";
  let reloading = false;
  let reloadPending = false;
  let deferredRefreshTimer: ReturnType<typeof setTimeout> | null = null;

  function clearDeferredRefresh() {
    if (deferredRefreshTimer === null) return;
    clearTimeout(deferredRefreshTimer);
    deferredRefreshTimer = null;
  }

  async function updateServiceWorker() {
    try {
      if ("serviceWorker" in navigator) {
        const registration = await navigator.serviceWorker.getRegistration();
        await registration?.update();
      }
    } catch (error) {
      console.warn("Could not update Prompta service worker for deployment", error);
    }
  }

  async function refresh() {
    if (reloading) return;
    clearDeferredRefresh();
    reloading = true;
    reloadPending = false;
    await updateServiceWorker();
    window.location.reload();
  }

  function scheduleRefresh() {
    if (!reloadPending || reloading) return;
    if (shouldDeferReload()) {
      if (deferredRefreshTimer === null) {
        deferredRefreshTimer = setTimeout(() => {
          deferredRefreshTimer = null;
          scheduleRefresh();
        }, deferRetryMs);
      }
      return;
    }
    clearDeferredRefresh();
    void refresh();
  }

  function observeHead(value) {
    const nextHead = String(value || "").trim().toLowerCase();
    if (!nextHead) return;
    if (!head) {
      head = nextHead;
      return;
    }
    if (nextHead === head || reloading) return;
    head = nextHead;
    reloadPending = true;
    scheduleRefresh();
  }

  function handleVisibilityChange() {
    scheduleRefresh();
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("./sw.js", { updateViaCache: "none" }).catch((error) => {
      console.warn("Could not register Prompta service worker", error);
    });
  }

  return {
    handleVisibilityChange,
    observeHead,
    registerServiceWorker,
  };
}
