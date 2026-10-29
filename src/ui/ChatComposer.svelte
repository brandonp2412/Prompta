<script lang="ts">
  import { onMount } from "svelte";

  type ImageRef = { ref: string; name: string; url: string };
  type SendResult = { ok: boolean; message: string; ambiguous?: boolean };

  let { mode, chatId, onSend, onNewChat, disabled = false, sendDisabled = false, sendHint = "", restoreDraft = "", retryablePreflight = false }: {
    mode: "fresh" | "reply";
    chatId?: string;
    onSend: (text: string, images: string[]) => Promise<SendResult>;
    onNewChat: () => void;
    disabled?: boolean;
    sendDisabled?: boolean;
    sendHint?: string;
    restoreDraft?: string;
    retryablePreflight?: boolean;
  } = $props();

  let draft = $state("");
  let restoredDraft = $state("");
  let restoredPreflight = $state(false);
  let hydrated = $state(false);
  let images = $state<ImageRef[]>([]);
  let uploading = $state(false);
  let sending = $state(false);
  let locked = $state(false);
  let feedback = $state("");
  let dragging = $state(false);
  let textarea = $state<HTMLTextAreaElement>();
  let fileInput = $state<HTMLInputElement>();
  const newChatDraftKey = "prompta.new-chat-draft.v1";
  const draftStorageKey = $derived(mode === "fresh" ? newChatDraftKey : chatId ? "prompta.reply-draft.v1." + chatId : "");
  const canAttach = $derived(mode === "fresh" && !disabled && !locked && !sending && !uploading);
  const hasDraft = $derived(!!draft.trim());
  const canSend = $derived(!disabled && !sendDisabled && !locked && !sending && !uploading && hasDraft);

  $effect(() => {
    if (mode !== "reply" || !restoreDraft || !hydrated) return;
    // Saved reply intents are immutable. Hydrate them only when the server
    // changes the intent/status, never on each keystroke in this composer.
    if (restoredDraft === restoreDraft && restoredPreflight === retryablePreflight) return;
    restoredDraft = restoreDraft;
    restoredPreflight = retryablePreflight;
    if (!sending && draft !== restoreDraft) {
      draft = restoreDraft;
      try { if (draftStorageKey) localStorage.setItem(draftStorageKey, draft); } catch { /* In-memory editing still works. */ }
      requestAnimationFrame(resizeTextarea);
    }
  });

  onMount(() => {
    try { if (draftStorageKey) draft = localStorage.getItem(draftStorageKey)?.slice(0, 32000) ?? ""; } catch { /* Storage may be unavailable. */ }
    hydrated = true;
    if (mode === "fresh") textarea?.focus();
    requestAnimationFrame(resizeTextarea);
    window.addEventListener("resize", resizeTextarea);
    return () => window.removeEventListener("resize", resizeTextarea);
  });

  function resizeTextarea() {
    if (!textarea) return;
    textarea.style.height = "auto";
    const maxHeight = Number.parseFloat(getComputedStyle(textarea).maxHeight);
    const contentHeight = textarea.scrollHeight;
    textarea.style.height = Math.min(contentHeight, maxHeight) + "px";
    textarea.style.overflowY = contentHeight > maxHeight ? "auto" : "hidden";
  }

  function draftChanged(event: Event) {
    if (draftStorageKey) {
      try { localStorage.setItem(draftStorageKey, (event.currentTarget as HTMLTextAreaElement).value); } catch { /* In-memory editing still works. */ }
    }
    resizeTextarea();
  }

  async function addFiles(files: File[]) {
    if (!files.length) return;
    if (!canAttach) {
      feedback = mode === "reply" ? "Images can only be sent with fresh chats." : "Wait for the current upload.";
      return;
    }
    if (images.length + files.length > 4) {
      feedback = "At most four images per fresh chat.";
      return;
    }
    uploading = true;
    feedback = "";
    try {
      for (const file of files) {
        if (!["image/png", "image/jpeg", "image/gif", "image/webp"].includes(file.type)) {
          throw new Error("Only PNG, JPEG, GIF or WebP images are supported.");
        }
        if (file.size > 8 * 1024 * 1024) throw new Error("Images must be 8 MiB or smaller.");
        const data = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(new Error("Could not read image."));
          reader.onload = () => {
            const encoded = reader.result;
            if (typeof encoded !== "string" || !encoded.includes(",")) reject(new Error("Could not encode image."));
            else resolve(encoded.slice(encoded.indexOf(",") + 1));
          };
          reader.readAsDataURL(file);
        });
        const response = await fetch("./api/images", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name: file.name, data }),
        });
        if (!response.ok) throw new Error("Image upload failed.");
        const result = await response.json() as { image?: ImageRef };
        if (!result.image?.ref || !result.image.url.startsWith("./api/images/")) {
          throw new Error("Image upload receipt was invalid.");
        }
        images = [...images, result.image];
      }
    } catch (error) {
      feedback = error instanceof Error ? error.message : "Image upload failed.";
    } finally {
      uploading = false;
    }
  }

  async function submit() {
    if (!canSend) return;
    sending = true;
    feedback = "";
    try {
      const submitted = draft;
      const result = await onSend(submitted, images.map((image) => image.ref));
      if (result.ok) {
        draft = "";
        images = [];
        feedback = result.message;
        try { if (draftStorageKey) localStorage.removeItem(draftStorageKey); } catch { /* Storage may be unavailable. */ }
        requestAnimationFrame(resizeTextarea);
      } else {
        feedback = result.message;
        locked = !!result.ambiguous;
      }
    } catch {
      locked = true;
      feedback = "Send confirmation was lost. Check local Chats before making a separate new request; this draft will not retry.";
    } finally {
      sending = false;
    }
  }

  function keydown(event: KeyboardEvent) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      void submit();
    }
  }

  function pasted(event: ClipboardEvent) {
    const files = Array.from(event.clipboardData?.files || []);
    if (!files.length) return;
    if (!event.clipboardData?.getData("text/plain")) event.preventDefault();
    void addFiles(files);
  }

  function dropped(event: DragEvent) {
    event.preventDefault();
    dragging = false;
    void addFiles(Array.from(event.dataTransfer?.files || []));
  }
