<script lang="ts">
  import { onMount } from "svelte";

  type ImageRef = { ref: string; name: string; url: string };
  type SendResult = { ok: boolean; message: string; ambiguous?: boolean };

  let { mode, onSend, disabled = false, sendDisabled = false, restoreDraft = "" }: {
    mode: "fresh" | "reply";
    onSend: (text: string, images: string[]) => Promise<SendResult>;
    disabled?: boolean;
    sendDisabled?: boolean;
    restoreDraft?: string;
  } = $props();

  let draft = $state("");
  let restoredDraft = $state("");
  let lastSubmitted = $state("");
  let images = $state<ImageRef[]>([]);
  let uploading = $state(false);
  let sending = $state(false);
  let locked = $state(false);
  let feedback = $state("");
  let dragging = $state(false);
  let textarea = $state<HTMLTextAreaElement>();
  let fileInput = $state<HTMLInputElement>();
  const newChatDraftKey = "prompta.new-chat-draft.v1";
  const canAttach = $derived(mode === "fresh" && !disabled && !locked && !sending && !uploading);
  const canSend = $derived(!disabled && !sendDisabled && !locked && !sending && !uploading && !!draft.trim());

  $effect(() => {
    if (mode !== "reply" || !restoreDraft || restoredDraft === restoreDraft) return;
    restoredDraft = restoreDraft;
    // Restore a pending intent only on a later visit. Never refill the field
    // immediately after the user's original successful Send click.
    if (!draft && !sending && restoreDraft !== lastSubmitted) {
      draft = restoreDraft;
      requestAnimationFrame(resizeTextarea);
    }
  });

  onMount(() => {
    if (mode === "fresh") {
      try { draft = localStorage.getItem(newChatDraftKey)?.slice(0, 32000) ?? ""; } catch { /* Storage may be unavailable. */ }
      textarea?.focus();
    }
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
    if (mode === "fresh") {
      try { localStorage.setItem(newChatDraftKey, (event.currentTarget as HTMLTextAreaElement).value); } catch { /* In-memory editing still works. */ }
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
        lastSubmitted = submitted;
        draft = "";
        images = [];
        feedback = result.message;
        if (mode === "fresh") {
          try { localStorage.removeItem(newChatDraftKey); } catch { /* Storage may be unavailable. */ }
        }
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
      <button class="composer-send" type="submit" disabled={!canSend}
        aria-label={sending ? "Sending" : mode === "fresh" ? "Send fresh chat" : "Send reply"}>
        {sending ? "Sending…" : "↑"}
      </button>
    </div>
  </div>
  {#if feedback}<p class:composer-error={locked} class="composer-feedback" role="status">{feedback}</p>{/if}
</form>
