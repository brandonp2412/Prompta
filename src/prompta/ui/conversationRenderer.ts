import { messageAgeText, messageTimestampMillis } from "./clientLogic";
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
  return `<div class="message-attachments">${images.map((attachment) => {
    const src = imageAttachmentSrc(attachment);
    const name = String(attachment.name || "Attached image");
    return `<img class="message-image-preview" src="${escapeHtml(src)}" alt="${escapeHtml(name)}" loading="lazy" decoding="async">`;
  }).join("")}</div>`;
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

export function createConversationRenderer({ onRetry }) {
  const conversation = requiredElement<HTMLElement>("#conversation");
  const viewport = requiredElement<HTMLElement>("#conversationViewport");

  function messageTimestamp(message) {
    const millis = messageTimestampMillis(message.created_at, message.updated_at);
    if (millis === null) return { text: "Time unavailable", iso: "", millis: null, age: "" };
    const date = new Date(millis);
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];
    const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const hour24 = date.getHours();
    const hour12 = hour24 % 12 || 12;
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const period = hour24 < 12 ? "am" : "pm";
    return {
      text: `${date.getDate()} ${months[date.getMonth()]} ${weekdays[date.getDay()]} ${hour12}:${minutes}${period}`,
      iso: date.toISOString(),
      millis,
      age: messageAgeText(millis),
    };
  }
  function renderMessageSection(message, allowStreaming = true) {
    const role = message.role === "user" ? "user" : "assistant";
    const streaming = Boolean(message.pending_activity)
      || (allowStreaming && message.status === "streaming");
    const activityLabel = message.pending_activity_label || "writing";
    const label = message.send_error ? "Send error" : "Prompta run";
    const timestamp = messageTimestamp(message);
    const contentHtml = message.pending_activity ? "" : renderMarkdown(message.content);
    const attachmentsHtml = message.pending_activity ? "" : renderMessageAttachments(message);
    return `
      <section class="message ${role}${message.send_error ? " send-error" : ""}">
        <div class="message-inner">
          ${role === "assistant" ? `
            <div class="message-label"><span class="assistant-avatar">${message.send_error ? "!" : "P"}</span> ${label}</div>
          ` : ""}
          ${attachmentsHtml}
          <div class="message-content">${contentHtml}</div>
          ${message.send_error && message.retry_scope && message.retry_key ? `
            <button type="button"
                    class="retry-send-button"
                    data-retry-scope="${escapeHtml(message.retry_scope)}"
                    data-retry-key="${escapeHtml(message.retry_key)}">Retry</button>
          ` : ""}
          ${streaming ? `
            <div class="streaming-indicator">
              <span class="streaming-dots"><i></i><i></i><i></i></span>
              ${escapeHtml(activityLabel)}
            </div>
          ` : ""}
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
      message.created_at,
      message.updated_at,
      allowStreaming,
    ]);
  }
  const boundCopyButtons = new WeakSet();
  const boundRetryButtons = new WeakSet();
  function bindRetryButtons(root) {
    for (const button of root.querySelectorAll(".retry-send-button")) {
      if (boundRetryButtons.has(button)) continue;
      boundRetryButtons.add(button);
      button.addEventListener("click", () => {
        onRetry(button.dataset.retryScope || "", button.dataset.retryKey || "");
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
          setTimeout(() => { setTextIfChanged(button, previous); }, 1000);
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
    return node;
  }
  function patchDomNode(current, next) {
    if (
      current.nodeType !== next.nodeType
      || (current.nodeType === Node.ELEMENT_NODE && current.tagName !== next.tagName)
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
      if (!next) { current.remove(); continue; }
      if (!current) { currentParent.append(next.cloneNode(true)); index += 1; continue; }
      const nextKey = domPatchKey(next);
      if (nextKey && domPatchKey(current) !== nextKey) {
        const match = Array.from(currentParent.childNodes).slice(index + 1).find((candidate) => domPatchKey(candidate) === nextKey);
        if (match) { currentParent.insertBefore(match, current); current = match; }
        else { currentParent.insertBefore(next.cloneNode(true), current); index += 1; continue; }
      }
      patchDomNode(current, next);
      index += 1;
    }
  }
  function patchHtmlChildren(element: Element, html: string) {
    const template = document.createElement("template");
    template.innerHTML = html;
    patchDomChildren(element, template.content);
  }
  function updateMessageNode(node, message, allowStreaming) {
    const role = message.role === "user" ? "user" : "assistant";
    const sendError = Boolean(message.send_error);
    const expectedRole = node.classList.contains("user") ? "user" : "assistant";
    const structuralMismatch = expectedRole !== role
      || node.classList.contains("send-error") !== sendError;
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
    const retryButton = node.querySelector(".retry-send-button") as HTMLButtonElement | null;
    const shouldRetry = sendError && Boolean(message.retry_scope) && Boolean(message.retry_key);
    if (shouldRetry) {
      if (retryButton) {
        retryButton.dataset.retryScope = String(message.retry_scope);
        retryButton.dataset.retryKey = String(message.retry_key);
      } else {
        content.insertAdjacentHTML("afterend", `
          <button type="button"
                  class="retry-send-button"
                  data-retry-scope="${escapeHtml(message.retry_scope)}"
                  data-retry-key="${escapeHtml(message.retry_key)}">Retry</button>
        `);
        bindRetryButtons(node);
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

    const shouldStream = Boolean(message.pending_activity)
      || (allowStreaming && message.status === "streaming");
    const activityLabel = message.pending_activity_label || "writing";
    const indicator = node.querySelector(".streaming-indicator");
    if (shouldStream && !indicator) {
      timestamp.insertAdjacentHTML("beforebegin", `
        <div class="streaming-indicator">
          <span class="streaming-dots"><i></i><i></i><i></i></span>
          ${escapeHtml(activityLabel)}
        </div>
      `);
    } else if (shouldStream && indicator) {
      const labelNode = indicator.lastChild;
      if (labelNode?.nodeType === Node.TEXT_NODE && labelNode.textContent !== ` ${activityLabel}`) labelNode.textContent = ` ${activityLabel}`;
    } else if (!shouldStream && indicator) {
      indicator.remove();
    }
    node.dataset.renderFingerprint = messageNodeFingerprint(message, allowStreaming);
    return true;
  }
  function renderMessageNodes(messages, allowStreaming) {
    const existing = new Map(
      (Array.from(conversation.children) as HTMLElement[])
        .map((node) => [node.dataset.messageKey, node]),
    );
    const desiredKeys = new Set();
    const lastUserIndex = messages.findLastIndex((message) => message.role === "user");
    const lastAssistantIndex = messages.findLastIndex((message) => (
      message.role === "assistant" && !message.send_error
    ));
    const streamingIndex = allowStreaming
      && lastAssistantIndex > lastUserIndex
      && messages[lastAssistantIndex]?.status === "streaming"
      ? lastAssistantIndex
      : -1;
    messages.forEach((message, index) => {
      const messageKey = String(message.message_key || `${message.role || "message"}:${index}`);
      const streamThisMessage = index === streamingIndex;
      desiredKeys.add(messageKey);
      const fingerprint = messageNodeFingerprint(message, streamThisMessage);
      let node = existing.get(messageKey);
      if (!node) {
        node = createMessageNode(message, streamThisMessage, messageKey);
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
    conversation.innerHTML = `
      <div class="conversation-loading" data-message-key="__loading__" aria-live="polite" aria-label="Loading conversation">
        <div class="conversation-loading-row conversation-loading-user"></div>
        <div class="conversation-loading-row conversation-loading-assistant"></div>
        <div class="conversation-loading-row conversation-loading-assistant short"></div>
      </div>`;
  }

  const CONVERSATION_BOTTOM_SLOP = 24;
  function captureConversationViewport() {
    const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    const bottomGap = Math.max(0, maxScrollTop - viewport.scrollTop);
    const pinnedToBottom = bottomGap <= CONVERSATION_BOTTOM_SLOP;
    const snapshot = {
      pinnedToBottom,
      scrollTop: viewport.scrollTop,
      anchorKey: "",
      anchorOffset: 0,
    };
    if (pinnedToBottom) return snapshot;

    const viewportTop = viewport.getBoundingClientRect().top;
    for (const node of Array.from(conversation.children) as HTMLElement[]) {
      const rect = node.getBoundingClientRect();
      if (rect.bottom <= viewportTop + 1) continue;
      snapshot.anchorKey = String(node.dataset.messageKey || "");
      snapshot.anchorOffset = rect.top - viewportTop;
      break;
    }
    return snapshot;
  }
  function restoreConversationViewport(snapshot, forceBottom = false) {
    if (forceBottom || snapshot.pinnedToBottom) {
      viewport.scrollTop = viewport.scrollHeight;
      return;
    }
    if (snapshot.anchorKey) {
      const anchor = Array.from(conversation.children)
        .find((node) => (node as HTMLElement).dataset.messageKey === snapshot.anchorKey) as HTMLElement | undefined;
      if (anchor) {
        const viewportTop = viewport.getBoundingClientRect().top;
        const nextOffset = anchor.getBoundingClientRect().top - viewportTop;
        const delta = nextOffset - snapshot.anchorOffset;
        if (Math.abs(delta) > 0.5) viewport.scrollTop += delta;
        return;
      }
    }
    const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    viewport.scrollTop = Math.min(snapshot.scrollTop, maxScrollTop);
  }

  return {
    renderMessageNodes,
    renderLoadingState,
    messageNodeFingerprint,
    captureConversationViewport,
    restoreConversationViewport,
  };
}
