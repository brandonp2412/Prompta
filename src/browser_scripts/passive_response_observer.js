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
  const markdownFromRoot = (root) => {
    if (!root.childNodes) return root.innerText || root.textContent || "";
    const escape = (value) => value.replace(/\\/g, "\\\\").replace(/([`*_[\]|])/g, "\\$1");
    const ignored = new Set(["SCRIPT", "STYLE", "BUTTON", "SVG", "NOSCRIPT"]);
    const blockTags = new Set([
      "P", "DIV", "SECTION", "ARTICLE", "H1", "H2", "H3", "H4", "H5", "H6",
      "UL", "OL", "PRE", "BLOCKQUOTE", "TABLE", "HR",
    ]);
    const allowedNode = (node) => node.nodeType !== 1 ||
      (!ignored.has(node.tagName) && !node.hidden && node.getAttribute("aria-hidden") !== "true");
    const fenceFor = (value, minimum) => {
      const runs = value.match(/`+/g) || [];
      return "`".repeat(Math.max(minimum, ...runs.map((run) => run.length + 1)));
    };
    const inline = (node) => {
      if (node.nodeType === 3) return escape((node.nodeValue || "").replace(/\s+/g, " "));
      if (node.nodeType !== 1 || !allowedNode(node)) return "";
      const tag = node.tagName.toLowerCase();
      if (tag === "br") return "\n";
      if (tag === "img") return escape(node.getAttribute("alt") || "");
      if (tag === "code") {
        const value = node.textContent || "";
        const fence = fenceFor(value, 1);
        const pad = value.startsWith("`") || value.endsWith("`") ? " " : "";
        return `${fence}${pad}${value}${pad}${fence}`;
      }
      const content = [...node.childNodes].map(inline).join("");
      if (tag === "strong" || tag === "b") return `**${content.trim()}**`;
      if (tag === "em" || tag === "i") return `*${content.trim()}*`;
      if (tag === "del" || tag === "s") return `~~${content.trim()}~~`;
      if (tag === "a") {
        const href = node.getAttribute("href") || "";
        try {
          const url = new URL(href, location.href);
          if (url.protocol === "https:" || url.protocol === "http:") {
            return `[${content.trim()}](${url.href.replace(/\(/g, "%28").replace(/\)/g, "%29")})`;
          }
        } catch {}
      }
      return content;
    };
    const groupedChildren = (element) => {
      const sections = [];
      let current = "";
      const flush = () => {
        if (current.trim()) sections.push(current.trim());
        current = "";
      };
      for (const child of element.childNodes) {
        if (!allowedNode(child)) continue;
        if (child.nodeType === 1 && blockTags.has(child.tagName)) {
          flush();
          const value = block(child);
          if (value) sections.push(value);
        } else {
          current += inline(child);
        }
      }
      flush();
      return sections.join("\n\n");
    };
    const list = (element) => {
      const ordered = element.tagName === "OL";
      const start = Number(element.getAttribute("start")) || 1;
      return [...element.children].filter((child) => child.tagName === "LI").map((li, index) => {
        const nested = [];
        const text = [];
        for (const child of li.childNodes) {
          if (child.nodeType === 1 && (child.tagName === "UL" || child.tagName === "OL")) {
            nested.push(list(child));
          } else if (child.nodeType === 1 && blockTags.has(child.tagName)) {
            text.push(block(child));
          } else {
            text.push(inline(child));
          }
        }
        const marker = ordered ? `${start + index}. ` : "- ";
        return marker + text.join(" ").trim().replace(/\n\n/g, "\n  ") +
          (nested.length ? "\n" + nested.join("\n").split("\n").map((line) => "  " + line).join("\n") : "");
      }).join("\n");
    };
    const table = (element) => {
      const rows = [...element.querySelectorAll("tr")].map((tr) =>
        [...tr.children].filter((cell) => cell.tagName === "TD" || cell.tagName === "TH")
          .map((cell) => inline(cell).replace(/\n/g, " ").trim()),
      ).filter((cells) => cells.length);
      if (!rows.length) return "";
      const columns = Math.max(...rows.map((cells) => cells.length));
      const formatRow = (cells) => "| " + Array.from({ length: columns }, (_, i) => cells[i] || "").join(" | ") + " |";
      return [formatRow(rows[0]), formatRow(Array(columns).fill("---")), ...rows.slice(1).map(formatRow)].join("\n");
    };
    const block = (node) => {
      if (node.nodeType !== 1) return inline(node).trim();
      if (!allowedNode(node)) return "";
      const tag = node.tagName.toLowerCase();
      if (/^h[1-6]$/.test(tag)) return `${"#".repeat(Number(tag[1]))} ${inline(node).trim()}`;
      if (tag === "p") return inline(node).trim();
      if (tag === "ul" || tag === "ol") return list(node);
      if (tag === "table") return table(node);
      if (tag === "hr") return "---";
      if (tag === "pre") {
        const code = node.querySelector("code");
        const value = (code || node).textContent || "";
        const language = (code?.className || "").match(/(?:^|\s)language-([\w+#.-]+)/)?.[1] || "";
        const fence = fenceFor(value, 3);
        return `${fence}${language}\n${value.replace(/\n+$/, "")}\n${fence}`;
      }
      if (tag === "blockquote") {
        return groupedChildren(node).split("\n").map((line) => line ? "> " + line : ">").join("\n");
      }
      return groupedChildren(node);
    };
    return block(root).trim();
  };
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