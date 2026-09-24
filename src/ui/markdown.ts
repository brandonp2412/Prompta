import bash from "highlight.js/lib/languages/bash";
import cpp from "highlight.js/lib/languages/cpp";
import dart from "highlight.js/lib/languages/dart";
import diff from "highlight.js/lib/languages/diff";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import markdown from "highlight.js/lib/languages/markdown";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";
import type { RootContent } from "hast";
import { createLowlight } from "lowlight";
import { marked, type Token, type Tokens } from "marked";

import { extractToolCodeDiff, type ToolCodeDiff } from "./diffPreview";
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

const lowlight = createLowlight();
lowlight.register({
  bash,
  cpp,
  dart,
  diff,
  javascript,
  json,
  markdown,
  python,
  sql,
  typescript,
  xml,
  yaml,
});
lowlight.registerAlias({
  bash: ["sh", "shell", "zsh"],
  cpp: ["c", "cxx", "h", "hpp"],
  javascript: ["js", "jsx", "mjs", "cjs"],
  markdown: ["md"],
  diff: ["patch"],
  python: ["py"],
  typescript: ["ts", "tsx"],
  xml: ["html", "svg"],
  yaml: ["yml"],
});

export type MarkdownDocument = Token[];

const MARKDOWN_CACHE_MAX_ENTRIES = 192;
const MARKDOWN_CACHE_MAX_SOURCE_CHARS = 1_000_000;
const markdownCache = new Map<string, { document: MarkdownDocument; sourceChars: number }>();
let markdownCacheSourceChars = 0;

const HIGHLIGHT_CACHE_MAX_ENTRIES = 128;
const HIGHLIGHT_CACHE_MAX_CODE_CHARS = 512_000;
const highlightCache = new Map<string, { nodes: RootContent[]; codeChars: number }>();
let highlightCacheCodeChars = 0;

function promoteCacheEntry<T>(cache: Map<string, T>, key: string, value: T) {
  cache.delete(key);
  cache.set(key, value);
}

function evictCacheEntries<T extends { sourceChars?: number; codeChars?: number }>(
  cache: Map<string, T>,
  maxEntries: number,
  currentChars: number,
  incomingChars: number,
  maxChars: number,
) {
  let chars = currentChars;

  while (cache.size && (cache.size >= maxEntries || chars + incomingChars > maxChars)) {
    const oldestKey = cache.keys().next().value;
    if (oldestKey === undefined) break;

    const oldest = cache.get(oldestKey);
    cache.delete(oldestKey);
    chars -= oldest?.sourceChars ?? oldest?.codeChars ?? 0;
  }

  return chars;
}

export type ToolPresentation = {
  name: string;
  summary: string;
  action: string;
  connector: string;
  time: { text: string; iso: string } | null;
  hasMeta: boolean;
  diff: ToolCodeDiff | null;
};

export type CodePresentation = {
  code: string;
  language: string;
  label: string;
  highlight: boolean;
  highlighted: RootContent[];
  tool: ToolPresentation | null;
};

function escapeMarkdownLabel(value: string) {
  return value.replaceAll("\\", "\\\\").replaceAll("[", "\\[").replaceAll("]", "\\]");
}

function richMarkersToMarkdown(value: unknown) {
  return replaceChatGptRichMarkers(value, (label, url) => {
    const safeUrl = url.replaceAll(">", "%3E");

    return `[${escapeMarkdownLabel(label)}](<${safeUrl}>)`;
  });
}

function incompleteFenceStart(source: string) {
  const pattern = /^ {0,3}```[^\n]*(?:\n|$)/gm;
  let openAt = -1;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(source)) !== null) {
    openAt = openAt < 0 ? match.index : -1;
  }

  return openAt;
}

function lexMarkdown(source: string, renderIncompleteFence: boolean): MarkdownDocument {
  const openFenceAt = incompleteFenceStart(source);

  if (openFenceAt >= 0) {
    if (renderIncompleteFence) {
      source += "\n```";
    } else {
      const prefix = marked.lexer(source.slice(0, openFenceAt), {
        async: false,
        breaks: false,
        gfm: true,
      });
      const remainder = source.slice(openFenceAt);

      return [
        ...prefix,
        {
          type: "paragraph",
          raw: remainder,
          text: remainder,
          tokens: [{ type: "text", raw: remainder, text: remainder }],
        } satisfies Tokens.Paragraph,
      ];
    }
  }

  return marked.lexer(source, {
    async: false,
    breaks: false,
    gfm: true,
  });
}

export function parseMarkdown(
  raw: unknown,
  { renderIncompleteFence = false }: { renderIncompleteFence?: boolean } = {},
): MarkdownDocument {
  const source = richMarkersToMarkdown(raw);

  if (renderIncompleteFence || source.length > MARKDOWN_CACHE_MAX_SOURCE_CHARS) {
    return lexMarkdown(source, renderIncompleteFence);
  }

  const cached = markdownCache.get(source);
  if (cached) {
    promoteCacheEntry(markdownCache, source, cached);
    return cached.document;
  }

  const document = lexMarkdown(source, false);
  markdownCacheSourceChars = evictCacheEntries(
    markdownCache,
    MARKDOWN_CACHE_MAX_ENTRIES,
    markdownCacheSourceChars,
    source.length,
    MARKDOWN_CACHE_MAX_SOURCE_CHARS,
  );
  markdownCache.set(source, { document, sourceChars: source.length });
  markdownCacheSourceChars += source.length;
  return document;
}

