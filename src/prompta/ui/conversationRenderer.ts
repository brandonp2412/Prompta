import { formatClockTime12Hour, messageAgeText, messageTimestampMillis } from "./clientLogic";
import { renderMarkdown } from "./markdown";

function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);

  if (!element) throw new Error("Missing required conversation UI element: " + selector);

  return element;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setTextIfChanged(element: Element, value) {
  const text = String(value ?? "");

  if (element.textContent !== text) element.textContent = text;
}

export function canMorphPendingMessageNode(messageKey, role, sendError = false) {
  if (sendError) return false;

  if (role === "user") return String(messageKey).startsWith("pending-user-");

  return String(messageKey).startsWith("pending-activity-");
}

export function imageAttachments(message) {
  const attachments = Array.isArray(message?.attachments) ? message.attachments : [];

  return attachments.filter((attachment) => {
    if (!attachment || typeof attachment !== "object") return false;

    const type = String(attachment.type || "");
    const src = String(attachment.src || "");

    return type.startsWith("image/") && (Boolean(attachment.id) || src.startsWith("data:image/"));
  });
}

function imageAttachmentSrc(attachment) {
  const inline = String(attachment?.src || "");

  if (inline.startsWith("data:image/")) return inline;

  const id = String(attachment?.id || "");

  return id ? `api/attachment-previews/${encodeURIComponent(id)}` : "";
}

function renderMessageAttachments(message) {
  const images = imageAttachments(message);

  if (!images.length) return "";

  return `<div class="message-attachments">${images
    .map((attachment) => {
      const src = imageAttachmentSrc(attachment);
      const name = String(attachment.name || "Attached image");

      return `<img class="message-image-preview" src="${escapeHtml(src)}" alt="${escapeHtml(name)}" loading="lazy" decoding="async">`;
    })
    .join("")}</div>`;
}

export function pendingImageAttachments(serializedAttachments) {
  return serializedAttachments
    .filter((attachment) => String(attachment.type || "").startsWith("image/"))
    .map((attachment) => ({
      name: attachment.name,
      type: attachment.type,
      src: `data:${attachment.type};base64,${attachment.data}`,
    }));
}

export function shouldHandlePendingLongPress(pointerType: string, coarsePointer: boolean) {
  return pointerType !== "mouse" || coarsePointer;
}

export function pendingLongPressMoved(
  startX: number,
  startY: number,
  currentX: number,
  currentY: number,
  tolerance = 12,
) {
  return Math.hypot(currentX - startX, currentY - startY) > tolerance;
}

