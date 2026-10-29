(() => {
  "use strict";
  // Read only the first turn of one explicitly known Prompta-created conversation.
  // No account-wide listing, internal API request, or prompt submission.
  const conversation = __CONVERSATION__;
  const originalPrompt = __ORIGINAL_PROMPT__;
  const empty = { verified: false, ambiguous: false, message_id: "", branch_message_id: "", pathname: "", text: "", complete: false, rate_limited: false };
  if (location.origin !== "https://chatgpt.com" || location.pathname !== "/c/" + conversation) return empty;
  const visible = (node) => node.isConnected && node.getClientRects().length > 0 &&
    getComputedStyle(node).visibility !== "hidden";
  const normalize = (value) => value.replace(/\u200b/g, "").replace(/\s+/g, " ").trim();
  const rateText = [...document.querySelectorAll('[role="alert"], [role="status"], [role="dialog"]')]
    .filter(visible).map((node) => node.textContent || "").join(" ").toLowerCase();
  if (/too many requests|rate limit|try again in|usage cap|wait a few minutes/.test(rateText)) {
    return { ...empty, rate_limited: true };
  }
  const main = document.querySelector("main");
  if (!main) return empty;
  const users = [...main.querySelectorAll(
    '[data-message-author-role="user"], [data-chatgpt-search-unit-key$=":user"]'
  )].filter(visible);
  if (!users.length) return empty;
  const userText = normalize(users[0].innerText || users[0].textContent || "");
  const expected = normalize(originalPrompt);
  // Controls may append labels to the original user text, but must not replace it.
  if (!expected || (!userText.startsWith(expected) && userText !== expected)) {
    return { ...empty, ambiguous: true };
  }
  const assistants = [...main.querySelectorAll(
    '[data-message-author-role="assistant"][data-message-id], [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids]'
  )].filter(visible);
  if (!assistants.length) return { ...empty, verified: true };
  const assistant = assistants[0];
  const identity = assistant.getAttribute("data-message-id") ||
    assistant.getAttribute("data-chatgpt-search-unit-key") || "";
  if (!identity) return { ...empty, ambiguous: true };
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const roots = [...assistant.querySelectorAll(markdownSelector)].filter((root) =>
    !root.parentElement?.closest(markdownSelector) && visible(root)
  );
  // The main turn may contain tools and thoughts; only extract final-answer markdown.
  const text = roots.map((root) => root.innerText || root.textContent || "").filter(Boolean)
    .join("\n\n").trim().slice(0, 2 * 1024 * 1024);
  const turn = assistant.closest('[data-testid^="conversation-turn-"], article, [data-turn-key]') || assistant;
  const copyReady = [...turn.querySelectorAll(
    'button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]'
  )].some(visible);
  const streaming = !!turn.querySelector('[data-is-streaming="true"], .result-streaming');
  const generating = !!document.querySelector(
    'button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]'
  );
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const legacy = assistant.getAttribute("data-message-id") || "";
  let branch = uuid.test(legacy) ? legacy.toLowerCase() : "";
  if (!branch) {
    const raw = assistant.getAttribute("data-chatgpt-search-message-ids") || "";
    try {
      const ids = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
      if (Array.isArray(ids) && ids.length && ids.every((id) => typeof id === "string" && uuid.test(id))) {
        const unique = [...new Set(ids.map((id) => id.toLowerCase()))];
        if (unique.length === 1) branch = unique[0];
      }
    } catch {}
  }
  return {
    verified: true, ambiguous: false, message_id: identity,
    branch_message_id: branch, pathname: location.pathname, text,
    complete: !!text && copyReady && !streaming && !generating,
    rate_limited: false,
  };
})()
