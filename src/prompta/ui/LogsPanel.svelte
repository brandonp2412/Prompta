<script lang="ts">
  import { appViewState } from "./appViewState.svelte";
  import { registerLogsPanel } from "./uiControllers";

  let viewport: HTMLElement;
  const visible = $derived(appViewState.mode === "logs");
  let serverTitle = $state("Prompta · prompta.service");
  let meta = $state("Waiting for synced journal");
  let output = $state("Loading logs…");
  let fingerprint = "";
  let timer: ReturnType<typeof setInterval> | undefined;

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
    const nearBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 120;
    const initial = !fingerprint;
    if (next !== fingerprint) {
      fingerprint = next;
      output = lines.length ? lines.join("\n") : "No Prompta service logs are available yet.";
      if (initial || nearBottom) requestAnimationFrame(() => { viewport.scrollTop = viewport.scrollHeight; });
    }
    meta = payload.exists
      ? payload.source === "journal" ? `${lines.length} lines · live journal` : `${lines.length} lines · synced ${relativeTime(payload.updated_at)}`
      : "Waiting for Prompta service logs";
  }

  export async function load() {
    try {
      const response = await fetch("api/logs?limit=800", { cache: "no-store" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      render(await response.json());
    } catch (error) {
      meta = "Logs unavailable";
      console.error(error);
    }
  }

  export function setServerTitle(display: string) { serverTitle = `${display || ""} · prompta.service`; }
  registerLogsPanel({ load, setServerTitle });

  $effect(() => {
    if (!visible) return;

    void load();
    timer = setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, 2000);

    return () => {
      if (timer) clearInterval(timer);
      timer = undefined;
    };
  });
</script>

<section bind:this={viewport} class="logs-viewport" id="logsViewport" hidden={!visible}>
  <div class="logs-shell"><div class="logs-header"><div><strong>{serverTitle}</strong><span>{meta}</span></div><span class="logs-live"><i></i> live</span></div><pre class="log-output">{output}</pre></div>
</section>
