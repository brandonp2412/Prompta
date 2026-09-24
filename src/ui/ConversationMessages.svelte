<script lang="ts">
  import { MediaQuery } from "svelte/reactivity";

  import { appViewState } from "./appViewState.svelte";
  import { dialogVisibility } from "./browserAttachments.svelte";
  import { formatClockTime12Hour, messageAgeText, messageTimestampMillis } from "./clientLogic";
  import MarkdownContent from "./MarkdownContent.svelte";
  import { conversationState } from "./conversationState.svelte";
  import {
    messageDisplayContent,
    pendingLongPressMoved,
    shouldHandlePendingLongPress,
  } from "./conversationLogic";

  type Message = Record<string, any>;

  const coarsePointer = new MediaQuery("(pointer: coarse)");
  let actionsKey = $state("");
  let actionsCanBump = $state(false);
  let actionsOpen = $state(false);
  let pendingLongPressTimer: ReturnType<typeof setTimeout> | undefined;
  let pendingLongPressPointerId: number | null = null;
  let pendingLongPressStartX = 0;
  let pendingLongPressStartY = 0;

  function timestamp(message: Message, _clockTick: number) {
    const millis = messageTimestampMillis(message.display_at, message.created_at ?? message.updated_at);

    if (millis === null) return { text: "Time unavailable", iso: "", millis: null, age: "" };

    const date = new Date(millis);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];
    const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

    return {
      text: `${date.getDate()} ${months[date.getMonth()]} ${weekdays[date.getDay()]} ${formatClockTime12Hour(date)}`,
      iso: date.toISOString(),
      millis,
      age: messageAgeText(millis),
    };
  }

  function key(message: Message, index: number) {
    return String(message.message_key || `${message.role || "message"}:${index}`);
  }

  function streaming(message: Message) {
    return (
      Boolean(message.pending_activity) ||
      (conversationState.allowStreaming && message.status === "streaming")
    );
  }

  function images(message: Message) {
    return Array.isArray(message.attachments)
      ? message.attachments.filter(
          (item) => item && String(item.type || "").startsWith("image/"),
        )
      : [];
  }

  function imageSrc(item: Record<string, any>) {
    return String(item.src || "").startsWith("data:image/")
      ? item.src
      : item.id
        ? `api/attachment-previews/${encodeURIComponent(item.id)}`
        : "";
  }

  function clearPendingLongPress() {
    if (pendingLongPressTimer !== undefined) {
      clearTimeout(pendingLongPressTimer);
      pendingLongPressTimer = undefined;
    }

    pendingLongPressPointerId = null;
  }

  function startPendingLongPress(event: PointerEvent, message: Message) {
    if (
      !message.pending_delete_key ||
      !shouldHandlePendingLongPress(event.pointerType, coarsePointer.current)
    ) {
      return;
    }

    clearPendingLongPress();
    pendingLongPressPointerId = event.pointerId;
    pendingLongPressStartX = event.clientX;
    pendingLongPressStartY = event.clientY;
    pendingLongPressTimer = setTimeout(() => {
      pendingLongPressTimer = undefined;
      pendingLongPressPointerId = null;
      openActions(message);
    }, 480);
  }

  function movePendingLongPress(event: PointerEvent) {
    if (event.pointerId !== pendingLongPressPointerId) return;

    if (
      pendingLongPressMoved(
        pendingLongPressStartX,
        pendingLongPressStartY,
        event.clientX,
        event.clientY,
      )
    ) {
      clearPendingLongPress();
    }
  }

  function endPendingLongPress(event: PointerEvent) {
    if (event.pointerId === pendingLongPressPointerId) clearPendingLongPress();
  }

  function openActions(message: Message) {
    if (!message.pending_delete_key) return;

    clearPendingLongPress();
    actionsKey = String(message.pending_delete_key);
    actionsCanBump = Boolean(message.pending_bump_key);
    actionsOpen = true;
  }

  function closeActions() {
    actionsOpen = false;
  }

  function bumpPending() {
    closeActions();
    conversationState.onBump(actionsKey);
  }

  function editPending() {
    closeActions();
    conversationState.onEdit(actionsKey);
  }

  function deletePending() {
    closeActions();
    conversationState.onDelete(actionsKey);
  }
</script>

<svelte:window
  onkeydown={(event) => {
    if (event.key === "Escape" && actionsOpen) closeActions();
  }}
/>

