import {
  formatClockTime12Hour,
  pythonToolCallCode,
  replaceChatGptRichMarkers,
  toolCallDisplayName,
  toolCallHasUsefulDetail,
  toolCallIsInvocationPlaceholder,
  toolCallSummary,
  toolCallTimestampMillis,
} from "./clientLogic";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const LANGUAGE_ALIASES = {
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  ts: "typescript",
  tsx: "typescript",
  py: "python",
  sh: "bash",
  shell: "bash",
  zsh: "bash",
  yml: "yaml",
  c: "cpp",
  cxx: "cpp",
  h: "cpp",
  hpp: "cpp",
  html: "markup",
  xml: "markup",
  svg: "markup",
  md: "markdown",
};

const CODE_KEYWORDS = {
  javascript: new Set(
    "as async await break case catch class const continue default delete do else export extends false finally for from function get if import in instanceof let new null of return set static super switch this throw true try typeof undefined var void while yield".split(
      " ",
    ),
  ),
  typescript: new Set(
    "abstract any as async await boolean break case catch class const constructor continue declare default do else enum export extends false finally for from function get if implements import in infer instanceof interface keyof let namespace never new null number object of private protected public readonly return satisfies set static string super switch symbol this throw true try type typeof undefined unknown var void while yield".split(
      " ",
    ),
  ),
  python: new Set(
    "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield".split(
      " ",
    ),
  ),
  bash: new Set(
    "case do done elif else esac export fi for function if in local readonly return select then time until while".split(
      " ",
    ),
  ),
  cpp: new Set(
    "auto bool break case catch char class const constexpr continue default delete do double else enum explicit extern false float for friend if inline int long namespace new nullptr operator private protected public return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using virtual void volatile while".split(
      " ",
    ),
  ),
  dart: new Set(
    "abstract as assert async await break case catch class const continue default deferred do dynamic else enum export extends extension external factory false final finally for Function get hide if implements import in interface is late library mixin new null of on operator part required rethrow return set show static super switch sync this throw true try typedef var void while with yield".split(
      " ",
    ),
  ),
  sql: new Set(
    "ADD ALL ALTER AND ANY AS ASC BETWEEN BY CASE CHECK COLUMN CONSTRAINT CREATE DATABASE DEFAULT DELETE DESC DISTINCT DROP ELSE END EXISTS FOREIGN FROM FULL GROUP HAVING IN INDEX INNER INSERT INTO IS JOIN KEY LEFT LIKE LIMIT NOT NULL OR ORDER OUTER PRIMARY RIGHT SELECT SET TABLE UNION UNIQUE UPDATE VALUES VIEW WHEN WHERE WITH".split(
      " ",
    ),
  ),
  json: new Set(["true", "false", "null"]),
};

function normalizeLanguage(language) {
  const raw = String(language || "")
    .trim()
    .toLowerCase()
    .split(/\s+/)[0];

  return LANGUAGE_ALIASES[raw] || raw || "code";
}

function syntaxToken(className, value) {
  return `<span class="syntax-${className}">${escapeHtml(value)}</span>`;
}

