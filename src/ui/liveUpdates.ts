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
const reconnectDelayMs = 2000;
const maxReconnectDelayMs = 30000;
const staleStreamMs = 60000; // Server sends a ping at least every 15 seconds.
let source: EventSource | null = null;
let fallbackTimer: number | undefined;
let fallbackIntervalMs: number | undefined;
let statusTimer: number | undefined;
let reconnectTimer: number | undefined;
let watchdogTimer: number | undefined;
let reconnectAttempts = 0;
let lastStreamFrameAt = 0;
let streamConnected = false;
let updatesDelayed = false;
let observedOffline = false;

function notify(topic: Topic) {
  if (document.visibilityState !== "visible") return;
  for (const listener of listeners[topic]) listener();
}

function refreshBoth() {
  if (observedOffline) return;
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

function scheduleReconnect() {
  if (observedOffline || reconnectTimer !== undefined || !hasSubscribers()) return;
  const delay = Math.min(maxReconnectDelayMs, reconnectDelayMs * 2 ** reconnectAttempts);
  reconnectAttempts = Math.min(reconnectAttempts + 1, 4);
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = undefined;
    if (!hasSubscribers()) return;
    source?.close();
    source = null;
    connect();
  }, delay);
}

function armWatchdog(current: EventSource) {
  window.clearTimeout(watchdogTimer);
  watchdogTimer = window.setTimeout(() => {
    watchdogTimer = undefined;
    if (source !== current || document.visibilityState !== "visible") return;
    if (Date.now() - lastStreamFrameAt < staleStreamMs) {
      armWatchdog(current);
      return;
    }
    // A silently stalled stream can remain OPEN forever. Recover it even if
    // the browser never emits an error; periodic GETs still work meanwhile.
    connectionLost();
    scheduleReconnect();
  }, staleStreamMs);
}

function connect() {
  if (typeof EventSource === "undefined") return;
  try {
    const nextSource = new EventSource("./api/events");
    source = nextSource;
    lastStreamFrameAt = Date.now();
    armWatchdog(nextSource);
    nextSource.addEventListener("open", () => {
      if (source !== nextSource) return;
      lastStreamFrameAt = Date.now();
      armWatchdog(nextSource);
      // A socket can open without delivering any events. Keep bounded polling
      // and the degraded indicator until an actual server frame arrives.
    });
    nextSource.addEventListener("error", () => {
      if (source !== nextSource) return;
      connectionLost();
      // CONNECTING is auto-retried by browsers. CLOSED is terminal and needs
      // a new EventSource instance; never leave the UI polling indefinitely.
      if (nextSource.readyState === 2) scheduleReconnect();
    });
    for (const topic of ["sync", "jobs", "chats", "ping"] as const) {
      nextSource.addEventListener(topic, () => {
        if (source !== nextSource) return;
        lastStreamFrameAt = Date.now();
        armWatchdog(nextSource);
        reconnectAttempts = 0;
        connectionRestored();
        if (topic === "sync") refreshBoth();
        else if (topic !== "ping") notify(topic);
      });
    }
  } catch {
    // Browser policies can reject construction; retain GET fallback and try
    // again with bounded backoff instead of crashing the entire page.
    connectionLost();
    scheduleReconnect();
  }
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
  if (document.visibilityState !== "visible") return;
  refreshBoth();
  const current = source;
  if (current?.readyState === 2 || (current && Date.now() - lastStreamFrameAt >= staleStreamMs)) {
    connectionLost();
    scheduleReconnect();
    return;
  }
  // A watchdog timeout that fired while hidden does not schedule another check.
  // Re-arm it on return even when the most recent frame is still fresh.
  if (current) armWatchdog(current);
}

function offline() {
  observedOffline = true;
  window.clearTimeout(reconnectTimer);
  reconnectTimer = undefined;
  connectionLost();
}

function onlineAgain() {
  const wasOffline = observedOffline;
  observedOffline = false;
  if (wasOffline) {
    // An EventSource may remain CONNECTING after the network returns. Replace
    // that exact stream now, rather than waiting for the 60-second watchdog.
    retryLiveConnection();
    return;
  }
  visibleAgain();
}

function start() {
  // Browsers reconnect CONNECTING streams. Our watchdog additionally repairs
  // terminal CLOSED or silent stalls; GET polling continues during both.
  connectionLost();
  connect();
  document.addEventListener("visibilitychange", visibleAgain);
  window.addEventListener("online", onlineAgain);
  window.addEventListener("offline", offline);
  window.addEventListener("pageshow", visibleAgain);
}

function stop() {
  source?.close();
  source = null;
  window.clearInterval(fallbackTimer);
  window.clearTimeout(statusTimer);
  window.clearTimeout(reconnectTimer);
  window.clearTimeout(watchdogTimer);
  fallbackTimer = undefined;
  fallbackIntervalMs = undefined;
  statusTimer = undefined;
  reconnectTimer = undefined;
  watchdogTimer = undefined;
  reconnectAttempts = 0;
  lastStreamFrameAt = 0;
  streamConnected = false;
  observedOffline = false;
  publishStatus(false);
  document.removeEventListener("visibilitychange", visibleAgain);
  window.removeEventListener("online", onlineAgain);
  window.removeEventListener("offline", offline);
  window.removeEventListener("pageshow", visibleAgain);
}

function hasSubscribers() {
  return listeners.jobs.size > 0 || listeners.chats.size > 0 || statusListeners.size > 0;
}

export function retryLiveConnection() {
  if (!hasSubscribers()) return;
  window.clearTimeout(reconnectTimer);
  window.clearTimeout(watchdogTimer);
  reconnectTimer = undefined;
  watchdogTimer = undefined;
  source?.close();
  source = null;
  reconnectAttempts = 0;
  const wasConnected = streamConnected;
  connectionLost();
  connect();
  if (!wasConnected) refreshBoth();
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