export function createConversationRenderer({ onRetry, onDelete, onEdit }) {
  const conversation = requiredElement<HTMLElement>("#conversation");
  const viewport = requiredElement<HTMLElement>("#conversationViewport");

  function messageTimestamp(message) {
    const millis = messageTimestampMillis(message.created_at, message.updated_at);

    if (millis === null) return { text: "Time unavailable", iso: "", millis: null, age: "" };

    const date = new Date(millis);
    const months = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sept",
      "Oct",
      "Nov",
      "Dec",
    ];
    const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

    return {
      text: `${date.getDate()} ${months[date.getMonth()]} ${weekdays[date.getDay()]} ${formatClockTime12Hour(date)}`,
      iso: date.toISOString(),
      millis,
      age: messageAgeText(millis),
    };
  }
  function renderMessageSection(message, allowStreaming = true) {
    const role = message.role === "user" ? "user" : "assistant";
    const streaming =
      Boolean(message.pending_activity) || (allowStreaming && message.status === "streaming");
    const activityLabel = message.pending_activity_label || "writing";
    const label = message.send_error ? "Send error" : "Prompta run";
    const timestamp = messageTimestamp(message);
    const contentHtml = message.pending_activity ? "" : renderMarkdown(message.content);
    const attachmentsHtml = message.pending_activity ? "" : renderMessageAttachments(message);

    return `
      <section class="message ${role}${message.send_error ? " send-error" : ""}">
        <div class="message-inner">
          ${
            role === "assistant"
              ? `
            <div class="message-label"><span class="assistant-avatar">${message.send_error ? "!" : "P"}</span> ${label}</div>
          `
              : ""
          }
          ${attachmentsHtml}
          <div class="message-content">${contentHtml}</div>
          ${
            message.send_error && message.retry_scope && message.retry_key
              ? `
            <button type="button"
                    class="retry-send-button"
                    data-retry-scope="${escapeHtml(message.retry_scope)}"
                    data-retry-key="${escapeHtml(message.retry_key)}">Retry</button>
          `
              : ""
          }
          ${
            message.pending_delete_key
              ? `<button type="button" class="delete-pending-button" data-delete-pending-key="${escapeHtml(message.pending_delete_key)}">Delete</button>`
              : ""
          }
          ${
            streaming
              ? `
            <div class="streaming-indicator">
              <span class="streaming-dots"><i></i><i></i><i></i></span>
              ${escapeHtml(activityLabel)}
            </div>
          `
              : ""
          }
          <time class="message-timestamp" datetime="${timestamp.iso}"${timestamp.millis === null ? "" : ` data-message-at="${timestamp.millis}"`}>
            <span class="message-clock">${escapeHtml(timestamp.text)}</span>${timestamp.age ? `<span class="message-age"> · ${escapeHtml(timestamp.age)}</span>` : ""}
          </time>
        </div>
      </section>`;
  }
  function messageNodeFingerprint(message, allowStreaming) {
    return JSON.stringify([
      message.role,
      message.status,
      message.content,
      imageAttachments(message).map((attachment) => [
        attachment.id || "",
        attachment.name || "",
        attachment.type || "",
        String(attachment.src || "").length,
      ]),
      Boolean(message.send_error),
      Boolean(message.pending_activity),
      message.pending_activity_label,
      message.retry_scope,
      message.retry_key,
      message.pending_delete_key,
      message.created_at,
      message.updated_at,
      allowStreaming,
    ]);
  }
  const boundCopyButtons = new WeakSet();
  const boundRetryButtons = new WeakSet();
  const boundDeleteButtons = new WeakSet();
  const boundPendingActionTargets = new WeakSet<HTMLElement>();
  let pendingActionsSheet: HTMLDialogElement | null = null;
  let activePendingActionKey = "";

  function getPendingActionsSheet() {
    if (pendingActionsSheet) return pendingActionsSheet;

    const dialog = document.createElement("dialog");
    dialog.className = "pending-message-actions";
    dialog.setAttribute("aria-labelledby", "pendingMessageActionsTitle");

    const shell = document.createElement("div");
    shell.className = "pending-message-actions-shell";

    const title = document.createElement("div");
    title.id = "pendingMessageActionsTitle";
    title.className = "pending-message-actions-title";
    title.textContent = "Pending message";

    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "pending-message-action";
    editButton.textContent = "Edit message";

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "pending-message-action danger";
    deleteButton.textContent = "Delete message";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "pending-message-action cancel";
    cancelButton.textContent = "Cancel";

    shell.append(title, editButton, deleteButton, cancelButton);
    dialog.append(shell);
    document.body.append(dialog);

    editButton.addEventListener("click", () => {
      const key = activePendingActionKey;
      dialog.close();
      activePendingActionKey = "";

      if (key) onEdit(key);
    });
    deleteButton.addEventListener("click", () => {
      const key = activePendingActionKey;
      dialog.close();
      activePendingActionKey = "";

      if (key) onDelete(key);
    });
    cancelButton.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
      activePendingActionKey = "";
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });

    pendingActionsSheet = dialog;

    return dialog;
  }

  function openPendingActions(deleteKey: string) {
    if (!deleteKey) return;

    activePendingActionKey = deleteKey;
    const dialog = getPendingActionsSheet();

    if (!dialog.open) dialog.showModal();
  }

  function bindPendingActionTargets(root) {
    const targets = root.matches?.(".message.user")
      ? [root]
      : Array.from(root.querySelectorAll(".message.user"));

    for (const target of targets) {
      const node = target as HTMLElement;

      if (boundPendingActionTargets.has(node)) continue;

      if (!node.querySelector(".delete-pending-button")) continue;

      boundPendingActionTargets.add(node);
      node.classList.add("pending-message-action-target");

      let timer = 0;
      let startX = 0;
      let startY = 0;

      const cancelLongPress = () => {
        if (!timer) return;

        clearTimeout(timer);
        timer = 0;
      };
      const actionKey = () =>
        (node.querySelector(".delete-pending-button") as HTMLButtonElement | null)?.dataset
          .deletePendingKey || "";

      node.addEventListener("pointerdown", (event) => {
        if (
          !shouldHandlePendingLongPress(event.pointerType, matchMedia("(pointer: coarse)").matches)
        ) {
          return;
        }

        cancelLongPress();
        startX = event.clientX;
        startY = event.clientY;
        timer = window.setTimeout(() => {
          timer = 0;
          openPendingActions(actionKey());
        }, 480);
      });
      node.addEventListener("pointermove", (event) => {
        if (timer && pendingLongPressMoved(startX, startY, event.clientX, event.clientY)) {
          cancelLongPress();
        }
      });
      node.addEventListener("pointerup", cancelLongPress);
      node.addEventListener("pointercancel", cancelLongPress);
      node.addEventListener("lostpointercapture", cancelLongPress);
      node.addEventListener("contextmenu", (event) => {
        if (!matchMedia("(pointer: coarse)").matches) return;

        event.preventDefault();
        cancelLongPress();
        openPendingActions(actionKey());
      });
    }
  }

  function bindRetryButtons(root) {
    for (const button of root.querySelectorAll(".retry-send-button")) {
      if (boundRetryButtons.has(button)) continue;

      boundRetryButtons.add(button);
      button.addEventListener("click", () => {
        onRetry(button.dataset.retryScope || "", button.dataset.retryKey || "");
      });
    }
  }
  function bindDeleteButtons(root) {
    for (const button of root.querySelectorAll(".delete-pending-button")) {
      if (boundDeleteButtons.has(button)) continue;

      boundDeleteButtons.add(button);
      button.addEventListener("click", () => {
        onDelete(button.dataset.deletePendingKey || "");
      });
    }
  }
  function bindCopyButtons(root) {
    for (const button of root.querySelectorAll(".copy-code")) {
      if (boundCopyButtons.has(button)) continue;

      boundCopyButtons.add(button);
      button.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        const code = button.closest(".code-block")?.querySelector("pre code")?.textContent || "";

        try {
          await navigator.clipboard.writeText(code);
          const previous = button.textContent;
          setTextIfChanged(button, "copied");
          setTimeout(() => {
            setTextIfChanged(button, previous);
          }, 1000);
        } catch {
          setTextIfChanged(button, "copy unavailable");
        }
      });
    }
  }
  function createMessageNode(message, allowStreaming, messageKey) {
    const template = document.createElement("template");
    template.innerHTML = renderMessageSection(message, allowStreaming).trim();
    const node = template.content.firstElementChild as HTMLElement;
    node.dataset.messageKey = messageKey;
    node.dataset.renderFingerprint = messageNodeFingerprint(message, allowStreaming);
    bindCopyButtons(node);
    bindRetryButtons(node);
    bindDeleteButtons(node);
    bindPendingActionTargets(node);

    return node;
  }
  function patchDomNode(current, next) {
    if (
      current.nodeType !== next.nodeType ||
      (current.nodeType === Node.ELEMENT_NODE && current.tagName !== next.tagName)
    ) {
      const replacement = next.cloneNode(true);
      current.replaceWith(replacement);

      return replacement;
    }

    if (current.nodeType === Node.TEXT_NODE) {
      if (current.data !== next.data) current.data = next.data;

      return current;
    }

    if (current.nodeType !== Node.ELEMENT_NODE) return current;

    const preserveDetailsOpen = current.tagName === "DETAILS" && next.tagName === "DETAILS";
    const detailsOpen = preserveDetailsOpen ? (current as HTMLDetailsElement).open : false;

    for (const attribute of Array.from(current.attributes as NamedNodeMap) as Attr[]) {
      if (preserveDetailsOpen && attribute.name === "open") continue;

      if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
    }

    for (const attribute of Array.from(next.attributes as NamedNodeMap) as Attr[]) {
      if (preserveDetailsOpen && attribute.name === "open") continue;

      if (current.getAttribute(attribute.name) !== attribute.value) {
        current.setAttribute(attribute.name, attribute.value);
      }
    }

    patchDomChildren(current, next);

    if (preserveDetailsOpen) (current as HTMLDetailsElement).open = detailsOpen;

    return current;
  }
  function domPatchKey(node) {
    if (!node || node.nodeType !== Node.ELEMENT_NODE) return "";

    return (node as HTMLElement).dataset.domKey || "";
  }
  function patchDomChildren(currentParent, nextParent) {
    let index = 0;

    while (index < nextParent.childNodes.length || index < currentParent.childNodes.length) {
      let current = currentParent.childNodes[index];
      const next = nextParent.childNodes[index];

      if (!next) {
        current.remove();
        continue;
      }

      if (!current) {
        currentParent.append(next.cloneNode(true));
        index += 1;
        continue;
      }

      const nextKey = domPatchKey(next);

      if (nextKey && domPatchKey(current) !== nextKey) {
        const match = Array.from(currentParent.childNodes)
          .slice(index + 1)
          .find((candidate) => domPatchKey(candidate) === nextKey);

        if (match) {
          currentParent.insertBefore(match, current);
          current = match;
        } else {
          currentParent.insertBefore(next.cloneNode(true), current);
          index += 1;
          continue;
        }
      }

      patchDomNode(current, next);
      index += 1;
    }
  }
  function updateMessageNode(node, message, allowStreaming) {
    const role = message.role === "user" ? "user" : "assistant";
    const sendError = Boolean(message.send_error);
    const expectedRole = node.classList.contains("user") ? "user" : "assistant";
    const structuralMismatch =
      expectedRole !== role || node.classList.contains("send-error") !== sendError;

    if (structuralMismatch) return false;

    const content = node.querySelector(".message-content");

    if (!content) return false;

    let currentAttachments = node.querySelector(".message-attachments") as HTMLElement | null;
    const nextAttachments = message.pending_activity ? "" : renderMessageAttachments(message);

    if (!nextAttachments) {
      currentAttachments?.remove();
      currentAttachments = null;
    } else if (!currentAttachments) {
      const template = document.createElement("template");
      template.innerHTML = nextAttachments;
      const nextNode = template.content.firstElementChild;

      if (nextNode) content.before(nextNode);
    } else if (currentAttachments.outerHTML !== nextAttachments) {
      const template = document.createElement("template");
      template.innerHTML = nextAttachments;
      const nextNode = template.content.firstElementChild;

      if (nextNode) patchDomNode(currentAttachments, nextNode);
    }

    const nextContent = message.pending_activity ? "" : renderMarkdown(message.content);

    if (content.innerHTML !== nextContent) {
      const template = document.createElement("template");
      template.innerHTML = nextContent;
      patchDomChildren(content, template.content);
      bindCopyButtons(content);
    }

    const deleteButton = node.querySelector(".delete-pending-button") as HTMLButtonElement | null;
    const deleteKey = String(message.pending_delete_key || "");

    if (deleteKey) {
      if (deleteButton) {
        deleteButton.dataset.deletePendingKey = deleteKey;
      } else {
        content.insertAdjacentHTML(
          "afterend",
          `<button type="button" class="delete-pending-button" data-delete-pending-key="${escapeHtml(deleteKey)}">Delete</button>`,
        );
        bindDeleteButtons(node);
        bindPendingActionTargets(node);
      }
    } else if (deleteButton) {
      deleteButton.remove();
    }

    const retryButton = node.querySelector(".retry-send-button") as HTMLButtonElement | null;
    const shouldRetry = sendError && Boolean(message.retry_scope) && Boolean(message.retry_key);

    if (shouldRetry) {
      if (retryButton) {
        retryButton.dataset.retryScope = String(message.retry_scope);
        retryButton.dataset.retryKey = String(message.retry_key);
      } else {
        content.insertAdjacentHTML(
          "afterend",
          `
          <button type="button"
                  class="retry-send-button"
                  data-retry-scope="${escapeHtml(message.retry_scope)}"
                  data-retry-key="${escapeHtml(message.retry_key)}">Retry</button>
        `,
        );
        bindRetryButtons(node);
        bindDeleteButtons(node);
      }
    } else if (retryButton) {
      retryButton.remove();
    }

    const timestamp = node.querySelector(".message-timestamp") as HTMLTimeElement | null;

    if (!timestamp) return false;

    const nextTimestamp = messageTimestamp(message);
    const clock = timestamp.querySelector(".message-clock") as HTMLElement | null;

    if (!clock) return false;

    setTextIfChanged(clock, nextTimestamp.text);

    if (timestamp.dateTime !== nextTimestamp.iso) timestamp.dateTime = nextTimestamp.iso;

    if (nextTimestamp.millis === null) {
      delete timestamp.dataset.messageAt;
    } else if (timestamp.dataset.messageAt !== String(nextTimestamp.millis)) {
      timestamp.dataset.messageAt = String(nextTimestamp.millis);
    }

    let age = timestamp.querySelector(".message-age") as HTMLElement | null;

    if (nextTimestamp.age) {
      if (!age) {
        timestamp.insertAdjacentHTML("beforeend", '<span class="message-age"></span>');
        age = timestamp.querySelector(".message-age") as HTMLElement | null;
      }

      if (age) setTextIfChanged(age, ` · ${nextTimestamp.age}`);
    } else {
      age?.remove();
    }

    const shouldStream =
      Boolean(message.pending_activity) || (allowStreaming && message.status === "streaming");
    const activityLabel = message.pending_activity_label || "writing";
    const indicator = node.querySelector(".streaming-indicator");

    if (shouldStream && !indicator) {
      timestamp.insertAdjacentHTML(
        "beforebegin",
        `
        <div class="streaming-indicator">
          <span class="streaming-dots"><i></i><i></i><i></i></span>
          ${escapeHtml(activityLabel)}
        </div>
      `,
      );
    } else if (shouldStream && indicator) {
      const labelNode = indicator.lastChild;

      if (labelNode?.nodeType === Node.TEXT_NODE && labelNode.textContent !== ` ${activityLabel}`)
        labelNode.textContent = ` ${activityLabel}`;
    } else if (!shouldStream && indicator) {
      indicator.remove();
    }

    node.dataset.renderFingerprint = messageNodeFingerprint(message, allowStreaming);

    return true;
  }
  function reusablePendingNode(node: Element | undefined, message) {
    if (!(node instanceof HTMLElement) || message.send_error) return null;

    const key = node.dataset.messageKey || "";
    const role = message.role === "user" ? "user" : "assistant";

    if (!canMorphPendingMessageNode(key, role, Boolean(message.send_error))) return null;

    return node.classList.contains(role) ? node : null;
  }

  function renderMessageNodes(messages, allowStreaming) {
    const existing = new Map(
      (Array.from(conversation.children) as HTMLElement[]).map((node) => [
        node.dataset.messageKey,
        node,
      ]),
    );
    const desiredKeys = new Set();
    const lastUserIndex = messages.findLastIndex((message) => message.role === "user");
    const lastAssistantIndex = messages.findLastIndex(
      (message) => message.role === "assistant" && !message.send_error,
    );
    const streamingIndex =
      allowStreaming &&
      lastAssistantIndex > lastUserIndex &&
      messages[lastAssistantIndex]?.status === "streaming"
        ? lastAssistantIndex
        : -1;
    messages.forEach((message, index) => {
      const messageKey = String(message.message_key || `${message.role || "message"}:${index}`);
      const streamThisMessage = index === streamingIndex;
      desiredKeys.add(messageKey);
      const fingerprint = messageNodeFingerprint(message, streamThisMessage);
      let node = existing.get(messageKey);

      if (!node) {
        const candidate = reusablePendingNode(
          conversation.children[index] as HTMLElement | undefined,
          message,
        );

        if (candidate && updateMessageNode(candidate, message, streamThisMessage)) {
          candidate.dataset.messageKey = messageKey;
          node = candidate;
        } else {
          node = createMessageNode(message, streamThisMessage, messageKey);
        }
      } else if (node.dataset.renderFingerprint !== fingerprint) {
        if (!updateMessageNode(node, message, streamThisMessage)) {
          const replacement = createMessageNode(message, streamThisMessage, messageKey);
          node.replaceWith(replacement);
          node = replacement;
        }
      }

      const currentAtIndex = conversation.children[index];

      if (currentAtIndex !== node) {
        conversation.insertBefore(node, currentAtIndex || null);
      }
    });

    for (const node of Array.from(conversation.children) as HTMLElement[]) {
      if (!desiredKeys.has(node.dataset.messageKey)) node.remove();
    }
  }
  function renderLoadingState() {
    if (conversation.children.length) return;

    const loading = document.createElement("div");
    loading.className = "conversation-loading";
    loading.dataset.messageKey = "__loading__";
    loading.setAttribute("aria-live", "polite");
    loading.setAttribute("aria-label", "Loading conversation");

    for (const className of [
      "conversation-loading-row conversation-loading-user",
      "conversation-loading-row conversation-loading-assistant",
      "conversation-loading-row conversation-loading-assistant short",
    ]) {
      const row = document.createElement("div");
      row.className = className;
      loading.append(row);
    }

    conversation.append(loading);
  }

  const CONVERSATION_BOTTOM_SLOP = 24;
  type ConversationViewportSnapshot = {
    pinnedToBottom: boolean;
    scrollTop: number;
    anchorElement: HTMLElement | null;
    anchorKey: string;
    anchorIndex: number;
    anchorFingerprint: string;
    anchorOffset: number;
  };
  let trackedViewport: ConversationViewportSnapshot | null = null;

  function scrollAnchorCandidates(root: Element) {
    return Array.from(
      root.querySelectorAll<HTMLElement>(
        ".message-attachments, .message-content > *, .streaming-indicator, .message-timestamp",
      ),
    );
  }
  function scrollAnchorFingerprint(element: HTMLElement) {
    const text = String(element.textContent || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 160);

    return [element.tagName, element.className, text].join("|");
  }
  function captureConversationViewport() {
    const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    const bottomGap = Math.max(0, maxScrollTop - viewport.scrollTop);
    const pinnedToBottom = bottomGap <= CONVERSATION_BOTTOM_SLOP;
    const snapshot = {
      pinnedToBottom,
      scrollTop: viewport.scrollTop,
      anchorElement: null as HTMLElement | null,
      anchorKey: "",
      anchorIndex: -1,
      anchorFingerprint: "",
      anchorOffset: 0,
    };

    if (pinnedToBottom) return snapshot;

    const viewportTop = viewport.getBoundingClientRect().top;
    const message = (Array.from(conversation.children) as HTMLElement[]).find(
      (node) => node.getBoundingClientRect().bottom > viewportTop + 1,
    );

    if (!message) return snapshot;

    snapshot.anchorKey = String(message.dataset.messageKey || "");
    const candidates = scrollAnchorCandidates(message);
    const anchor =
      candidates.find((node) => node.getBoundingClientRect().bottom > viewportTop + 1) || message;
    snapshot.anchorElement = anchor;
    snapshot.anchorIndex = candidates.indexOf(anchor);
    snapshot.anchorFingerprint = scrollAnchorFingerprint(anchor);
    snapshot.anchorOffset = anchor.getBoundingClientRect().top - viewportTop;

    return snapshot;
  }
  function resolveConversationAnchor(snapshot) {
    const direct = snapshot.anchorElement as HTMLElement | null;

    if (
      direct &&
      direct.isConnected &&
      conversation.contains(direct) &&
      scrollAnchorFingerprint(direct) === snapshot.anchorFingerprint
    )
      return direct;

    const message = (Array.from(conversation.children) as HTMLElement[]).find(
      (node) => node.dataset.messageKey === snapshot.anchorKey,
    );

    if (!message) return null;

    const candidates = scrollAnchorCandidates(message);

    if (snapshot.anchorFingerprint) {
      const matching = candidates
        .map((node, index) => ({ node, index }))
        .filter(({ node }) => scrollAnchorFingerprint(node) === snapshot.anchorFingerprint)
        .sort(
          (left, right) =>
            Math.abs(left.index - snapshot.anchorIndex) -
            Math.abs(right.index - snapshot.anchorIndex),
        );

      if (matching.length) return matching[0].node;
    }

    return candidates[snapshot.anchorIndex] || message;
  }
  function restoreConversationViewport(snapshot, forceBottom = false) {
    if (forceBottom || snapshot.pinnedToBottom) {
      viewport.scrollTop = viewport.scrollHeight;
      trackedViewport = captureConversationViewport();

      return;
    }

    const anchor = resolveConversationAnchor(snapshot);

    if (anchor) {
      const viewportTop = viewport.getBoundingClientRect().top;
      const nextOffset = anchor.getBoundingClientRect().top - viewportTop;
      const delta = nextOffset - snapshot.anchorOffset;

      if (Math.abs(delta) > 0.5) viewport.scrollTop += delta;
    } else {
      const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
      viewport.scrollTop = Math.min(snapshot.scrollTop, maxScrollTop);
    }

    trackedViewport = captureConversationViewport();
  }

  viewport.addEventListener(
    "scroll",
    () => {
      trackedViewport = captureConversationViewport();
    },
    { passive: true },
  );

  conversation.addEventListener(
    "load",
    (event) => {
      if (!(event.target instanceof HTMLImageElement) || !trackedViewport) return;

      restoreConversationViewport(trackedViewport);
    },
    true,
  );

  if ("ResizeObserver" in window) {
    const resizeObserver = new ResizeObserver(() => {
      if (!trackedViewport) trackedViewport = captureConversationViewport();

      restoreConversationViewport(trackedViewport);
    });
    resizeObserver.observe(conversation);
    resizeObserver.observe(viewport);
  }

  trackedViewport = captureConversationViewport();

  return {
    renderMessageNodes,
    renderLoadingState,
    messageNodeFingerprint,
    captureConversationViewport,
    restoreConversationViewport,
  };
}
