<script lang="ts">
  import { onMount, untrack } from "svelte";
  import { clearComposerDraft, clearComposerImages, readComposerDraft, readComposerImages, rememberComposerDraft, rememberComposerImages } from "./composerDraftMemory";
  import type { ComposerImageRef } from "./composerDraftMemory";
  import { localPost, localUploadTimeoutMs } from "./localMutation";

  type ImageRef = ComposerImageRef;
  type SendResult = { ok: boolean; message: string; ambiguous?: boolean; fallbackAvailable?: boolean };

  let { mode, chatId, onSend, onFallbackSend, onNewChat, disabled = false, sendDisabled = false, restoreDraft = "", retryablePreflight = false }: {
    mode: "fresh" | "reply";
    chatId?: string;
    onSend: (text: string, images: string[]) => Promise<SendResult>;
    onFallbackSend?: (text: string, images: string[]) => Promise<SendResult>;
    onNewChat: () => void;
    disabled?: boolean;
    sendDisabled?: boolean;
    restoreDraft?: string;
    retryablePreflight?: boolean;
  } = $props();

  let draft = $state("");
  let restoredDraft = $state("");
  let restoredPreflight = $state(false);
  let hydrated = $state(false);
  let hydratedKey = "";
  let hasLocalDraft = $state(false);
  let images = $state<ImageRef[]>([]);
  let uploading = $state(false);
  let uploadGeneration = 0;
  let uploadAbort: AbortController | null = null;
  let sending = $state(false);
  let feedback = $state("");
  let fallbackAvailable = $state(false);
  let dragging = $state(false);
  let textarea = $state<HTMLTextAreaElement>();
  let fileInput = $state<HTMLInputElement>();
  const newChatDraftKey = "prompta.new-chat-draft.v1";
  const draftStorageKey = $derived(mode === "fresh" ? newChatDraftKey : chatId ? "prompta.reply-draft.v1." + chatId : "");
  const canAttach = $derived(mode === "fresh" && !disabled && !sending && !uploading);
  const hasDraft = $derived(!!draft.trim());
  const canSend = $derived(!disabled && !sendDisabled && !sending && !uploading && hasDraft);

  $effect(() => {
    const key = draftStorageKey;
    untrack(() => {
      if (key === hydratedKey) return;
      hydratedKey = key;
      // An upload started for an old chat must never attach its late receipt
      // to the composer after a route/mode change.
      uploadGeneration += 1;
      uploadAbort?.abort();
      uploadAbort = null;
      uploading = false;
      // Memory wins over readable-but-unwritable storage with stale values.
      let saved = key ? readComposerDraft(key) || "" : "";
      let found = !!key && readComposerDraft(key) !== undefined;
      if (!found) {
        try {
          const cached = key ? localStorage.getItem(key) : null;
          if (cached !== null) {
            saved = cached.slice(0, 32000);
            found = true;
            rememberComposerDraft(key, saved);
          }
        } catch { /* Storage may be unavailable. */ }
      }
      draft = saved;
      hasLocalDraft = found;
      images = readComposerImages(key);
      feedback = "";
      fallbackAvailable = false;
      restoredDraft = "";
      restoredPreflight = false;
      sending = false;
      hydrated = true;
      // Keep the composer height stable when switching between saved replies.
      // Long drafts remain scrollable and grow once the user edits them.
    });
  });

  $effect(() => {
    if (mode !== "reply" || !restoreDraft || !hydrated) return;
    // Saved reply intents are immutable. Hydrate them only when the server
    // changes the intent/status, never on each keystroke in this composer.
    if (restoredDraft === restoreDraft && restoredPreflight === retryablePreflight) return;
    restoredDraft = restoreDraft;
    restoredPreflight = retryablePreflight;
    if (!sending && !hasLocalDraft) {
      draft = restoreDraft;
      hasLocalDraft = true;
      rememberComposerDraft(draftStorageKey, draft);
      try { if (draftStorageKey) localStorage.setItem(draftStorageKey, draft); } catch { /* In-memory editing still works. */ }
      // A restored failed send must not resize the surrounding transcript.
    }
  });

  onMount(() => {
    if (mode === "fresh") textarea?.focus();
    requestAnimationFrame(resizeTextarea);
    window.addEventListener("resize", resizeTextarea);
    return () => {
      window.removeEventListener("resize", resizeTextarea);
      uploadGeneration += 1;
      uploadAbort?.abort();
      uploadAbort = null;
    };
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
    hasLocalDraft = true;
    fallbackAvailable = false;
    if (draftStorageKey) {
      rememberComposerDraft(draftStorageKey, (event.currentTarget as HTMLTextAreaElement).value);
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
    // Validate the entire selection first: an invalid later file must not
    // leave an unexpected partial batch of attachments.
    if (files.some((file) => !["image/png", "image/jpeg", "image/gif", "image/webp"].includes(file.type))) {
      feedback = "Only PNG, JPEG, GIF or WebP images are supported.";
      return;
    }
    if (files.some((file) => file.size > 8 * 1024 * 1024)) {
      feedback = "Images must be 8 MiB or smaller.";
      return;
    }
    const key = draftStorageKey;
    const generation = ++uploadGeneration;
    const batchRefs: string[] = [];
    const controller = new AbortController();
    uploadAbort = controller;
    uploading = true;
    feedback = "";
    try {
      for (const file of files) {
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
        if (generation !== uploadGeneration || key !== draftStorageKey) return;
        const response = await localPost("./api/images", { name: file.name, data }, {
          signal: controller.signal, timeoutMs: localUploadTimeoutMs,
        });
        if (generation !== uploadGeneration || key !== draftStorageKey) return;
        if (!response.ok) throw new Error("Image upload failed.");
        const result = await response.json() as { image?: ImageRef };
        if (!result.image?.ref || !result.image.url.startsWith("./api/images/")) {
          throw new Error("Image upload receipt was invalid.");
        }
        // A content-addressed image may have been selected more than once.
        if (!images.some((image) => image.ref === result.image?.ref)) {
          images = [...images, result.image];
          batchRefs.push(result.image.ref);
          rememberComposerImages(key, images);
        }
      }
    } catch (error) {
      if (generation === uploadGeneration && key === draftStorageKey) {
        // Roll back this batch if a later file fails; retain older attachments.
        images = images.filter((image) => !batchRefs.includes(image.ref));
        rememberComposerImages(key, images);
        feedback = error instanceof DOMException && error.name === "TimeoutError"
          ? "Image upload timed out. The unsent attachments were restored; try again."
          : error instanceof Error ? error.message : "Image upload failed.";
      }
    } finally {
      if (generation === uploadGeneration && key === draftStorageKey) {
        uploadAbort = null;
        uploading = false;
      }
    }
  }

  async function submit(useFallback = false) {
    if (!canSend || (useFallback && (!fallbackAvailable || !onFallbackSend))) return;
    const submittedKey = draftStorageKey;
    sending = true;
    feedback = "";
    try {
      const submitted = draft;
      const send = useFallback && onFallbackSend ? onFallbackSend : onSend;
      const result = await send(submitted, images.map((image) => image.ref));
      if (draftStorageKey !== submittedKey) return;
      if (result.ok) {
        draft = "";
        images = [];
        clearComposerImages(submittedKey);
        feedback = result.message;
        clearComposerDraft(submittedKey);
        try { if (draftStorageKey) localStorage.removeItem(draftStorageKey); } catch { /* Storage may be unavailable. */ }
        hasLocalDraft = false;
        fallbackAvailable = false;
        requestAnimationFrame(resizeTextarea);
      } else {
        feedback = result.message;
        fallbackAvailable = Boolean(result.fallbackAvailable);
      }
    } catch (error) {
      if (draftStorageKey === submittedKey) {
        // Receipt-ledger validation fails before any HTTP send. Explain that
        // the saved IDs need recovery instead of calling it a lost acknowledgment.
        const message = error instanceof Error ? error.message : "";
        feedback = message.startsWith("Unresolved chat receipts") ||
          message.startsWith("Unresolved reply receipts") ||
          message.startsWith("Unresolved chat requests") ||
          message.startsWith("Unresolved reply receipts are at capacity")
          ? message
          : "Send confirmation was lost. The draft is saved; press Send again to reconcile this request.";
      }
    } finally {
      if (draftStorageKey === submittedKey) sending = false;
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
              onclick={() => { images = images.filter((item) => item.ref !== image.ref); rememberComposerImages(draftStorageKey, images); }}>×</button>
          </div>
        {/each}
      </div>
    {/if}
    <textarea bind:this={textarea} bind:value={draft} oninput={draftChanged} onkeydown={keydown} onpaste={pasted}
      rows="1" maxlength="32000" disabled={disabled || sending}
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
      {#if !hasDraft && images.length === 0 && !uploading && !sending}
        <button class="composer-send composer-new-chat" type="button" disabled={disabled || uploading} onclick={onNewChat}
          aria-label="New chat" title="New chat">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M16 4l4 4M9 15l3.5-.7L21 5.8a2.1 2.1 0 0 0-3-3l-8.5 8.5L9 15Z" /></svg>
        </button>
      {:else}
        <button class="composer-send" type="submit" disabled={!canSend}
          aria-label={sending ? "Sending" : mode === "fresh" ? "Send fresh chat" : "Send reply"}>
          {#if sending}
            <svg class="composer-send-spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 1-9 9" /></svg>
          {:else}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
          {/if}
        </button>
      {/if}
    </div>
  </div>
  {#if feedback}
    <p class="composer-feedback" role="status">{feedback}</p>
  {/if}
  {#if fallbackAvailable && onFallbackSend && hasDraft}
    <button type="button" class="composer-fallback" disabled={sending} onclick={() => void submit(true)}>Continue in new chat</button>
  {/if}
</form>
