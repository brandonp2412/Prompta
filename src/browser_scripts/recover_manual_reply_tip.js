(() => {
  const conversation = __CONVERSATION__;
  const previousParent = __PARENT__;
  const expectedUser = __USER_TEXT__;
  const savedAnswer = __ASSISTANT_TEXT__;
  const turns = __TURN_COUNT__;
  if (location.origin !== "https://chatgpt.com" ||
      location.pathname !== "/c/" + conversation || turns < 2) return null;
  const visible = (element) => element.getClientRects().length > 0 &&
    getComputedStyle(element).visibility !== "hidden";
  const assistants = [...document.querySelectorAll(
    'main [data-message-author-role="assistant"][data-message-id], main [data-chatgpt-search-unit-key$=":assistant"][data-chatgpt-search-message-ids]'
  )].filter(visible);
  const users = [...document.querySelectorAll(
    'main [data-message-author-role="user"], main [data-chatgpt-search-unit-key$=":user"]'
  )].filter(visible);
  // The last saved manual reply must be the actual conversation tip.
  if (assistants.length !== turns || users.length !== turns) return null;
  const previous = assistants.at(-2);
  const latest = assistants.at(-1);
  const lastUser = users.at(-1);
  const follows = (earlier, later) =>
    Boolean(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING);
  if (!follows(previous, lastUser) || !follows(lastUser, latest)) return null;
  const normalize = (value) => value.replace(/\s+/g, " ").trim();
  if (normalize(lastUser.innerText || lastUser.textContent || "") !== normalize(expectedUser)) return null;
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const roots = [...latest.querySelectorAll(markdownSelector)].filter(
    (root) => !root.parentElement?.closest(markdownSelector) && visible(root)
  );
  if (savedAnswer) {
    const observed = normalize(roots.map((root) => root.innerText || root.textContent || "").join("\n\n"));
    if (!observed.startsWith(normalize(savedAnswer))) return null;
  }
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const ids = (node) => {
    const legacy = node.getAttribute("data-message-id");
    if (legacy) return uuid.test(legacy) ? [legacy.toLowerCase()] : [];
    const raw = node.getAttribute("data-chatgpt-search-message-ids") || "";
    try {
      const parsed = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
      return Array.isArray(parsed) && parsed.length && parsed.every((id) =>
        typeof id === "string" && uuid.test(id))
        ? [...new Set(parsed.map((id) => id.toLowerCase()))] : [];
    } catch { return []; }
  };
  if (!ids(previous).includes(previousParent.toLowerCase())) return null;
  const candidates = ids(latest);
  return candidates.length === 1 && candidates[0] !== previousParent.toLowerCase()
    ? candidates[0] : null;
})()