function highlightCode(raw, language) {
  const source = String(raw || "");
  const normalized = normalizeLanguage(language);
  const keywords = CODE_KEYWORDS[normalized] || new Set();
  const sql = normalized === "sql";
  const hashComments = ["python", "bash", "yaml"].includes(normalized);
  let html = "";
  let index = 0;

  while (index < source.length) {
    if (normalized === "markup" && source.startsWith("<!--", index)) {
      const end = source.indexOf("-->", index + 4);
      const next = end < 0 ? source.length : end + 3;
      html += syntaxToken("comment", source.slice(index, next));
      index = next;
      continue;
    }

    if (source.startsWith("/*", index)) {
      const end = source.indexOf("*/", index + 2);
      const next = end < 0 ? source.length : end + 2;
      html += syntaxToken("comment", source.slice(index, next));
      index = next;
      continue;
    }

    if (source.startsWith("//", index) && normalized !== "json") {
      const end = source.indexOf("\n", index + 2);
      const next = end < 0 ? source.length : end;
      html += syntaxToken("comment", source.slice(index, next));
      index = next;
      continue;
    }

    if (hashComments && source[index] === "#") {
      const end = source.indexOf("\n", index + 1);
      const next = end < 0 ? source.length : end;
      html += syntaxToken("comment", source.slice(index, next));
      index = next;
      continue;
    }

    const quote = source[index];

    if (quote === '"' || quote === "'" || quote === "`") {
      let cursor = index + 1;

      while (cursor < source.length) {
        if (source[cursor] === "\\") {
          cursor += 2;
          continue;
        }

        if (source[cursor] === quote) {
          cursor += 1;
          break;
        }

        cursor += 1;
      }

      const value = source.slice(index, cursor);
      const property = normalized === "json" && /^\s*:/.test(source.slice(cursor));
      html += syntaxToken(property ? "property" : "string", value);
      index = cursor;
      continue;
    }

    const number = source
      .slice(index)
      .match(/^-?(?:0x[\da-f]+|0b[01]+|\d+(?:\.\d+)?(?:e[+-]?\d+)?)/i);

    if (number) {
      html += syntaxToken("number", number[0]);
      index += number[0].length;
      continue;
    }

    if (/[A-Za-z_$]/.test(source[index])) {
      let cursor = index + 1;

      while (/[A-Za-z0-9_$]/.test(source[cursor] || "")) cursor += 1;

      const value = source.slice(index, cursor);
      const lookup = sql ? value.toUpperCase() : value;

      if (keywords.has(lookup)) html += syntaxToken("keyword", value);
      else if (/^\s*\(/.test(source.slice(cursor))) html += syntaxToken("function", value);
      else html += escapeHtml(value);

      index = cursor;
      continue;
    }

    html += /[[\]{}(),.:;]/.test(source[index])
      ? syntaxToken("punctuation", source[index])
      : escapeHtml(source[index]);
    index += 1;
  }

  return html;
}

function inlineMarkdown(text) {
  const placeholders: Array<[string, string]> = [];
  let source = String(text || "");
  const stash = (html) => {
    let token = `\uE000PROMPTA_INLINE_${placeholders.length}\uE001`;

    while (source.includes(token)) token += "\uE002";

    placeholders.push([token, html]);

    return token;
  };
  source = replaceChatGptRichMarkers(source, (label, url) =>
    stash(
      `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(label)}</a>`,
    ),
  );
  source = source.replace(/`([^`\n]+)`/g, (_, code) =>
    stash(`<code class="inline-code">${escapeHtml(code)}</code>`),
  );
  source = source.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)(?:\s+"[^"]*")?\)/g, (_, label, url) =>
    stash(
      `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(label)}</a>`,
    ),
  );
  let html = escapeHtml(source);
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
  html = html.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
  html = html.replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g, "$1<em>$2</em>");

  for (const [token, value] of placeholders) html = html.replaceAll(token, value);

  return html;
}

function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderListItem(content) {
  const task = content.match(/^\[([ xX])\]\s+(.+)$/);

  if (!task) return `<li>${inlineMarkdown(content)}</li>`;

  const checked = task[1].toLowerCase() === "x";

  return `<li class="task-item"><input type="checkbox" disabled${checked ? " checked" : ""}> <span>${inlineMarkdown(task[2])}</span></li>`;
}

function listLine(line) {
  const match = line.match(/^(\s*)([-+*]|\d+[.)])\s+(.+)$/);

  if (!match) return null;

  return {
    indent: match[1].replace(/\t/g, "    ").length,
    ordered: /^\d/.test(match[2]),
    content: match[3],
  };
}

function renderListBlock(lines, startIndex, baseIndent = null) {
  const first = listLine(lines[startIndex]);

  if (!first) return { html: "", index: startIndex };

  const indent = baseIndent ?? first.indent;
  const ordered = first.ordered;
  const tag = ordered ? "ol" : "ul";
  const items: string[] = [];
  let index = startIndex;

  while (index < lines.length) {
    const current = listLine(lines[index]);

    if (!current || current.indent < indent) break;

    if (current.indent === indent && current.ordered !== ordered) break;

    if (current.indent > indent) {
      if (!items.length) break;

      const nested = renderListBlock(lines, index, current.indent);

      if (!nested.html || nested.index === index) break;

      items[items.length - 1] = items[items.length - 1].replace(/<\/li>$/, `${nested.html}</li>`);
      index = nested.index;
      continue;
    }

    items.push(renderListItem(current.content));
    index += 1;
  }

  return { html: `<${tag}>${items.join("")}</${tag}>`, index };
}

function renderTextBlock(text) {
  const lines = String(text || "")
    .replace(/\r/g, "")
    .split("\n");
  const out: string[] = [];
  let index = 0;
  const startsBlock = (line, next = "") =>
    !line.trim() ||
    /^(#{1,6})\s+/.test(line) ||
    /^\s*([-+*]|\d+[.)])\s+/.test(line) ||
    /^\s*>\s?/.test(line) ||
    /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line) ||
    (line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(next));

  while (index < lines.length) {
    const line = lines[index];
    const next = lines[index + 1] || "";

    if (!line.trim()) {
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);

    if (heading) {
      const level = heading[1].length;
      out.push(`<h${level}>${inlineMarkdown(heading[2].replace(/\s+#+\s*$/, ""))}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      out.push("<hr>");
      index += 1;
      continue;
    }

    if (line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(next)) {
      const headers = splitTableRow(line);
      const aligns = splitTableRow(next).map((cell) => {
        const left = cell.startsWith(":");
        const right = cell.endsWith(":");

        return left && right ? "center" : right ? "right" : left ? "left" : "";
      });
      index += 2;
      const rows: string[][] = [];

      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }

      const tableScrollClass =
        headers.length >= 3 ? "table-scroll table-scroll-wide" : "table-scroll";
      out.push(
        `<div class="${tableScrollClass}"><table><thead><tr>${headers
          .map(
            (cell, column) =>
              `<th${aligns[column] ? ` style="text-align:${aligns[column]}"` : ""}>${inlineMarkdown(cell)}</th>`,
          )
          .join("")}</tr></thead><tbody>${rows
          .map(
            (row) =>
              `<tr>${headers
                .map(
                  (_, column) =>
                    `<td${aligns[column] ? ` style="text-align:${aligns[column]}"` : ""}>${inlineMarkdown(row[column] || "")}</td>`,
                )
                .join("")}</tr>`,
          )
          .join("")}</tbody></table></div>`,
      );
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quoted: string[] = [];

      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quoted.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }

      out.push(`<blockquote>${renderTextBlock(quoted.join("\n"))}</blockquote>`);
      continue;
    }

    const list = listLine(line);

    if (list) {
      const rendered = renderListBlock(lines, index);
      out.push(rendered.html);
      index = rendered.index;
      continue;
    }

    const paragraph = [line.trim()];
    index += 1;

    while (index < lines.length && !startsBlock(lines[index], lines[index + 1] || "")) {
      paragraph.push(lines[index].trim());
      index += 1;
    }

    out.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
  }

  return out.join("");
}

