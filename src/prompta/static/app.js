// src/prompta/ui/clientLogic.ts
function sidebarPreviewText(value) {
  return String(value || "").replace(/```(?:tool|tool-call|function|function-call)(?::[^\n\x60]*)?\n?[\s\S]*?```/gi, " ").replace(/\s+/g, " ").trim();
}
function matchingOptimisticConversation(chats, pending) {
  if (!pending)
    return null;
  if (pending.conversationId) {
    const exact = chats.find((chat) => chat.id === pending.conversationId);
    if (exact)
      return exact;
  }
  const prompt = String(pending.message || "").trim();
  if (!prompt)
    return null;
  const createdAt = Number(pending.createdAt || 0);
  return chats.find((chat) => {
    if (String(chat.prompt || "").trim() !== prompt)
      return false;
    const chatCreatedAt = Number(chat.created_at || 0);
    return !createdAt || !chatCreatedAt || Math.abs(chatCreatedAt - createdAt) <= 30;
  }) || null;
}
function parseScheduleSlashCommand(message) {
  if (!message.startsWith("/every"))
    return null;
  const match = message.match(/^\/every\s+(\d+(?:\.\d+)?)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours)?\s+([\s\S]+)$/i);
  if (!match) {
    return { error: "Use /every <minutes> <prompt>, for example: /every 30 fix bugs" };
  }
  const amount = Number(match[1]);
  const unit = String(match[2] || "m").toLowerCase();
  const intervalMinutes = amount * (unit.startsWith("h") ? 60 : 1);
  const prompt = match[3].trim();
  if (!Number.isFinite(intervalMinutes) || intervalMinutes <= 0 || !prompt) {
    return { error: "Schedule interval and prompt are required." };
  }
  return { intervalMinutes, prompt };
}
function formatScheduleInterval(minutes) {
  if (minutes >= 60 && minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}
function parseAtSlashCommand(message, now = new Date) {
  if (!message.startsWith("/at"))
    return null;
  const match = message.match(/^\/at\s+(today|tomorrow|\d{4}-\d{2}-\d{2})(?:[T\s]+)([01]\d|2[0-3]):([0-5]\d)\s+([\s\S]+)$/i);
  if (!match) {
    return {
      error: "Use /at <date> <time> <prompt>, for example: /at 2026-09-21 09:30 review failures"
    };
  }
  const dateToken = match[1].toLowerCase();
  const hour = Number(match[2]);
  const minute = Number(match[3]);
  const prompt = match[4].trim();
  let target;
  if (dateToken === "today" || dateToken === "tomorrow") {
    target = new Date(now);
    if (dateToken === "tomorrow")
      target.setDate(target.getDate() + 1);
    target.setHours(hour, minute, 0, 0);
  } else {
    const parts = dateToken.split("-").map(Number);
    target = new Date(parts[0], parts[1] - 1, parts[2], hour, minute, 0, 0);
    if (target.getFullYear() !== parts[0] || target.getMonth() !== parts[1] - 1 || target.getDate() !== parts[2]) {
      return { error: "Schedule date is invalid." };
    }
  }
  if (!prompt)
    return { error: "Schedule prompt is required." };
  const runAtEpoch = target.getTime() / 1000;
  if (!Number.isFinite(runAtEpoch) || runAtEpoch <= now.getTime() / 1000) {
    return { error: "Schedule time must be in the future." };
  }
  const runAtLabel = target.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
  return { runAtEpoch, runAtLabel, prompt };
}

// src/prompta/ui/app.ts
var PINNED_CHATS_KEY = "prompta:pinned-chats";
function loadPinnedIds() {
  try {
    const stored = JSON.parse(localStorage.getItem(PINNED_CHATS_KEY) || "[]");
    return new Set(Array.isArray(stored) ? stored.map((id) => String(id)) : []);
  } catch {
    return new Set;
  }
}
function savePinnedIds() {
  try {
    localStorage.setItem(PINNED_CHATS_KEY, JSON.stringify(Array.from(state.pinnedIds)));
  } catch {}
}
var state = {
  chats: [],
  selectedId: null,
  selectedUpdatedAt: null,
  selectedFingerprint: "",
  search: "",
  sidebarFingerprint: "",
  refreshTimer: null,
  mode: "chats",
  logFingerprint: "",
  logRefreshTimer: null,
  sending: false,
  composingNew: false,
  pendingNewId: null,
  pendingNewSend: null,
  pendingReplies: new Map,
  newChatFingerprint: "",
  selectedMetaFingerprint: "",
  chatsRequestId: 0,
  selectedRequestId: 0,
  selectedChat: null,
  optimisticSequence: 0,
  serverName: "",
  serverOnline: null,
  chatStatuses: new Map,
  statusBaselineReady: false,
  attachments: [],
  pinnedIds: loadPinnedIds()
};
function syncViewportHeight() {
  const viewportHeight = window.visualViewport?.height || window.innerHeight;
  document.documentElement.style.setProperty("--app-height", `${Math.round(viewportHeight)}px`);
}
syncViewportHeight();
window.setTimeout(() => document.documentElement.classList.remove("booting"), 1200);
window.addEventListener("resize", syncViewportHeight);
window.visualViewport?.addEventListener("resize", syncViewportHeight);
function requiredElement(selector) {
  const element = document.querySelector(selector);
  if (!element)
    throw new Error(`Missing required UI element: ${selector}`);
  return element;
}
var els = {
  chatList: requiredElement("#chatList"),
  searchInput: requiredElement("#searchInput"),
  conversation: requiredElement("#conversation"),
  emptyState: requiredElement("#emptyState"),
  viewport: requiredElement("#conversationViewport"),
  chatHeading: requiredElement("#chatHeading"),
  syncLabel: requiredElement("#syncLabel"),
  cacheSummary: requiredElement("#cacheSummary"),
  headLabel: requiredElement("#headLabel"),
  globalLiveOrb: requiredElement("#globalLiveOrb"),
  serverLabel: requiredElement("#serverLabel"),
  sidebar: requiredElement("#sidebar"),
  openSidebar: requiredElement("#openSidebar"),
  closeSidebar: requiredElement("#closeSidebar"),
  sidebarScrim: requiredElement("#sidebarScrim"),
  logsButton: document.querySelector("#logsButton"),
  newChatButton: requiredElement("#newChatButton"),
  pinChatButton: requiredElement("#pinChatButton"),
  shareChatButton: requiredElement("#shareChatButton"),
  attachmentButton: requiredElement("#attachmentButton"),
  attachmentMenu: requiredElement("#attachmentMenu"),
  fileUploadInput: requiredElement("#fileUploadInput"),
  photoUploadInput: requiredElement("#photoUploadInput"),
  cameraUploadInput: requiredElement("#cameraUploadInput"),
  attachmentChips: requiredElement("#attachmentChips"),
  slashMenu: requiredElement("#slashMenu"),
  logsViewport: requiredElement("#logsViewport"),
  composerFooter: requiredElement("#composerFooter"),
  logOutput: requiredElement("#logOutput"),
  logsMeta: requiredElement("#logsMeta"),
  logsServerTitle: requiredElement("#logsServerTitle"),
  messageForm: requiredElement("#messageForm"),
  messageInput: requiredElement("#messageInput"),
  sendButton: requiredElement("#sendButton"),
  composerStatus: requiredElement("#composerStatus")
};
function setTextIfChanged(element, value) {
  const text = String(value ?? "");
  if (element.textContent !== text)
    element.textContent = text;
}
function setHiddenIfChanged(element, hidden) {
  if (element.hidden !== hidden)
    element.hidden = hidden;
}
function displayServerName(value) {
  const raw = String(value || "").trim();
  if (!raw)
    return "";
  return raw.split(/[-_\s]+/).filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}
function setServerStatus(server, online) {
  const raw = String(server || "").trim();
  if (raw)
    state.serverName = raw;
  if (typeof online === "boolean")
    state.serverOnline = online;
  const display = displayServerName(state.serverName || location.hostname);
  const knownOnline = state.serverOnline;
  setTextIfChanged(els.serverLabel, knownOnline === false ? `Server · ${display} · offline` : `Server · ${display}`);
  document.title = `Prompta · ${display}`;
  setTextIfChanged(els.logsServerTitle, `${display} · prompta.service`);
  const appleTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]');
  if (appleTitle)
    appleTitle.setAttribute("content", `Prompta ${display}`);
  els.globalLiveOrb.classList.toggle("live", knownOnline === true);
  els.globalLiveOrb.title = knownOnline === false ? `${display} is offline` : knownOnline === true ? `${display} is online` : `${display} status unknown`;
}
function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function formatRelativeTime(epochSeconds) {
  if (!epochSeconds)
    return "";
  const delta = Date.now() - epochSeconds * 1000;
  const abs = Math.abs(delta);
  if (abs < 45000)
    return "now";
  if (abs < 3600000)
    return `${Math.max(1, Math.round(abs / 60000))}m`;
  if (abs < 86400000)
    return `${Math.round(abs / 3600000)}h`;
  if (abs < 604800000)
    return `${Math.round(abs / 86400000)}d`;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(epochSeconds * 1000));
}
function chatActivityAt(chat) {
  if (!chat)
    return 0;
  if (chat._optimisticNew || chat._optimisticReply || chat.status === "active") {
    return Number(chat.updated_at || chat.last_message_at || 0);
  }
  return Number(chat.last_message_at || chat.updated_at || 0);
}
function sameLocalDay(epochSeconds, offsetDays = 0) {
  if (!epochSeconds)
    return false;
  const d = new Date(epochSeconds * 1000);
  const target = new Date;
  target.setDate(target.getDate() - offsetDays);
  return d.getFullYear() === target.getFullYear() && d.getMonth() === target.getMonth() && d.getDate() === target.getDate();
}
function chatTitle(chat) {
  const title = (chat.title || "").replace(/^ChatGPT\s*[-–—:]?\s*/i, "").trim();
  if (title && title.toLowerCase() !== "chatgpt")
    return title;
  if (chat.job_name)
    return chat.job_name.replaceAll("-", " ");
  const preview = sidebarPreviewText(chat.preview);
  if (preview)
    return preview.slice(0, 72);
  return "Untitled conversation";
}
function truncate(value, length = 88) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= length ? text : `${text.slice(0, length - 1)}…`;
}
function groupChats(chats) {
  const pinned = chats.filter((chat) => state.pinnedIds.has(chat.id));
  const unpinned = chats.filter((chat) => !state.pinnedIds.has(chat.id));
  const groups = [
    ["Pinned", pinned],
    ["Active", unpinned.filter((chat) => chat.status === "active")],
    ["Today", unpinned.filter((chat) => chat.status !== "active" && sameLocalDay(chatActivityAt(chat)))],
    ["Yesterday", unpinned.filter((chat) => chat.status !== "active" && sameLocalDay(chatActivityAt(chat), 1))],
    ["Previous", unpinned.filter((chat) => chat.status !== "active" && !sameLocalDay(chatActivityAt(chat)) && !sameLocalDay(chatActivityAt(chat), 1))]
  ];
  return groups.filter(([, items]) => items.length);
}
function sidebarStatusDot(status) {
  if (status === "interrupted")
    return "";
  const statusClass = ["active", "complete"].includes(status) ? status : "neutral";
  return `<span class="item-status-dot ${statusClass}"></span>`;
}
var iconStatusClasses = new Set([
  "active",
  "running",
  "succeeded",
  "complete",
  "cached",
  "local",
  "interrupted",
  "queued",
  "pending",
  "failed",
  "live",
  "journal",
  "new",
  "idle"
]);
function setStatusIcon(element, status, label, kind = "") {
  const statusClassName = iconStatusClasses.has(status) ? status : "neutral";
  element.className = ["status-icon", kind, statusClassName].filter(Boolean).join(" ");
  element.title = label;
  element.setAttribute("aria-label", label);
}
function reconcileOptimisticNew(chats) {
  const pending = state.pendingNewSend;
  if (!pending)
    return;
  const matched = matchingOptimisticConversation(chats, pending);
  if (!matched)
    return;
  pending.conversationId = matched.id;
  state.pendingNewId = matched.id;
}
function sidebarChats() {
  const chats = state.chats.map((chat) => {
    const pending2 = state.pendingReplies.get(chat.id) || [];
    if (!pending2.length)
      return chat;
    const latest = pending2[pending2.length - 1];
    return {
      ...chat,
      status: latest.status === "failed" ? chat.status : "active",
      preview: latest.message,
      updated_at: Math.max(Number(chat.updated_at || 0), Number(latest.updatedAt || 0)),
      _optimisticReply: true
    };
  });
  const pending = state.pendingNewSend;
  if (!pending)
    return chats;
  const matched = matchingOptimisticConversation(chats, pending);
  if (matched) {
    pending.conversationId = matched.id;
    state.pendingNewId = matched.id;
    return chats;
  }
  const pendingId = pending.conversationId || `pending-new-${pending.clientId}`;
  const optimistic = {
    id: pendingId,
    status: pending.status === "failed" ? "failed" : "active",
    title: truncate(pending.message, 72) || "New chat",
    preview: pending.message,
    message_count: 1,
    job_name: "new chat",
    updated_at: pending.updatedAt,
    _optimisticNew: true
  };
  const needle = state.search.trim().toLowerCase();
  if (needle && ![
    optimistic.title,
    optimistic.preview,
    optimistic.job_name
  ].some((value) => String(value || "").toLowerCase().includes(needle))) {
    return chats;
  }
  return [optimistic, ...chats];
}
function renderSidebar(force = false) {
  const chats = sidebarChats();
  const fingerprint = JSON.stringify(chats.map((chat) => [
    chat.id,
    chat.status,
    chat.title,
    chat.status === "active" ? "" : chat.preview,
    chat.message_count,
    chat.job_name,
    formatRelativeTime(chatActivityAt(chat)),
    Boolean(chat._optimisticNew),
    Boolean(chat._optimisticReply),
    state.pinnedIds.has(chat.id)
  ])) + state.selectedId + state.composingNew;
  if (!force && fingerprint === state.sidebarFingerprint)
    return;
  state.sidebarFingerprint = fingerprint;
  if (!chats.length) {
    els.chatList.innerHTML = `
      <div class="list-empty">
        ${state.search ? "No cached chats match your search." : "No cached conversations yet.<br>Prompta runs will appear here live."}
      </div>`;
    return;
  }
  els.chatList.innerHTML = groupChats(chats).map(([label, groupedChats]) => `
    <section class="chat-group">
      <div class="chat-group-label">${escapeHtml(label)}</div>
      ${groupedChats.map((chat) => {
    const selected = chat.id === state.selectedId || chat._optimisticNew && state.composingNew;
    return `
        <div class="chat-item ${selected ? "selected" : ""}">
          <button type="button"
                  class="chat-item-select"
                  data-chat-id="${escapeHtml(chat.id)}"
                  data-optimistic-new="${chat._optimisticNew ? "true" : "false"}">
            <div class="chat-item-top">
              ${sidebarStatusDot(chat.status)}
              <span class="chat-title">${escapeHtml(chatTitle(chat))}</span>
            </div>
            <div class="chat-preview">${escapeHtml(truncate(sidebarPreviewText(chat.preview) || "Waiting for messages…"))}</div>
            <div class="chat-meta">
              <span class="chat-job">${escapeHtml(chat.job_name || `${chat.message_count || 0} messages`)}</span>
              <span class="chat-time">${escapeHtml(formatRelativeTime(chatActivityAt(chat)))}</span>
            </div>
          </button>
          <button type="button"
                  class="chat-row-pin ${state.pinnedIds.has(chat.id) ? "active" : ""}"
                  data-pin-chat-id="${escapeHtml(chat.id)}"
                  aria-label="${state.pinnedIds.has(chat.id) ? "Unpin chat" : "Pin chat"}"
                  title="${state.pinnedIds.has(chat.id) ? "Unpin chat" : "Pin chat"}"
                  aria-pressed="${String(state.pinnedIds.has(chat.id))}">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l-.8 5 3.3 3.3v1.4H13v7.8l-1 1-1-1v-7.8H6.5v-1.4L9.8 8 9 3z"></path></svg>
          </button>
        </div>`;
  }).join("")}
    </section>
  `).join("");
  for (const item of els.chatList.querySelectorAll("[data-chat-id]")) {
    item.addEventListener("click", () => {
      if (item.dataset.optimisticNew === "true" && !state.pendingNewSend?.conversationId) {
        renderNewChat();
        document.body.classList.remove("sidebar-open");
        return;
      }
      selectChat(item.dataset.chatId);
    });
  }
  for (const pin of els.chatList.querySelectorAll("[data-pin-chat-id]")) {
    pin.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const chatId = pin.dataset.pinChatId;
      if (!chatId)
        return;
      if (state.pinnedIds.has(chatId))
        state.pinnedIds.delete(chatId);
      else
        state.pinnedIds.add(chatId);
      savePinnedIds();
      state.sidebarFingerprint = "";
      renderSidebar(true);
      updatePinButton();
    });
  }
}
var LANGUAGE_ALIASES = {
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
  md: "markdown"
};
var CODE_KEYWORDS = {
  javascript: new Set("as async await break case catch class const continue default delete do else export extends false finally for from function get if import in instanceof let new null of return set static super switch this throw true try typeof undefined var void while yield".split(" ")),
  typescript: new Set("abstract any as async await boolean break case catch class const constructor continue declare default do else enum export extends false finally for from function get if implements import in infer instanceof interface keyof let namespace never new null number object of private protected public readonly return satisfies set static string super switch symbol this throw true try type typeof undefined unknown var void while yield".split(" ")),
  python: new Set("and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield".split(" ")),
  bash: new Set("case do done elif else esac export fi for function if in local readonly return select then time until while".split(" ")),
  cpp: new Set("auto bool break case catch char class const constexpr continue default delete do double else enum explicit extern false float for friend if inline int long namespace new nullptr operator private protected public return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using virtual void volatile while".split(" ")),
  dart: new Set("abstract as assert async await break case catch class const continue default deferred do dynamic else enum export extends extension external factory false final finally for Function get hide if implements import in interface is late library mixin new null of on operator part required rethrow return set show static super switch sync this throw true try typedef var void while with yield".split(" ")),
  sql: new Set("ADD ALL ALTER AND ANY AS ASC BETWEEN BY CASE CHECK COLUMN CONSTRAINT CREATE DATABASE DEFAULT DELETE DESC DISTINCT DROP ELSE END EXISTS FOREIGN FROM FULL GROUP HAVING IN INDEX INNER INSERT INTO IS JOIN KEY LEFT LIKE LIMIT NOT NULL OR ORDER OUTER PRIMARY RIGHT SELECT SET TABLE UNION UNIQUE UPDATE VALUES VIEW WHEN WHERE WITH".split(" ")),
  json: new Set(["true", "false", "null"])
};
function normalizeLanguage(language) {
  const raw = String(language || "").trim().toLowerCase().split(/\s+/)[0];
  return LANGUAGE_ALIASES[raw] || raw || "code";
}
function syntaxToken(className, value) {
  return `<span class="syntax-${className}">${escapeHtml(value)}</span>`;
}
function highlightCode(raw, language) {
  const source = String(raw || "");
  const normalized = normalizeLanguage(language);
  const keywords = CODE_KEYWORDS[normalized] || new Set;
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
      const end = source.indexOf(`
`, index + 2);
      const next = end < 0 ? source.length : end;
      html += syntaxToken("comment", source.slice(index, next));
      index = next;
      continue;
    }
    if (hashComments && source[index] === "#") {
      const end = source.indexOf(`
`, index + 1);
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
    const number = source.slice(index).match(/^-?(?:0x[\da-f]+|0b[01]+|\d+(?:\.\d+)?(?:e[+-]?\d+)?)/i);
    if (number) {
      html += syntaxToken("number", number[0]);
      index += number[0].length;
      continue;
    }
    if (/[A-Za-z_$]/.test(source[index])) {
      let cursor = index + 1;
      while (/[A-Za-z0-9_$]/.test(source[cursor] || ""))
        cursor += 1;
      const value = source.slice(index, cursor);
      const lookup = sql ? value.toUpperCase() : value;
      if (keywords.has(lookup))
        html += syntaxToken("keyword", value);
      else if (/^\s*\(/.test(source.slice(cursor)))
        html += syntaxToken("function", value);
      else
        html += escapeHtml(value);
      index = cursor;
      continue;
    }
    html += /[\[\]{}(),.:;]/.test(source[index]) ? syntaxToken("punctuation", source[index]) : escapeHtml(source[index]);
    index += 1;
  }
  return html;
}
function inlineMarkdown(text) {
  const placeholders = [];
  const stash = (html2) => {
    const token = `PROMPTA_INLINE_${placeholders.length}_TOKEN`;
    placeholders.push([token, html2]);
    return token;
  };
  let source = String(text || "");
  source = source.replace(/`([^`\n]+)`/g, (_, code) => stash(`<code class="inline-code">${escapeHtml(code)}</code>`));
  source = source.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)(?:\s+"[^"]*")?\)/g, (_, label, url) => stash(`<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml(label)}</a>`));
  let html = escapeHtml(source);
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
  html = html.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
  html = html.replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g, "$1<em>$2</em>");
  for (const [token, value] of placeholders)
    html = html.replaceAll(token, value);
  return html;
}
function splitTableRow(line) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
}
function renderListItem(content) {
  const task = content.match(/^\[([ xX])\]\s+(.+)$/);
  if (!task)
    return `<li>${inlineMarkdown(content)}</li>`;
  const checked = task[1].toLowerCase() === "x";
  return `<li class="task-item"><input type="checkbox" disabled${checked ? " checked" : ""}> <span>${inlineMarkdown(task[2])}</span></li>`;
}
function renderTextBlock(text) {
  const lines = String(text || "").replace(/\r/g, "").split(`
