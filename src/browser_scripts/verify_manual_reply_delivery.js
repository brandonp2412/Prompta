(() => {
  "use strict";
  // Only inspect the currently owned, exact conversation after one user-initiated send.
  // No navigation, network calls, history lookup, or prompt submission.
  const conversation = __CONVERSATION__;
  const parent = __PARENT__;
  const targetReply = __REPLY__;
  const empty = { verified: false, complete: false, message_id: "", text: "" };
  if (location.origin !== "https://chatgpt.com" ||
      location.pathname !== "/c/" + conversation) return empty;

  const visible = (node) => node.isConnected && node.getClientRects().length > 0 &&
    getComputedStyle(node).visibility !== "hidden";
  const normalize = (value) => (value || "").replace(/\u200b/g, "")
    .replace(/\s+/g, " ").trim();
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  if (!uuid.test(parent) || !normalize(targetReply)) return empty;
  const main = document.querySelector("main");
  if (!main) return empty;

  const nodes = [...main.querySelectorAll(
    '[data-message-author-role], [data-chatgpt-search-unit-key], [data-content-search-unit-key]'
  )].filter(visible).map((node) => ({
    node,
    role: node.getAttribute("data-message-author-role") ||
      (node.getAttribute("data-chatgpt-search-unit-key") || node.getAttribute("data-content-search-unit-key") || "").split(":").at(-1),
  })).filter((item) => item.role === "user" || item.role === "assistant");
  const ids = (node) => {
    const legacy = node.getAttribute("data-message-id");
    if (legacy) return uuid.test(legacy) ? [legacy.toLowerCase()] : [];
    const raw = node.getAttribute("data-chatgpt-search-message-ids") || node.getAttribute("data-content-search-message-ids") || "";
    try {
      const parsed = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
      return Array.isArray(parsed) && parsed.length &&
        parsed.every((id) => typeof id === "string" && uuid.test(id))
        ? [...new Set(parsed.map((id) => id.toLowerCase()))] : [];
    } catch { return []; }
  };
  const parentIndex = nodes.findIndex(
    (item) => item.role === "assistant" && ids(item.node).includes(parent.toLowerCase())
  );
  if (parentIndex < 0) return empty;
  const after = nodes.slice(parentIndex + 1);
  if (!after.length || after[0].role !== "user" ||
      after.slice(1).some((item) => item.role === "user")) return empty;

  const replyNode = after[0].node;
  const replyBody = replyNode.querySelector(".whitespace-pre-wrap") || replyNode;
  if (normalize(replyBody.innerText || replyBody.textContent) !== normalize(targetReply)) {
    return empty;
  }
  const later = after.slice(1);
  if (later.length === 0) return { ...empty, verified: true };
  if (later.length !== 1 || later[0].role !== "assistant") return empty;
  const assistant = later[0].node;
  const messageIds = ids(assistant);
  if (messageIds.length !== 1 || messageIds[0] === parent.toLowerCase()) return empty;

  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const roots = [...assistant.querySelectorAll(markdownSelector)]
    .filter((root) => !root.parentElement?.closest(markdownSelector) && visible(root));
  const text = roots.map((root) => root.innerText || root.textContent || "")
    .filter(Boolean).join("\n\n").trim().slice(0, 2 * 1024 * 1024);
  const turn = assistant.closest('[data-testid^="conversation-turn-"], article, [data-turn-key]') ||
    assistant;
  const copyReady = [...turn.querySelectorAll(
    'button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]'
  )].some(visible);
  const streaming = !!turn.querySelector('[data-is-streaming="true"], .result-streaming');
  const generating = [...document.querySelectorAll(
    'button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]'
  )].some(visible);
  return { verified: true, complete: !!text && copyReady && !streaming && !generating,
    message_id: messageIds[0], text };
})()