const CONTEXTUAL_TOOL_ACTION = /(?:^|_)(?:repl|execute|shell|python|command)(?:_|$)/i;

function expandedToolMetaAddsInformation(summary, action, connector) {
  if (!action) return false;

  if (summary) return true;

  return Boolean(connector && CONTEXTUAL_TOOL_ACTION.test(action));
}

function renderCodeBlock(code, language) {
  const rawLanguage = String(language || "").trim();
  const normalized = normalizeLanguage(rawLanguage);
  const toolMatch = rawLanguage.match(/^(?:tool|tool-call|function|function-call)(?::\s*(.+))?$/i);
  const inlineToolMatch = code.match(/^\s*(?:tool|function|to)\s*[:=]\s*([\w.-]+)/i);
  const toolish = Boolean(toolMatch || inlineToolMatch);
  const rawToolName = toolMatch?.[1]?.trim() || inlineToolMatch?.[1] || "";
  const toolName = toolCallDisplayName(rawToolName);
  const trimmedCode = code.trim();
  const genericToolInvocation = toolish && toolCallIsInvocationPlaceholder(trimmedCode);
  const hasUsefulToolDetail = !toolish || toolCallHasUsefulDetail(trimmedCode);

  if (toolish && !toolName && !hasUsefulToolDetail && !genericToolInvocation) return "";

  const pythonCode = toolish ? pythonToolCallCode(rawToolName, trimmedCode) : "";
  const toolSummary = toolish ? toolCallSummary(trimmedCode) : "";
  const toolTimestamp = toolish ? toolCallTimestampMillis(trimmedCode) : null;
  const toolTimeText = toolTimestamp === null ? "" : formatClockTime12Hour(toolTimestamp, true);
  const toolTime =
    toolTimestamp === null
      ? ""
      : `<time class="tool-time" datetime="${new Date(toolTimestamp).toISOString()}">${escapeHtml(toolTimeText)}</time>`;
  const renderedCode =
    pythonCode || (toolish && (!hasUsefulToolDetail || genericToolInvocation) ? "" : code);
  const highlightLanguage = pythonCode
    ? "python"
    : toolish
      ? trimmedCode.startsWith("{") || trimmedCode.startsWith("[")
        ? "json"
        : "code"
      : normalized;
  const label = pythonCode ? "python" : toolish ? "tool call" : rawLanguage || "code";
  const copyButton = renderedCode.trim()
    ? '<button type="button" class="copy-code">copy</button>'
    : "";
  const collapsedLabel = toolish && toolName ? toolName : label;
  const header = toolish
    ? toolSummary
      ? `<span class="tool-summary">${escapeHtml(toolSummary)}</span>${toolTime}`
      : `
        <span class="${toolName ? "tool-primary-name" : "code-language"}">${escapeHtml(collapsedLabel)}</span>
        ${toolTime}`
    : `
      <span class="code-language">${escapeHtml(label)}</span>
      ${copyButton}`;
  const body = renderedCode.trim()
    ? `<pre><code class="language-${escapeHtml(highlightLanguage)}">${highlightCode(renderedCode, highlightLanguage)}</code></pre>`
    : "";

  if (toolish) {
    const toolIdentityParts = toolName.split(/\s*·\s*/).filter(Boolean);
    const expandedAction =
      toolIdentityParts.length > 1 ? toolIdentityParts[toolIdentityParts.length - 1] : toolName;
    const expandedConnector =
      toolIdentityParts.length > 1 ? toolIdentityParts.slice(0, -1).join(" · ") : "";
    const expandedToolHeader = expandedToolMetaAddsInformation(
      toolSummary,
      expandedAction,
      expandedConnector,
    )
      ? `<div class="tool-expanded-meta"><span class="tool-expanded-action">${escapeHtml(expandedAction)}</span>${expandedConnector ? `<span class="tool-expanded-separator">|</span><span class="tool-expanded-connector">${escapeHtml(expandedConnector)}</span>` : ""}</div>`
      : "";

    return `
      <details class="code-block tool-call-block${toolSummary ? " tool-has-summary" : ""}${expandedToolHeader ? " tool-has-meta" : ""}">
        <summary class="code-header">${header}</summary>
        ${expandedToolHeader}
        ${body}
      </details>`;
  }

  return `
    <div class="code-block">
      <div class="code-header">${header}</div>
      ${body}
    </div>`;
}

export function renderMarkdown(raw) {
  const source = String(raw || "");
  const pattern = /^ {0,3}```([^\n`]*)\r?\n([\s\S]*?)^ {0,3}```[ \t]*\r?$/gm;
  let lastIndex = 0;
  let html = "";
  let match;

  while ((match = pattern.exec(source)) !== null) {
    html += renderTextBlock(source.slice(lastIndex, match.index));
    const language = match[1].trim() || "code";
    const code = match[2].replace(/\n$/, "");
    html += renderCodeBlock(code, language);
    lastIndex = pattern.lastIndex;
  }

  html += renderTextBlock(source.slice(lastIndex));

  return html || "<p></p>";
}
