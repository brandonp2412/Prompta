export function createLiveUpdates({
  loadChats,
  loadServerIdentity,
  setServerStatus,
  observeHead,
  refreshDisplayedTimes,
  onStreamError,
  onPageShow,
}) {
  let eventSource: EventSource | null = null;
  let fallbackTimer: ReturnType<typeof setInterval> | null = null;
  let timeRefreshTimer: ReturnType<typeof setInterval> | null = null;
  let paused = false;
  let refreshQueued = false;

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
      stopFallbackRefresh();
      try {
        const payload = JSON.parse(event.data || "{}");
        setServerStatus(payload.server, payload.online);
        observeHead(payload.head);
      } catch (error) {
        console.warn("Could not parse Prompta SSE status", error);
      }
      queueRefresh();
    });
    events.addEventListener("error", () => {
      onStreamError();
      startFallbackRefresh();
    });
  }

  function start() {
    startEventStream();
    startTimeRefresh();
  }

  function stop() {
    stopEventStream();
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
