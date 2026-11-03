import type React from "react";
import { signal, computed, effect, batch } from "@preact/signals-react";
import { untracked as untrack } from "@preact/signals-core";
import {
  clearComposerDraft,
  clearComposerImages,
  composerEditRevision,
  readComposerDraft,
  readComposerImages,
  rememberComposerDraft,
  rememberComposerImages,
  validImage,
} from "./composerDraftMemory";
import type { ComposerImageRef } from "./composerDraftMemory";
import { localPost, localRejectionDetail, localUploadTimeoutMs } from "./localMutation";
import { attachmentSelectionError, isVideoAttachment } from "./mediaAttachments";
export type SendResult = {
  ok: boolean;
  message: string;
  ambiguous?: boolean;
  fallbackAvailable?: boolean;
};
export type Props = {
  mode: "fresh" | "reply";
  chatId?: string;
  onSend: (text: string, images: string[]) => Promise<SendResult>;
  onFallbackSend?: (text: string, images: string[]) => Promise<SendResult>;
  onNewChat: () => void;
  onStop?: () => void | Promise<void>;
  active?: boolean;
  stopping?: boolean;
  disabled?: boolean;
  sendDisabled?: boolean;
  restoreDraft?: string;
  retryablePreflight?: boolean;
  offerFreshContinuation?: boolean;
};
export function createChatComposerController(initialProps: Props) {
  type ImageRef = ComposerImageRef;

  const mode = signal(initialProps.mode);
  const chatId = signal(initialProps.chatId);
  const onSend = signal(initialProps.onSend);
  const onFallbackSend = signal(initialProps.onFallbackSend);
  const onNewChat = signal(initialProps.onNewChat);
  const onStop = signal(initialProps.onStop);
  const active = signal(initialProps.active);
  const stopping = signal(initialProps.stopping);
  const disabled = signal(initialProps.disabled);
  const sendDisabled = signal(initialProps.sendDisabled);
  const restoreDraft = signal(initialProps.restoreDraft);
  const retryablePreflight = signal(initialProps.retryablePreflight);
  const offerFreshContinuation = signal(initialProps.offerFreshContinuation);

  let draft = signal("");
  let restoredDraft = signal("");
  let restoredPreflight = signal(false);
  let hydrated = signal(false);
  let hydratedKey = "";
  let hasLocalDraft = signal(false);
  let images = signal<ImageRef[]>([]);
  let uploading = signal(false);
  let uploadGeneration = 0;
  let uploadAbort: AbortController | null = null;
  let sending = signal(false);
  // A late acknowledgment belongs to the composer selection that submitted it.
  // Switching away and back must not erase a newer draft or unlock another send.
  let submissionGeneration = 0;
  let feedback = signal("");
  let fallbackAvailable = signal(false);
  let dragging = signal(false);
  let textarea = signal<HTMLTextAreaElement>();
  let fileInput = signal<HTMLInputElement>();
  const newChatDraftKey = "prompta.new-chat-draft.v1";
  const draftStorageKey = computed(() => {
    if (mode.value === "fresh") return newChatDraftKey;
    return chatId.value ? "prompta.reply-draft.v1." + chatId.value : "";
  });
  const canAttach = computed(
    () => mode.value === "fresh" && !disabled.value && !sending.value && !uploading.value,
  );
  const hasDraft = computed(() => !!draft.value.trim());
  const showStop = computed(
    () =>
      mode.value === "reply" &&
      !!active.value &&
      !hasDraft.value &&
      !sending.value &&
      !uploading.value,
  );
  const canSend = computed(
    () =>
      !disabled.value &&
      !sendDisabled.value &&
      !sending.value &&
      !uploading.value &&
      hasDraft.value,
  );
  const canFallback = computed(
    () =>
      mode.value === "reply" &&
      !disabled.value &&
      !sending.value &&
      !uploading.value &&
      hasDraft.value &&
      (fallbackAvailable.value || offerFreshContinuation.value) &&
      !!onFallbackSend.value,
  );

  function resizeTextarea() {
    fitTextarea();
  }

  function fitTextarea(animateCollapse = false) {
    if (!textarea.value) return;
    textarea.value.getAnimations().forEach((animation) => animation.cancel());
    const previousHeight = textarea.value.getBoundingClientRect().height;
    textarea.value.style.height = "auto";
    const maxHeight = Number.parseFloat(getComputedStyle(textarea.value).maxHeight);
    const contentHeight = textarea.value.scrollHeight;
    const nextHeight = Number.isFinite(maxHeight)
      ? Math.min(contentHeight, maxHeight)
      : contentHeight;
    textarea.value.style.height = nextHeight + "px";
    textarea.value.style.overflowY =
      Number.isFinite(maxHeight) && contentHeight > maxHeight ? "auto" : "hidden";
    // The transcript grows as the composer shrinks. Ease that movement after
    // a successful send without delaying textarea growth while typing.
    if (
      animateCollapse &&
      previousHeight > nextHeight &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      textarea.value.animate([{ height: previousHeight + "px" }, { height: nextHeight + "px" }], {
        duration: 160,
        easing: "ease-out",
      });
    }
  }

  function setDraft(value: string) {
    draft.value = value;
    hasLocalDraft.value = true;
    fallbackAvailable.value = false;
    if (draftStorageKey.value) {
      rememberComposerDraft(draftStorageKey.value, value);
      try {
        localStorage.setItem(draftStorageKey.value, value);
      } catch {
        /* In-memory editing still works. */
      }
    }
    resizeTextarea();
  }

  function draftChanged(event: React.FormEvent<HTMLTextAreaElement>) {
    setDraft(event.currentTarget.value);
  }

  async function addFiles(files: File[]) {
    if (!files.length) return;
    if (!canAttach.value) {
      feedback.value =
        mode.value === "reply"
          ? "Attachments can only be sent with fresh chats."
          : "Wait for the current upload.";
      return;
    }
    const invalid = attachmentSelectionError(files, images.value.length, "fresh chat");
    if (invalid) {
      feedback.value = invalid;
      return;
    }
    const key = draftStorageKey.value;
    const generation = ++uploadGeneration;
    const batchRefs: string[] = [];
    const controller = new AbortController();
    uploadAbort = controller;
    uploading.value = true;
    feedback.value = "";
    try {
      for (const file of files) {
        const data = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(new Error("Could not read attachment."));
          reader.onload = () => {
            const encoded = reader.result;
            if (typeof encoded !== "string" || !encoded.includes(","))
              reject(new Error("Could not encode attachment."));
            else resolve(encoded.slice(encoded.indexOf(",") + 1));
          };
          reader.readAsDataURL(file);
        });
        if (generation !== uploadGeneration || key !== draftStorageKey.value) return;
        const response = await localPost(
          isVideoAttachment(file.name) ? "./api/videos" : "./api/images",
          { name: file.name, data },
          {
            signal: controller.signal,
            timeoutMs: localUploadTimeoutMs,
          },
        );
        if (generation !== uploadGeneration || key !== draftStorageKey.value) return;
        if (!response.ok)
          throw new Error(await localRejectionDetail(response, "Attachment upload failed."));
        const result: unknown = await response.json();
        const image =
          result && typeof result === "object" && "image" in result ? result.image : null;
        if (!validImage(image)) throw new Error("Attachment upload receipt was invalid.");
        if (!images.value.some((item) => item.ref === image.ref)) {
          images.value = [...images.value, image];
          batchRefs.push(image.ref);
          rememberComposerImages(key, images.value);
        }
      }
    } catch (error) {
      if (generation === uploadGeneration && key === draftStorageKey.value) {
        // Roll back this batch if a later file fails; retain older attachments.
        images.value = images.value.filter((image) => !batchRefs.includes(image.ref));
        rememberComposerImages(key, images.value);
        if (error instanceof DOMException && error.name === "TimeoutError")
          feedback.value = "Attachment upload timed out. Reattach any images that did not upload.";
        else if (error instanceof Error) feedback.value = error.message;
        else feedback.value = "Attachment upload failed.";
      }
    } finally {
      if (generation === uploadGeneration && key === draftStorageKey.value) {
        uploadAbort = null;
        uploading.value = false;
      }
    }
  }

  async function submit(useFallback = false) {
    if (useFallback ? !canFallback.value : !canSend.value) return;
    if (mode.value === "reply" && !useFallback) {
      // A reply click is consent to queue and revive its branch. Free the
      // composer synchronously; branch verification and delivery are worker
      // concerns, not a pending send-button state.
      const submittedKey = draftStorageKey.value;
      const submitted = draft.value;
      const send = onSend.value;
      clearComposerDraft(submittedKey);
      clearComposerImages(submittedKey);
      try {
        if (submittedKey && localStorage.getItem(submittedKey) === submitted)
          localStorage.removeItem(submittedKey);
      } catch {
        /* Storage may be unavailable. */
      }
      draft.value = "";
      images.value = [];
      hasLocalDraft.value = false;
      feedback.value = "";
      fallbackAvailable.value = false;
      requestAnimationFrame(() => fitTextarea(true));
      const restore = (reason: string, fallback = false) => {
        // The POST may have failed before SQLite accepted it. Never drop the
        // text, even if another draft was composed in the meantime.
        const current = readComposerDraft(submittedKey) ?? "";
        const restored = current ? submitted + "\n\n" + current : submitted;
        rememberComposerDraft(submittedKey, restored);
        if (draftStorageKey.value === submittedKey) {
          draft.value = restored;
          hasLocalDraft.value = true;
          fallbackAvailable.value = fallback;
          feedback.value = reason;
          requestAnimationFrame(resizeTextarea);
        }
        try {
          if (submittedKey) localStorage.setItem(submittedKey, restored);
        } catch {
          /* Retained in memory when persistent storage is blocked. */
        }
      };
      try {
        const result = await send(submitted, []);
        if (!result.ok) restore(result.message, Boolean(result.fallbackAvailable));
      } catch {
        restore("Queue confirmation was lost. Your message was restored for safe reconciliation.");
      }
      return;
    }
    const submittedKey = draftStorageKey.value;
    const generation = ++submissionGeneration;
    const submitted = draft.value;
    const submittedImages = images.value.map((image) => image.ref);
    const submittedEditRevision = composerEditRevision(submittedKey);
    sending.value = true;
    feedback.value = "";
    try {
      const send = useFallback && onFallbackSend.value ? onFallbackSend.value : onSend.value;
      const result = await send(submitted, submittedImages);
      const current = generation === submissionGeneration && draftStorageKey.value === submittedKey;
      if (result.ok && !current) {
        // A successful fresh send normally navigates to its new chat before
        // the promise resolves. Clear only an unchanged draft from the old
        // selection; never touch the newly selected composer.
        if (
          draftStorageKey.value !== submittedKey &&
          readComposerDraft(submittedKey) === submitted &&
          composerEditRevision(submittedKey) === submittedEditRevision &&
          readComposerImages(submittedKey).length === submittedImages.length &&
          readComposerImages(submittedKey).every(
            (image, index) => image.ref === submittedImages[index],
          )
        ) {
          clearComposerImages(submittedKey);
          clearComposerDraft(submittedKey);
          try {
            if (localStorage.getItem(submittedKey) === submitted)
              localStorage.removeItem(submittedKey);
          } catch {
            /* Storage may be unavailable. */
          }
        }
        return;
      }
      if (!current) return;
      if (result.ok) {
        // The textarea is read-only during this send; a newer edit or route
        // navigation wins if a state transition happened while waiting.
        if (draft.value !== submitted) {
          feedback.value = "Message accepted. Your newer draft was kept.";
          return;
        }
        clearComposerImages(submittedKey);
        clearComposerDraft(submittedKey);
        try {
          if (submittedKey && localStorage.getItem(submittedKey) === submitted)
            localStorage.removeItem(submittedKey);
        } catch {
          /* Storage may be unavailable. */
        }
        draft.value = "";
        images.value = [];
        feedback.value = result.message;
        hasLocalDraft.value = false;
        fallbackAvailable.value = false;
        requestAnimationFrame(() => fitTextarea(true));
      } else {
        feedback.value = result.message;
        fallbackAvailable.value = Boolean(result.fallbackAvailable);
      }
    } catch (error) {
      if (generation === submissionGeneration && draftStorageKey.value === submittedKey) {
        // Receipt-ledger validation fails before any HTTP send. Explain that
        // the saved IDs need recovery instead of calling it a lost acknowledgment.
        const message = error instanceof Error ? error.message : "";
        feedback.value =
          message.startsWith("Unresolved chat receipts") ||
          message.startsWith("Unresolved reply receipts") ||
          message.startsWith("Unresolved chat requests") ||
          message.startsWith("Unresolved reply receipts are at capacity")
            ? message
            : "Send confirmation was lost. The draft is saved; press Send again to reconcile this request.";
      }
    } finally {
      if (generation === submissionGeneration && draftStorageKey.value === submittedKey)
        sending.value = false;
    }
  }

  async function stop() {
    if (!showStop.value || stopping.value || disabled.value) return;
    await onStop.value?.();
  }

  function keydown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (showStop.value) void stop();
      else void submit();
    }
  }

  function pasted(event: React.ClipboardEvent<HTMLTextAreaElement>) {
    const files = Array.from(event.clipboardData?.files || []);
    if (!files.length) return;
    if (!event.clipboardData?.getData("text/plain")) event.preventDefault();
    void addFiles(files);
  }

  function dropped(event: React.DragEvent<HTMLFormElement>) {
    event.preventDefault();
    dragging.value = false;
    void addFiles(Array.from(event.dataTransfer?.files || []));
  }

  const onMountImpl = () => {
    window.addEventListener("resize", resizeTextarea);
    return () => {
      window.removeEventListener("resize", resizeTextarea);
      uploadGeneration += 1;
      uploadAbort?.abort();
      uploadAbort = null;
    };
  };
  function mount() {
    const cleanup = onMountImpl();
    const disposers = [
      effect(() => {
        const key = draftStorageKey.value;
        untrack(() => {
          if (key === hydratedKey) return;
          hydratedKey = key;
          submissionGeneration += 1;
          // An upload started for an old chat must never attach its late receipt
          // to the composer after a route/mode change.
          uploadGeneration += 1;
          uploadAbort?.abort();
          uploadAbort = null;
          uploading.value = false;
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
            } catch {
              /* Storage may be unavailable. */
            }
          }
          draft.value = saved;
          hasLocalDraft.value = found;
          images.value = readComposerImages(key);
          feedback.value = "";
          fallbackAvailable.value = false;
          restoredDraft.value = "";
          restoredPreflight.value = false;
          sending.value = false;
          hydrated.value = true;
        });
      }),
      effect(() => {
        if (mode.value !== "reply" || !restoreDraft.value || !hydrated.value) return;
        // Saved reply intents are immutable. Hydrate them only when the server
        // changes the intent/status, never on each keystroke in this composer.
        if (
          restoredDraft.value === restoreDraft.value &&
          restoredPreflight.value === retryablePreflight.value
        )
          return;
        restoredDraft.value = restoreDraft.value;
        restoredPreflight.value = Boolean(retryablePreflight.value);
        if (!sending.value && !hasLocalDraft.value) {
          draft.value = restoreDraft.value;
          hasLocalDraft.value = true;
          rememberComposerDraft(draftStorageKey.value, draft.value);
          try {
            if (draftStorageKey.value) localStorage.setItem(draftStorageKey.value, draft.value);
          } catch {
            /* In-memory editing still works. */
          }
        }
      }),
    ];
    return () => {
      for (const dispose of disposers) dispose();
      if (typeof cleanup === "function") cleanup();
    };
  }
  function syncProps(next: Props) {
    batch(() => {
      if (mode.peek() !== next.mode) mode.value = next.mode;
      if (chatId.peek() !== next.chatId) chatId.value = next.chatId;
      if (onSend.peek() !== next.onSend) onSend.value = next.onSend;
      if (onFallbackSend.peek() !== next.onFallbackSend) onFallbackSend.value = next.onFallbackSend;
      if (onNewChat.peek() !== next.onNewChat) onNewChat.value = next.onNewChat;
      if (onStop.peek() !== next.onStop) onStop.value = next.onStop;
      if (active.peek() !== next.active) active.value = next.active;
      if (stopping.peek() !== next.stopping) stopping.value = next.stopping;
      if (disabled.peek() !== next.disabled) disabled.value = next.disabled;
      if (sendDisabled.peek() !== next.sendDisabled) sendDisabled.value = next.sendDisabled;
      if (restoreDraft.peek() !== next.restoreDraft) restoreDraft.value = next.restoreDraft;
      if (retryablePreflight.peek() !== next.retryablePreflight)
        retryablePreflight.value = next.retryablePreflight;
      if (offerFreshContinuation.peek() !== next.offerFreshContinuation)
        offerFreshContinuation.value = next.offerFreshContinuation;
    });
  }
  return {
    mode,
    showStop,
    stopping,
    onFallbackSend,
    onNewChat,
    disabled,
    draft,
    images,
    uploading,
    sending,
    feedback,
    fallbackAvailable,
    offerFreshContinuation,
    dragging,
    textarea,
    fileInput,
    draftStorageKey,
    canAttach,
    hasDraft,
    canSend,
    canFallback,
    setDraft,
    draftChanged,
    addFiles,
    stop,
    submit,
    keydown,
    pasted,
    dropped,
    mount,
    resizeTextarea,
    syncProps,
  };
}
