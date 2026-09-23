<script lang="ts">
  import { MediaQuery } from "svelte/reactivity";

  import { appViewState } from "./appViewState.svelte";
  import { dialogVisibility } from "./browserAttachments.svelte";
  import { formatRelativeTime } from "./clientLogic";
  import { pendingLongPressMoved } from "./conversationLogic";
  import { sidebarListActions, sidebarListState } from "./sidebarState.svelte";

  const coarsePointer = new MediaQuery("(pointer: coarse)");
  let actionsChatId = $state("");
  let actionsChatPinned = $state(false);
  let actionsOpen = $state(false);
  let longPressTimer: ReturnType<typeof setTimeout> | undefined;
  let longPressPointerId: number | null = null;
  let longPressStartX = 0;
  let longPressStartY = 0;
  let suppressSelectChatId = "";

  function clearLongPress() {
    if (longPressTimer !== undefined) {
      clearTimeout(longPressTimer);
      longPressTimer = undefined;
    }

    longPressPointerId = null;
  }

  function openActions(chatId: string, pinned: boolean) {
    clearLongPress();
    actionsChatId = chatId;
    actionsChatPinned = pinned;
    actionsOpen = true;
  }

  function closeActions() {
    actionsOpen = false;
    suppressSelectChatId = "";
  }

  function startLongPress(event: PointerEvent, chatId: string, pinned: boolean) {
    sidebarListActions.onPrefetch(chatId);

    if (!coarsePointer.current || event.pointerType === "mouse") return;

    clearLongPress();
    suppressSelectChatId = "";
    longPressPointerId = event.pointerId;
    longPressStartX = event.clientX;
    longPressStartY = event.clientY;
    longPressTimer = setTimeout(() => {
      longPressTimer = undefined;
      longPressPointerId = null;
      suppressSelectChatId = chatId;
      openActions(chatId, pinned);
    }, 480);
  }

  function moveLongPress(event: PointerEvent) {
    if (event.pointerId !== longPressPointerId) return;

    if (pendingLongPressMoved(longPressStartX, longPressStartY, event.clientX, event.clientY)) {
      clearLongPress();
    }
  }

  function endLongPress(event: PointerEvent) {
    if (event.pointerId === longPressPointerId) clearLongPress();
  }

  function selectChat(chatId: string, optimisticNew: boolean) {
    if (suppressSelectChatId === chatId) {
      suppressSelectChatId = "";
      return;
    }

    sidebarListActions.onSelect(chatId, optimisticNew);
  }

  function togglePinFromActions() {
    const chatId = actionsChatId;
    closeActions();
    if (chatId) sidebarListActions.onPin(chatId);
  }
</script>

<svelte:window
  onkeydown={(event) => {
    if (event.key === "Escape" && actionsOpen) closeActions();
  }}
/>

{#if sidebarListState.model.groups.length === 0}
  <div class="list-empty">
    {#if sidebarListState.model.emptyState === "search"}
      No cached chats match your search.
    {:else if sidebarListState.model.emptyState === "filter"}
      No conversations match these filters.
    {:else}
      No cached conversations yet.<br />Prompta runs will appear here live.
    {/if}
  </div>
{:else}
  {#each sidebarListState.model.groups as group (group.label)}
    <section class="chat-group" data-dom-key={"group:" + group.label}>
      <div class="chat-group-label">{group.label}</div>
      {#each group.chats as chat (chat.id)}
        <div
          class={[
            "chat-item",
            {
              selected: chat.id === sidebarListState.selectedConversationId,
              unread: chat.unread,
            },
          ]}
          data-dom-key={"chat:" + chat.id}
        >
          <button
            type="button"
            class="chat-item-select"
            data-chat-id={chat.id}
            data-optimistic-new={chat.optimisticNew ? "true" : "false"}
            aria-current={chat.id === sidebarListState.selectedConversationId ? "true" : undefined}
            onpointerdown={(event) => startLongPress(event, chat.id, chat.pinned)}
            onpointermove={moveLongPress}
            onpointerup={endLongPress}
            onpointercancel={endLongPress}
            oncontextmenu={(event) => {
              if (!coarsePointer.current) return;
              event.preventDefault();
              suppressSelectChatId = chat.id;
              openActions(chat.id, chat.pinned);
            }}
            onclick={() => selectChat(chat.id, chat.optimisticNew)}
          >
            <div class="chat-item-top">
              {#if chat.statusClass}
                <span
                  class={["item-status-dot", chat.statusClass]}
                  title={chat.statusLabel || undefined}
                  aria-label={chat.statusLabel || undefined}
                ></span>
              {/if}
              <span class="chat-title">{chat.title}</span>
              {#if chat.broken}
                <span
                  class="chat-broken-badge"
                  title="No ChatGPT response for at least 40 minutes"
                >Broken</span>
              {/if}
            </div>
            <div class="chat-preview">{chat.preview}</div>
            <div class="chat-meta">
              <span class="chat-job">{chat.jobLabel}</span>
              <span class="chat-time" data-activity-at={chat.activityAt}>
                {formatRelativeTime(chat.activityAt, appViewState.clockTick)}
              </span>
            </div>
          </button>
          <button
            type="button"
            class={["chat-row-pin", { active: chat.pinned }]}
            data-pin-chat-id={chat.id}
            aria-label={chat.pinned ? "Unpin chat" : "Pin chat"}
            title={chat.pinned ? "Unpin chat" : "Pin chat"}
            aria-pressed={chat.pinned}
            onclick={() => sidebarListActions.onPin(chat.id)}
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

{#if sidebarListState.model.hasMore}
  <button
    type="button"
    class="sidebar-load-more"
    disabled={sidebarListState.model.loadingMore}
    aria-busy={sidebarListState.model.loadingMore}
    onclick={() => sidebarListActions.onLoadMore()}
  >
    {sidebarListState.model.loadingMore ? "Loading older chats…" : "Load older chats"}
  </button>
{/if}

<dialog
  {@attach dialogVisibility(() => actionsOpen, () => true, closeActions)}
  class="pending-message-actions"
  aria-labelledby="sidebarChatActionsTitle"
  onclick={(event) => {
    if (event.target === event.currentTarget) closeActions();
  }}
>
  <div class="pending-message-actions-shell">
    <div id="sidebarChatActionsTitle" class="pending-message-actions-title">Chat actions</div>
    <button type="button" class="pending-message-action" onclick={togglePinFromActions}>
      {actionsChatPinned ? "Unpin chat" : "Pin chat"}
    </button>
    <button type="button" class="pending-message-action cancel" onclick={closeActions}>Cancel</button>
  </div>
</dialog>
