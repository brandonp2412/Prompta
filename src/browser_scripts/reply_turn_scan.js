// Read only the target user turn and assistant units belonging to its exact branch.
// Never infer a reply from another chat, and never expose hidden thinking or tool bodies.
const scanExactReplyTurn = (conversation, originalPrompt, replyText, parent, allowEarlierTurns = false) => {
  const empty = { verified: false, ambiguous: false, message_id: "", branch_message_id: "",
    latest_branch_message_id: "", pathname: "", text: "", complete: false,
    rate_limited: false, tool_calls: [] };
  if (location.origin !== "https://chatgpt.com" ||
      location.pathname !== "/c/" + conversation) return empty;
  const visible = (node) => node.isConnected && node.getClientRects().length > 0 &&
    getComputedStyle(node).visibility !== "hidden";
  const normalize = (value) => (value || "").replace(/\u200b/g, "")
    .replace(/\s+/g, " ").trim();
  const rateText = [...document.querySelectorAll('[role="alert"], [role="status"], [role="dialog"]')]
    .filter(visible).map((node) => node.textContent || "").join(" ").toLowerCase();
  if (/too many requests|rate limit|try again in|usage cap|wait a few minutes/.test(rateText)) {
    return { ...empty, rate_limited: true };
  }
  const main = document.querySelector("main");
  if (!main) return empty;
  const selector = '[data-message-author-role], [data-chatgpt-search-unit-key], [data-content-search-unit-key]';
  const nodes = [...main.querySelectorAll(selector)].filter((node) =>
    visible(node) && !node.parentElement?.closest(selector)
  ).map((node) => {
    const key = node.getAttribute("data-chatgpt-search-unit-key") ||
      node.getAttribute("data-content-search-unit-key") || "";
    return { node, key, role: node.getAttribute("data-message-author-role") || key.split(":").at(-1) };
  }).filter(({ role }) => role === "user" || role === "assistant");
  const users = nodes.map((item, index) => ({ ...item, index }))
    .filter(({ role }) => role === "user");
  if (users.length < 2 || (!allowEarlierTurns && users.length !== 2)) {
    return { ...empty, ambiguous: users.length > 2 };
  }
  const userText = (item) => {
    const body = item.node.querySelector(".whitespace-pre-wrap") || item.node;
    return normalize(body.innerText || body.textContent);
  };
  const previousUser = users.at(-2);
  const replyUser = users.at(-1);
  if ((!allowEarlierTurns && !normalize(originalPrompt)) ||
      (normalize(originalPrompt) && !userText(users[0]).startsWith(normalize(originalPrompt))) ||
      !normalize(replyText) || userText(replyUser) !== normalize(replyText)) {
    return { ...empty, ambiguous: true };
  }
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const ids = (node) => {
    const legacy = node.getAttribute("data-message-id") || "";
    if (legacy) return uuid.test(legacy) ? [legacy.toLowerCase()] : [];
    const raw = node.getAttribute("data-chatgpt-search-message-ids") ||
      node.getAttribute("data-content-search-message-ids") || "";
    try {
      const parsed = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
      return Array.isArray(parsed) && parsed.length &&
        parsed.every((id) => typeof id === "string" && uuid.test(id))
        ? [...new Set(parsed.map((id) => id.toLowerCase()))] : [];
    } catch { return []; }
  };
  const originalAssistants = nodes.slice(previousUser.index + 1, replyUser.index)
    .filter(({ role }) => role === "assistant");
  if (!originalAssistants.length ||
      !originalAssistants.some(({ node }) => ids(node).includes(parent.toLowerCase()))) {
    return { ...empty, ambiguous: true };
  }
  const later = nodes.slice(replyUser.index + 1);
  if (later.some(({ role }) => role !== "assistant")) return { ...empty, ambiguous: true };
  if (!later.length) return { ...empty, verified: true, pathname: location.pathname,
    verified_parent_id: parent };
  // Modern ChatGPT can render multiple final assistant chunks in one turn.
  // They must share one fallback-turn identity; distinct turns remain ambiguous.
  if (later.length > 1) {
    const group = later[0].key.match(/^(fallback-turn-\d+):\d+:assistant$/)?.[1];
    if (!group || later.some(({ key }) =>
      key.match(/^(fallback-turn-\d+):\d+:assistant$/)?.[1] !== group
    ) || originalAssistants.some(({ key }) => key.startsWith(group + ":"))) {
      return { ...empty, ambiguous: true };
    }
  }
  if (later.some(({ node }) => ids(node).includes(parent.toLowerCase()))) {
    return { ...empty, ambiguous: true };
  }
  const markdownSelector = '.markdown, [data-markdown-text-style="assistant-message"]';
  const segments = later.map(({ node }) => {
    const roots = [...node.querySelectorAll(markdownSelector)].filter((root) =>
      !root.parentElement?.closest(markdownSelector) && visible(root)
    );
    return roots.map(markdownFromRoot).filter(Boolean).join("\n\n").trim();
  });
  const text = segments.filter(Boolean).join("\n\n").trim().slice(0, 2 * 1024 * 1024);
  const after = (earlier, laterNode) => Boolean(
    earlier.compareDocumentPosition(laterNode) & Node.DOCUMENT_POSITION_FOLLOWING
  );
  const copyReady = [...main.querySelectorAll(
    'button[data-testid="copy-turn-action-button"], button[aria-label="Copy"]'
  )].some((button) => visible(button) && after(replyUser.node, button));
  const streaming = later.some(({ node }) =>
    !!node.querySelector('[data-is-streaming="true"], .result-streaming')
  );
  const generating = [...document.querySelectorAll(
    'button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]'
  )].some(visible);
  const lastTextIndex = segments.findLastIndex(Boolean);
  const finalNode = lastTextIndex < 0 ? null : later[lastTextIndex].node;
  const finalIds = finalNode ? ids(finalNode) : [];
  const complete = !!text && copyReady && !streaming && !generating && finalIds.length === 1;
  const toolSelector = '[data-testid*="tool-call"], [data-testid*="tool-card"], [data-testid*="tool-result"], [aria-label^="Used "]';
  const tool_calls = later.flatMap(({ node }) => {
    const turn = node.closest('[data-testid^="conversation-turn-"], article, [data-turn-key], .group.flex.flex-col') ||
      node;
    return [...turn.querySelectorAll(toolSelector)]
      .filter((item) => visible(item) && !item.closest(markdownSelector) &&
        !item.parentElement?.closest(toolSelector));
  }).map((item) => {
    const heading = item.getAttribute("aria-label") || item.getAttribute("data-tool-name") ||
      item.querySelector('[data-testid*="tool-name"]')?.textContent || "Tool activity";
    const state = item.getAttribute("data-state") || "";
    return { action: heading.slice(0, 120), status: /error|fail/i.test(state) ? "error" :
      /running|loading|pending/i.test(state) ? "running" :
      /complete|success|done/i.test(state) ? "completed" : "observed" };
  }).slice(0, 128);
  const first = later[0];
  const identity = first.node.getAttribute("data-message-id") || first.key;
  if (!identity) return { ...empty, ambiguous: true };
  return { ...empty, verified: true, message_id: identity,
    branch_message_id: complete ? finalIds[0] : "",
    latest_branch_message_id: finalIds.length === 1 ? finalIds[0] : "",
    verified_parent_id: parent, pathname: location.pathname,
    text, complete, tool_calls };
};
