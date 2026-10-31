(() => {
  const conversation = __CONVERSATION__;
  const originalAnswer = __ORIGINAL_ANSWER__;
  const originalPrompt = __ORIGINAL_PROMPT__;
  const allowPartial = __ALLOW_PARTIAL__;
  if (location.origin !== "https://chatgpt.com" ||
      location.pathname !== "/c/" + conversation) return null;
  const visible = (element) => element.getClientRects().length > 0 &&
    getComputedStyle(element).visibility !== "hidden";
  const assistantSelector =
    'main [data-message-author-role="assistant"][data-message-id], main [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids], main [data-content-search-unit-key$=":assistant"]';
  const userSelector =
    'main [data-message-author-role="user"], main [data-chatgpt-search-unit-key$=":user"], main [data-content-search-unit-key$=":user"]';
  const assistants = [...document.querySelectorAll(assistantSelector)].filter(visible);
  const users = [...document.querySelectorAll(userSelector)].filter(visible);
  // An externally continued chat cannot be mistaken for the original single turn.
  if (assistants.length !== 1 || users.length !== 1) return null;
  const normalize = (value) => value.replace(/\u200b/g, "").replace(/\s+/g, " ").trim();
  const expectedPrompt = normalize(originalPrompt);
  const userBody = users[0].querySelector(".whitespace-pre-wrap") || users[0];
  const visiblePrompt = normalize(userBody.innerText || userBody.textContent || "");
  if (expectedPrompt && (originalAnswer ? !visiblePrompt.startsWith(expectedPrompt) : visiblePrompt !== expectedPrompt)) return null;
  const last = assistants[0];
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const roots = [...last.querySelectorAll(markdownSelector)].filter(
    (root) => !root.parentElement?.closest(markdownSelector) && visible(root)
  );
  if (!roots.length) return null;
  const visibleAnswer = normalize(roots.map((root) => root.innerText || root.textContent || "")
    .join("\n\n"));
  const savedAnswer = normalize(originalAnswer);
  if (savedAnswer) {
    if (allowPartial ? !visibleAnswer.startsWith(savedAnswer) : visibleAnswer !== savedAnswer)
      return null;
  } else {
    // Without persisted answer text, the exact original user prompt plus a
    // completed assistant turn must prove the parent. Never trust a placeholder.
    if (!expectedPrompt || !visibleAnswer) return null;
    const turn = last.closest('[data-testid^="conversation-turn-"]') || last;
    const copyReady = [...turn.querySelectorAll('button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]')].some(visible);
    const streaming = turn.matches('[data-is-streaming="true"], .result-streaming') ||
      !!turn.querySelector('[data-is-streaming="true"], .result-streaming');
    const generating = [...document.querySelectorAll('button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]')].some(visible);
    if (!copyReady || streaming || generating) return null;
  }
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const legacy = last.getAttribute("data-message-id");
  if (legacy) return uuid.test(legacy) ? legacy.toLowerCase() : null;
  const raw = last.getAttribute("data-chatgpt-search-message-ids") || last.getAttribute("data-content-search-message-ids") || "";
  try {
    const ids = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
    if (!Array.isArray(ids) || !ids.length ||
        !ids.every((id) => typeof id === "string" && uuid.test(id))) return null;
    const unique = [...new Set(ids.map((id) => id.toLowerCase()))];
    return unique.length === 1 ? unique[0] : null;
  } catch { return null; }
})()
