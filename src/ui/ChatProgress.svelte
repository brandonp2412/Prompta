<script lang="ts">
  import { conversationState } from "./conversationState.svelte";
  import { appViewState } from "./appViewState.svelte";
  import { chatProgressLabel } from "./chatProgress";
  import { formatClockTime12Hour } from "./clientLogic";
  const progress = $derived(conversationState.progress);
</script>

{#if progress}
  <div class="chat-progress" role="status" aria-live="polite" aria-atomic="true">
    <strong>{chatProgressLabel(progress, appViewState.clockTick / 1000)}</strong>
    {#if progress.last_activity_at}
      <span>Last message activity <time datetime={new Date(progress.last_activity_at * 1000).toISOString()} title={new Date(progress.last_activity_at * 1000).toLocaleString()}>{formatClockTime12Hour(new Date(progress.last_activity_at * 1000))}</time></span>
    {/if}
  </div>
{/if}

