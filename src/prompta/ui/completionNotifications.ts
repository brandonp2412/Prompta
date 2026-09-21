export function createCompletionNotifications({
  displayServerName,
  getServerName,
  chatTitle,
}) {
  const chatStatuses = new Map();
  let baselineReady = false;

  async function requestPermissionFromGesture() {
    if (!("Notification" in window) || Notification.permission !== "default") return;
    try {
      await Notification.requestPermission();
    } catch (error) {
      console.warn("Could not request notification permission", error);
    }
  }

  async function notifyChatFinished(chat) {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const display = displayServerName(getServerName() || location.hostname);
    const title = chatTitle(chat);
    try {
      if ("serviceWorker" in navigator) {
        const registration = await navigator.serviceWorker.ready;
        await registration.showNotification("Prompta · " + display, {
          body: title + " finished",
          tag: "prompta-finished-" + chat.id,
          icon: "./icon.svg",
          badge: "./icon.svg",
          data: { url: "./#/" + encodeURIComponent(chat.id) },
        });
        return;
      }
      new Notification("Prompta · " + display, { body: title + " finished" });
    } catch (error) {
      console.warn("Could not show Prompta completion notification", error);
    }
  }

  function trackCompletions(chats) {
    if (baselineReady) {
      for (const chat of chats) {
        if (chatStatuses.get(chat.id) === "active" && chat.status === "complete") {
          void notifyChatFinished(chat);
        }
      }
    }
    for (const chat of chats) chatStatuses.set(chat.id, chat.status);
    baselineReady = true;
  }

  return {
    requestPermissionFromGesture,
    trackCompletions,
  };
}
