export function createCompletionNotifications({ displayServerName, getServerName, chatTitle }) {
  const chatStatuses = new Map();
  const explicitlyActive = new Set();
  const pendingFinishedChats = new Map();
  const notifiedCompletions = new Set();
  let baselineReady = false;
  let permissionRequest: Promise<string> | null = null;
  let flushingNotifications = false;

  function completionKey(chat) {
    return String(chat.id || "") + ":" + String(chat.completed_at ?? chat.updated_at ?? "");
  }

  async function showChatFinished(chat) {
    if (!("Notification" in window) || Notification.permission !== "granted") return false;
    const display = displayServerName(getServerName() || location.hostname);
    const title = chatTitle(chat);
    const options = {
      body: title + " finished",
      tag: "prompta-finished-" + chat.id,
      icon: "./icon.svg",
      badge: "./icon.svg",
      data: { url: "./#/" + encodeURIComponent(chat.id) },
    };
    if ("serviceWorker" in navigator) {
      try {
        let registration: ServiceWorkerRegistration | null | undefined =
          typeof navigator.serviceWorker.getRegistration === "function"
            ? await navigator.serviceWorker.getRegistration()
            : null;
        if (!registration) {
          registration = await Promise.race([
            navigator.serviceWorker.ready,
            new Promise<ServiceWorkerRegistration | null>((resolve) =>
              setTimeout(() => resolve(null), 1500),
            ),
          ]);
        }
        if (registration) {
          await registration.showNotification("Prompta · " + display, options);
          return true;
        }
      } catch (error) {
        console.warn("Could not show Prompta service worker notification", error);
      }
    }
    try {
      new Notification("Prompta · " + display, options);
      return true;
    } catch (error) {
      console.warn("Could not show Prompta completion notification", error);
      return false;
    }
  }

  async function flushPendingNotifications() {
    if (
      flushingNotifications ||
      !("Notification" in window) ||
      Notification.permission !== "granted"
    )
      return;
    flushingNotifications = true;
    try {
      while (pendingFinishedChats.size) {
        const [key, chat] = pendingFinishedChats.entries().next().value;
        if (!(await showChatFinished(chat))) break;
        pendingFinishedChats.delete(key);
        notifiedCompletions.add(key);
      }
    } finally {
      flushingNotifications = false;
    }
  }

  async function requestPermissionFromGesture() {
    if (!("Notification" in window)) return;
    if (Notification.permission === "granted") {
      await flushPendingNotifications();
      return;
    }
    if (Notification.permission !== "default") return;
    if (!permissionRequest) {
      permissionRequest = Notification.requestPermission()
        .catch((error) => {
          console.warn("Could not request notification permission", error);
          return "default";
        })
        .finally(() => {
          permissionRequest = null;
        });
    }
    const permission = await permissionRequest;
    if (permission === "granted") {
      await flushPendingNotifications();
    }
  }

  function queueFinishedChat(chat) {
    const key = completionKey(chat);
    if (!chat.id || notifiedCompletions.has(key) || pendingFinishedChats.has(key)) return;
    pendingFinishedChats.set(key, chat);
    void flushPendingNotifications();
  }

  function markActive(conversationId) {
    const id = String(conversationId || "");
    if (!id) return;
    chatStatuses.set(id, "active");
    explicitlyActive.add(id);
  }

  function trackCompletions(chats) {
    for (const chat of chats) {
      const wasActive = chatStatuses.get(chat.id) === "active" || explicitlyActive.has(chat.id);
      if (
        (baselineReady || explicitlyActive.has(chat.id)) &&
        wasActive &&
        chat.status === "complete"
      ) {
        queueFinishedChat(chat);
        explicitlyActive.delete(chat.id);
      } else if (!["active", "complete"].includes(chat.status)) {
        explicitlyActive.delete(chat.id);
      }
    }
    for (const chat of chats) chatStatuses.set(chat.id, chat.status);
    baselineReady = true;
    void flushPendingNotifications();
  }

  return {
    markActive,
    requestPermissionFromGesture,
    trackCompletions,
  };
}
