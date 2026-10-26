(() => {
  "use strict";
  // Installed in a NEW Prompta-owned tab before sending; never sends requests.
  const key = "__promptaPassiveResponseObserver";
  window[key]?.stop?.();
  const main = document.querySelector("main");
  if (!main) return false;
  const messageSelector = '[data-message-author-role="assistant"][data-message-id], [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids]';
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const stopSelector = 'button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]';
  const copySelector = 'button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]';
  const baseline = new Set(main.querySelectorAll(messageSelector));
  const visible = (element) => element.isConnected && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden";
  const identity = (element) => {
    const legacy = element.getAttribute("data-message-id");
    if (legacy) return legacy;
    const ids = [...new Set((element.getAttribute("data-chatgpt-search-message-ids") || "").trim().split(/\s+/).filter(Boolean))];
    return ids.length === 1 ? ids[0] : "";
  };
  let timer = null;
  let changedAt = Date.now();
  let lastText = "";
  let result = { message_id: "", text: "", complete: false, ambiguous: false };
  const sample = () => {
    const fresh = [...main.querySelectorAll(messageSelector)].filter((element) => !baseline.has(element) && visible(element));
    if (fresh.length > 1 || fresh.some((element) => !identity(element))) {
      result = { message_id: "", text: "", complete: false, ambiguous: true };
      return;
    }
    if (!fresh.length) return;
    const element = fresh[0];
    const roots = [...element.querySelectorAll(markdownSelector)].filter((root) => !root.parentElement?.closest(markdownSelector) && visible(root));
    // Never fall back to the whole turn, which may include tool UI/controls.
    const text = roots.map((root) => root.innerText || root.textContent || "").join("\n").trim();
    if (text !== lastText) {
      changedAt = Date.now();
      lastText = text;
    }
    const turn = element.closest('[data-testid^="conversation-turn-"], article, [data-turn-key]') || element;
    const copyReady = [...turn.querySelectorAll(copySelector)].some(visible);
    const streaming = !!turn.querySelector('[data-is-streaming="true"], .result-streaming');
    const generating = !!document.querySelector(stopSelector);
    result = {
      message_id: identity(element),
      text,
      complete: !!text && copyReady && !streaming && !generating && Date.now() - changedAt >= 750,
      ambiguous: false,
    };
  };
  const schedule = () => {
    if (timer !== null) return; // mutation-driven, at most one scan per 450ms
    timer = setTimeout(() => {
      timer = null;
      sample();
    }, 450);
  };
  const observer = new MutationObserver(schedule);
  observer.observe(main, {
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
      timer = null;
    },
  };
  return true;
})()