</script>

<form class:dragging class="chat-composer-wrap" aria-label={mode === "fresh" ? "New chat composer" : "Reply composer"}
  onsubmit={(event) => { event.preventDefault(); void submit(); }}
  ondragover={(event) => { event.preventDefault(); dragging = mode === "fresh"; }}
  ondragleave={() => dragging = false}
  ondrop={dropped}>
  <div class="chat-composer">
    {#if images.length}
      <div class="composer-previews" aria-label="Images to attach">
        {#each images as image (image.ref)}
          <div class="composer-preview">
            <img src={image.url} alt={image.name} />
            <button type="button" aria-label={"Remove " + image.name} disabled={!canAttach}
              onclick={() => images = images.filter((item) => item.ref !== image.ref)}>×</button>
          </div>
        {/each}
      </div>
    {/if}
    <textarea bind:this={textarea} bind:value={draft} oninput={draftChanged} onkeydown={keydown} onpaste={pasted}
      rows="1" maxlength="32000" disabled={disabled || locked || sending}
      aria-label={mode === "fresh" ? "Message for new chat" : "Message for current chat"}
      placeholder="Message Prompta…"></textarea>
    <div class="composer-actions">
      <div class="composer-attach">
        {#if mode === "fresh"}
          <button type="button" aria-label="Attach images" title="Attach images" disabled={!canAttach}
            onclick={() => fileInput?.click()}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m20.5 11.5-8.7 8.7a5.5 5.5 0 0 1-7.8-7.8l9.4-9.4a3.7 3.7 0 0 1 5.2 5.2l-9.4 9.4a1.9 1.9 0 0 1-2.7-2.7l8.6-8.6" /></svg>
            <span>{images.length ? `Add images (${images.length}/4)` : "Attach images"}</span>
          </button>
          <input bind:this={fileInput} type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple
            aria-label="Choose images" disabled={!canAttach}
            onchange={(event) => {
              void addFiles(Array.from(event.currentTarget.files || []));
              event.currentTarget.value = "";
            }} />
        {/if}
        {#if uploading}<small role="status">Uploading images…</small>{/if}
      </div>
      {#if !hasDraft && !sending}
        <button class="composer-send composer-new-chat" type="button" onclick={onNewChat}
          aria-label="New chat" title="New chat">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 4l4 4M9 15l3.5-.7L21 5.8a2.1 2.1 0 0 0-3-3l-8.5 8.5L9 15Z" /></svg>
        </button>
      {:else}
        <button class="composer-send" type="submit" disabled={!canSend}
          aria-label={sending ? "Sending" : mode === "fresh" ? "Send fresh chat" : "Send reply"}>
          {sending ? "Sending…" : "↑"}
        </button>
      {/if}
    </div>
  </div>
  {#if feedback}<p class:composer-error={locked} class="composer-feedback" role="status">{feedback}</p>{/if}
  {#if sendHint && !feedback}<p class="composer-hint" role="status">{sendHint}</p>{/if}
</form>
