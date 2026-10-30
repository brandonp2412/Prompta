(() => {
  "use strict";
  // Installed in a NEW Prompta-owned tab before sending; never sends requests.
  const key = "__promptaPassiveResponseObserver";
  window[key]?.stop?.();
  const root = document.documentElement;
  if (!root) return false;
  const messageSelector = '[data-message-author-role="assistant"][data-message-id], [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids]';
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const stopSelector = 'button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]';
  const copySelector = 'button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]';
  const toolSelector = '[data-testid*="tool-call"], [data-testid*="tool-card"], [data-testid*="tool-result"], [aria-label^="Used "]';
  const visible = (element) => element.isConnected && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden";
  // Preserve visible response headings, lists, tables and code as Markdown.
  // Only the newly owned final-answer node is read; no history or HTTP requests.
  /* PROMPTA_MARKDOWN_FROM_DOM */
  const identity = (element) => {
    const legacy = element.getAttribute("data-message-id");
    if (legacy) return legacy;
    // Modern assistant turns aggregate multiple message IDs (tools/thoughts/final).
    // The assistant unit key identifies the rendered answer container across updates.
    return element.getAttribute("data-chatgpt-search-unit-key") || "";
  };
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const branchMessageId = (element) => {
    const legacy = element.getAttribute("data-message-id") || "";
    if (uuid.test(legacy)) return legacy.toLowerCase();
    const raw = element.getAttribute("data-chatgpt-search-message-ids");
    if (!raw) return "";
    try {
      // ChatGPT also emits whitespace-separated IDs, sometimes repeating the
      // same backend ID. Only one distinct UUID can identify a reply parent.
      const ids = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
      if (!Array.isArray(ids) || !ids.length ||
          !ids.every((id) => typeof id === "string" && uuid.test(id))) return "";
      const unique = [...new Set(ids.map((id) => id.toLowerCase()))];
      return unique.length === 1 ? unique[0] : "";
    } catch { return ""; }
  };
  const baseline = new Set([...document.querySelectorAll(messageSelector)].map(identity).filter(Boolean));
  let timer = null;
  let settleTimer = null;
  let published = "";
  let changedAt = Date.now();
  let lastText = "";
  let observedId = "";
  let ambiguous = false;
  let result = { message_id: "", branch_message_id: "", pathname: "", text: "", complete: false, ambiguous: false };
  const publish = () => {
    const signature = `${result.message_id}:${result.branch_message_id}:${result.pathname}:${result.complete}:${result.ambiguous}:${result.text}:${JSON.stringify(result.tool_calls || [])}`;
    if (signature !== published && typeof window.__promptaPassiveUpdate === "function") {
      published = signature;
      Promise.resolve(window.__promptaPassiveUpdate({ ...result })).catch(() => {});
    }
  };
  const sample = () => {
    // ChatGPT can replace <main> when the new conversation receives its URL.
    const main = document.querySelector("main");
    if (!main) return;
    const fresh = [...main.querySelectorAll(messageSelector)].filter((element) => !baseline.has(identity(element)) && visible(element));
    const nextId = fresh.length === 1 ? identity(fresh[0]) : "";
    if (ambiguous || fresh.length > 1 || (fresh.length && (!nextId || (observedId && nextId !== observedId)))) {
      ambiguous = true; // A DOM branch rollover must not silently replace an earlier answer.
      result = { message_id: "", branch_message_id: "", pathname: "", text: "", complete: false, ambiguous: true };
      publish();
      return;
    }
    if (!fresh.length) return;
    observedId = nextId;
    const element = fresh[0];
    const roots = [...element.querySelectorAll(markdownSelector)].filter((root) => !root.parentElement?.closest(markdownSelector) && visible(root));
    // Never fall back to the whole turn, which may include tool UI/controls.
    const text = roots.map(markdownFromRoot).filter(Boolean).join("\n\n").trim();
    if (text !== lastText) {
      changedAt = Date.now();
      lastText = text;
      if (settleTimer !== null) clearTimeout(settleTimer);
      settleTimer = setTimeout(() => {
        settleTimer = null;
        sample(); // single delayed finality check after this text change
      }, 850);
    }
    const turn = element.closest('[data-testid^="conversation-turn-"], article, [data-turn-key]') || element;
    const tool_calls = [...turn.querySelectorAll(toolSelector)].filter((node) =>
      visible(node) && !node.closest(markdownSelector) && !node.parentElement?.closest(toolSelector)
    ).slice(0, 128).map((node) => {
      const heading = node.getAttribute('aria-label') || node.getAttribute('data-tool-name') ||
        node.querySelector('[data-testid*="tool-name"]')?.textContent || 'Tool activity';
      const state = node.getAttribute('data-state') || '';
      return { action: heading.slice(0, 120), status: /error|fail/i.test(state) ? 'error' :
        /running|loading|pending/i.test(state) ? 'running' : /complete|success|done/i.test(state) ? 'completed' : 'observed' };
    });
    const copyReady = [...turn.querySelectorAll(copySelector)].some(visible);
    const streaming = !!turn.querySelector('[data-is-streaming="true"], .result-streaming');
    const generating = !!document.querySelector(stopSelector);
    result = {
      message_id: identity(element),
      branch_message_id: branchMessageId(element),
      pathname: location.pathname,
      text: text.slice(0, 2 * 1024 * 1024),
      complete: !!text && copyReady && !streaming && !generating && Date.now() - changedAt >= 750,
      ambiguous: false,
      tool_calls,
    };
    // Emit only mutation-coalesced changes over Playwright's in-page binding.
    // No network request, periodic polling, or alternate conversation access.
    publish();
  };
  const schedule = () => {
    if (timer !== null) return; // mutation-driven, at most one scan per 450ms
    timer = setTimeout(() => {
      timer = null;
      sample();
    }, 450);
  };
  const observer = new MutationObserver(schedule);
  observer.observe(root, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["data-is-streaming", "aria-label", "data-testid", "disabled"],
  });
  window[key] = {
    read: () => {
      sample();
      return { ...result };
    },
    stop: () => {
      observer.disconnect();
      if (timer !== null) clearTimeout(timer);
      if (settleTimer !== null) clearTimeout(settleTimer);
      timer = null;
      settleTimer = null;
    },
  };
  return true;
})()