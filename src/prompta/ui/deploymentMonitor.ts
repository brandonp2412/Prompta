export function createDeploymentMonitor({
  onUpdateAvailable = () => {},
}: {
  onUpdateAvailable?: (head: string) => void;
} = {}) {
  let head = "";
  let updateAvailable = false;
  let reloading = false;

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

  async function applyUpdate() {
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
    if (nextHead === head) return;
    head = nextHead;
    updateAvailable = true;
    onUpdateAvailable(head);
  }

  function handleVisibilityChange() {
    if (updateAvailable) onUpdateAvailable(head);
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("./sw.js", { updateViaCache: "none" }).catch((error) => {
      console.warn("Could not register Prompta service worker", error);
    });
  }

  return {
    applyUpdate,
    handleVisibilityChange,
    observeHead,
    registerServiceWorker,
  };
}
