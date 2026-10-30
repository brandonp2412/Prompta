<script lang="ts">
  import type { CapturedToolCall } from "./resultFormatting";

  let { calls }: { calls: CapturedToolCall[] } = $props();
  let failures = $derived(calls.filter((call) => call.status === "error" || call.error).length);
  const title = (call: CapturedToolCall) => [call.connector, call.action].filter(Boolean).join(" · ") || "Tool call";
  const status = (call: CapturedToolCall) => call.status === "error" || call.error ? "Failed" :
    call.status === "running" ? "Running" : call.status === "observed" ? "Observed" : "Completed";
</script>

{#if calls.length}
  <details class="tool-timeline">
    <summary class="tool-timeline-summary">
      <span class="tool-timeline-icon" aria-hidden="true">⌘</span>
      <span>{calls.length} tool {calls.length === 1 ? "call" : "calls"}</span>
      {#if failures}<span class="tool-failure-count">{failures} failed</span>{/if}
      <span class="tool-timeline-toggle" aria-hidden="true">⌄</span>
    </summary>
    <div class="tool-call-list">
      {#each calls as call, index (call.id || index)}
        <details class="tool-call" class:failed={status(call) === "Failed"} class:running={status(call) === "Running"}>
          <summary class="tool-call-summary">
            <span class="tool-call-mark" aria-hidden="true">{status(call) === "Failed" ? "!" : status(call) === "Running" ? "…" : status(call) === "Observed" ? "·" : "✓"}</span>
            <span class="tool-call-name">{title(call)}</span>
            <span class="tool-call-status">{status(call)}</span>
            <span class="tool-call-chevron" aria-hidden="true">⌄</span>
          </summary>
          <div class="tool-call-body">
            {#if call.arguments}
              <section><h4>Input</h4><pre>{call.arguments}</pre></section>
            {/if}
            {#if call.result}
              <section><h4>Output</h4><pre>{call.result}</pre></section>
            {/if}
            {#if call.error}
              <section><h4>Error</h4><pre>{call.error}</pre></section>
            {/if}
            {#if !call.arguments && !call.result && !call.error}
              <p>No additional details captured.</p>
            {/if}
          </div>
        </details>
      {/each}
    </div>
  </details>
{/if}
