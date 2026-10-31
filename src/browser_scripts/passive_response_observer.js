(() => {
  "use strict";
  // Installed in a NEW Prompta-owned tab before sending; never sends requests.
  const key = "__promptaPassiveResponseObserver";
  window[key]?.stop?.();
  const root = document.documentElement;
  if (!root) return false;
  const messageSelector = '[data-message-author-role="assistant"][data-message-id], [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids], [data-content-search-unit-key$=":assistant"]';
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const stopSelector = 'button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]';
  const copySelector = 'button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]';

  const visible = (element) => element.isConnected && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden";
  // Preserve visible response headings, lists, tables and code as Markdown.
  // Only the newly owned final-answer node is read; no history or HTTP requests.
  /* PROMPTA_MARKDOWN_FROM_DOM */
  const identity = (element) => {
    const legacy = element.getAttribute("data-message-id");
    if (legacy) return legacy;
    // Modern assistant turns aggregate multiple message IDs (tools/thoughts/final).
    // The assistant unit key identifies the rendered answer container across updates.
    return element.getAttribute("data-chatgpt-search-unit-key") || element.getAttribute("data-content-search-unit-key") || "";
  };
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const branchMessageId = (element) => {
    const legacy = element.getAttribute("data-message-id") || "";
    if (uuid.test(legacy)) return legacy.toLowerCase();
    const raw = element.getAttribute("data-chatgpt-search-message-ids") || element.getAttribute("data-content-search-message-ids");
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
  const replyIdentity = (elements) => {
    if (!elements.length) return "";
    const modern = elements.map((element) =>
      identity(element).match(/^(fallback-turn-\d+):\d+:assistant$/)?.[1] || ""
    );
    if (modern[0] && modern.every((group) => group === modern[0])) return modern[0];
    return elements.length === 1 ? identity(elements[0]) : "";
  };
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
    const nextId = replyIdentity(fresh);
    if (ambiguous || (fresh.length && (!nextId || (observedId && nextId !== observedId)))) {
      ambiguous = true; // Different turns must not silently replace an earlier answer.
      result = { message_id: "", branch_message_id: "", pathname: "", text: "", complete: false, ambiguous: true };
      publish();
      return;
    }
    if (!fresh.length) return;
    observedId = nextId;
    const segments = fresh.map((element) => {
      const roots = [...element.querySelectorAll(markdownSelector)].filter((root) =>
        !root.parentElement?.closest(markdownSelector) && visible(root));
      return roots.map(markdownFromRoot).filter(Boolean).join("\n\n").trim();
    });
    // Aggregate separate user-visible final chunks of the SAME reply turn.
    const text = segments.filter(Boolean).join("\n\n").trim();
    if (text !== lastText) {
      changedAt = Date.now();
      lastText = text;
      if (settleTimer !== null) clearTimeout(settleTimer);
      settleTimer = setTimeout(() => {
        settleTimer = null;
        sample(); // single delayed finality check after this text change
      }, 850);
    }
    const turns = fresh.map((element) =>
      element.closest('[data-testid^="conversation-turn-"], article, [data-turn-key], .group.flex.flex-col') ||
      element);
    const tool_calls = toolCallsFromTurns(turns, visible, markdownSelector);
    const copyReady = turns.some((turn) => [...turn.querySelectorAll(copySelector)].some(visible));
    const streaming = turns.some((turn) =>
      !!turn.querySelector('[data-is-streaming="true"], .result-streaming'));
    const generating = [...document.querySelectorAll(stopSelector)].some(visible);
    const complete = !!text && copyReady && !streaming && !generating &&
      Date.now() - changedAt >= 750;
    const lastTextIndex = segments.findLastIndex(Boolean);
    const lastAnswer = lastTextIndex < 0 ? null : fresh[lastTextIndex];
    result = {
      message_id: nextId,
      branch_message_id: lastAnswer ? branchMessageId(lastAnswer) : "",
      pathname: location.pathname,
      text: text.slice(0, 2 * 1024 * 1024),
      complete,
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
    attributeFilter: ["data-is-streaming", "aria-label", "data-testid", "data-state", "data-tool-name", "disabled"],
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