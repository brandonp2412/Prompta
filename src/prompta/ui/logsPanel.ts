function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error("Missing required logs UI element: " + selector);
  return element;
}

function setTextIfChanged(element: Element, value) {
  const text = String(value ?? "");
  if (element.textContent !== text) element.textContent = text;
}

export function createLogsPanel({ fetchJson, formatRelativeTime }) {
  const els = {
    viewport: requiredElement<HTMLElement>("#logsViewport"),
    output: requiredElement<HTMLElement>("#logOutput"),
    meta: requiredElement<HTMLElement>("#logsMeta"),
    serverTitle: requiredElement<HTMLElement>("#logsServerTitle"),
  };
  let fingerprint = "";
  let refreshTimer: ReturnType<typeof setInterval> | null = null;
  let visible = false;

  function render(payload) {
    const lines = Array.isArray(payload.lines) ? payload.lines : [];
    const nextFingerprint = JSON.stringify([payload.updated_at, lines]);
    const wasNearBottom = els.viewport.scrollHeight
      - els.viewport.scrollTop
      - els.viewport.clientHeight < 120;
    const isInitial = !fingerprint;
    if (nextFingerprint !== fingerprint) {
      fingerprint = nextFingerprint;
      setTextIfChanged(
        els.output,
        lines.length ? lines.join("\n") : "No Prompta service logs are available yet.",
      );
      if (isInitial || wasNearBottom) {
        requestAnimationFrame(() => {
          els.viewport.scrollTop = els.viewport.scrollHeight;
        });
      }
    }
    setTextIfChanged(
      els.meta,
      payload.exists
        ? payload.source === "journal"
          ? lines.length + " lines · live journal"
          : lines.length + " lines · synced " + formatRelativeTime(payload.updated_at)
        : "Waiting for Prompta service logs",
    );
  }

  async function load() {
    try {
      render(await fetchJson("api/logs?limit=800"));
    } catch (error) {
      setTextIfChanged(els.meta, "Logs unavailable");
      console.error(error);
    }
  }

  function stopRefresh() {
    if (refreshTimer === null) return;
    clearInterval(refreshTimer);
    refreshTimer = null;
  }

  function setVisible(nextVisible) {
    visible = Boolean(nextVisible);
    els.viewport.hidden = !visible;
    stopRefresh();
    if (!visible) return;
    void load();
    refreshTimer = setInterval(() => {
      if (visible && document.visibilityState === "visible") void load();
    }, 2000);
  }

  function setServerTitle(display) {
    setTextIfChanged(els.serverTitle, String(display || "") + " · prompta.service");
  }

  return {
    load,
    setServerTitle,
    setVisible,
  };
}
