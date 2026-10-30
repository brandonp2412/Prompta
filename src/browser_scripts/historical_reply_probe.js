(() => {
  "use strict";
  // Exact, read-only recovery of the first explicit reply to a Prompta-owned chat.
  // A claimed reply is NEVER resent; no other account history is examined.
  const conversation = __CONVERSATION__;
  const originalPrompt = __ORIGINAL_PROMPT__;
  const replyText = __REPLY_TEXT__;
  const parent = __PARENT__;
  const empty = { verified: false, ambiguous: false, message_id: "", branch_message_id: "", pathname: "", text: "", complete: false, rate_limited: false, tool_calls: [] };
  if (location.origin !== "https://chatgpt.com" || location.pathname !== "/c/" + conversation) return empty;
  const visible = (node) => node.isConnected && node.getClientRects().length > 0 &&
    getComputedStyle(node).visibility !== "hidden";
  const normalize = (value) => value.replace(/\u200b/g, "").replace(/\s+/g, " ").trim();
  /* PROMPTA_MARKDOWN_FROM_DOM */
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
  const assistants = [...main.querySelectorAll(
    '[data-message-author-role="assistant"][data-message-id], [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids]'
  )].filter(visible);
  if (users.length !== 2 || assistants.length > 2) return { ...empty, ambiguous: users.length > 2 || assistants.length > 2 };
  const texts = [originalPrompt, replyText];
  if (users.some((node, index) => !normalize(node.innerText || node.textContent || "").startsWith(normalize(texts[index])) || !normalize(texts[index]))) {
    return { ...empty, ambiguous: true };
  }
  if (!assistants.length) return { ...empty, verified: true };
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const branchId = (node) => {
    const legacy = node.getAttribute("data-message-id") || "";
    if (uuid.test(legacy)) return legacy.toLowerCase();
    const raw = node.getAttribute("data-chatgpt-search-message-ids") || "";
    try {
      const ids = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
      if (!Array.isArray(ids) || !ids.length || !ids.every((id) => typeof id === "string" && uuid.test(id))) return "";
      const unique = [...new Set(ids.map((id) => id.toLowerCase()))];
      return unique.length === 1 ? unique[0] : "";
    } catch { return ""; }
  };
  if (branchId(assistants[0]) !== parent.toLowerCase()) return { ...empty, ambiguous: true };
  if (assistants.length < 2) return { ...empty, verified: true };
  const assistant = assistants[1];
  const identity = assistant.getAttribute("data-message-id") || assistant.getAttribute("data-chatgpt-search-unit-key") || "";
  if (!identity || identity === parent) return { ...empty, ambiguous: true };
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const roots = [...assistant.querySelectorAll(markdownSelector)].filter((root) =>
    !root.parentElement?.closest(markdownSelector) && visible(root)
  );
  const text = roots.map(markdownFromRoot).filter(Boolean).join("\n\n").trim().slice(0, 2 * 1024 * 1024);
  const turn = assistant.closest('[data-testid^="conversation-turn-"], article, [data-turn-key]') || assistant;
  const toolSelector = '[data-testid*="tool-call"], [data-testid*="tool-card"], [data-testid*="tool-result"], [aria-label^="Used "]';
  const tool_calls = [...turn.querySelectorAll(toolSelector)].filter((node) =>
    visible(node) && !node.closest(markdownSelector) && !node.parentElement?.closest(toolSelector)
  ).slice(0, 128).map((node) => {
    const heading = node.getAttribute('aria-label') || node.getAttribute('data-tool-name') ||
      node.querySelector('[data-testid*="tool-name"]')?.textContent || 'Tool activity';
    const state = node.getAttribute('data-state') || '';
    return { action: heading.slice(0, 120), status: /error|fail/i.test(state) ? 'error' :
      /running|loading|pending/i.test(state) ? 'running' : /complete|success|done/i.test(state) ? 'completed' : 'observed' };
  });
  const copyReady = [...turn.querySelectorAll(
    'button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]'
  )].some(visible);
  const streaming = !!turn.querySelector('[data-is-streaming="true"], .result-streaming');
  const generating = !!document.querySelector(
    'button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]'
  );
  return {
    verified: true, ambiguous: false, message_id: identity,
    branch_message_id: branchId(assistant), verified_parent_id: parent,
    pathname: location.pathname, text, tool_calls,
    complete: !!text && copyReady && !streaming && !generating, rate_limited: false,
  };
})()
