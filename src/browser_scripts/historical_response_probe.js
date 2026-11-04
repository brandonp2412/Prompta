(() => {
  "use strict";
  // Read only the first turn of one explicitly known Prompta-created conversation.
  // No account-wide listing, internal API request, or prompt submission.
  const conversation = __CONVERSATION__;
  const originalPrompt = __ORIGINAL_PROMPT__;
  const stream_error = [...document.querySelectorAll('[role="alert"], [data-testid="error-message"]')]
    .filter(node => node.isConnected && node.getClientRects().length > 0)
    .some(node => /error in (?:the )?response stream|error (?:occurred )?while (?:generating|streaming)|something went wrong (?:while generating|with the response)/i.test(node.textContent || ""));
  const empty = { verified: false, ambiguous: false, message_id: "", branch_message_id: "", pathname: "", text: "", complete: false, generating: false, rate_limited: false, stream_error };
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
  // Prompta sends scheduled jobs inside a marked prompt block, but stores only
  // the job text. Verify the complete block, never an arbitrary substring.
  const wrapped = userText.match(
    /^(?:\[BEGIN PROMPTA SYSTEM PROMPT\] .*? \[END PROMPTA SYSTEM PROMPT\] )?\[BEGIN JOB PROMPT\] (.*?) \[END JOB PROMPT\]$/
  );
  // Controls may append labels to ordinary user text, but must not replace it.
  if (!expected || (!userText.startsWith(expected) && wrapped?.[1] !== expected)) {
    return { ...empty, ambiguous: true };
  }
  const assistantSelector = '[data-message-author-role="assistant"][data-message-id], [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids], [data-content-search-unit-key$=":assistant"]';
  const assistants = topLevelResponseNodes(main, assistantSelector).filter(visible);
  if (!assistants.length) {
    // Agent activity can render before its assistant answer placeholder becomes
    // visible. Bind public progress markdown to this exact verified user turn;
    // never treat activity (or a hidden answer) as a completed response.
    const turn = users[0].closest('[data-content-search-turn-key]');
    const key = turn?.getAttribute('data-content-search-turn-key') || "";
    const placeholder = turn?.querySelector('[data-content-search-unit-key$=":assistant"]');
    const identity = placeholder?.getAttribute('data-content-search-unit-key') || key + ":activity:assistant";
    if (!/^fallback-turn-\d+$/.test(key) || !identity.startsWith(key + ":") ||
        !turn.querySelector('[data-talvt-turn-state="in_progress"]') ||
        (users[1] && turn.contains(users[1]))) return { ...empty, verified: true, pathname: location.pathname };
    const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
    const display_blocks = displayBlocksFromUnits([turn], visible, markdownSelector);
    const text = display_blocks.filter((block) => block.kind === 'text')
      .map((block) => block.text).join("\n\n").trim().slice(0, 2 * 1024 * 1024);
    return { ...empty, verified: true, message_id: identity,
      pathname: location.pathname, text, generating: users.length === 1,
      tool_calls: toolCallsFromTurns([turn], visible, markdownSelector),
      display_blocks,
    };
  }
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
  const display_blocks = displayBlocksFromUnits(answerUnits, visible, markdownSelector);
  const text = display_blocks.filter((block) => block.kind === 'text')
    .map((block) => block.text).join("\n\n").trim().slice(0, 2 * 1024 * 1024);
  const turns = answerUnits.map(responseTurnRoot);
  // Only visible tool headings in this verified turn, never tool bodies or reasoning.
  const tool_calls = toolCallsFromTurns(turns, visible, markdownSelector);
  const copyReady = turns.some((turn) => [...turn.querySelectorAll(
    'button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]'
  )].some(visible));
  const streaming = turns.some((turn) => !!turn.querySelector('[data-is-streaming="true"], .result-streaming'));
  const generating = users.length === 1 && (
    turns.some((turn) => !!turn.querySelector('[data-talvt-turn-state="in_progress"]')) ||
    [...document.querySelectorAll(
      'button[data-testid="stop-button"], button[aria-label="Stop"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]'
    )].some(visible)
  );
  const finalAnswer = answerUnits.at(-1) || assistant;
  const finalIds = assistantMessageIdsFromDom(finalAnswer, true);
  const branch = finalIds.length === 1 ? finalIds[0] : "";
  return {
    verified: true, ambiguous: false, message_id: identity,
    branch_message_id: branch, pathname: location.pathname, text,
    turn_message_ids: [...new Set(answerUnits.flatMap(assistantMessageIdsFromDom))],
    complete: !!text && copyReady && !streaming && !generating &&
      (!firstGroup || !!assistantDisplayScope(finalAnswer).querySelector('[data-talvt-turn-state="complete"]')),
    generating, rate_limited: false, tool_calls,
    display_blocks,
  };
})()
