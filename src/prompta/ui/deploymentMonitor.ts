export function createDeploymentMonitor() {
  let head = "";
  let reloading = false;
  let reloadPending = false;
  let reloadArmed = false;

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
    reloading = true;
    await updateServiceWorker();
    window.location.reload();
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
    reloadArmed = document.visibilityState !== "visible";
    void updateServiceWorker();
  }

  function handleVisibilityChange() {
    if (!reloadPending || reloading) return;
    if (document.visibilityState !== "visible") {
      reloadArmed = true;
      return;
    }
    if (!reloadArmed) return;
    void refresh();
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
