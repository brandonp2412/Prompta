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

// Search units can wrap legacy message nodes. Treat each rendered unit once.
const topLevelResponseNodes = (root, selector) => [...root.querySelectorAll(selector)]
  .filter((node) => !node.parentElement?.closest(selector));
const assistantMessageIdsFromDom = (element) => {
  const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const legacy = element.getAttribute("data-message-id") || "";
  if (legacy) return uuid.test(legacy) ? [legacy.toLowerCase()] : [];
  // A final legacy node inside a modern search unit is stronger evidence than
  // an aggregate list that also contains tool and thought message identities.
  const nested = [...element.querySelectorAll('[data-message-author-role="assistant"][data-message-id]')]
    .map((node) => node.getAttribute?.("data-message-id")).filter(Boolean);
  if (nested.length) return nested.every((id) => uuid.test(id))
    ? [...new Set(nested.map((id) => id.toLowerCase()))] : [];
  const raw = element.getAttribute("data-chatgpt-search-message-ids") || element.getAttribute("data-content-search-message-ids") || "";
  try {
    const ids = raw.trim().startsWith("[") ? JSON.parse(raw) : raw.trim().split(/\s+/);
    return Array.isArray(ids) && ids.length && ids.every((id) => typeof id === "string" && uuid.test(id))
      ? [...new Set(ids.map((id) => id.toLowerCase()))] : [];
  } catch { return []; }
};

// Read visible tool headings only inside the already verified owned response turn.
// Never expand controls, read tool bodies/thoughts, or issue requests.
const responseTurnRoot = (element) =>
  element.closest('[data-testid^="conversation-turn-"]') ||
  element.closest('[data-turn-key]') ||
  element.closest("article") ||
  element.closest(".group.flex.flex-col") ||
  element;

const toolCallsFromTurns = (turns, visible, markdownSelector) => {
  const toolSelector = '[data-testid*="tool-call"], [data-testid*="tool-card"], [data-testid*="tool-result"], [data-tool-name], [aria-label^="Used "]';
  const seen = new Set();
  return turns.flatMap((turn) => [...turn.querySelectorAll(toolSelector + ', button, [role="button"]')]
    .filter((node) => {
      if (seen.has(node) || !visible(node) || node.closest(markdownSelector) ||
          node.parentElement?.closest(toolSelector)) return false;
      // Modern connector disclosures can have only a visible "Used …" label.
      if (!node.matches(toolSelector) && !/^Used\s+\S/i.test(node.textContent?.trim() || "")) return false;
      seen.add(node);
      return true;
    }).map((node) => {
      const heading = node.getAttribute("aria-label") || node.getAttribute("data-tool-name") ||
        node.querySelector('[data-testid*="tool-name"]')?.textContent ||
        node.querySelector('summary, button, [role="button"]')?.textContent ||
        (node.matches('button, [role="button"]') ? node.textContent : "") || "Tool activity";
      const state = node.getAttribute("data-state") || "";
      return { action: heading.trim().slice(0, 120), status: /error|fail/i.test(state) ? "error" :
        /running|loading|pending/i.test(state) ? "running" :
        /complete|success|done/i.test(state) ? "completed" : "observed" };
    })).slice(0, 128);
};