`);
  const out = [];
  let index = 0;
  const startsBlock = (line, next = "") => !line.trim() || /^(#{1,6})\s+/.test(line) || /^\s*([-+*]|\d+[.)])\s+/.test(line) || /^\s*>\s?/.test(line) || /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line) || line.includes("|") && /^\s*\|?\s*:?-{3,}/.test(next);
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
      const rows = [];
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      out.push(`<div class="table-scroll"><table><thead><tr>${headers.map((cell, column) => `<th${aligns[column] ? ` style="text-align:${aligns[column]}"` : ""}>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headers.map((_, column) => `<td${aligns[column] ? ` style="text-align:${aligns[column]}"` : ""}>${inlineMarkdown(row[column] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (/^\s*>\s?/.test(line)) {
      const quoted = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quoted.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      out.push(`<blockquote>${renderTextBlock(quoted.join(`
`))}</blockquote>`);
      continue;
    }
    const list = line.match(/^(\s*)([-+*]|\d+[.)])\s+(.+)$/);
    if (list) {
      const ordered = /^\d/.test(list[2]);
      const tag = ordered ? "ol" : "ul";
      const items = [];
      while (index < lines.length) {
        const match = lines[index].match(/^(\s*)([-+*]|\d+[.)])\s+(.+)$/);
        if (!match || /^\d/.test(match[2]) !== ordered)
          break;
        items.push(renderListItem(match[3]));
        index += 1;
      }
      out.push(`<${tag}>${items.join("")}</${tag}>`);
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
function renderCodeBlock(code, language) {
  const rawLanguage = String(language || "").trim();
  const normalized = normalizeLanguage(rawLanguage);
  const toolMatch = rawLanguage.match(/^(?:tool|tool-call|function|function-call)(?::\s*(.+))?$/i);
  const inlineToolMatch = code.match(/^\s*(?:tool|function|to)\s*[:=]\s*([\w.-]+)/i);
  const toolish = Boolean(toolMatch || inlineToolMatch);
  const toolName = toolMatch?.[1]?.trim() || inlineToolMatch?.[1] || "";
  const toolFence = ["tool", "tool-call", "function", "function-call"].includes(normalized);
  const trimmedCode = code.trim();
  const highlightLanguage = toolish && toolFence ? trimmedCode.startsWith("{") || trimmedCode.startsWith("[") ? "json" : "code" : normalized;
  const label = toolish ? "tool call" : rawLanguage || "code";
  return `
    <div class="code-block${toolish ? " tool-call-block" : ""}">
      <div class="code-header">
        <span class="code-language">${escapeHtml(label)}</span>
        ${toolName ? `<span class="tool-name">${escapeHtml(toolName)}</span>` : ""}
        <button type="button" class="copy-code" data-code="${encodeURIComponent(code)}">copy</button>
      </div>
      <pre><code class="language-${escapeHtml(highlightLanguage)}">${highlightCode(code, highlightLanguage)}</code></pre>
    </div>`;
}
function renderMarkdown(raw) {
  const source = String(raw || "");
  const pattern = /```([^\n`]*)\n?([\s\S]*?)```/g;
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
function messageTimestamp(message) {
  const raw = Number(message.created_at || message.updated_at || Date.now() / 1000);
  const date = new Date(raw < 1000000000000 ? raw * 1000 : raw);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];
  const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const hour24 = date.getHours();
  const hour12 = hour24 % 12 || 12;
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const period = hour24 < 12 ? "am" : "pm";
  return {
    text: `${date.getDate()} ${months[date.getMonth()]} ${weekdays[date.getDay()]} ${hour12}:${minutes}${period}`,
    iso: date.toISOString()
  };
}
function renderMessageSection(message, allowStreaming = true) {
  const role = message.role === "user" ? "user" : "assistant";
  const streaming = allowStreaming && message.status === "streaming";
  const label = message.send_error ? "Send error" : "Prompta run";
  const timestamp = messageTimestamp(message);
  return `
    <section class="message ${role}${message.send_error ? " send-error" : ""}">
      <div class="message-inner">
        ${role === "assistant" ? `
          <div class="message-label"><span class="assistant-avatar">${message.send_error ? "!" : "P"}</span> ${label}</div>
        ` : ""}
        <div class="message-content">${renderMarkdown(message.content)}</div>
        ${message.send_error && message.retry_scope && message.retry_key ? `
          <button type="button"
                  class="retry-send-button"
                  data-retry-scope="${escapeHtml(message.retry_scope)}"
                  data-retry-key="${escapeHtml(message.retry_key)}">Retry</button>
        ` : ""}
        ${streaming ? `
          <div class="streaming-indicator">
            <span class="streaming-dots"><i></i><i></i><i></i></span>
            writing
          </div>
        ` : ""}
        <time class="message-timestamp" datetime="${timestamp.iso}">${timestamp.text}</time>
      </div>
    </section>`;
}
function messageNodeFingerprint(message, allowStreaming) {
  return JSON.stringify([
    message.role,
    message.status,
    message.content,
    Boolean(message.send_error),
    message.retry_scope,
    message.retry_key,
    message.created_at,
    message.updated_at,
    allowStreaming
  ]);
}
var boundCopyButtons = new WeakSet;
var boundRetryButtons = new WeakSet;
function bindRetryButtons(root) {
  for (const button of root.querySelectorAll(".retry-send-button")) {
    if (boundRetryButtons.has(button))
      continue;
    boundRetryButtons.add(button);
    button.addEventListener("click", () => {
      retryFailedSend(button.dataset.retryScope || "", button.dataset.retryKey || "");
    });
  }
}
function bindCopyButtons(root) {
  for (const button of root.querySelectorAll(".copy-code")) {
    if (boundCopyButtons.has(button))
      continue;
    boundCopyButtons.add(button);
    button.addEventListener("click", async () => {
      const code = decodeURIComponent(button.dataset.code || "");
      try {
        await navigator.clipboard.writeText(code);
        const previous = button.textContent;
        button.textContent = "copied";
        setTimeout(() => {
          button.textContent = previous;
        }, 1000);
      } catch {
        button.textContent = "copy unavailable";
      }
    });
  }
}
function createMessageNode(message, allowStreaming, messageKey) {
  const template = document.createElement("template");
  template.innerHTML = renderMessageSection(message, allowStreaming).trim();
  const node = template.content.firstElementChild;
  node.dataset.messageKey = messageKey;
  node.dataset.renderFingerprint = messageNodeFingerprint(message, allowStreaming);
  bindCopyButtons(node);
  bindRetryButtons(node);
  return node;
}
function patchDomNode(current, next) {
  if (current.nodeType !== next.nodeType || current.nodeType === Node.ELEMENT_NODE && current.tagName !== next.tagName) {
    const replacement = next.cloneNode(true);
    current.replaceWith(replacement);
    return replacement;
  }
  if (current.nodeType === Node.TEXT_NODE) {
    if (current.data !== next.data)
      current.data = next.data;
    return current;
  }
  if (current.nodeType !== Node.ELEMENT_NODE)
    return current;
  for (const attribute of Array.from(current.attributes)) {
    if (!next.hasAttribute(attribute.name))
      current.removeAttribute(attribute.name);
  }
  for (const attribute of Array.from(next.attributes)) {
    if (current.getAttribute(attribute.name) !== attribute.value) {
      current.setAttribute(attribute.name, attribute.value);
    }
  }
  patchDomChildren(current, next);
  return current;
}
function patchDomChildren(currentParent, nextParent) {
  let index = 0;
  while (index < nextParent.childNodes.length || index < currentParent.childNodes.length) {
    const current = currentParent.childNodes[index];
    const next = nextParent.childNodes[index];
    if (!next) {
      current.remove();
      continue;
    }
    if (!current) {
      currentParent.append(next.cloneNode(true));
      index += 1;
      continue;
    }
    patchDomNode(current, next);
    index += 1;
  }
}
function updateMessageNode(node, message, allowStreaming) {
  const role = message.role === "user" ? "user" : "assistant";
  const sendError = Boolean(message.send_error);
  const expectedRole = node.classList.contains("user") ? "user" : "assistant";
  const structuralMismatch = expectedRole !== role || node.classList.contains("send-error") !== sendError;
  if (structuralMismatch)
    return false;
  const content = node.querySelector(".message-content");
  if (!content)
    return false;
  const nextContent = renderMarkdown(message.content);
  if (content.innerHTML !== nextContent) {
    const template = document.createElement("template");
    template.innerHTML = nextContent;
    patchDomChildren(content, template.content);
    bindCopyButtons(content);
  }
  const shouldStream = allowStreaming && message.status === "streaming";
  const indicator = node.querySelector(".streaming-indicator");
  if (shouldStream && !indicator) {
    node.querySelector(".message-inner")?.insertAdjacentHTML("beforeend", `
      <div class="streaming-indicator">
        <span class="streaming-dots"><i></i><i></i><i></i></span>
        writing
      </div>
    `);
  } else if (!shouldStream && indicator) {
    indicator.remove();
  }
  node.dataset.renderFingerprint = messageNodeFingerprint(message, allowStreaming);
  return true;
}
function renderMessageNodes(messages, allowStreaming) {
  const existing = new Map(Array.from(els.conversation.children).map((node) => [node.dataset.messageKey, node]));
  const desiredKeys = new Set;
  const lastUserIndex = messages.findLastIndex((message) => message.role === "user");
  const lastAssistantIndex = messages.findLastIndex((message) => message.role === "assistant" && !message.send_error);
  const streamingIndex = allowStreaming && lastAssistantIndex > lastUserIndex && messages[lastAssistantIndex]?.status === "streaming" ? lastAssistantIndex : -1;
  messages.forEach((message, index) => {
    const messageKey = String(message.message_key || `${message.role || "message"}:${index}`);
    const streamThisMessage = index === streamingIndex;
    desiredKeys.add(messageKey);
    const fingerprint = messageNodeFingerprint(message, streamThisMessage);
    let node = existing.get(messageKey);
    if (!node) {
      node = createMessageNode(message, streamThisMessage, messageKey);
    } else if (node.dataset.renderFingerprint !== fingerprint) {
      if (!updateMessageNode(node, message, streamThisMessage)) {
        const replacement = createMessageNode(message, streamThisMessage, messageKey);
        node.replaceWith(replacement);
        node = replacement;
      }
    }
    const currentAtIndex = els.conversation.children[index];
    if (currentAtIndex !== node) {
      els.conversation.insertBefore(node, currentAtIndex || null);
    }
  });
  for (const node of Array.from(els.conversation.children)) {
    if (!desiredKeys.has(node.dataset.messageKey))
      node.remove();
  }
}
function pendingReplyMessages(conversationId, cachedMessages) {
  const pending = state.pendingReplies.get(conversationId) || [];
  const claimedCachedIndexes = new Set;
  for (const item of pending) {
    const content = item.message.trim();
    const earliestMatch = Number(item.createdAt || item.updatedAt || 0) - 3;
    let matchedIndex = -1;
    for (let index = cachedMessages.length - 1;index >= 0; index -= 1) {
      if (claimedCachedIndexes.has(index))
        continue;
      const message = cachedMessages[index];
      if (message.role !== "user" || String(message.content || "").trim() !== content)
        continue;
      const messageTime = Number(message.created_at || message.updated_at || 0);
      if (messageTime && earliestMatch && messageTime < earliestMatch)
        continue;
      matchedIndex = index;
      break;
    }
    if (matchedIndex >= 0) {
      claimedCachedIndexes.add(matchedIndex);
      item.observedInCache = true;
    }
  }
  const remaining = pending.filter((item) => item.status !== "succeeded" || !item.observedInCache);
  if (remaining.length)
    state.pendingReplies.set(conversationId, remaining);
  else
    state.pendingReplies.delete(conversationId);
  return remaining.flatMap((item) => {
    const messages = [];
    if (!item.observedInCache) {
      messages.push({
        message_key: `pending-user-${item.clientId || item.sendId}`,
        role: "user",
        content: item.message,
        status: "complete",
        updated_at: item.updatedAt
      });
    }
    if (item.status === "failed") {
      messages.push({
        message_key: `pending-error-${item.clientId || item.sendId}`,
        role: "assistant",
        content: `Send failed: ${item.error || "Unknown Prompta send error"}`,
        status: "complete",
        updated_at: item.updatedAt,
        send_error: true,
        retry_scope: "reply",
        retry_key: item.clientId || item.sendId
      });
    }
    return messages;
  });
}
function updatePinButton() {
  const chatId = state.selectedId;
  const available = Boolean(chatId) && !state.composingNew;
  const pinned = available && state.pinnedIds.has(chatId);
  els.pinChatButton.disabled = !available;
  els.pinChatButton.classList.toggle("active", Boolean(pinned));
  els.pinChatButton.setAttribute("aria-pressed", String(Boolean(pinned)));
  const label = pinned ? "Unpin chat" : "Pin chat";
  els.pinChatButton.title = label;
  els.pinChatButton.setAttribute("aria-label", label);
}
function toggleSelectedPin() {
  const chatId = state.selectedId;
  if (!chatId || state.composingNew)
    return;
  if (state.pinnedIds.has(chatId))
    state.pinnedIds.delete(chatId);
  else
    state.pinnedIds.add(chatId);
  savePinnedIds();
  state.sidebarFingerprint = "";
  renderSidebar(true);
  updatePinButton();
}
function renderConversation(chat) {
  state.selectedChat = chat;
  const messages = Array.isArray(chat.messages) ? chat.messages : [];
  const visibleMessages = [
    ...messages,
    ...pendingReplyMessages(chat.id, messages)
  ];
  const fingerprint = JSON.stringify([
    chat.status,
    visibleMessages.map((message) => [
      message.message_key,
      message.status,
      message.content,
      message.send_error
    ])
  ]);
  const wasNearBottom = els.viewport.scrollHeight - els.viewport.scrollTop - els.viewport.clientHeight < 120;
  const isInitial = state.selectedFingerprint === "";
  if (fingerprint !== state.selectedFingerprint) {
    state.selectedFingerprint = fingerprint;
    const allowStreaming = chat.status === "active";
    renderMessageNodes(visibleMessages, allowStreaming);
    if (isInitial || wasNearBottom) {
      requestAnimationFrame(() => {
        els.viewport.scrollTop = els.viewport.scrollHeight;
      });
    }
  }
  const title = chatTitle(chat);
  const activityLabel = chat.status === "active" ? "updating live" : chat.status === "interrupted" ? `interrupted · ${formatRelativeTime(chatActivityAt(chat))}` : formatRelativeTime(chatActivityAt(chat));
  const meta = [
    chat.job_name || "one-shot",
    `${visibleMessages.length} message${visibleMessages.length === 1 ? "" : "s"}`,
    activityLabel
  ].join(" · ");
  const metaFingerprint = JSON.stringify([title, meta, chat.status]);
  if (metaFingerprint !== state.selectedMetaFingerprint) {
    state.selectedMetaFingerprint = metaFingerprint;
    els.chatHeading.innerHTML = `
      <div class="heading-title">${escapeHtml(title)}</div>
      <div class="heading-meta">${escapeHtml(meta)}</div>`;
    const syncStatus = chat.status === "active" ? "active" : chat.status === "interrupted" ? "interrupted" : "cached";
    const syncLabel = chat.status === "active" ? "Syncing from SQLite" : chat.status === "interrupted" ? "Last run was interrupted" : "Cached in SQLite";
    setStatusIcon(els.syncLabel, syncStatus, syncLabel, "sync");
  }
  setHiddenIfChanged(els.emptyState, true);
  setHiddenIfChanged(els.conversation, false);
  els.messageInput.disabled = false;
  els.sendButton.disabled = state.sending;
  els.shareChatButton.disabled = false;
  state.composingNew = false;
  updatePinButton();
  if (!state.sending) {
    setTextIfChanged(els.composerStatus, chat.status === "active" ? "Uses the existing live ChatGPT tab." : chat.status === "interrupted" ? "The last run was interrupted. Sending will reopen this chat." : "Sending will reopen this chat once if its retained tab has expired.");
  }
}
function renderLogs(payload) {
  const lines = Array.isArray(payload.lines) ? payload.lines : [];
  const fingerprint = JSON.stringify([payload.updated_at, lines]);
  const wasNearBottom = els.logsViewport.scrollHeight - els.logsViewport.scrollTop - els.logsViewport.clientHeight < 120;
  const isInitial = !state.logFingerprint;
  if (fingerprint !== state.logFingerprint) {
    state.logFingerprint = fingerprint;
    els.logOutput.textContent = lines.length ? lines.join(`
`) : "No Prompta service logs are available yet.";
    if (isInitial || wasNearBottom) {
      requestAnimationFrame(() => {
        els.logsViewport.scrollTop = els.logsViewport.scrollHeight;
      });
    }
  }
  setTextIfChanged(els.logsMeta, payload.exists ? payload.source === "journal" ? lines.length + " lines · live journal" : lines.length + " lines · synced " + formatRelativeTime(payload.updated_at) : "Waiting for Prompta service logs");
}
async function loadLogs() {
  try {
    const payload = await fetchJson("api/logs?limit=800");
    renderLogs(payload);
  } catch (error) {
    els.logsMeta.textContent = "Logs unavailable";
    console.error(error);
  }
}
function showMode(mode) {
  state.mode = mode === "logs" ? "logs" : "chats";
  const logsMode = state.mode === "logs";
  els.viewport.hidden = logsMode;
  els.logsViewport.hidden = !logsMode;
  if (state.logRefreshTimer) {
    clearInterval(state.logRefreshTimer);
    state.logRefreshTimer = null;
  }
  if (els.logsButton) {
    els.logsButton.textContent = logsMode ? "chats" : "logs";
    els.logsButton.classList.toggle("active", logsMode);
    els.logsButton.setAttribute("aria-pressed", String(logsMode));
  }
  els.composerFooter.hidden = logsMode;
  if (logsMode) {
    state.selectedMetaFingerprint = "";
    const display = displayServerName(state.serverName || location.hostname);
    els.chatHeading.innerHTML = `<div class="heading-title">${escapeHtml(display)} Prompta logs</div>` + `<div class="heading-meta">journalctl · prompta.service · ${escapeHtml(display)}</div>`;
    setStatusIcon(els.syncLabel, "journal", `${display} journal`, "sync");
    els.messageInput.disabled = true;
    els.sendButton.disabled = true;
    els.shareChatButton.disabled = true;
    els.composerStatus.textContent = "Switch back to chats to send a message.";
    loadLogs();
    state.logRefreshTimer = setInterval(() => {
      if (state.mode === "logs" && document.visibilityState === "visible")
        loadLogs();
    }, 2000);
    return;
  }
  if (state.selectedId) {
    loadSelectedChat();
  } else if (state.composingNew) {
    renderNewChat();
  } else {
    clearConversation();
  }
}
function clearConversation() {
  state.composingNew = false;
  state.selectedId = null;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedMetaFingerprint = "";
  state.selectedChat = null;
  els.emptyState.hidden = false;
  els.conversation.hidden = true;
  els.conversation.innerHTML = "";
  els.chatHeading.innerHTML = `
    <div class="heading-title">Prompta</div>
    <div class="heading-meta">Local conversation history</div>`;
  setStatusIcon(els.syncLabel, "local", "Local cache", "sync");
  els.messageInput.disabled = true;
  els.sendButton.disabled = true;
  els.shareChatButton.disabled = true;
  updatePinButton();
  els.messageInput.placeholder = "Message Prompta…";
  els.composerStatus.textContent = "Select a chat to send a message.";
}
function renderNewChat() {
  const enteringNewChat = !state.composingNew;
  state.composingNew = true;
  state.selectedId = null;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedChat = null;
  state.mode = "chats";
  const pending = state.pendingNewSend;
  const waiting = pending && !["failed", "succeeded"].includes(pending.status);
  const fingerprint = JSON.stringify([
    pending?.sendId || "",
    pending?.message || "",
    pending?.status || "",
    pending?.error || "",
    pending?.conversationId || ""
  ]);
  if (fingerprint !== state.newChatFingerprint) {
    state.newChatFingerprint = fingerprint;
    if (pending) {
      const messages = [{
        message_key: `pending-user-${pending.clientId || pending.sendId}`,
        role: "user",
        content: pending.message,
        status: "complete",
        updated_at: pending.updatedAt
      }];
      if (pending.status === "failed") {
        messages.push({
          message_key: `pending-error-${pending.clientId || pending.sendId}`,
          role: "assistant",
          content: `Send failed: ${pending.error || "Unknown Prompta send error"}`,
          status: "complete",
          updated_at: pending.updatedAt,
          send_error: true,
          retry_scope: "new",
          retry_key: pending.clientId || pending.sendId
        });
      }
      els.emptyState.hidden = true;
      els.conversation.hidden = false;
      els.conversation.innerHTML = messages.map((message) => renderMessageSection(message)).join("");
      bindCopyButtons(els.conversation);
      bindRetryButtons(els.conversation);
      requestAnimationFrame(() => {
        els.viewport.scrollTop = els.viewport.scrollHeight;
      });
    } else {
      els.emptyState.hidden = false;
      els.conversation.hidden = true;
      els.conversation.innerHTML = "";
    }
    els.chatHeading.innerHTML = `
      <div class="heading-title">New chat</div>
      <div class="heading-meta">${pending ? "Queued through the live Prompta session" : "Starts a fresh ChatGPT conversation"}</div>`;
    setStatusIcon(els.syncLabel, pending ? "queued" : "new", pending ? "Send queued" : "Fresh conversation", "sync");
    els.messageInput.disabled = false;
    els.sendButton.disabled = Boolean(waiting);
    els.shareChatButton.disabled = true;
    updatePinButton();
    els.messageInput.placeholder = "Start a new chat…";
    els.composerStatus.textContent = pending ? pending.status === "failed" ? "Send failed. The error is shown in the chat." : "Sent to Prompta. Waiting for ChatGPT to accept it…" : "Your first message will open a fresh ChatGPT chat.";
  }
  if (enteringNewChat) {
    els.viewport.hidden = false;
    els.logsViewport.hidden = true;
    if (els.logsButton) {
      els.logsButton.textContent = "logs";
      els.logsButton.classList.remove("active");
    }
    history.replaceState(null, "", `${location.pathname}${location.search}`);
    renderSidebar();
    document.body.classList.remove("sidebar-open");
    if (!waiting && matchMedia("(pointer: fine)").matches) {
      requestAnimationFrame(() => els.messageInput.focus());
    }
  }
}
async function fetchJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok)
    throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}
async function postJson(url, payload, attempts = 1) {
  let lastError = new Error("Request failed");
  for (let attempt = 0;attempt < Math.max(1, attempts); attempt += 1) {
    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      if (attempt + 1 >= attempts)
        throw lastError;
      await new Promise((resolve) => setTimeout(resolve, 350 * (attempt + 1)));
      continue;
    }
    const data = await response.json().catch(() => ({}));
    if (response.ok)
      return data;
    lastError = new Error(data.error || `${response.status} ${response.statusText}`);
    if (response.status < 500 || attempt + 1 >= attempts)
      throw lastError;
    await new Promise((resolve) => setTimeout(resolve, 350 * (attempt + 1)));
  }
  throw lastError;
}
async function loadServerIdentity() {
  try {
    const payload = await fetchJson("api/health");
    setServerStatus(payload.server, payload.online);
    const head = String(payload.head || "").trim().toLowerCase();
    setTextIfChanged(els.headLabel, head ? head : "unknown");
    els.headLabel.title = head ? "UI commit " + head : "UI commit unavailable";
  } catch (error) {
    setServerStatus(state.serverName || location.hostname, false);
    console.warn("Could not load Prompta server identity", error);
  }
}
async function requestNotificationPermissionFromGesture() {
  if (!("Notification" in window) || Notification.permission !== "default")
    return;
  try {
    await Notification.requestPermission();
  } catch (error) {
    console.warn("Could not request notification permission", error);
  }
}
async function notifyChatFinished(chat) {
  if (!("Notification" in window) || Notification.permission !== "granted")
    return;
  const display = displayServerName(state.serverName || location.hostname);
  const title = chatTitle(chat);
  try {
    if ("serviceWorker" in navigator) {
      const registration = await navigator.serviceWorker.ready;
      await registration.showNotification(`Prompta · ${display}`, {
        body: `${title} finished`,
        tag: `prompta-finished-${chat.id}`,
        icon: "./icon.svg",
        badge: "./icon.svg",
        data: { url: `./#/${encodeURIComponent(chat.id)}` }
      });
      return;
    }
    new Notification(`Prompta · ${display}`, { body: `${title} finished` });
  } catch (error) {
    console.warn("Could not show Prompta completion notification", error);
  }
}
function trackChatCompletions(chats) {
  const nextStatuses = new Map(chats.map((chat) => [chat.id, chat.status]));
  if (state.statusBaselineReady) {
    for (const chat of chats) {
      if (state.chatStatuses.get(chat.id) === "active" && chat.status === "complete") {
        notifyChatFinished(chat);
      }
    }
  }
  state.chatStatuses = nextStatuses;
  state.statusBaselineReady = true;
}
async function loadChats() {
  const requestId = ++state.chatsRequestId;
  try {
    const query = state.search ? `?q=${encodeURIComponent(state.search)}` : "";
    const payload = await fetchJson(`api/chats${query}`);
    if (requestId !== state.chatsRequestId)
      return;
    const chats = payload.chats || [];
    reconcileOptimisticNew(chats);
    trackChatCompletions(chats);
    state.chats = chats;
    const activeCount = state.chats.filter((chat) => chat.status === "active").length;
    setTextIfChanged(els.cacheSummary, `${state.chats.length} cached · ${activeCount} active`);
    const hashId = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
    if (!state.selectedId && hashId && state.chats.some((chat) => chat.id === hashId)) {
      state.selectedId = hashId;
    }
    if (!state.selectedId && state.chats.length && !state.composingNew) {
      state.selectedId = state.chats[0].id;
    }
    if (state.selectedId && !state.composingNew && state.pendingNewId !== state.selectedId && !state.chats.some((chat) => chat.id === state.selectedId) && !state.search) {
      state.selectedId = state.chats[0]?.id || null;
      state.selectedFingerprint = "";
    }
    renderSidebar();
    if (state.mode === "chats") {
      if (state.selectedId) {
        const summary = state.chats.find((chat) => chat.id === state.selectedId);
        const shouldRefresh = !summary || summary.status === "active" || state.selectedUpdatedAt !== summary.updated_at || !state.selectedFingerprint;
        if (shouldRefresh)
          await loadSelectedChat();
      } else if (!state.composingNew) {
        clearConversation();
      }
    } else {
      await loadLogs();
    }
  } catch (error) {
    if (requestId !== state.chatsRequestId)
      return;
    if (els.globalLiveOrb.classList.contains("live")) {
      els.globalLiveOrb.classList.remove("live");
    }
    setTextIfChanged(els.cacheSummary, "Cache unavailable");
    console.error(error);
  }
}
async function loadSelectedChat() {
  if (!state.selectedId || state.mode !== "chats")
    return;
  const selectedId = state.selectedId;
  const requestId = ++state.selectedRequestId;
  try {
    const chat = await fetchJson(`api/chats/${encodeURIComponent(selectedId)}`);
    if (requestId !== state.selectedRequestId || selectedId !== state.selectedId || chat.id !== state.selectedId)
      return;
    if (state.pendingNewId === chat.id) {
      state.pendingNewId = null;
      if (state.pendingNewSend?.conversationId === chat.id)
        state.pendingNewSend = null;
    }
    state.selectedUpdatedAt = chat.updated_at;
    renderConversation(chat);
  } catch (error) {
    if (requestId !== state.selectedRequestId || selectedId !== state.selectedId)
      return;
    const missing = String(error).startsWith("Error: 404");
    if (missing && state.pendingNewId !== state.selectedId)
      clearConversation();
    if (!missing || state.pendingNewId !== state.selectedId)
      console.error(error);
  }
}
async function selectChat(id) {
  if (!id)
    return;
  if (state.mode !== "chats")
    showMode("chats");
  if (id === state.selectedId) {
    if (!state.selectedChat || state.selectedChat.id !== id) {
      await loadSelectedChat();
    }
    document.body.classList.remove("sidebar-open");
    return;
  }
  state.composingNew = false;
  state.pendingNewId = null;
  els.messageInput.placeholder = "Message Prompta…";
  state.selectedId = id;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedMetaFingerprint = "";
  state.selectedChat = null;
  history.replaceState(null, "", `#/${encodeURIComponent(id)}`);
  renderSidebar();
  await loadSelectedChat();
  document.body.classList.remove("sidebar-open");
}
var searchTimer;
els.searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.search = els.searchInput.value.trim();
    state.sidebarFingerprint = "";
    loadChats();
  }, 140);
});
document.addEventListener("keydown", (event) => {
  const typing = document.activeElement === els.searchInput || document.activeElement === els.messageInput;
  if (event.key === "/" && !typing) {
    event.preventDefault();
    els.searchInput.focus();
  }
  if (event.key === "Escape") {
    els.searchInput.blur();
    document.body.classList.remove("sidebar-open");
  }
});
function openSidebar() {
  document.body.classList.add("sidebar-open");
}
function closeSidebar() {
  document.body.classList.remove("sidebar-open");
}
els.openSidebar.addEventListener("click", openSidebar);
els.closeSidebar.addEventListener("click", closeSidebar);
els.sidebarScrim.addEventListener("click", closeSidebar);
var sidebarSwipe = {
  startX: 0,
  startY: 0,
  lastX: 0,
  lastTime: 0,
  velocityX: 0,
  sidebarWidth: 0,
  progress: 0,
  wasOpen: false,
  tracking: false,
  directionLocked: false,
  horizontal: false,
  frameId: 0,
  pendingX: 0
};
function mobileSidebarEnabled() {
  return window.matchMedia("(max-width: 780px)").matches;
}
document.addEventListener("touchstart", (event) => {
  if (!mobileSidebarEnabled() || event.touches.length !== 1)
    return;
  const touch = event.touches[0];
  const sidebarOpen = document.body.classList.contains("sidebar-open");
  if (!sidebarOpen && touch.clientX > 96)
    return;
  sidebarSwipe.startX = touch.clientX;
  sidebarSwipe.startY = touch.clientY;
  sidebarSwipe.lastX = touch.clientX;
  sidebarSwipe.lastTime = performance.now();
  sidebarSwipe.velocityX = 0;
  sidebarSwipe.sidebarWidth = els.sidebar.getBoundingClientRect().width;
  sidebarSwipe.progress = sidebarOpen ? 1 : 0;
  sidebarSwipe.wasOpen = sidebarOpen;
  sidebarSwipe.tracking = true;
  sidebarSwipe.directionLocked = false;
  sidebarSwipe.horizontal = false;
  sidebarSwipe.pendingX = sidebarOpen ? 0 : -sidebarSwipe.sidebarWidth;
  els.sidebar.style.transition = "none";
  els.sidebarScrim.style.transition = "none";
}, { passive: true });
function applySidebarDragPosition(x) {
  const width = sidebarSwipe.sidebarWidth || els.sidebar.getBoundingClientRect().width;
  sidebarSwipe.progress = Math.max(0, Math.min(1, 1 + x / width));
  els.sidebar.style.transform = `translate3d(${x}px, 0, 0)`;
  els.sidebarScrim.style.opacity = String(sidebarSwipe.progress);
}
function queueSidebarDragPosition(x) {
  sidebarSwipe.pendingX = x;
  if (sidebarSwipe.frameId)
    return;
  sidebarSwipe.frameId = requestAnimationFrame(() => {
    sidebarSwipe.frameId = 0;
    applySidebarDragPosition(sidebarSwipe.pendingX);
  });
}
document.addEventListener("touchmove", (event) => {
  if (!sidebarSwipe.tracking || event.touches.length !== 1)
    return;
  const touch = event.touches[0];
  const deltaX = touch.clientX - sidebarSwipe.startX;
  const deltaY = touch.clientY - sidebarSwipe.startY;
  if (!sidebarSwipe.directionLocked && (Math.abs(deltaX) > 8 || Math.abs(deltaY) > 8)) {
    sidebarSwipe.directionLocked = true;
    sidebarSwipe.horizontal = Math.abs(deltaX) > Math.abs(deltaY) * 1.15;
  }
  if (!sidebarSwipe.horizontal)
    return;
  event.preventDefault();
  const width = sidebarSwipe.sidebarWidth;
  const startX = sidebarSwipe.wasOpen ? 0 : -width;
  const x = Math.max(-width, Math.min(0, startX + deltaX));
  const now = performance.now();
  const elapsed = Math.max(1, now - sidebarSwipe.lastTime);
  sidebarSwipe.velocityX = (touch.clientX - sidebarSwipe.lastX) / elapsed;
  sidebarSwipe.lastX = touch.clientX;
  sidebarSwipe.lastTime = now;
  queueSidebarDragPosition(x);
}, { passive: false });
function settleSidebarDrag(open) {
  const width = sidebarSwipe.sidebarWidth || els.sidebar.getBoundingClientRect().width;
  if (sidebarSwipe.frameId) {
    cancelAnimationFrame(sidebarSwipe.frameId);
    sidebarSwipe.frameId = 0;
    applySidebarDragPosition(sidebarSwipe.pendingX);
  }
  const currentX = -width * (1 - sidebarSwipe.progress);
  const targetX = open ? 0 : -width;
  const remaining = Math.abs(targetX - currentX);
  const speed = Math.max(0.6, Math.abs(sidebarSwipe.velocityX));
  const duration = Math.max(90, Math.min(180, Math.round(remaining / speed)));
  document.body.classList.toggle("sidebar-open", open);
  els.sidebar.style.transition = `transform ${duration}ms cubic-bezier(0.2, 0, 0, 1)`;
  els.sidebar.style.transform = `translate3d(${targetX}px, 0, 0)`;
  els.sidebarScrim.style.transition = `opacity ${duration}ms linear`;
  els.sidebarScrim.style.opacity = open ? "1" : "0";
  window.setTimeout(() => {
    els.sidebar.style.removeProperty("transition");
    els.sidebar.style.removeProperty("transform");
    els.sidebarScrim.style.removeProperty("transition");
    els.sidebarScrim.style.removeProperty("opacity");
  }, duration + 30);
}
document.addEventListener("touchend", () => {
  if (!sidebarSwipe.tracking)
    return;
  if (sidebarSwipe.horizontal) {
    const fastOpen = sidebarSwipe.velocityX > 0.35;
    const fastClose = sidebarSwipe.velocityX < -0.35;
    const shouldOpen = fastOpen || !fastClose && sidebarSwipe.progress >= 0.5;
    settleSidebarDrag(shouldOpen);
  }
  sidebarSwipe.tracking = false;
}, { passive: true });
document.addEventListener("touchcancel", () => {
  if (sidebarSwipe.tracking && sidebarSwipe.horizontal) {
    settleSidebarDrag(sidebarSwipe.wasOpen);
  }
  sidebarSwipe.tracking = false;
}, { passive: true });
if (els.logsButton) {
  els.logsButton.addEventListener("click", () => {
    showMode(state.mode === "logs" ? "chats" : "logs");
  });
}
els.newChatButton.addEventListener("click", () => {
  state.pendingNewSend = null;
  state.newChatFingerprint = "";
  renderNewChat();
});
function resizeComposer() {
  els.messageInput.style.overflowY = "hidden";
  if (!els.messageInput.value) {
    els.messageInput.style.height = "34px";
    return;
  }
  els.messageInput.style.height = "auto";
  const contentHeight = els.messageInput.scrollHeight;
  els.messageInput.style.height = `${Math.min(180, contentHeight)}px`;
  els.messageInput.style.overflowY = contentHeight > 180 ? "auto" : "hidden";
}
function renderAttachments() {
  const files = state.attachments || [];
  els.attachmentChips.hidden = files.length === 0;
  els.attachmentChips.innerHTML = files.map((file, index) => '<span class="attachment-chip">' + '<span title="' + escapeHtml(file.name) + '">' + escapeHtml(truncate(file.name, 28)) + "</span>" + '<button type="button" data-remove-attachment="' + index + '" aria-label="Remove attachment">×</button>' + "</span>").join("");
}
function clearAttachments() {
  state.attachments = [];
  els.fileUploadInput.value = "";
  els.photoUploadInput.value = "";
  els.cameraUploadInput.value = "";
  renderAttachments();
}
function addAttachments(files) {
  const current = state.attachments || [];
  for (const file of files) {
    if (current.length >= 5)
      break;
    const duplicate = current.some((existing) => existing.name === file.name && existing.size === file.size && existing.lastModified === file.lastModified);
    if (!duplicate)
      current.push(file);
  }
  state.attachments = current;
  renderAttachments();
  if (files.length && current.length >= 5) {
    setTextIfChanged(els.composerStatus, "Prompta supports up to 5 attachments per message.");
  }
}
async function attachmentPayload(file) {
  if (file.size > 25 * 1024 * 1024) {
    throw new Error(file.name + " is larger than 25 MB");
  }
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader;
    reader.onerror = () => reject(reader.error || new Error("Could not read " + file.name));
    reader.onload = () => resolve(String(reader.result || ""));
    reader.readAsDataURL(file);
  });
  const comma = dataUrl.indexOf(",");
  return {
    name: file.name,
    type: file.type || "application/octet-stream",
    data: comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl
  };
}
async function serializeAttachments() {
  const files = state.attachments || [];
  const total = files.reduce((sum, file) => sum + Number(file.size || 0), 0);
  if (total > 25 * 1024 * 1024) {
    throw new Error("Attachments exceed the 25 MB Prompta upload limit");
  }
  return Promise.all(files.map(attachmentPayload));
}
els.attachmentButton.addEventListener("click", () => {
  els.attachmentMenu.hidden = !els.attachmentMenu.hidden;
});
els.attachmentMenu.addEventListener("click", (event) => {
  const button = event.target.closest("[data-attachment-kind]");
  if (!button)
    return;
  els.attachmentMenu.hidden = true;
  const kind = button.dataset.attachmentKind;
  if (kind === "photo")
    els.photoUploadInput.click();
  else if (kind === "camera")
    els.cameraUploadInput.click();
  else
    els.fileUploadInput.click();
});
for (const input of [els.fileUploadInput, els.photoUploadInput, els.cameraUploadInput]) {
  input.addEventListener("change", () => addAttachments(Array.from(input.files || [])));
}
els.attachmentChips.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove-attachment]");
  if (!button)
    return;
  const index = Number(button.dataset.removeAttachment);
  if (!Number.isInteger(index))
    return;
  state.attachments.splice(index, 1);
  renderAttachments();
});
document.addEventListener("click", (event) => {
  const target = event.target;
  if (!els.attachmentMenu.hidden && !els.attachmentMenu.contains(target) && !els.attachmentButton.contains(target)) {
    els.attachmentMenu.hidden = true;
  }
});
async function runScheduleSlashCommand(command) {
  state.sending = true;
  els.sendButton.disabled = true;
  els.messageInput.value = "";
  resizeComposer();
  setTextIfChanged(els.composerStatus, "Saving schedule…");
  try {
    const result = await postJson("api/schedule", {
      interval_minutes: command.intervalMinutes,
      prompt: command.prompt
    });
    const server = displayServerName(result.server || state.serverName || location.hostname);
    const interval = formatScheduleInterval(Number(result.interval_minutes));
    setTextIfChanged(els.composerStatus, `Scheduled on ${server}: every ${interval} · ${command.prompt}`);
  } catch (error) {
    setTextIfChanged(els.composerStatus, `Schedule failed: ${String(error).replace(/^Error:\s*/, "")}`);
    console.error(error);
  } finally {
    state.sending = false;
    els.messageInput.disabled = false;
    els.sendButton.disabled = false;
    if (matchMedia("(pointer: fine)").matches)
      els.messageInput.focus();
  }
}
async function runAtSlashCommand(command) {
  state.sending = true;
  els.sendButton.disabled = true;
  els.messageInput.value = "";
  resizeComposer();
  updateSlashMenu();
  setTextIfChanged(els.composerStatus, "Saving one-time schedule…");
  try {
    const result = await postJson("api/schedule-at", {
      run_at_epoch: command.runAtEpoch,
      prompt: command.prompt
    });
    const server = displayServerName(result.server || state.serverName || location.hostname);
    setTextIfChanged(els.composerStatus, `Scheduled on ${server}: ${command.runAtLabel} · ${command.prompt}`);
  } catch (error) {
    setTextIfChanged(els.composerStatus, `Schedule failed: ${String(error).replace(/^Error:\s*/, "")}`);
    console.error(error);
  } finally {
    state.sending = false;
    els.messageInput.disabled = false;
    els.sendButton.disabled = false;
    if (matchMedia("(pointer: fine)").matches)
      els.messageInput.focus();
  }
}
function pendingReply(conversationId, sendId) {
  return (state.pendingReplies.get(conversationId) || []).find((item) => item.sendId === sendId);
}
function updatePendingReply(conversationId, sendId, updates) {
  const item = pendingReply(conversationId, sendId);
  if (!item)
    return false;
  const previous = JSON.stringify([item.status || "", item.error || ""]);
  Object.assign(item, updates);
  const changed = JSON.stringify([item.status || "", item.error || ""]) !== previous;
  if (changed)
    item.updatedAt = Date.now() / 1000;
  return changed;
}
async function watchSend(sendId, creatingNew, conversationId) {
  let statusFailures = 0;
  while (true) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    let job;
    try {
      job = await fetchJson(`api/sends/${encodeURIComponent(sendId)}`);
      statusFailures = 0;
    } catch (error) {
      statusFailures += 1;
      if (statusFailures < 8) {
        await new Promise((resolve) => setTimeout(resolve, Math.min(2500, 250 * statusFailures)));
        continue;
      }
      job = {
        status: "failed",
        error: String(error).replace(/^Error:\s*/, "")
      };
    }
    const status = job.status || "running";
    if (creatingNew) {
      if (state.pendingNewSend?.sendId !== sendId)
        return;
      const nextError = job.error || "";
      const nextConversationId = job.conversation_id || state.pendingNewSend.conversationId || "";
      const changed2 = state.pendingNewSend.status !== status || state.pendingNewSend.error !== nextError || state.pendingNewSend.conversationId !== nextConversationId;
      Object.assign(state.pendingNewSend, {
        status,
        error: nextError,
        conversationId: nextConversationId
      });
      if (changed2)
        state.pendingNewSend.updatedAt = Date.now() / 1000;
      if (status === "succeeded") {
        const newId = job.conversation_id;
        if (!newId) {
          state.pendingNewSend.status = "failed";
          state.pendingNewSend.error = "Prompta reported success without a conversation id";
          if (state.composingNew)
            renderNewChat();
          return;
        }
        state.composingNew = false;
        state.selectedId = newId;
        state.pendingNewId = newId;
        history.replaceState(null, "", `#/${encodeURIComponent(newId)}`);
        els.messageInput.placeholder = "Message Prompta…";
        els.composerStatus.textContent = "Sent. Waiting for the cached response…";
        state.selectedUpdatedAt = null;
        await loadChats();
        await loadSelectedChat();
        return;
      }
      if (status === "failed") {
        if (state.composingNew)
          renderNewChat();
        renderSidebar();
        return;
      }
      if (changed2) {
        if (state.composingNew)
          renderNewChat();
        renderSidebar();
      }
      continue;
    }
    const changed = updatePendingReply(conversationId, sendId, {
      status,
      error: job.error || ""
    });
    if (changed)
      renderSidebar();
    if (state.selectedId === conversationId)
      await loadSelectedChat();
    if (status === "succeeded") {
      els.composerStatus.textContent = "Sent. Waiting for the cached response…";
      await loadChats();
      return;
    }
    if (status === "failed") {
      els.composerStatus.textContent = "Send failed. The error is shown in the chat.";
      return;
    }
  }
}
async function retryFailedSend(scope, retryKey) {
  if (!retryKey || state.sending)
    return;
  let pending = null;
  if (scope === "new") {
    if (state.pendingNewSend && (state.pendingNewSend.clientId === retryKey || state.pendingNewSend.sendId === retryKey)) {
      pending = state.pendingNewSend;
      state.pendingNewSend = null;
      state.newChatFingerprint = "";
      state.composingNew = true;
      renderNewChat();
    }
  } else if (scope === "reply" && state.selectedId) {
    const items = state.pendingReplies.get(state.selectedId) || [];
    pending = items.find((item) => item.clientId === retryKey || item.sendId === retryKey) || null;
    if (pending) {
      const remaining = items.filter((item) => item !== pending);
      if (remaining.length)
        state.pendingReplies.set(state.selectedId, remaining);
      else
        state.pendingReplies.delete(state.selectedId);
      state.selectedFingerprint = "";
      if (state.selectedChat?.id === state.selectedId)
        renderConversation(state.selectedChat);
    }
  }
  if (!pending)
    return;
  els.messageInput.value = pending.message || "";
  resizeComposer();
  if ((pending.attachmentNames || []).length) {
    setTextIfChanged(els.composerStatus, "Reattach the files, then send again.");
    els.messageInput.focus();
    return;
  }
  await sendSelectedMessage();
}
async function sendSelectedMessage() {
  const message = els.messageInput.value.trim();
  const creatingNew = state.composingNew;
  const conversationId = state.selectedId;
  const attachments = [...state.attachments || []];
  if (!message || state.mode !== "chats" || state.sending)
    return;
  requestNotificationPermissionFromGesture();
  const scheduleCommand = parseScheduleSlashCommand(message);
  if (scheduleCommand) {
    if (attachments.length) {
      setTextIfChanged(els.composerStatus, "Scheduled prompts do not include attachments.");
      return;
    }
    if ("error" in scheduleCommand) {
      setTextIfChanged(els.composerStatus, scheduleCommand.error);
      return;
    }
    await runScheduleSlashCommand(scheduleCommand);
    return;
  }
  const atCommand = parseAtSlashCommand(message);
  if (atCommand) {
    if (attachments.length) {
      setTextIfChanged(els.composerStatus, "Scheduled prompts do not include attachments.");
      return;
    }
    if ("error" in atCommand) {
      setTextIfChanged(els.composerStatus, atCommand.error);
      return;
    }
    await runAtSlashCommand(atCommand);
    return;
  }
  if (!creatingNew && !conversationId)
    return;
  let serializedAttachments = [];
  if (attachments.length) {
    state.sending = true;
    els.sendButton.disabled = true;
    setTextIfChanged(els.composerStatus, "Preparing attachments…");
    try {
      serializedAttachments = await serializeAttachments();
    } catch (error) {
      state.sending = false;
      els.sendButton.disabled = false;
      setTextIfChanged(els.composerStatus, "Attachment failed: " + String(error).replace(/^Error:\s*/, ""));
      return;
    }
    state.sending = false;
  }
  const now = Date.now() / 1000;
  const pending = {
    sendId: "",
    clientId: `${Date.now()}-${++state.optimisticSequence}`,
    message,
    status: "queued",
    error: "",
    conversationId: conversationId || "",
    createdAt: now,
    updatedAt: now,
    attachmentNames: attachments.map((file) => file.name)
  };
  state.sending = true;
  els.sendButton.disabled = true;
  els.messageInput.value = "";
  resizeComposer();
  if (creatingNew) {
    state.pendingNewSend = pending;
    state.newChatFingerprint = "";
    renderNewChat();
    renderSidebar();
  } else {
    const items = state.pendingReplies.get(conversationId) || [];
    items.push(pending);
    state.pendingReplies.set(conversationId, items);
    state.selectedFingerprint = "";
    if (state.selectedChat?.id === conversationId)
      renderConversation(state.selectedChat);
    renderSidebar();
  }
  try {
    const result = creatingNew ? await postJson("api/chats", { message, attachments: serializedAttachments, client_id: pending.clientId }, attachments.length ? 1 : 3) : await postJson(`api/chats/${encodeURIComponent(conversationId)}/messages`, { message, attachments: serializedAttachments, client_id: pending.clientId }, attachments.length ? 1 : 3);
    if (!result.send_id)
      throw new Error("Prompta did not return a send id");
    pending.sendId = result.send_id;
    pending.status = result.status || "queued";
    pending.updatedAt = Date.now() / 1000;
    if (attachments.length)
      clearAttachments();
    if (creatingNew) {
      state.newChatFingerprint = "";
      renderNewChat();
    } else {
      state.selectedFingerprint = "";
      if (state.selectedChat?.id === conversationId)
        renderConversation(state.selectedChat);
    }
    renderSidebar();
    watchSend(result.send_id, creatingNew, conversationId);
  } catch (error) {
    pending.status = "failed";
    pending.error = String(error).replace(/^Error:\s*/, "");
    pending.updatedAt = Date.now() / 1000;
    if (creatingNew) {
      state.newChatFingerprint = "";
      renderNewChat();
    } else {
      state.selectedFingerprint = "";
      if (state.selectedChat?.id === conversationId)
        renderConversation(state.selectedChat);
    }
    renderSidebar();
    console.error(error);
  } finally {
    state.sending = false;
    if (!creatingNew && state.selectedId && state.mode === "chats") {
      els.messageInput.disabled = false;
      els.sendButton.disabled = false;
      if (matchMedia("(pointer: fine)").matches)
        els.messageInput.focus();
    } else if (creatingNew && state.pendingNewSend?.status === "failed" && state.mode === "chats") {
      els.messageInput.disabled = false;
      els.sendButton.disabled = false;
      if (matchMedia("(pointer: fine)").matches)
        els.messageInput.focus();
    }
  }
}
async function copySelectedChatUrl() {
  if (!state.selectedId)
    return;
  const url = new URL(location.href);
  url.hash = `/${encodeURIComponent(state.selectedId)}`;
  try {
    await navigator.clipboard.writeText(url.toString());
    setTextIfChanged(els.composerStatus, "Chat link copied.");
  } catch (error) {
    const textarea = document.createElement("textarea");
    textarea.value = url.toString();
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
    setTextIfChanged(els.composerStatus, "Chat link copied.");
  }
}
function updateSlashMenu() {
  const value = els.messageInput.value;
  const firstToken = value.split(/\s/, 1)[0].toLowerCase();
  const candidates = Array.from(els.slashMenu.querySelectorAll("[data-slash-command]"));
  const show = value.startsWith("/") && !value.includes(`
`) && !value.includes(" ");
  let visible = 0;
  for (const button of candidates) {
    const command = String(button.dataset.slashCommand || "").trim().toLowerCase();
    const matches = show && command.startsWith(firstToken);
    button.hidden = !matches;
    if (matches)
      visible += 1;
  }
  els.slashMenu.hidden = visible === 0;
}
function insertSlashCommand(command) {
  els.messageInput.value = command;
  els.slashMenu.hidden = true;
  resizeComposer();
  els.messageInput.focus();
  els.messageInput.setSelectionRange(command.length, command.length);
}
els.pinChatButton.addEventListener("click", toggleSelectedPin);
els.shareChatButton.addEventListener("click", copySelectedChatUrl);
els.slashMenu.addEventListener("click", (event) => {
  const button = event.target.closest("[data-slash-command]");
  if (!button)
    return;
  insertSlashCommand(String(button.dataset.slashCommand || ""));
});
els.messageForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendSelectedMessage();
});
els.messageInput.addEventListener("input", () => {
  resizeComposer();
  updateSlashMenu();
});
els.messageInput.addEventListener("keydown", (event) => {
  if (!els.slashMenu.hidden && ["Tab", "ArrowDown"].includes(event.key)) {
    const first = els.slashMenu.querySelector("[data-slash-command]:not([hidden])");
    if (first) {
      event.preventDefault();
      insertSlashCommand(String(first.dataset.slashCommand || ""));
      return;
    }
  }
  const mobileInput = matchMedia("(pointer: coarse)").matches;
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !mobileInput) {
    event.preventDefault();
    sendSelectedMessage();
  }
});
window.addEventListener("hashchange", () => {
  const id = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  if (id && id !== state.selectedId)
    selectChat(id);
});
var liveRefreshQueued = false;
function queueLiveRefresh() {
  if (liveRefreshQueued)
    return;
  liveRefreshQueued = true;
  requestAnimationFrame(async () => {
    liveRefreshQueued = false;
    await loadChats();
  });
}
function startEventStream() {
  if (!("EventSource" in window)) {
    state.refreshTimer = setInterval(loadChats, 5000);
    return;
  }
  const events = new EventSource("api/events");
  events.addEventListener("refresh", (event) => {
    try {
      const payload = JSON.parse(event.data || "{}");
      setServerStatus(payload.server, payload.online);
    } catch (error) {
      console.warn("Could not parse Prompta SSE status", error);
    }
    queueLiveRefresh();
  });
  events.addEventListener("error", () => {
    els.globalLiveOrb.classList.remove("live");
  });
  window.addEventListener("pagehide", () => events.close(), { once: true });
}
function registerServiceWorker() {
  if (!("serviceWorker" in navigator))
    return;
  navigator.serviceWorker.register("./sw.js").catch((error) => {
    console.warn("Could not register Prompta service worker", error);
  });
}
async function startApp() {
  registerServiceWorker();
  loadServerIdentity();
  resizeComposer();
  document.documentElement.classList.remove("booting");
  await loadChats();
  startEventStream();
}
startApp();
