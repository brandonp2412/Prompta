export function createLiveUpdates({
  loadChats,
  loadServerIdentity,
  setServerStatus,
  observeHead,
  refreshDisplayedTimes,
  onStreamError,
  onPageShow,
  presenceStaleMs = 16_000,
  presenceCheckMs = 1_000,
}) {
  let eventSource: EventSource | null = null;
  let fallbackTimer: ReturnType<typeof setInterval> | null = null;
  let timeRefreshTimer: ReturnType<typeof setInterval> | null = null;
  let presenceTimer: ReturnType<typeof setInterval> | null = null;
  let paused = false;
  let refreshQueued = false;
  let lastPresenceAt = 0;
  let lastServer = "";

  function queueRefresh() {
    if (refreshQueued) return;
    refreshQueued = true;
    requestAnimationFrame(async () => {
      refreshQueued = false;
      await loadChats();
    });
  }

  function stopTimeRefresh() {
    if (timeRefreshTimer === null) return;
    clearInterval(timeRefreshTimer);
    timeRefreshTimer = null;
  }

  function startTimeRefresh() {
    if (timeRefreshTimer !== null) return;
    timeRefreshTimer = setInterval(refreshDisplayedTimes, 30_000);
  }

  function stopFallbackRefresh() {
    if (fallbackTimer === null) return;
    clearInterval(fallbackTimer);
    fallbackTimer = null;
  }

  function startFallbackRefresh() {
    if (fallbackTimer !== null) return;
    fallbackTimer = setInterval(() => {
      void loadChats();
      void loadServerIdentity();
    }, 5000);
  }

  function markPresence(payload) {
    const server = String(payload.server || lastServer || "");
    if (server) lastServer = server;
    lastPresenceAt = Date.now();
    if (server && typeof payload.online === "boolean") setServerStatus(server, payload.online);
  }

  function markStreamOffline() {
    lastPresenceAt = 0;
    if (lastServer) setServerStatus(lastServer, false);
    onStreamError();
  }

  function handleStatusEvent(event, refreshChats) {
    stopFallbackRefresh();
    try {
      const payload = JSON.parse(event.data || "{}");
      markPresence(payload);
      if (payload.head) observeHead(payload.head);
    } catch (error) {
      console.warn("Could not parse Prompta SSE status", error);
    }
    if (refreshChats) queueRefresh();
  }

  function stopPresenceWatchdog() {
    if (presenceTimer === null) return;
    clearInterval(presenceTimer);
    presenceTimer = null;
  }

  function startPresenceWatchdog() {
    if (presenceTimer !== null) return;
    presenceTimer = setInterval(() => {
      if (!lastPresenceAt || Date.now() - lastPresenceAt <= presenceStaleMs) return;
      markStreamOffline();
      startFallbackRefresh();
    }, presenceCheckMs);
  }

  function stopEventStream() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    stopFallbackRefresh();
  }

  function startEventStream() {
    if (eventSource) return;
    if (!("EventSource" in window)) {
      startFallbackRefresh();
      return;
    }
    const events = new EventSource("api/events");
    eventSource = events;
    events.addEventListener("refresh", (event) => {
      handleStatusEvent(event, true);
    });
    events.addEventListener("heartbeat", (event) => {
      handleStatusEvent(event, false);
    });
    events.addEventListener("error", () => {
      markStreamOffline();
      startFallbackRefresh();
    });
  }

  function start() {
    startEventStream();
    startPresenceWatchdog();
    startTimeRefresh();
  }

  function stop() {
    stopEventStream();
    stopPresenceWatchdog();
    stopTimeRefresh();
  }

  window.addEventListener("pagehide", () => {
    paused = true;
    stop();
  });

  window.addEventListener("pageshow", () => {
    onPageShow();
    if (!paused) return;
    paused = false;
    void loadServerIdentity();
    void loadChats();
    start();
  });

  return {
    start,
    stop,
  };
}
