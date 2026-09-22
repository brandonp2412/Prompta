<script module lang="ts">
  export type SidebarListModel = {
    emptyState: "none" | "search" | "empty";
    groups: Array<{
      label: string;
      chats: Array<{
        id: string;
        selected: boolean;
        optimisticNew: boolean;
        statusClass: "active" | "complete" | "neutral" | null;
        title: string;
        preview: string;
        jobLabel: string;
        activityAt: string | number;
        relativeTime: string;
        pinned: boolean;
      }>;
    }>;
  };
</script>

<script lang="ts">
  type Props = {
    onSelect: (chatId: string, optimisticNew: boolean) => void;
    onPin: (chatId: string) => void;
  };

  let { onSelect, onPin }: Props = $props();
  let model = $state<SidebarListModel>({ emptyState: "none", groups: [] });

  export function update(next: SidebarListModel) {
    model = next;
  }
</script>

{#if model.groups.length === 0}
  <div class="list-empty">
    {#if model.emptyState === "search"}
      No cached chats match your search.
    {:else}
      No cached conversations yet.<br />Prompta runs will appear here live.
    {/if}
  </div>
{:else}
  {#each model.groups as group (group.label)}
    <section class="chat-group" data-dom-key={"group:" + group.label}>
      <div class="chat-group-label">{group.label}</div>
      {#each group.chats as chat (chat.id)}
        <div class:selected={chat.selected} class="chat-item" data-dom-key={"chat:" + chat.id}>
          <button
            type="button"
            class="chat-item-select"
            data-chat-id={chat.id}
            data-optimistic-new={chat.optimisticNew ? "true" : "false"}
            aria-current={chat.selected ? "true" : undefined}
            onclick={() => onSelect(chat.id, chat.optimisticNew)}
          >
            <div class="chat-item-top">
              {#if chat.statusClass}
                <span class={"item-status-dot " + chat.statusClass}></span>
              {/if}
              <span class="chat-title">{chat.title}</span>
            </div>
            <div class="chat-preview">{chat.preview}</div>
            <div class="chat-meta">
              <span class="chat-job">{chat.jobLabel}</span>
              <span class="chat-time" data-activity-at={chat.activityAt}>{chat.relativeTime}</span>
            </div>
          </button>
          <button
            type="button"
            class:active={chat.pinned}
            class="chat-row-pin"
            data-pin-chat-id={chat.id}
            aria-label={chat.pinned ? "Unpin chat" : "Pin chat"}
            title={chat.pinned ? "Unpin chat" : "Pin chat"}
            aria-pressed={chat.pinned}
            onclick={() => onPin(chat.id)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M9 3h6l-.8 5 3.3 3.3v1.4H13v7.8l-1 1-1-1v-7.8H6.5v-1.4L9.8 8 9 3z"></path>
            </svg>
          </button>
        </div>
      {/each}
    </section>
  {/each}
{/if}
