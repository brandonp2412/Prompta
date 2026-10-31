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
  /* PROMPTA_MARKDOWN_FROM_DOM */
  const rateText = [...document.querySelectorAll('[role="alert"], [role="status"], [role="dialog"]')]
    .filter(visible).map((node) => node.textContent || "").join(" ").toLowerCase();
  if (/too many requests|rate limit|try again in|usage cap|wait a few minutes/.test(rateText)) {
    return { ...empty, rate_limited: true };
  }
  const main = document.querySelector("main");
  if (!main) return empty;
  const userSelector = '[data-message-author-role="user"], [data-chatgpt-search-unit-key$=":user"], [data-content-search-unit-key$=":user"]';
  const users = topLevelResponseNodes(main, userSelector).filter(visible);
  if (!users.length) return empty;
  const userBody = users[0].querySelector?.(".whitespace-pre-wrap") || users[0];
  const userText = normalize(userBody.innerText || userBody.textContent || "");
  const expected = normalize(originalPrompt);
  // Controls may append labels to the original user text, but must not replace it.
  if (!expected || (!userText.startsWith(expected) && userText !== expected)) {
    return { ...empty, ambiguous: true };
  }
  const assistantSelector = '[data-message-author-role="assistant"][data-message-id], [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids], [data-content-search-unit-key$=":assistant"]';
  const assistants = topLevelResponseNodes(main, assistantSelector).filter(visible);
  if (!assistants.length) return { ...empty, verified: true };
  const assistant = assistants[0];
  const beforeNextUser = (node) => !users[1] || Boolean(
    node.compareDocumentPosition(users[1]) & Node.DOCUMENT_POSITION_FOLLOWING);
  if (!beforeNextUser(assistant)) return { ...empty, verified: true };
  const identity = assistant.getAttribute("data-message-id") ||
    assistant.getAttribute("data-chatgpt-search-unit-key") || assistant.getAttribute("data-content-search-unit-key") || "";
  if (!identity) return { ...empty, ambiguous: true };
  const firstGroup = identity.match(/^(fallback-turn-\d+):\d+:assistant$/)?.[1];
  const answerUnits = firstGroup ? assistants.filter((node) => {
    const key = node.getAttribute("data-chatgpt-search-unit-key") || node.getAttribute("data-content-search-unit-key") || "";
    return beforeNextUser(node) && key.match(/^(fallback-turn-\d+):\d+:assistant$/)?.[1] === firstGroup;
  }) : [assistant];
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const segments = answerUnits.map((node) => [...node.querySelectorAll(markdownSelector)]
    .filter((root) => !root.parentElement?.closest(markdownSelector) && visible(root))
    .map(markdownFromRoot).filter(Boolean).join("\n\n").trim());
  // The main turn may contain tools and thoughts; only extract final-answer markdown.
  const text = segments.filter(Boolean)
    .join("\n\n").trim().slice(0, 2 * 1024 * 1024);
  const turns = answerUnits.map((node) =>
    node.closest('[data-testid^="conversation-turn-"], article, [data-turn-key]') || node);
  // Only visible tool headings in this verified turn, never tool bodies or reasoning.
  const tool_calls = toolCallsFromTurns(turns, visible, markdownSelector);
  const copyReady = turns.some((turn) => [...turn.querySelectorAll(
    'button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]'
  )].some(visible));
  const streaming = turns.some((turn) => !!turn.querySelector('[data-is-streaming="true"], .result-streaming'));
  const generating = [...document.querySelectorAll(
    'button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]'
  )].some(visible);
  const lastTextIndex = segments.findLastIndex(Boolean);
  const finalAnswer = lastTextIndex < 0 ? assistant : answerUnits[lastTextIndex];
  const finalIds = assistantMessageIdsFromDom(finalAnswer);
  const branch = finalIds.length === 1 ? finalIds[0] : "";
  return {
    verified: true, ambiguous: false, message_id: identity,
    branch_message_id: branch, pathname: location.pathname, text,
    complete: !!text && copyReady && !streaming && !generating,
    rate_limited: false, tool_calls,
  };
})()