<div role="presentation">
  {#if conversationState.loading}
    <div
      class="conversation-loading"
      data-message-key="__loading__"
      aria-live="polite"
      aria-label="Loading conversation"
    >
      <div class="conversation-loading-row conversation-loading-user"></div>
      <div class="conversation-loading-row conversation-loading-assistant"></div>
      <div class="conversation-loading-row conversation-loading-assistant short"></div>
    </div>
  {/if}

  {#each conversationState.messages as message, index (key(message, index))}
    {const value = timestamp(message, appViewState.clockTick)}
    {const deleting = conversationState.deletingKeys.has(String(message.pending_delete_key || ""))}
    {const role = message.role === "user" ? "user" : "assistant"}

    <section
      role="presentation"
      class={[
        "message",
        role,
        {
          "send-error": Boolean(message.send_error),
          "pending-activity": Boolean(message.pending_activity),
          "pending-message-action-target": Boolean(message.pending_delete_key),
          "pending-message-bumpable": Boolean(message.pending_bump_key),
          "pending-message-deleting": deleting,
        },
      ]}
      data-message-key={key(message, index)}
      onpointerdown={(event) => startPendingLongPress(event, message)}
      onpointermove={movePendingLongPress}
      onpointerup={endPendingLongPress}
      onpointercancel={endPendingLongPress}
      oncontextmenu={(event) => {
        if (message.pending_delete_key && coarsePointer.current) {
          event.preventDefault();
          openActions(message);
        }
      }}
    >
      <div class="message-inner">
        {#if role === "assistant"}
          <div class="message-label">
            <span class="assistant-avatar">{message.send_error ? "!" : "P"}</span>
            {message.send_error ? "Send error" : "Prompta run"}
          </div>
        {/if}

        {#if !message.pending_activity}
          {#each images(message) as image (image.id || image.src || image.name)}
            <div class="message-attachments">
              <img
                class="message-image-preview"
                src={imageSrc(image)}
                alt={image.name || "Attached image"}
                loading="lazy"
                decoding="async"
              />
            </div>
          {/each}
        {/if}

        <div class="message-content">
          {#if !message.pending_activity}
            <MarkdownContent source={messageDisplayContent(message)} streaming={streaming(message)} />
          {/if}
        </div>

        {#if message.send_error && message.retry_scope && message.retry_key}
          <button
            type="button"
            class="retry-send-button"
            onclick={() =>
              conversationState.onRetry(String(message.retry_scope), String(message.retry_key))}
          >
            Retry
          </button>
        {/if}

        {#if message.pending_delete_key}
          <div class="pending-message-controls" aria-label="Queued message actions">
            <button
              type="button"
              class="pending-message-button edit-pending-button"
              aria-label="Edit queued message"
              title="Edit queued message"
              disabled={deleting}
              onclick={() => conversationState.onEdit(String(message.pending_delete_key))}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="m4 20 4.2-1 10.9-10.9a2.1 2.1 0 0 0-3-3L5.2 16 4 20Zm10.6-13.4 3 3"></path>
              </svg>
            </button>
            {#if message.pending_bump_key}
              <button
                type="button"
                class="pending-message-button bump-pending-button"
                aria-label="Send queued message next"
                title="Send queued message next"
                disabled={deleting}
                onclick={() => conversationState.onBump(String(message.pending_bump_key))}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path d="M12 19V5m-6 6 6-6 6 6"></path>
                </svg>
              </button>
            {/if}
            <button
              type="button"
              class="pending-message-button delete-pending-button"
              aria-label="Delete queued message"
              title="Delete queued message"
              disabled={deleting}
              aria-busy={deleting ? "true" : undefined}
              onclick={() => conversationState.onDelete(String(message.pending_delete_key))}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5"></path>
              </svg>
            </button>
          </div>
        {/if}

        {#if streaming(message)}
          <div class="streaming-indicator">
            <span class="streaming-dots"><i></i><i></i><i></i></span>
            {message.pending_activity_label || "writing"}
          </div>
        {/if}

        <time
          class="message-timestamp"
          datetime={value.iso}
          data-message-at={value.millis ?? undefined}
        >
          <span class="message-clock">{value.text}</span>
          {#if value.age}<span class="message-age"> · {value.age}</span>{/if}
        </time>
      </div>
    </section>
  {/each}
</div>

<dialog
  {@attach dialogVisibility(() => actionsOpen, () => true, closeActions)}
  class="pending-message-actions"
  aria-labelledby="pendingMessageActionsTitle"
  onclick={(event) => {
    if (event.target === event.currentTarget) closeActions();
  }}
>
  <div class="pending-message-actions-shell">
    <div id="pendingMessageActionsTitle" class="pending-message-actions-title">Pending message</div>
    {#if actionsCanBump}
      <button type="button" class="pending-message-action" onclick={bumpPending}>
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M12 19V5m-6 6 6-6 6 6"></path>
        </svg>
        <span>Send next</span>
      </button>
    {/if}
    <button type="button" class="pending-message-action" onclick={editPending}>
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="m4 20 4.2-1 10.9-10.9a2.1 2.1 0 0 0-3-3L5.2 16 4 20Zm10.6-13.4 3 3"></path>
      </svg>
      <span>Edit message</span>
    </button>
    <button type="button" class="pending-message-action danger" onclick={deletePending}>
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5"></path>
      </svg>
      <span>Delete message</span>
    </button>
    <button type="button" class="pending-message-action cancel" onclick={closeActions}>
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M6 6l12 12M18 6 6 18"></path>
      </svg>
      <span>Cancel</span>
    </button>
  </div>
</dialog>