function normalizedLanguage(value: string | null | undefined) {
  const raw = String(value || "")
    .trim()
    .toLowerCase()
    .split(/\s+/)[0];

  const aliases: Record<string, string> = {
    c: "c",
    cjs: "javascript",
    cxx: "cpp",
    h: "c",
    hpp: "cpp",
    html: "xml",
    js: "javascript",
    jsx: "javascript",
    md: "markdown",
    mjs: "javascript",
    py: "python",
    sh: "bash",
    shell: "bash",
    svg: "xml",
    ts: "typescript",
    tsx: "typescript",
    xml: "xml",
    yml: "yaml",
    zsh: "bash",
  };

  return aliases[raw] || raw || "plaintext";
}

export function highlightedCode(code: string, language: string): RootContent[] {
  if (!code) return [];

  const normalized = normalizedLanguage(language);

  if (!lowlight.registered(normalized)) return [{ type: "text", value: code }];

  const key = `${normalized}\u0000${code}`;
  const cached = highlightCache.get(key);
  if (cached) {
    promoteCacheEntry(highlightCache, key, cached);
    return cached.nodes;
  }

  let nodes: RootContent[];
  try {
    nodes = lowlight.highlight(normalized, code).children;
  } catch {
    nodes = [{ type: "text", value: code }];
  }

  if (code.length <= HIGHLIGHT_CACHE_MAX_CODE_CHARS) {
    highlightCacheCodeChars = evictCacheEntries(
      highlightCache,
      HIGHLIGHT_CACHE_MAX_ENTRIES,
      highlightCacheCodeChars,
      code.length,
      HIGHLIGHT_CACHE_MAX_CODE_CHARS,
    );
    highlightCache.set(key, { nodes, codeChars: code.length });
    highlightCacheCodeChars += code.length;
  }

  return nodes;
}

export function codePresentation(token: Tokens.Code): CodePresentation | null {
  const rawLanguage = String(token.lang || "").trim();
  const language = normalizedLanguage(rawLanguage);
  const toolMatch = rawLanguage.match(/^(?:tool|tool-call|function|function-call)(?::\s*(.+))?$/i);
  const inlineToolMatch = token.text.match(/^\s*(?:tool|function|to)\s*[:=]\s*([\w.-]+)/i);
  const toolish = Boolean(toolMatch || inlineToolMatch);
  const extracted = toolish
    ? extractToolCodeDiff(token.text)
    : { code: token.text, diff: null as ToolCodeDiff | null };
  const toolCode = extracted.code.trim();
  const rawToolName = toolMatch?.[1]?.trim() || inlineToolMatch?.[1] || "";
  const toolName = toolCallDisplayName(rawToolName);
  const genericToolInvocation = toolish && toolCallIsInvocationPlaceholder(toolCode);
  const hasUsefulToolDetail = !toolish || toolCallHasUsefulDetail(toolCode);

  if (toolish && !toolName && !hasUsefulToolDetail && !genericToolInvocation) return null;

  const pythonCode = toolish ? pythonToolCallCode(rawToolName, toolCode) : "";
  const code =
    pythonCode ||
    (toolish && (!hasUsefulToolDetail || genericToolInvocation) ? "" : extracted.code);
  const highlightLanguage = pythonCode
    ? "python"
    : toolish
      ? toolCode.startsWith("{") || toolCode.startsWith("[")
        ? "json"
        : "plaintext"
      : language;
  const label = pythonCode ? "python" : toolish ? "tool call" : rawLanguage || "code";

  if (!toolish) {
    return {
      code,
      language: highlightLanguage,
      label,
      highlight: true,
      highlighted: highlightedCode(code, highlightLanguage),
      tool: null,
    };
  }

  const summary = toolCallSummary(toolCode);
  const timestamp = toolCallTimestampMillis(toolCode);
  const parts = toolName.split(/\s*·\s*/).filter(Boolean);
  const action = parts.length > 1 ? parts[parts.length - 1] : toolName;
  const connector = parts.length > 1 ? parts.slice(0, -1).join(" · ") : "";

  return {
    code,
    language: highlightLanguage,
    label,
    highlight: Boolean(pythonCode),
    highlighted: pythonCode
      ? highlightedCode(code, highlightLanguage)
      : [{ type: "text", value: code }],
    tool: {
      name: toolName,
      summary,
      action,
      connector,
      time:
        timestamp === null
          ? null
          : {
              text: formatClockTime12Hour(timestamp, true),
              iso: new Date(timestamp).toISOString(),
            },
      hasMeta: Boolean(summary && action),
      diff: extracted.diff,
    },
  };
}

export function safeLinkHref(value: string | null | undefined) {
  const href = String(value || "").trim();

  return /^https?:\/\//i.test(href) ? href : "";
}
