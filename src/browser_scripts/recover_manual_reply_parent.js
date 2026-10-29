(() => {
  const conversation = __CONVERSATION__;
  const originalAnswer = __ORIGINAL_ANSWER__;
  if (location.origin !== "https://chatgpt.com" ||
      location.pathname !== "/c/" + conversation) return null;
  const visible = (element) => element.getClientRects().length > 0 &&
    getComputedStyle(element).visibility !== "hidden";
  const assistantSelector =
    'main [data-message-author-role="assistant"][data-message-id], main [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids]';
  const userSelector =
    'main [data-message-author-role="user"], main [data-chatgpt-search-unit-key$=":user"]';
  const assistants = [...document.querySelectorAll(assistantSelector)].filter(visible);
  const users = [...document.querySelectorAll(userSelector)].filter(visible);
  // An externally continued chat cannot be mistaken for the original single turn.
  if (assistants.length !== 1 || users.length !== 1) return null;
  const last = assistants[0];
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const roots = [...last.querySelectorAll(markdownSelector)].filter(
    (root) => !root.parentElement?.closest(markdownSelector) && visible(root)
  );
  const normalize = (value) => value.replace(/\s+/g, " ").trim();
  if (!roots.length || normalize(roots.map((root) => root.innerText || root.textContent || "")
    .join("\n\n")) !== normalize(originalAnswer)) return null;
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const legacy = last.getAttribute("data-message-id");
  if (legacy) return uuid.test(legacy) ? legacy.toLowerCase() : null;
  const raw = last.getAttribute("data-chatgpt-search-message-ids") || "";
  try {
    const ids = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
    if (!Array.isArray(ids) || !ids.length ||
        !ids.every((id) => typeof id === "string" && uuid.test(id))) return null;
    const unique = [...new Set(ids.map((id) => id.toLowerCase()))];
    return unique.length === 1 ? unique[0] : null;
  } catch { return null; }
})()
