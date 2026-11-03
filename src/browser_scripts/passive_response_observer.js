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
  // Only newly owned, rendered response units are read; no history or HTTP requests.
  /* PROMPTA_MARKDOWN_FROM_DOM */
  const identity = (element) => {
    const legacy = element.getAttribute("data-message-id");
    if (legacy) return legacy;
    // Modern assistant turns aggregate multiple message IDs (tools/thoughts/final).
    // The assistant unit key identifies the rendered answer container across updates.
    return element.getAttribute("data-chatgpt-search-unit-key") || element.getAttribute("data-content-search-unit-key") || "";
  };
  const branchMessageId = (element) => {
    const ids = assistantMessageIdsFromDom(element, true);
    return ids.length === 1 ? ids[0] : "";
  };
  const baseline = new Set(topLevelResponseNodes(document, messageSelector).map(identity).filter(Boolean));
  const turnSelector = '[data-content-search-turn-key]';
  const baselineTurns = new Set(topLevelResponseNodes(document, turnSelector)
    .map((turn) => turn.getAttribute('data-content-search-turn-key')).filter(Boolean));
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
  const hasStreamError = () => [...document.querySelectorAll('[role="alert"], [data-testid="error-message"]')]
    .filter(visible).some((node) =>
      /error in (?:the )?response stream|error (?:occurred )?while (?:generating|streaming)|something went wrong (?:while generating|with the response)/i
        .test(node.textContent || ""));
  const publish = () => {
    const signature = `${result.message_id}:${result.branch_message_id}:${result.pathname}:${result.complete}:${result.ambiguous}:${result.text}:${JSON.stringify(result.tool_calls || [])}:${JSON.stringify(result.display_blocks || [])}}`;
    if (signature !== published && typeof window.__promptaPassiveUpdate === "function") {
      published = signature;
      Promise.resolve(window.__promptaPassiveUpdate({ ...result })).catch(() => {});
    }
  };
  const sample = () => {
    // ChatGPT can replace <main> when the new conversation receives its URL.
    const main = document.querySelector("main");
    if (!main) return;
    const fresh = topLevelResponseNodes(main, messageSelector).filter((element) => !baseline.has(identity(element)) && visible(element));
    // A new ChatGPT turn can render visible commentary long before an assistant
    // unit exists. Scope by the verified new turn, not its eventual final node.
    const freshTurns = topLevelResponseNodes(main, turnSelector).filter((turn) => {
      const key = turn.getAttribute('data-content-search-turn-key');
      return key && !baselineTurns.has(key) && visible(turn);
    });
    const scope = freshTurns.length === 1 ? freshTurns : fresh;
    const nextId = freshTurns.length === 1
      ? freshTurns[0].getAttribute('data-content-search-turn-key') : replyIdentity(fresh);
    if (ambiguous || freshTurns.length > 1 ||
        (scope.length && (!nextId || (observedId && nextId !== observedId)))) {
      ambiguous = true; // Different turns must not silently replace an earlier answer.
      result = { message_id: "", branch_message_id: "", pathname: "", text: "", complete: false, ambiguous: true };
      publish();
      return;
    }
    if (!scope.length) {
      if (hasStreamError()) {
        result = { ...result, stream_error: true };
        publish();
      }
      return;
    }
    observedId = nextId;
    const display_blocks = displayBlocksFromUnits(scope, visible, markdownSelector);
    const text = display_blocks.filter((block) => block.kind === 'text')
      .map((block) => block.text).join("\n\n").trim();
    if (text !== lastText) {
      changedAt = Date.now();
      lastText = text;
      if (settleTimer !== null) clearTimeout(settleTimer);
      settleTimer = setTimeout(() => {
        settleTimer = null;
        sample(); // single delayed finality check after this text change
      }, 850);
    }
    const turns = scope.map(responseTurnRoot);
    const tool_calls = toolCallsFromTurns(turns, visible, markdownSelector);
    const copyReady = turns.some((turn) => [...turn.querySelectorAll(copySelector)].some(visible));
    const streaming = turns.some((turn) =>
      !!turn.querySelector('[data-is-streaming="true"], .result-streaming'));
    const generating = [...document.querySelectorAll(stopSelector)].some(visible);
    // Modern turns keep Copy controls visible during tool pauses. Their explicit
    // lifecycle marker is the only reliable completion signal.
    const modernTurn = freshTurns.length === 1 ? freshTurns[0] : null;
    const turnComplete = !modernTurn || !!modernTurn.querySelector('[data-talvt-turn-state="complete"]');
    const complete = !!text && copyReady && !streaming && !generating && turnComplete &&
      Date.now() - changedAt >= 750;
    const lastAnswer = fresh.at(-1) || null;
    result = {
      message_id: nextId,
      branch_message_id: lastAnswer ? branchMessageId(lastAnswer) : "",
      pathname: location.pathname,
      text: text.slice(0, 2 * 1024 * 1024),
      complete,
      ambiguous: false,
      tool_calls,
      display_blocks,
      stream_error: hasStreamError(),
    };
    // Emit only mutation-coalesced changes over Patchright's in-page binding.
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
    attributeFilter: ["data-is-streaming", "data-talvt-turn-state", "aria-label", "data-testid", "data-state", "data-tool-name", "disabled"],
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
