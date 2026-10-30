// One same-origin event stream shared by Jobs and Chats. Payloads only invalidate local GETs.
type Topic = "jobs" | "chats";
type Listener = () => void;

const listeners: Record<Topic, Set<Listener>> = {
  jobs: new Set(),
  chats: new Set(),
};
let source: EventSource | null = null;
let fallbackTimer: number | undefined;
let streamDisconnected = true;
let repairTicks = 0;
const repairIntervalMs = 15_000;
const connectedRepairTicks = 8;

function notify(topic: Topic) {
  if (document.visibilityState !== "visible") return;
  for (const listener of listeners[topic]) listener();
}

function refreshBoth() {
  notify("jobs");
  notify("chats");
}

function visibleAgain() {
  if (document.visibilityState === "visible") refreshBoth();
}

function periodicRepair() {
  // When an SSE connection fails, repair local views every 15s instead of
  // waiting two minutes. A healthy stream keeps the inexpensive 2m audit.
  repairTicks += 1;
  if (streamDisconnected || repairTicks >= connectedRepairTicks) {
    repairTicks = 0;
    refreshBoth();
  }
}

function start() {
  streamDisconnected = true;
  repairTicks = 0;
  if (typeof EventSource !== "undefined") {
    source = new EventSource("./api/events");
    source.addEventListener("open", () => {
      // The server immediately emits sync on each connection. Let that event
      // own the GET invalidation to avoid two full fetches per reconnect.
      streamDisconnected = false;
      repairTicks = 0;
    });
    source.addEventListener("error", () => {
      const wasConnected = !streamDisconnected;
      streamDisconnected = true;
      repairTicks = 0;
      // Repeated EventSource failures can fire while already offline.
      // The 15s repair timer owns that state; do not bombard local GETs.
      if (wasConnected) refreshBoth();
    });
    // An unconditional sync after each (re)connection covers missed events.
    source.addEventListener("sync", () => {
      streamDisconnected = false;
      repairTicks = 0;
      refreshBoth();
    });
    source.addEventListener("jobs", () => notify("jobs"));
    source.addEventListener("chats", () => notify("chats"));
  }
  // Subscribers already coalesce GETs and retain the last confirmed data.
  fallbackTimer = window.setInterval(periodicRepair, repairIntervalMs);
  document.addEventListener("visibilitychange", visibleAgain);
  window.addEventListener("online", visibleAgain);
  window.addEventListener("pageshow", visibleAgain);
}

function stop() {
  source?.close();
  source = null;
  window.clearInterval(fallbackTimer);
  fallbackTimer = undefined;
  streamDisconnected = true;
  repairTicks = 0;
  document.removeEventListener("visibilitychange", visibleAgain);
  window.removeEventListener("online", visibleAgain);
  window.removeEventListener("pageshow", visibleAgain);
}

export function subscribeLiveUpdates(topic: Topic, listener: Listener): () => void {
  const wasEmpty = listeners.jobs.size === 0 && listeners.chats.size === 0;
  listeners[topic].add(listener);
  if (wasEmpty) start();
  return () => {
    listeners[topic].delete(listener);
    if (!listeners.jobs.size && !listeners.chats.size) stop();
  };
}
