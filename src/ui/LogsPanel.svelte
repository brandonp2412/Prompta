<script lang="ts">
  import { appViewState } from "./appViewState.svelte";
  import { stickToBottom } from "./browserAttachments.svelte";
  import { registerLogsPanel } from "./uiControllers";

  const logServices = [
    { key: "ui", label: "UI", unit: "prompta-ui.service" },
    { key: "scheduler", label: "Scheduler", unit: "prompta-scheduler.service" },
    { key: "delivery", label: "Delivery worker", unit: "prompta-delivery-worker.service" },
    { key: "conversation", label: "Conversation worker", unit: "prompta-conversation-worker.service" },
    { key: "browser", label: "Browser", unit: "prompta-browser.service" },
  ] as const;
  type LogServiceKey = (typeof logServices)[number]["key"];

  const visible = $derived(appViewState.mode === "logs");
  let serverDisplay = $state("Prompta");
  let selectedService = $state<LogServiceKey>("ui");
  const selectedServiceOption = $derived(
    logServices.find((service) => service.key === selectedService) ?? logServices[0],
  );
  const serverTitle = $derived(serverDisplay + " · " + selectedServiceOption.unit);
  let meta = $state("Waiting for synced journal");
  let output = $state("Loading logs…");
  let fingerprint = $state("");
  let syncState = $state<"loading" | "live" | "retrying">("loading");
  const syncLabel = $derived(
    syncState === "live" ? "Live" : syncState === "retrying" ? "Retrying" : "Loading",
  );
  let refreshTimer: ReturnType<typeof setTimeout> | undefined;
  let activeRequest: AbortController | undefined;

  function relativeTime(epochSeconds: unknown) {
    const value = Number(epochSeconds || 0);

    if (!value) return "";

    const delta = Math.abs(Date.now() - value * 1000);

    if (delta < 45_000) return "now";
    if (delta < 3_600_000) return `${Math.max(1, Math.round(delta / 60_000))}m`;
    if (delta < 86_400_000) return `${Math.round(delta / 3_600_000)}h`;

    return `${Math.round(delta / 86_400_000)}d`;
  }

  function render(payload: Record<string, unknown>) {
    const lines = Array.isArray(payload.lines) ? payload.lines.map(String) : [];
    const next = JSON.stringify([payload.updated_at, lines]);

    if (next !== fingerprint) {
      fingerprint = next;
      output = lines.length ? lines.join("\n") : "No Prompta service logs are available yet.";
    }

    meta = payload.exists
      ? payload.source === "journal"
        ? `${lines.length} lines · live journal`
        : `${lines.length} lines · synced ${relativeTime(payload.updated_at)}`
      : "Waiting for Prompta service logs";
  }

  export async function load() {
    activeRequest?.abort();

    const controller = new AbortController();
    const requestedService = selectedService;
    activeRequest = controller;

    try {
      const params = new URLSearchParams({ limit: "800", service: requestedService });
      const response = await fetch("api/logs?" + params, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(response.status + " " + response.statusText);
      const payload = await response.json();
      if (controller.signal.aborted || requestedService !== selectedService) return;

      render(payload);
      syncState = "live";
    } catch (error) {
      if (controller.signal.aborted || requestedService !== selectedService) return;

      meta = "Logs unavailable";
      syncState = "retrying";
      console.error(error);
    } finally {
      if (activeRequest === controller) activeRequest = undefined;
    }
  }

  function selectService(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    if (!logServices.some((service) => service.key === value)) return;

    selectedService = value as LogServiceKey;
    fingerprint = "";
    meta = "Loading logs…";
    output = "Loading logs…";
    syncState = "loading";
  }

  export function setServerTitle(display: string) {
    serverDisplay = display || "Prompta";
  }

  registerLogsPanel({ load, setServerTitle });

  $effect(() => {
    if (!visible) return;

    const watchedService = selectedService;
    let cancelled = false;

    const poll = async () => {
      await load();
      if (cancelled || !visible || selectedService !== watchedService) return;

      refreshTimer = setTimeout(() => void poll(), 2000);
    };

    void poll();

    return () => {
      cancelled = true;
      activeRequest?.abort();
      activeRequest = undefined;
      if (refreshTimer) clearTimeout(refreshTimer);
      refreshTimer = undefined;
    };
  });
</script>

<section
  {@attach stickToBottom(() => fingerprint)}
  class="logs-viewport"
  id="logsViewport"
  hidden={!visible}
>
  <div class="logs-shell">
    <div class="logs-header">
      <div class="logs-heading"><strong>{serverTitle}</strong><span>{meta}</span></div>
      <div class="logs-controls">
        <label class="logs-service-picker">
          <span>Service</span>
          <select aria-label="Log service" value={selectedService} onchange={selectService}>
            {#each logServices as service (service.key)}
              <option value={service.key}>{service.label}</option>
            {/each}
          </select>
        </label>
        <span
          class={["logs-live", { live: syncState === "live" }]}
          role="status"
          aria-live="polite"
          aria-atomic="true"
        ><i></i>{syncLabel}</span>
      </div>
    </div>
    <pre class="log-output">{output}</pre>
  </div>
</section>
