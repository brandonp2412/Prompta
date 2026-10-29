// One same-origin event stream shared by Jobs and Chats. Payloads only invalidate local GETs.
type Topic = "jobs" | "chats";
type Listener = () => void;

const listeners: Record<Topic, Set<Listener>> = {
  jobs: new Set(),
  chats: new Set(),
};
let source: EventSource | null = null;
let fallbackTimer: number | undefined;

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

function start() {
  if (typeof EventSource !== "undefined") {
    source = new EventSource("./api/events");
    // An unconditional sync after each (re)connection covers every missed event.
    source.addEventListener("sync", refreshBoth);
    source.addEventListener("jobs", () => notify("jobs"));
    source.addEventListener("chats", () => notify("chats"));
  }
  // If the stream is unsupported or offline, use a slower safety-net refresh.
  fallbackTimer = window.setInterval(() => {
    if (!source || source.readyState !== EventSource.OPEN) refreshBoth();
  }, 60000);
  document.addEventListener("visibilitychange", visibleAgain);
}

function stop() {
  source?.close();
  source = null;
  window.clearInterval(fallbackTimer);
  fallbackTimer = undefined;
  document.removeEventListener("visibilitychange", visibleAgain);
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
