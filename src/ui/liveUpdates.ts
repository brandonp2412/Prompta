// One same-origin event stream shared by Jobs and Chats. Payloads only invalidate local GETs.
type Topic = "jobs" | "chats";
type Listener = () => void;
type StatusListener = (delayed: boolean) => void;

const listeners: Record<Topic, Set<Listener>> = {
  jobs: new Set(),
  chats: new Set(),
};
const statusListeners = new Set<StatusListener>();
const healthyPollMs = 120000;
const recoveryPollMs = 15000;
const statusGraceMs = 10000;
let source: EventSource | null = null;
let fallbackTimer: number | undefined;
let fallbackIntervalMs: number | undefined;
let statusTimer: number | undefined;
let streamConnected = false;
let updatesDelayed = false;

function notify(topic: Topic) {
  if (document.visibilityState !== "visible") return;
  for (const listener of listeners[topic]) listener();
}

function refreshBoth() {
  notify("jobs");
  notify("chats");
}

function publishStatus(delayed: boolean) {
  if (updatesDelayed === delayed) return;
  updatesDelayed = delayed;
  for (const listener of statusListeners) listener(delayed);
}

function setPollingInterval(milliseconds: number) {
  if (fallbackIntervalMs === milliseconds) return;
  window.clearInterval(fallbackTimer);
  fallbackIntervalMs = milliseconds;
  fallbackTimer = window.setInterval(refreshBoth, milliseconds);
}

function connectionLost() {
  const wasConnected = streamConnected;
  streamConnected = false;
  setPollingInterval(recoveryPollMs);
  if (statusTimer === undefined) {
    statusTimer = window.setTimeout(() => {
      statusTimer = undefined;
      if (!streamConnected) publishStatus(true);
    }, statusGraceMs);
  }
  // Recheck immediately after a healthy stream drops. Repeated errors use
  // bounded polling instead of triggering a request storm.
  if (wasConnected) refreshBoth();
}

function connectionRestored() {
  streamConnected = true;
  window.clearTimeout(statusTimer);
  statusTimer = undefined;
  publishStatus(false);
  setPollingInterval(healthyPollMs);
}

function visibleAgain() {
  if (document.visibilityState === "visible") refreshBoth();
}

function offline() {
  connectionLost();
}

function start() {
  // EventSource reconnects automatically; each sync repairs missed revisions.
  // Poll faster while connecting or disconnected, but not when healthy.
  connectionLost();
  if (typeof EventSource !== "undefined") {
    const nextSource = new EventSource("./api/events");
    source = nextSource;
    nextSource.addEventListener("open", () => {
      if (source === nextSource) connectionRestored();
    });
    nextSource.addEventListener("error", () => {
      if (source === nextSource) connectionLost();
    });
    nextSource.addEventListener("sync", refreshBoth);
    nextSource.addEventListener("jobs", () => notify("jobs"));
    nextSource.addEventListener("chats", () => notify("chats"));
  }
  document.addEventListener("visibilitychange", visibleAgain);
  window.addEventListener("online", visibleAgain);
  window.addEventListener("offline", offline);
  window.addEventListener("pageshow", visibleAgain);
}

function stop() {
  source?.close();
  source = null;
  window.clearInterval(fallbackTimer);
  window.clearTimeout(statusTimer);
  fallbackTimer = undefined;
  fallbackIntervalMs = undefined;
  statusTimer = undefined;
  streamConnected = false;
  publishStatus(false);
  document.removeEventListener("visibilitychange", visibleAgain);
  window.removeEventListener("online", visibleAgain);
  window.removeEventListener("offline", offline);
  window.removeEventListener("pageshow", visibleAgain);
}

function hasSubscribers() {
  return listeners.jobs.size > 0 || listeners.chats.size > 0 || statusListeners.size > 0;
}

export function subscribeLiveUpdates(topic: Topic, listener: Listener): () => void {
  const wasEmpty = !hasSubscribers();
  listeners[topic].add(listener);
  if (wasEmpty) start();
  return () => {
    listeners[topic].delete(listener);
    if (!hasSubscribers()) stop();
  };
}

export function subscribeLiveStatus(listener: StatusListener): () => void {
  const wasEmpty = !hasSubscribers();
  statusListeners.add(listener);
  listener(updatesDelayed);
  if (wasEmpty) start();
  return () => {
    statusListeners.delete(listener);
    if (!hasSubscribers()) stop();
  };
}
