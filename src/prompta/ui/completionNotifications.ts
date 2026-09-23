export function createCompletionNotifications({ displayServerName, getServerName, chatTitle }) {
  const chatStatuses = new Map();
  const explicitlyActive = new Set();
  const pendingFinishedChats = new Map();
  const notifiedCompletions = new Set();
  let baselineReady = false;
  let permissionRequest: Promise<string> | null = null;
  let pushSetup: Promise<boolean> | null = null;
  let pushRegisteredAt = 0;
  let flushingNotifications = false;

  function decodeApplicationServerKey(value: string) {
    const padded = value
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(value.length / 4) * 4, "=");
    const raw = atob(padded);
    const bytes = new Uint8Array(raw.length);

    for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);

    return bytes;
  }

  function sameApplicationServerKey(current: ArrayBuffer | null, expected: Uint8Array) {
    if (!current) return false;

    const bytes = new Uint8Array(current);

    return (
      bytes.length === expected.length && bytes.every((value, index) => value === expected[index])
    );
  }

  async function ensurePushSubscription() {
    if (pushRegisteredAt) return true;

    if (pushSetup) return pushSetup;

    if (!("serviceWorker" in navigator)) return false;

    pushSetup = (async () => {
      try {
        const registration = await navigator.serviceWorker.ready;

        if (!registration.pushManager) return false;

        const keyResponse = await fetch("api/push/public-key", { cache: "no-store" });

        if (!keyResponse.ok) throw new Error("Could not load Web Push public key");

        const payload = await keyResponse.json();
        const publicKey = String(payload.public_key || "");
        const applicationServerKey = decodeApplicationServerKey(publicKey);
        let subscription = await registration.pushManager.getSubscription();

        if (
          subscription &&
          !sameApplicationServerKey(subscription.options.applicationServerKey, applicationServerKey)
        ) {
          await subscription.unsubscribe();
          subscription = null;
        }

        subscription ??= await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey,
        });

        const saveResponse = await fetch("api/push/subscriptions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(subscription.toJSON()),
        });

        if (!saveResponse.ok) throw new Error("Could not save Web Push subscription");

        pushRegisteredAt = Date.now() / 1000;

        return true;
      } catch (error) {
        console.warn("Could not enable Prompta background notifications", error);

        return false;
      } finally {
        pushSetup = null;
      }
    })();

    return pushSetup;
  }

  async function initialize() {
    if (!("Notification" in window) || Notification.permission !== "granted") return;

    await ensurePushSubscription();
  }

  function completionKey(chat) {
    return String(chat.id || "") + ":" + String(chat.completed_at ?? chat.updated_at ?? "");
  }

  async function showChatFinished(chat) {
    if (!("Notification" in window) || Notification.permission !== "granted") return false;

    const completedAt = Number(chat.completed_at ?? chat.updated_at ?? 0);

    if (pushRegisteredAt && completedAt >= pushRegisteredAt) return true;

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
      await ensurePushSubscription();
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
      await ensurePushSubscription();
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
    initialize,
    markActive,
    requestPermissionFromGesture,
    trackCompletions,
  };
}
