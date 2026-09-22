// src/prompta/ui/clientLogic.ts
function preserveSidebarChatOrder(previous, incoming) {
  if (!previous.length)
    return [...incoming];
  const incomingById = new Map(incoming.map((chat) => [chat.id, chat]));
  const previousIds = new Set(previous.map((chat) => chat.id));
  const added = incoming.filter((chat) => !previousIds.has(chat.id));
  const retained = previous.map((chat) => incomingById.get(chat.id)).filter((chat) => Boolean(chat));
  return [...added, ...retained];
}
var CHATGPT_RICH_START = "";
var CHATGPT_RICH_END = "";
var CHATGPT_RICH_SEPARATOR = "";
function textValue(value, fallback = "") {
  if (typeof value === "string")
    return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  return fallback;
}
function readableRichMarkerFallback(parts) {
  return parts.find((part) => {
    const value = part.trim();
    return Boolean(value) && value.length <= 200 && !/^turn\d+[a-z]+\d+$/i.test(value) && !/^https?:\/\//i.test(value) && !/^[{[]/.test(value);
  })?.trim() || "";
}
function replaceChatGptRichMarkers(value, renderUrl = (label) => label) {
  const source = textValue(value);
  let output = "";
  let cursor = 0;
  while (cursor < source.length) {
    const start = source.indexOf(CHATGPT_RICH_START, cursor);
    if (start < 0) {
      output += source.slice(cursor);
      break;
    }
    output += source.slice(cursor, start);
    const end = source.indexOf(CHATGPT_RICH_END, start + CHATGPT_RICH_START.length);
    if (end < 0) {
      break;
    }
    const body = source.slice(start + CHATGPT_RICH_START.length, end);
    const [rawType, ...parts] = body.split(CHATGPT_RICH_SEPARATOR);
    const type = rawType.trim().toLowerCase();
    let replacement = "";
    if (type === "url") {
      const label = String(parts[0] || parts[1] || "").trim();
      const url = String(parts[1] || "").trim();
      replacement = /^https?:\/\//i.test(url) ? renderUrl(label || url, url) : label || readableRichMarkerFallback(parts);
    } else if (type !== "cite" && type !== "memcite") {
      replacement = readableRichMarkerFallback(parts);
    }
    output += replacement;
    cursor = end + CHATGPT_RICH_END.length;
  }
  return output;
}
function retryDelayText(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0)
    return "soon";
  if (value < 60)
    return "<1m";
  const minutes = Math.ceil(value / 60);
  if (minutes < 60)
    return `${minutes}m`;
  const hours = Math.ceil(minutes / 60);
  return `${hours}h`;
}
function pendingSendActivity(status, hasSendId, retryAfterSeconds = 0, retryAtEpoch = 0, nowEpoch = Date.now() / 1000) {
  const normalized = textValue(status, "queued").trim().toLowerCase();
  if (["failed", "dead_lettered"].includes(normalized))
    return null;
  if (!hasSendId)
    return { label: "sending", statusText: "Sending…" };
  if (normalized === "queued")
    return { label: "queued", statusText: "Queued in Prompta…" };
  if (normalized === "retrying") {
    const deadline = Number(retryAtEpoch);
    const now = Number(nowEpoch);
    const remaining = Number.isFinite(deadline) && deadline > 0 && Number.isFinite(now) ? Math.max(0, deadline - now) : Number(retryAfterSeconds);
    if (remaining <= 0) {
      return { label: "retrying now", statusText: "Retry backoff elapsed; retrying now…" };
    }
    const delay = retryDelayText(remaining);
    return {
      label: `retrying · ${delay}`,
      statusText: `Send failed transiently — retrying automatically in ${delay}.`
    };
  }
  if (normalized === "rate_limited") {
    const deadline = Number(retryAtEpoch);
    const now = Number(nowEpoch);
    const hasDeadline = Number.isFinite(deadline) && deadline > 0 && Number.isFinite(now);
    const remaining = hasDeadline ? Math.max(0, deadline - now) : Number(retryAfterSeconds);
    if (hasDeadline && remaining <= 0) {
      return {
        label: "rate limited · retrying now",
        statusText: "Rate limited — backoff elapsed; retrying now…"
      };
    }
    const delay = retryDelayText(remaining);
    return {
      label: `rate limited · retry in ${delay}`,
      statusText: `Rate limited — backing off; retrying automatically in ${delay}.`
    };
  }
  return { label: "waiting", statusText: "Waiting for ChatGPT…" };
}
function conversationIdFromHash(hash) {
  const encoded = textValue(hash).replace(/^#\/?/, "").trim();
  if (!encoded)
    return "";
  try {
    return decodeURIComponent(encoded);
  } catch {
    return "";
  }
}
var TOOL_UI_NOISE = /^(?:open tool call list|close tool call list|tool|tool call|expand|collapse|cot-v5-[\w-]+)$/i;
function toolCallDisplayName(value) {
  const name = textValue(value).replace(/\s+/g, " ").trim();
  return name && !TOOL_UI_NOISE.test(name) ? name : "";
}
function toolCallIsInvocationPlaceholder(value) {
  return /^called tool$/i.test(textValue(value).trim());
}
function toolCallHasUsefulDetail(value) {
  return textValue(value).split(/\n+/).map((line) => line.trim()).some((line) => Boolean(toolCallDisplayName(line)));
}
function parsedToolPayload(value) {
  let current = value;
  for (let depth = 0;depth < 3; depth += 1) {
    if (typeof current !== "string")
      return current;
    const trimmed = current.trim();
    if (!trimmed || !/^[{[]/.test(trimmed))
      return current;
    try {
      current = JSON.parse(trimmed);
    } catch {
      return current;
    }
  }
  return current;
}
function toolCallSummary(value) {
  const payload = parsedToolPayload(value);
  if (!payload || typeof payload !== "object" || Array.isArray(payload))
    return "";
  const record = payload;
  for (const candidate of [record.summary, record.reasoning_title, record.title]) {
    if (typeof candidate === "string" && candidate.trim())
      return candidate.trim();
  }
  return "";
}
function toolCallTimestampMillis(value) {
  const payload = parsedToolPayload(value);
  if (!payload || typeof payload !== "object" || Array.isArray(payload))
    return null;
  const record = payload;
  for (const candidate of [record.created_at, record.createdAt, record.timestamp, record.time]) {
    const numeric = Number(candidate);
    if (!Number.isFinite(numeric) || numeric <= 0)
      continue;
    const millis = numeric > 1000000000000 ? numeric : numeric * 1000;
    if (Number.isNaN(new Date(millis).getTime()))
      continue;
    return millis;
  }
  return null;
}
function pythonToolCallCode(toolName, value) {
  const name = textValue(toolName).trim().toLowerCase();
  const pythonTool = name.includes("execute_python") || name.includes("python") && (name.includes("nox") || name.includes("glass") || name.includes("mcp"));
  if (!pythonTool)
    return "";
  const payload = parsedToolPayload(value);
  if (!payload || typeof payload !== "object" || Array.isArray(payload))
    return "";
  const record = payload;
  const argumentPayload = parsedToolPayload(record.arguments ?? record.args ?? record);
  if (!argumentPayload || typeof argumentPayload !== "object" || Array.isArray(argumentPayload))
    return "";
  const code = argumentPayload.code;
  return typeof code === "string" ? code.replace(/^(?:[ \t]*\r?\n)+/, "") : "";
}
function sidebarPreviewText(value) {
  return replaceChatGptRichMarkers(value).replace(/```(?:tool|tool-call|function|function-call)(?::[^\n\x60]*)?\n?[\s\S]*?```/gi, " ").replace(/\s+/g, " ").trim();
}
function sidebarChatPreviewText(preview, prompt) {
  return sidebarPreviewText(preview) || sidebarPreviewText(prompt);
}
function missingPendingConversationSummaries(chats, pendingReplies, query = "") {
  const existingIds = new Set(chats.map((chat) => String(chat.id)));
  const needle = query.trim().toLowerCase();
  const summaries = [];
  for (const [conversationId, replies] of pendingReplies) {
    if (!conversationId || existingIds.has(conversationId) || !replies.length)
      continue;
    const latest = replies[replies.length - 1];
    const message = textValue(latest.message).trim();
    const title = message.slice(0, 72) || "New chat";
    const status = ["failed", "dead_lettered"].includes(textValue(latest.status)) ? textValue(latest.status) : "active";
    if (needle && ![title, message, "new chat"].some((value) => value.toLowerCase().includes(needle))) {
      continue;
    }
    const createdAt = Number(latest.createdAt || latest.updatedAt || 0);
    const updatedAt = Number(latest.updatedAt || latest.createdAt || 0);
    summaries.push({
      id: conversationId,
      status,
      title,
      preview: message,
      message_count: 1,
      job_name: "new chat",
      created_at: Number.isFinite(createdAt) ? createdAt : 0,
      updated_at: Number.isFinite(updatedAt) ? updatedAt : 0,
      _optimisticReply: true
    });
  }
  return summaries.sort((left, right) => right.updated_at - left.updated_at);
}
function pendingConversationDisplayId(pending) {
  if (!pending)
    return "";
  if (pending.conversationId)
    return String(pending.conversationId);
  const clientId = String(pending.clientId || "").trim();
  return clientId ? `pending-new-${clientId}` : "";
}
function promotePinnedConversationId(pinnedIds, pending, nextConversationId) {
  const nextId = String(nextConversationId || "").trim();
  if (!nextId)
    return false;
  const previousId = pendingConversationDisplayId(pending);
  if (!previousId || previousId === nextId || !pinnedIds.has(previousId))
    return false;
  pinnedIds.delete(previousId);
  pinnedIds.add(nextId);
  return true;
}
function comparableTimestampSeconds(value) {
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0)
    return 0;
  return timestamp >= 1000000000000 ? timestamp / 1000 : timestamp;
}
function comparablePrompt(value) {
  return textValue(value).trim().replace(/\s+/g, " ");
}
function matchingOptimisticConversation(chats, pending, knownConversationIds = new Set) {
  if (!pending)
    return null;
  if (pending.conversationId) {
    const exact = chats.find((chat) => chat.id === pending.conversationId);
    if (exact)
      return exact;
  }
  const prompt = comparablePrompt(pending.message);
  if (!prompt)
    return null;
  const createdAt = comparableTimestampSeconds(pending.createdAt);
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  if (createdAt > 0) {
    for (const chat of chats) {
      if (comparablePrompt(chat.prompt) !== prompt)
        continue;
      const chatCreatedAt = comparableTimestampSeconds(chat.created_at);
      if (chatCreatedAt <= 0)
        continue;
      const distance = Math.abs(chatCreatedAt - createdAt);
      if (distance > 30 || distance >= bestDistance)
        continue;
      best = chat;
      bestDistance = distance;
    }
  }
  if (best)
    return best;
  if (!knownConversationIds.size)
    return null;
  const unseenMatches = chats.filter((chat) => !knownConversationIds.has(chat.id) && comparablePrompt(chat.prompt) === prompt);
  return unseenMatches.length === 1 ? unseenMatches[0] : null;
}
function messageTimestampMillis(createdAt, updatedAt) {
  for (const candidate of [createdAt, updatedAt]) {
    const raw = Number(candidate);
    if (!Number.isFinite(raw) || raw <= 0)
      continue;
    const millis = raw < 1000000000000 ? raw * 1000 : raw;
    if (!Number.isFinite(millis))
      continue;
    const date = new Date(millis);
    if (!Number.isNaN(date.getTime()))
      return millis;
  }
  return null;
}
function formatClockTime12Hour(value, includeSeconds = false) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime()))
    return "";
  const hour24 = date.getHours();
  const hour12 = hour24 % 12 || 12;
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = includeSeconds ? `:${String(date.getSeconds()).padStart(2, "0")}` : "";
  return `${hour12}:${minutes}${seconds}${hour24 < 12 ? "am" : "pm"}`;
}
function formatDailyTime12Hour(value) {
  const raw = textValue(value);
  const match = raw.match(/^([01]\d|2[0-3]):([0-5]\d)$/);
  if (!match)
    return raw;
  const hour24 = Number(match[1]);
  const hour12 = hour24 % 12 || 12;
  return `${hour12}:${match[2]}${hour24 < 12 ? "am" : "pm"}`;
}
function messageAgeText(timestampMillis, nowMillis = Date.now()) {
  const timestamp = Number(timestampMillis);
  const now = Number(nowMillis);
  if (!Number.isFinite(timestamp) || timestamp <= 0 || !Number.isFinite(now))
    return "";
  const elapsed = Math.max(0, now - timestamp);
  if (elapsed < 45000)
    return "now";
  if (elapsed < 3600000)
    return `${Math.max(1, Math.floor(elapsed / 60000))}m ago`;
  if (elapsed < 86400000)
    return `${Math.max(1, Math.floor(elapsed / 3600000))}h ago`;
  if (elapsed < 604800000)
    return `${Math.max(1, Math.floor(elapsed / 86400000))}d ago`;
  if (elapsed < 2592000000)
    return `${Math.max(1, Math.floor(elapsed / 604800000))}w ago`;
  if (elapsed < 31536000000)
    return `${Math.max(1, Math.floor(elapsed / 2592000000))}mo ago`;
  return `${Math.max(1, Math.floor(elapsed / 31536000000))}y ago`;
}
function shouldRenderNewChatView(enteringNewChat, fingerprint, previousFingerprint) {
  return enteringNewChat || fingerprint !== previousFingerprint;
}
function pendingConversationSends(conversationId, replies, pendingNew) {
  if (!pendingNew || pendingNew.conversationId !== conversationId)
    return replies;
  const duplicate = replies.some((item) => item === pendingNew || pendingNew.clientId && item.clientId === pendingNew.clientId || pendingNew.sendId && item.sendId === pendingNew.sendId);
  return duplicate ? replies : [...replies, pendingNew];
}
function matchingPendingReplyMessageIndex(messages, pending, claimedIndexes = new Set) {
  const content = comparablePrompt(pending.message);
  const pendingAt = comparableTimestampSeconds(pending.createdAt || pending.updatedAt);
  if (!content || pendingAt <= 0)
    return -1;
  let bestIndex = -1;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = messages.length - 1;index >= 0; index -= 1) {
    if (claimedIndexes.has(index))
      continue;
    const message = messages[index];
    if (message.role !== "user" || comparablePrompt(message.content) !== content)
      continue;
    const messageTime = comparableTimestampSeconds(message.created_at || message.updated_at);
    if (messageTime <= 0)
      continue;
    const distance = Math.abs(messageTime - pendingAt);
    if (distance > 30 || distance >= bestDistance)
      continue;
    bestIndex = index;
    bestDistance = distance;
  }
  return bestIndex;
}
function parseScheduleSlashCommand(message) {
  if (!/^\/(?:add|every)(?:\s|$)/i.test(message))
    return null;
  const match = message.match(/^\/(?:add|every)\s+(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)?\s+([\s\S]+)$/i);
  if (!match) {
    return {
      error: "Use /add <interval> <prompt>, for example: /add 30 fix bugs or /add 2h review failures"
    };
  }
  const amount = Number(match[1]);
  const unit = String(match[2] || "m").toLowerCase();
  const multiplier = unit.startsWith("s") ? 1 / 60 : unit.startsWith("h") ? 60 : unit.startsWith("d") ? 1440 : 1;
  const intervalMinutes = amount * multiplier;
  const prompt = match[3].trim();
  if (!Number.isFinite(intervalMinutes) || intervalMinutes <= 0) {
    return { error: "Schedule interval must be a finite value greater than zero." };
  }
  if (intervalMinutes < 0.1) {
    return { error: "Schedule interval must be at least 6 seconds." };
  }
  if (intervalMinutes > 60 * 24 * 30) {
    return { error: "Schedule interval cannot exceed 30 days." };
  }
  if (!prompt) {
    return { error: "Schedule prompt is required." };
  }
  return { intervalMinutes, prompt };
}
function formatScheduleInterval(minutes) {
  if (minutes < 1) {
    const seconds = minutes * 60;
    return `${seconds} second${seconds === 1 ? "" : "s"}`;
  }
  if (minutes >= 1440 && minutes % 1440 === 0) {
    const days = minutes / 1440;
    return `${days} day${days === 1 ? "" : "s"}`;
  }
  if (minutes >= 60 && minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}
async function postJsonRequest(url, payload, attempts = 1, timeoutMs = 45000, fetchImpl = fetch) {
  let lastError = new Error("Request failed");
  for (let attempt = 0;attempt < Math.max(1, attempts); attempt += 1) {
    const controller = new AbortController;
    const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
    let response;
    let data = {};
    try {
      response = await fetchImpl(url, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      try {
        data = await response.json();
      } catch {
        if (controller.signal.aborted)
          throw new Error("Request timed out");
        if (response.ok)
          throw new Error("Prompta returned an invalid response");
      }
    } catch (error) {
      lastError = controller.signal.aborted ? new Error("Request timed out") : error instanceof Error ? error : new Error(String(error));
      if (attempt + 1 >= attempts)
        throw lastError;
      await new Promise((resolve) => globalThis.setTimeout(resolve, 350 * (attempt + 1)));
      continue;
    } finally {
      globalThis.clearTimeout(timeout);
    }
    if (response.ok)
      return data;
    const errorMessage = typeof data === "object" && data !== null && "error" in data && typeof data.error === "string" ? data.error : "";
    lastError = new Error(errorMessage || `${response.status} ${response.statusText}`);
    if (response.status < 500 || attempt + 1 >= attempts)
      throw lastError;
    await new Promise((resolve) => globalThis.setTimeout(resolve, 350 * (attempt + 1)));
  }
  throw lastError;
}
function composerHasContent(message, attachmentCount) {
  return Boolean(String(message || "").trim()) || attachmentCount > 0;
}
function shouldShowStopAction(chatStatus, composingNew, hasComposerContent = false) {
  return !hasComposerContent && !composingNew && textValue(chatStatus).trim().toLowerCase() === "active";
}
function shouldProbeHistoricalActivity(chatStatus) {
  return textValue(chatStatus).trim().toLowerCase() === "interrupted";
}
function shouldRefreshSelectedChat(summary, selectedUpdatedAt, selectedFingerprint, force = false) {
  return force || !summary || summary.status === "active" || selectedUpdatedAt !== summary.updated_at || !selectedFingerprint;
}
function parseAtSlashCommand(message, now = new Date) {
  if (!/^\/at(?:\s|$)/i.test(message))
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
  let expectedYear;
  let expectedMonth;
  let expectedDay;
  if (dateToken === "today" || dateToken === "tomorrow") {
    target = new Date(now);
    if (dateToken === "tomorrow")
      target.setDate(target.getDate() + 1);
    expectedYear = target.getFullYear();
    expectedMonth = target.getMonth();
    expectedDay = target.getDate();
    target.setHours(hour, minute, 0, 0);
  } else {
    const parts = dateToken.split("-").map(Number);
    expectedYear = parts[0];
    expectedMonth = parts[1] - 1;
    expectedDay = parts[2];
    target = new Date(expectedYear, expectedMonth, expectedDay, hour, minute, 0, 0);
    if (target.getFullYear() !== expectedYear || target.getMonth() !== expectedMonth || target.getDate() !== expectedDay) {
      return { error: "Schedule date is invalid." };
    }
  }
  if (target.getFullYear() !== expectedYear || target.getMonth() !== expectedMonth || target.getDate() !== expectedDay || target.getHours() !== hour || target.getMinutes() !== minute) {
    return { error: "Schedule time does not exist in the local timezone." };
  }
  if (!prompt)
    return { error: "Schedule prompt is required." };
  const runAtEpoch = target.getTime() / 1000;
  if (!Number.isFinite(runAtEpoch) || runAtEpoch <= now.getTime() / 1000) {
    return { error: "Schedule time must be in the future." };
  }
  const runAtLabel = `${target.toLocaleDateString([], {
    year: "numeric",
    month: "short",
    day: "numeric"
  })} ${formatClockTime12Hour(target)}`;
  return { runAtEpoch, runAtLabel, prompt };
}

// src/prompta/ui/recentChatCache.ts
var DATABASE_NAME = "prompta-recent-chats";
var DATABASE_VERSION = 2;
var STORE_NAME = "chats";
var SUMMARY_STORE_NAME = "summaries";
var SUMMARY_LIMIT = 200;

class RecentChatCache {
  scope;
  limit;
  memory = new Map;
  databasePromise = null;
  constructor(scope, limit = 20) {
    this.scope = scope;
    this.limit = limit;
  }
  getMemory(conversationId) {
    const chat = this.memory.get(conversationId);
    if (!chat)
      return null;
    this.memory.delete(conversationId);
    this.memory.set(conversationId, chat);
    return chat;
  }
  async get(conversationId) {
    const memoryChat = this.getMemory(conversationId);
    if (memoryChat)
      return memoryChat;
    const database = await this.database();
    if (!database)
      return null;
    const record = await new Promise((resolve) => {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const request = transaction.objectStore(STORE_NAME).get(this.key(conversationId));
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => resolve(null);
    });
    if (!record?.chat || record.scope !== this.scope)
      return null;
    this.rememberMemory(conversationId, record.chat);
    this.persist(record.chat);
    return record.chat;
  }
  remember(chat) {
    const conversationId = String(chat?.id || "");
    if (!conversationId)
      return;
    this.rememberMemory(conversationId, chat);
    this.persist(chat);
  }
  rememberSummaries(chats) {
    const summaries = chats.filter((chat) => String(chat?.id || "")).slice(0, SUMMARY_LIMIT);
    this.persistSummaries(summaries);
  }
  async warmSummaries() {
    const database = await this.database();
    if (!database)
      return [];
    const records = await new Promise((resolve) => {
      const transaction = database.transaction(SUMMARY_STORE_NAME, "readonly");
      const request = transaction.objectStore(SUMMARY_STORE_NAME).getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => resolve([]);
    });
    return records.filter((record) => record.scope === this.scope && record.chat).sort((left, right) => left.position - right.position).slice(0, SUMMARY_LIMIT).map((record) => record.chat);
  }
  async warm() {
    const database = await this.database();
    if (!database)
      return [];
    const records = await new Promise((resolve) => {
      const transaction = database.transaction(STORE_NAME, "readonly");
      const request = transaction.objectStore(STORE_NAME).getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => resolve([]);
    });
    const chats = records.filter((record) => record.scope === this.scope && record.chat).sort((left, right) => right.accessedAt - left.accessedAt).slice(0, this.limit).map((record) => record.chat);
    for (const chat of chats) {
      const conversationId = String(chat?.id || "");
      if (conversationId)
        this.rememberMemory(conversationId, chat);
    }
    return chats;
  }
  async remove(conversationId) {
    this.memory.delete(conversationId);
    const database = await this.database();
    if (!database)
      return;
    await new Promise((resolve) => {
      const transaction = database.transaction([STORE_NAME, SUMMARY_STORE_NAME], "readwrite");
      transaction.objectStore(STORE_NAME).delete(this.key(conversationId));
      transaction.objectStore(SUMMARY_STORE_NAME).delete(this.key(conversationId));
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => resolve();
      transaction.onabort = () => resolve();
    });
  }
  rememberMemory(conversationId, chat) {
    this.memory.delete(conversationId);
    this.memory.set(conversationId, chat);
    while (this.memory.size > this.limit) {
      const oldest = this.memory.keys().next().value;
      if (!oldest)
        break;
      this.memory.delete(oldest);
    }
  }
  key(conversationId) {
    return this.scope + ":" + conversationId;
  }
  async persist(chat) {
    const conversationId = String(chat?.id || "");
    if (!conversationId)
      return;
    const database = await this.database();
    if (!database)
      return;
    await new Promise((resolve) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      const store = transaction.objectStore(STORE_NAME);
      store.put({
        key: this.key(conversationId),
        scope: this.scope,
        conversationId,
        chat,
        accessedAt: Date.now()
      });
      const allRequest = store.getAll();
      allRequest.onsuccess = () => {
        const records = (allRequest.result || []).filter((record) => record.scope === this.scope).sort((left, right) => right.accessedAt - left.accessedAt);
        for (const record of records.slice(this.limit))
          store.delete(record.key);
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => resolve();
      transaction.onabort = () => resolve();
    });
  }
  async persistSummaries(chats) {
    const database = await this.database();
    if (!database)
      return;
    const retainedIds = new Set(chats.map((chat) => String(chat.id)));
    await new Promise((resolve) => {
      const transaction = database.transaction(SUMMARY_STORE_NAME, "readwrite");
      const store = transaction.objectStore(SUMMARY_STORE_NAME);
      const allRequest = store.getAll();
      allRequest.onsuccess = () => {
        for (const record of allRequest.result || []) {
          if (record.scope === this.scope && !retainedIds.has(String(record.conversationId || ""))) {
            store.delete(record.key);
          }
        }
        chats.forEach((chat, position) => {
          const conversationId = String(chat.id);
          store.put({
            key: this.key(conversationId),
            scope: this.scope,
            conversationId,
            chat,
            position
          });
        });
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => resolve();
      transaction.onabort = () => resolve();
    });
  }
  database() {
    if (this.databasePromise)
      return this.databasePromise;
    this.databasePromise = new Promise((resolve) => {
      if (!("indexedDB" in globalThis)) {
        resolve(null);
        return;
      }
      let request;
      try {
        request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
      } catch {
        resolve(null);
        return;
      }
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains(STORE_NAME)) {
          database.createObjectStore(STORE_NAME, { keyPath: "key" });
        }
        if (!database.objectStoreNames.contains(SUMMARY_STORE_NAME)) {
          database.createObjectStore(SUMMARY_STORE_NAME, { keyPath: "key" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
      request.onblocked = () => resolve(null);
    });
    return this.databasePromise;
  }
}

// src/prompta/ui/jobsDialog.ts
function requiredElement(selector) {
  const element = document.querySelector(selector);
  if (!element)
    throw new Error(`Missing required jobs UI element: ${selector}`);
  return element;
}
function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function setTextIfChanged(element, value) {
  const text = String(value ?? "");
  if (element.textContent !== text)
    element.textContent = text;
}
async function fetchJson(url, timeoutMs = 1e4) {
  const controller = new AbortController;
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal
    });
    if (!response.ok)
      throw new Error(`${response.status} ${response.statusText}`);
    return await response.json();
  } finally {
    window.clearTimeout(timeout);
  }
}
function formatJobMinutes(value) {
  const minutes = Number(value);
  if (!Number.isFinite(minutes))
    return "";
  if (minutes >= 60 && minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} hour${hours === 1 ? "" : "s"}`;
  }
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}
function jobScheduleText(job) {
  if (job.run_at_epoch) {
    const date = new Date(Number(job.run_at_epoch) * 1000);
    return `once · ${date.toLocaleDateString([], {
      year: "numeric",
      month: "short",
      day: "numeric"
    })} ${formatClockTime12Hour(date)}`;
  }
  if (job.daily_at)
    return `daily · ${formatDailyTime12Hour(job.daily_at)}`;
  return `every ${formatJobMinutes(job.interval_minutes)}${job.exact_interval ? " · exact" : ""}`;
}
function createJobsDialog({ closeSidebar, resizeComposer, syncSendButton }) {
  const els = {
    jobsSidebarButton: requiredElement("#jobsSidebarButton"),
    jobsDialog: requiredElement("#jobsDialog"),
    closeJobsDialog: requiredElement("#closeJobsDialog"),
    jobsDialogStatus: requiredElement("#jobsDialogStatus"),
    jobsList: requiredElement("#jobsList"),
    jobsForm: requiredElement("#jobsForm"),
    jobsFormTitle: requiredElement("#jobsFormTitle"),
    jobNameInput: requiredElement("#jobNameInput"),
    jobPromptInput: requiredElement("#jobPromptInput"),
    jobScheduleType: requiredElement("#jobScheduleType"),
    jobIntervalField: requiredElement("#jobIntervalField"),
    jobIntervalInput: requiredElement("#jobIntervalInput"),
    jobDailyField: requiredElement("#jobDailyField"),
    jobDailyInput: requiredElement("#jobDailyInput"),
    jobExactField: requiredElement("#jobExactField"),
    jobExactInput: requiredElement("#jobExactInput"),
    resetJobForm: requiredElement("#resetJobForm"),
    saveJobButton: requiredElement("#saveJobButton"),
    clearJobsButton: requiredElement("#clearJobsButton"),
    messageInput: requiredElement("#messageInput"),
    slashMenu: requiredElement("#slashMenu")
  };
  let scheduledJobs = [];
  const mobileJobsScreen = window.matchMedia("(max-width: 600px)");
  const appShell = document.querySelector(".app-shell");
  function closeJobsView() {
    if (!els.jobsDialog.open)
      return;
    els.jobsDialog.close();
  }
  function resetJobForm() {
    els.jobsForm.reset();
    setTextIfChanged(els.jobsFormTitle, "Add job");
    els.jobNameInput.readOnly = false;
    els.jobScheduleType.value = "interval";
    els.jobIntervalInput.value = "40";
    els.jobDailyInput.value = "09:00";
    els.jobExactInput.checked = false;
    syncJobScheduleFields();
  }
  function syncJobScheduleFields() {
    const daily = els.jobScheduleType.value === "daily";
    els.jobIntervalField.hidden = daily;
    els.jobDailyField.hidden = !daily;
    els.jobExactField.hidden = daily;
  }
  function renderJobs(jobs) {
    scheduledJobs = Array.isArray(jobs) ? jobs : [];
    els.clearJobsButton.disabled = scheduledJobs.length === 0;
    if (!scheduledJobs.length) {
      els.jobsList.innerHTML = '<div class="jobs-empty">No scheduled jobs.</div>';
      return;
    }
    els.jobsList.innerHTML = scheduledJobs.map((job) => {
      const paused = Boolean(job.paused);
      const canEdit = !job.run_at_epoch;
      return `
        <article class="job-row" data-job-name="${escapeHtml(job.name)}">
          <div class="job-row-top">
            <div>
              <div class="job-row-name">${escapeHtml(job.name)}</div>
              <div class="job-row-meta">${escapeHtml(jobScheduleText(job))}</div>
            </div>
            <span class="job-status">${escapeHtml(job.status || (paused ? "paused" : "pending"))}</span>
          </div>
          <div class="job-row-prompt">${escapeHtml(job.prompt || "")}</div>
          <div class="job-row-actions">
            ${canEdit ? '<button type="button" class="job-action" data-job-action="edit">Edit</button>' : ""}
            <button type="button" class="job-action" data-job-action="${paused ? "resume" : "pause"}">${paused ? "Resume" : "Pause"}</button>
            <button type="button" class="job-action" data-job-action="remove">Remove</button>
          </div>
        </article>
      `;
    }).join("");
  }
  async function loadJobs() {
    setTextIfChanged(els.jobsDialogStatus, "Loading jobs…");
    try {
      const result = await fetchJson("api/jobs");
      renderJobs(result.jobs);
      setTextIfChanged(els.jobsDialogStatus, `${result.jobs?.length || 0} configured job${result.jobs?.length === 1 ? "" : "s"}.`);
    } catch (error) {
      setTextIfChanged(els.jobsDialogStatus, `Could not load jobs: ${String(error).replace(/^Error:\s*/, "")}`);
    }
  }
  async function runJobCommand(payload, successText) {
    setTextIfChanged(els.jobsDialogStatus, "Running Prompta CLI command…");
    els.saveJobButton.disabled = true;
    try {
      const result = await postJsonRequest("api/jobs", payload);
      renderJobs(result.jobs);
      const command = Array.isArray(result.command) ? result.command.join(" ") : "";
      setTextIfChanged(els.jobsDialogStatus, command ? `${successText} · ${command}` : successText);
      return true;
    } catch (error) {
      setTextIfChanged(els.jobsDialogStatus, `Jobs command failed: ${String(error).replace(/^Error:\s*/, "")}`);
      return false;
    } finally {
      els.saveJobButton.disabled = false;
    }
  }
  async function open(clearComposer = false) {
    if (clearComposer) {
      els.messageInput.value = "";
      els.slashMenu.hidden = true;
      resizeComposer();
      syncSendButton();
    }
    resetJobForm();
    if (!els.jobsDialog.open) {
      const stacked = mobileJobsScreen.matches;
      els.jobsDialog.dataset.presentation = stacked ? "stack" : "modal";
      if (stacked) {
        els.jobsDialog.show();
        if (appShell)
          appShell.inert = true;
      } else {
        els.jobsDialog.showModal();
      }
    }
    await loadJobs();
  }
  els.jobsSidebarButton.addEventListener("click", async () => {
    closeSidebar();
    await open();
  });
  els.closeJobsDialog.addEventListener("click", closeJobsView);
  els.jobsDialog.addEventListener("click", (event) => {
    if (event.target === els.jobsDialog && els.jobsDialog.dataset.presentation !== "stack") {
      closeJobsView();
    }
  });
  els.jobsDialog.addEventListener("close", () => {
    if (appShell)
      appShell.inert = false;
    delete els.jobsDialog.dataset.presentation;
  });
  els.jobScheduleType.addEventListener("change", syncJobScheduleFields);
  els.resetJobForm.addEventListener("click", resetJobForm);
  els.jobsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const daily = els.jobScheduleType.value === "daily";
    const payload = {
      action: "add",
      name: els.jobNameInput.value.trim(),
      prompt: els.jobPromptInput.value.trim(),
      daily_at: daily ? els.jobDailyInput.value : "",
      interval_minutes: daily ? null : Number(els.jobIntervalInput.value),
      exact_interval: !daily && els.jobExactInput.checked
    };
    const saved = await runJobCommand(payload, `Saved ${payload.name}`);
    if (saved)
      resetJobForm();
  });
  els.jobsList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-job-action]");
    const row = button?.closest("[data-job-name]");
    if (!button || !row)
      return;
    const name = String(row.dataset.jobName || "");
    const job = scheduledJobs.find((item) => item.name === name);
    if (!job)
      return;
    const action = String(button.dataset.jobAction || "");
    if (action === "edit") {
      setTextIfChanged(els.jobsFormTitle, `Edit ${job.name}`);
      els.jobNameInput.value = job.name;
      els.jobNameInput.readOnly = true;
      els.jobPromptInput.value = job.prompt || "";
      els.jobScheduleType.value = job.daily_at ? "daily" : "interval";
      els.jobDailyInput.value = job.daily_at || "09:00";
      els.jobIntervalInput.value = String(job.interval_minutes || 40);
      els.jobExactInput.checked = Boolean(job.exact_interval);
      syncJobScheduleFields();
      els.jobPromptInput.focus();
      return;
    }
    await runJobCommand({ action, name }, `${action === "remove" ? "Removed" : action === "pause" ? "Paused" : "Resumed"} ${name}`);
  });
  els.clearJobsButton.addEventListener("click", async () => {
    if (!scheduledJobs.length)
      return;
    if (!window.confirm(`Clear all ${scheduledJobs.length} scheduled jobs?`))
      return;
    const cleared = await runJobCommand({ action: "clear" }, "Cleared all scheduled jobs");
    if (cleared)
      resetJobForm();
  });
  function close() {
    closeJobsView();
  }
  return { open, close };
}

// src/prompta/ui/sidebar.ts
function requiredElement2(selector) {
  const element = document.querySelector(selector);
  if (!element)
    throw new Error(`Missing required sidebar UI element: ${selector}`);
  return element;
}
function createSidebar({ onMotionEnd }) {
  const els = {
    sidebar: requiredElement2("#sidebar"),
    openSidebar: requiredElement2("#openSidebar"),
    closeSidebar: requiredElement2("#closeSidebar"),
    sidebarScrim: requiredElement2("#sidebarScrim")
  };
  const mobileSidebarMedia = window.matchMedia("(max-width: 780px)");
  const swipe = {
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
    pendingX: 0,
    cleanupTimer: 0
  };
  let moving = false;
  function isOpen() {
    return els.sidebar.classList.contains("is-open");
  }
  function isMoving() {
    return moving;
  }
  function beginMotion() {
    moving = true;
  }
  function endMotion() {
    if (!moving)
      return;
    moving = false;
    onMotionEnd();
  }
  function mobileEnabled() {
    return mobileSidebarMedia.matches;
  }
  function syncAccessibility() {
    const hidden = mobileSidebarMedia.matches && !isOpen();
    els.sidebar.toggleAttribute("inert", hidden);
    if (hidden)
      els.sidebar.setAttribute("aria-hidden", "true");
    else
      els.sidebar.removeAttribute("aria-hidden");
    els.openSidebar.setAttribute("aria-expanded", String(!hidden));
  }
  function resetDragStyles() {
    if (swipe.frameId) {
      cancelAnimationFrame(swipe.frameId);
      swipe.frameId = 0;
    }
    if (swipe.cleanupTimer) {
      clearTimeout(swipe.cleanupTimer);
      swipe.cleanupTimer = 0;
    }
    els.sidebar.style.removeProperty("transition");
    els.sidebar.style.removeProperty("transform");
    els.sidebarScrim.style.removeProperty("transition");
    els.sidebarScrim.style.removeProperty("opacity");
    endMotion();
  }
  function open() {
    resetDragStyles();
    if (mobileEnabled() && !isOpen())
      beginMotion();
    els.sidebar.classList.add("is-open");
    els.sidebarScrim.classList.add("is-open");
    syncAccessibility();
  }
  function close() {
    resetDragStyles();
    if (mobileEnabled() && isOpen())
      beginMotion();
    els.sidebar.classList.remove("is-open");
    els.sidebarScrim.classList.remove("is-open");
    syncAccessibility();
  }
  function applyDragPosition(x) {
    const width = swipe.sidebarWidth || els.sidebar.getBoundingClientRect().width;
    swipe.progress = Math.max(0, Math.min(1, 1 + x / width));
    els.sidebar.style.transform = `translate3d(${x}px, 0, 0)`;
    els.sidebarScrim.style.opacity = String(swipe.progress);
  }
  function queueDragPosition(x) {
    swipe.pendingX = x;
    if (swipe.frameId)
      return;
    swipe.frameId = requestAnimationFrame(() => {
      swipe.frameId = 0;
      applyDragPosition(swipe.pendingX);
    });
  }
  function settleDrag(opened) {
    const width = swipe.sidebarWidth || els.sidebar.getBoundingClientRect().width;
    if (swipe.frameId) {
      cancelAnimationFrame(swipe.frameId);
      swipe.frameId = 0;
      applyDragPosition(swipe.pendingX);
    }
    const currentX = -width * (1 - swipe.progress);
    const targetX = opened ? 0 : -width;
    const remaining = Math.abs(targetX - currentX);
    const speed = Math.max(0.6, Math.abs(swipe.velocityX));
    const duration = Math.max(90, Math.min(180, Math.round(remaining / speed)));
    els.sidebar.classList.toggle("is-open", opened);
    els.sidebarScrim.classList.toggle("is-open", opened);
    syncAccessibility();
    els.sidebar.style.transition = `transform ${duration}ms cubic-bezier(0.2, 0, 0, 1)`;
    els.sidebar.style.transform = `translate3d(${targetX}px, 0, 0)`;
    els.sidebarScrim.style.transition = `opacity ${duration}ms linear`;
    els.sidebarScrim.style.opacity = opened ? "1" : "0";
    if (swipe.cleanupTimer)
      clearTimeout(swipe.cleanupTimer);
    swipe.cleanupTimer = window.setTimeout(() => {
      swipe.cleanupTimer = 0;
      els.sidebar.style.removeProperty("transition");
      els.sidebar.style.removeProperty("transform");
      els.sidebarScrim.style.removeProperty("transition");
      els.sidebarScrim.style.removeProperty("opacity");
      endMotion();
    }, duration + 30);
  }
  els.openSidebar.addEventListener("click", open);
  els.closeSidebar.addEventListener("click", close);
  els.sidebarScrim.addEventListener("click", close);
  mobileSidebarMedia.addEventListener("change", syncAccessibility);
  window.addEventListener("resize", syncAccessibility);
  syncAccessibility();
  els.sidebar.addEventListener("transitionrun", (event) => {
    if (event.propertyName === "transform" && mobileEnabled())
      beginMotion();
  });
  els.sidebar.addEventListener("transitionend", (event) => {
    if (event.propertyName === "transform")
      endMotion();
  });
  els.sidebar.addEventListener("transitioncancel", (event) => {
    if (event.propertyName === "transform")
      endMotion();
  });
  document.addEventListener("touchstart", (event) => {
    if (!mobileEnabled() || event.touches.length !== 1)
      return;
    resetDragStyles();
    const touch = event.touches[0];
    const sidebarOpen = isOpen();
    if (!sidebarOpen && touch.clientX > 144)
      return;
    swipe.startX = touch.clientX;
    swipe.startY = touch.clientY;
    swipe.lastX = touch.clientX;
    swipe.lastTime = performance.now();
    swipe.velocityX = 0;
    swipe.sidebarWidth = els.sidebar.getBoundingClientRect().width;
    swipe.progress = sidebarOpen ? 1 : 0;
    swipe.wasOpen = sidebarOpen;
    swipe.tracking = true;
    swipe.directionLocked = false;
    swipe.horizontal = false;
    swipe.pendingX = sidebarOpen ? 0 : -swipe.sidebarWidth;
  }, { passive: true });
  document.addEventListener("touchmove", (event) => {
    if (!swipe.tracking || event.touches.length !== 1)
      return;
    const touch = event.touches[0];
    const deltaX = touch.clientX - swipe.startX;
    const deltaY = touch.clientY - swipe.startY;
    if (!swipe.directionLocked && (Math.abs(deltaX) > 8 || Math.abs(deltaY) > 8)) {
      swipe.directionLocked = true;
      swipe.horizontal = Math.abs(deltaX) > Math.abs(deltaY) * 1.15;
      if (swipe.horizontal) {
        beginMotion();
        els.sidebar.style.transition = "none";
        els.sidebarScrim.style.transition = "none";
      }
    }
    if (!swipe.horizontal)
      return;
    const width = swipe.sidebarWidth;
    const startX = swipe.wasOpen ? 0 : -width;
    const x = Math.max(-width, Math.min(0, startX + deltaX));
    const now = performance.now();
    const elapsed = Math.max(1, now - swipe.lastTime);
    swipe.velocityX = (touch.clientX - swipe.lastX) / elapsed;
    swipe.lastX = touch.clientX;
    swipe.lastTime = now;
    queueDragPosition(x);
  }, { passive: true });
  document.addEventListener("touchend", () => {
    if (!swipe.tracking)
      return;
    if (swipe.horizontal) {
      const fastOpen = swipe.velocityX > 0.35;
      const fastClose = swipe.velocityX < -0.35;
      const shouldOpen = fastOpen || !fastClose && swipe.progress >= 0.5;
      settleDrag(shouldOpen);
    }
    swipe.tracking = false;
  }, { passive: true });
  document.addEventListener("touchcancel", () => {
    if (swipe.tracking && swipe.horizontal)
      settleDrag(swipe.wasOpen);
    swipe.tracking = false;
  }, { passive: true });
  return { open, close, isMoving };
}

// src/prompta/ui/markdown.ts
function escapeHtml2(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
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
  return `<span class="syntax-${className}">${escapeHtml2(value)}</span>`;
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
        html += escapeHtml2(value);
      index = cursor;
      continue;
    }
    html += /[[\]{}(),.:;]/.test(source[index]) ? syntaxToken("punctuation", source[index]) : escapeHtml2(source[index]);
    index += 1;
  }
  return html;
}
function inlineMarkdown(text) {
  const placeholders = [];
  let source = String(text || "");
  const stash = (html2) => {
    let token = `PROMPTA_INLINE_${placeholders.length}`;
    while (source.includes(token))
      token += "";
    placeholders.push([token, html2]);
    return token;
  };
  source = replaceChatGptRichMarkers(source, (label, url) => stash(`<a href="${escapeHtml2(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml2(label)}</a>`));
  source = source.replace(/`([^`\n]+)`/g, (_, code) => stash(`<code class="inline-code">${escapeHtml2(code)}</code>`));
  source = source.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)(?:\s+"[^"]*")?\)/g, (_, label, url) => stash(`<a href="${escapeHtml2(url)}" target="_blank" rel="noreferrer noopener">${escapeHtml2(label)}</a>`));
  let html = escapeHtml2(source);
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
function listLine(line) {
  const match = line.match(/^(\s*)([-+*]|\d+[.)])\s+(.+)$/);
  if (!match)
    return null;
  return {
    indent: match[1].replace(/\t/g, "    ").length,
    ordered: /^\d/.test(match[2]),
    content: match[3]
  };
}
function renderListBlock(lines, startIndex, baseIndent = null) {
  const first = listLine(lines[startIndex]);
  if (!first)
    return { html: "", index: startIndex };
  const indent = baseIndent ?? first.indent;
  const ordered = first.ordered;
  const tag = ordered ? "ol" : "ul";
  const items = [];
  let index = startIndex;
  while (index < lines.length) {
    const current = listLine(lines[index]);
    if (!current || current.indent < indent)
      break;
    if (current.indent === indent && current.ordered !== ordered)
      break;
    if (current.indent > indent) {
      if (!items.length)
        break;
      const nested = renderListBlock(lines, index, current.indent);
      if (!nested.html || nested.index === index)
        break;
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
      const tableScrollClass = headers.length >= 3 ? "table-scroll table-scroll-wide" : "table-scroll";
      out.push(`<div class="${tableScrollClass}"><table><thead><tr>${headers.map((cell, column) => `<th${aligns[column] ? ` style="text-align:${aligns[column]}"` : ""}>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headers.map((_, column) => `<td${aligns[column] ? ` style="text-align:${aligns[column]}"` : ""}>${inlineMarkdown(row[column] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
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
var CONTEXTUAL_TOOL_ACTION = /(?:^|_)(?:repl|execute|shell|python|command)(?:_|$)/i;
function expandedToolMetaAddsInformation(summary, action, connector) {
  if (!action)
    return false;
  if (summary)
    return true;
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
  if (toolish && !toolName && !hasUsefulToolDetail && !genericToolInvocation)
    return "";
  const pythonCode = toolish ? pythonToolCallCode(rawToolName, trimmedCode) : "";
  const toolSummary = toolish ? toolCallSummary(trimmedCode) : "";
  const toolTimestamp = toolish ? toolCallTimestampMillis(trimmedCode) : null;
  const toolTimeText = toolTimestamp === null ? "" : formatClockTime12Hour(toolTimestamp, true);
  const toolTime = toolTimestamp === null ? "" : `<time class="tool-time" datetime="${new Date(toolTimestamp).toISOString()}">${escapeHtml2(toolTimeText)}</time>`;
  const renderedCode = pythonCode || (toolish && (!hasUsefulToolDetail || genericToolInvocation) ? "" : code);
  const highlightLanguage = pythonCode ? "python" : toolish ? trimmedCode.startsWith("{") || trimmedCode.startsWith("[") ? "json" : "code" : normalized;
  const label = pythonCode ? "python" : toolish ? "tool call" : rawLanguage || "code";
  const copyButton = renderedCode.trim() ? '<button type="button" class="copy-code">copy</button>' : "";
  const collapsedLabel = toolish && toolName ? toolName : label;
  const header = toolish ? toolSummary ? `<span class="tool-summary">${escapeHtml2(toolSummary)}</span>${toolTime}` : `
        <span class="${toolName ? "tool-primary-name" : "code-language"}">${escapeHtml2(collapsedLabel)}</span>
        ${toolTime}` : `
      <span class="code-language">${escapeHtml2(label)}</span>
      ${copyButton}`;
  const body = renderedCode.trim() ? `<pre><code class="language-${escapeHtml2(highlightLanguage)}">${highlightCode(renderedCode, highlightLanguage)}</code></pre>` : "";
  if (toolish) {
    const toolIdentityParts = toolName.split(/\s*·\s*/).filter(Boolean);
    const expandedAction = toolIdentityParts.length > 1 ? toolIdentityParts[toolIdentityParts.length - 1] : toolName;
    const expandedConnector = toolIdentityParts.length > 1 ? toolIdentityParts.slice(0, -1).join(" · ") : "";
    const expandedToolHeader = expandedToolMetaAddsInformation(toolSummary, expandedAction, expandedConnector) ? `<div class="tool-expanded-meta"><span class="tool-expanded-action">${escapeHtml2(expandedAction)}</span>${expandedConnector ? `<span class="tool-expanded-separator">|</span><span class="tool-expanded-connector">${escapeHtml2(expandedConnector)}</span>` : ""}</div>` : "";
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
function renderMarkdown(raw) {
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

// src/prompta/ui/conversationRenderer.ts
function requiredElement3(selector) {
  const element = document.querySelector(selector);
  if (!element)
    throw new Error("Missing required conversation UI element: " + selector);
  return element;
}
function escapeHtml3(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function setTextIfChanged2(element, value) {
  const text = String(value ?? "");
  if (element.textContent !== text)
    element.textContent = text;
}
function imageAttachments(message) {
  const attachments = Array.isArray(message?.attachments) ? message.attachments : [];
  return attachments.filter((attachment) => {
    if (!attachment || typeof attachment !== "object")
      return false;
    const type = String(attachment.type || "");
    const src = String(attachment.src || "");
    return type.startsWith("image/") && (Boolean(attachment.id) || src.startsWith("data:image/"));
  });
}
function imageAttachmentSrc(attachment) {
  const inline = String(attachment?.src || "");
  if (inline.startsWith("data:image/"))
    return inline;
  const id = String(attachment?.id || "");
  return id ? `api/attachment-previews/${encodeURIComponent(id)}` : "";
}
function renderMessageAttachments(message) {
  const images = imageAttachments(message);
  if (!images.length)
    return "";
  return `<div class="message-attachments">${images.map((attachment) => {
    const src = imageAttachmentSrc(attachment);
    const name = String(attachment.name || "Attached image");
    return `<img class="message-image-preview" src="${escapeHtml3(src)}" alt="${escapeHtml3(name)}" loading="lazy" decoding="async">`;
  }).join("")}</div>`;
}
function pendingImageAttachments(serializedAttachments) {
  return serializedAttachments.filter((attachment) => String(attachment.type || "").startsWith("image/")).map((attachment) => ({
    name: attachment.name,
    type: attachment.type,
    src: `data:${attachment.type};base64,${attachment.data}`
  }));
}
function createConversationRenderer({ onRetry, onDelete }) {
  const conversation = requiredElement3("#conversation");
  const viewport = requiredElement3("#conversationViewport");
  function messageTimestamp(message) {
    const millis = messageTimestampMillis(message.created_at, message.updated_at);
    if (millis === null)
      return { text: "Time unavailable", iso: "", millis: null, age: "" };
    const date = new Date(millis);
    const months = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sept",
      "Oct",
      "Nov",
      "Dec"
    ];
    const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    return {
      text: `${date.getDate()} ${months[date.getMonth()]} ${weekdays[date.getDay()]} ${formatClockTime12Hour(date)}`,
      iso: date.toISOString(),
      millis,
      age: messageAgeText(millis)
    };
  }
  function renderMessageSection(message, allowStreaming = true) {
    const role = message.role === "user" ? "user" : "assistant";
    const streaming = Boolean(message.pending_activity) || allowStreaming && message.status === "streaming";
    const activityLabel = message.pending_activity_label || "writing";
    const label = message.send_error ? "Send error" : "Prompta run";
    const timestamp = messageTimestamp(message);
    const contentHtml = message.pending_activity ? "" : renderMarkdown(message.content);
    const attachmentsHtml = message.pending_activity ? "" : renderMessageAttachments(message);
    return `
      <section class="message ${role}${message.send_error ? " send-error" : ""}">
        <div class="message-inner">
          ${role === "assistant" ? `
            <div class="message-label"><span class="assistant-avatar">${message.send_error ? "!" : "P"}</span> ${label}</div>
          ` : ""}
          ${attachmentsHtml}
          <div class="message-content">${contentHtml}</div>
          ${message.send_error && message.retry_scope && message.retry_key ? `
            <button type="button"
                    class="retry-send-button"
                    data-retry-scope="${escapeHtml3(message.retry_scope)}"
                    data-retry-key="${escapeHtml3(message.retry_key)}">Retry</button>
          ` : ""}
          ${message.pending_delete_key ? `<button type="button" class="delete-pending-button" data-delete-pending-key="${escapeHtml3(message.pending_delete_key)}">Delete</button>` : ""}
          ${streaming ? `
            <div class="streaming-indicator">
              <span class="streaming-dots"><i></i><i></i><i></i></span>
              ${escapeHtml3(activityLabel)}
            </div>
          ` : ""}
          <time class="message-timestamp" datetime="${timestamp.iso}"${timestamp.millis === null ? "" : ` data-message-at="${timestamp.millis}"`}>
            <span class="message-clock">${escapeHtml3(timestamp.text)}</span>${timestamp.age ? `<span class="message-age"> · ${escapeHtml3(timestamp.age)}</span>` : ""}
          </time>
        </div>
      </section>`;
  }
  function messageNodeFingerprint(message, allowStreaming) {
    return JSON.stringify([
      message.role,
      message.status,
      message.content,
      imageAttachments(message).map((attachment) => [
        attachment.id || "",
        attachment.name || "",
        attachment.type || "",
        String(attachment.src || "").length
      ]),
      Boolean(message.send_error),
      Boolean(message.pending_activity),
      message.pending_activity_label,
      message.retry_scope,
      message.retry_key,
      message.pending_delete_key,
      message.created_at,
      message.updated_at,
      allowStreaming
    ]);
  }
  const boundCopyButtons = new WeakSet;
  const boundRetryButtons = new WeakSet;
  const boundDeleteButtons = new WeakSet;
  function bindRetryButtons(root) {
    for (const button of root.querySelectorAll(".retry-send-button")) {
      if (boundRetryButtons.has(button))
        continue;
      boundRetryButtons.add(button);
      button.addEventListener("click", () => {
        onRetry(button.dataset.retryScope || "", button.dataset.retryKey || "");
      });
    }
  }
  function bindDeleteButtons(root) {
    for (const button of root.querySelectorAll(".delete-pending-button")) {
      if (boundDeleteButtons.has(button))
        continue;
      boundDeleteButtons.add(button);
      button.addEventListener("click", () => {
        onDelete(button.dataset.deletePendingKey || "");
      });
    }
  }
  function bindCopyButtons(root) {
    for (const button of root.querySelectorAll(".copy-code")) {
      if (boundCopyButtons.has(button))
        continue;
      boundCopyButtons.add(button);
      button.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        const code = button.closest(".code-block")?.querySelector("pre code")?.textContent || "";
        try {
          await navigator.clipboard.writeText(code);
          const previous = button.textContent;
          setTextIfChanged2(button, "copied");
          setTimeout(() => {
            setTextIfChanged2(button, previous);
          }, 1000);
        } catch {
          setTextIfChanged2(button, "copy unavailable");
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
    bindDeleteButtons(node);
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
    const preserveDetailsOpen = current.tagName === "DETAILS" && next.tagName === "DETAILS";
    const detailsOpen = preserveDetailsOpen ? current.open : false;
    for (const attribute of Array.from(current.attributes)) {
      if (preserveDetailsOpen && attribute.name === "open")
        continue;
      if (!next.hasAttribute(attribute.name))
        current.removeAttribute(attribute.name);
    }
    for (const attribute of Array.from(next.attributes)) {
      if (preserveDetailsOpen && attribute.name === "open")
        continue;
      if (current.getAttribute(attribute.name) !== attribute.value) {
        current.setAttribute(attribute.name, attribute.value);
      }
    }
    patchDomChildren(current, next);
    if (preserveDetailsOpen)
      current.open = detailsOpen;
    return current;
  }
  function domPatchKey(node) {
    if (!node || node.nodeType !== Node.ELEMENT_NODE)
      return "";
    return node.dataset.domKey || "";
  }
  function patchDomChildren(currentParent, nextParent) {
    let index = 0;
    while (index < nextParent.childNodes.length || index < currentParent.childNodes.length) {
      let current = currentParent.childNodes[index];
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
      const nextKey = domPatchKey(next);
      if (nextKey && domPatchKey(current) !== nextKey) {
        const match = Array.from(currentParent.childNodes).slice(index + 1).find((candidate) => domPatchKey(candidate) === nextKey);
        if (match) {
          currentParent.insertBefore(match, current);
          current = match;
        } else {
          currentParent.insertBefore(next.cloneNode(true), current);
          index += 1;
          continue;
        }
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
    let currentAttachments = node.querySelector(".message-attachments");
    const nextAttachments = message.pending_activity ? "" : renderMessageAttachments(message);
    if (!nextAttachments) {
      currentAttachments?.remove();
      currentAttachments = null;
    } else if (!currentAttachments) {
      const template = document.createElement("template");
      template.innerHTML = nextAttachments;
      const nextNode = template.content.firstElementChild;
      if (nextNode)
        content.before(nextNode);
    } else if (currentAttachments.outerHTML !== nextAttachments) {
      const template = document.createElement("template");
      template.innerHTML = nextAttachments;
      const nextNode = template.content.firstElementChild;
      if (nextNode)
        patchDomNode(currentAttachments, nextNode);
    }
    const nextContent = message.pending_activity ? "" : renderMarkdown(message.content);
    if (content.innerHTML !== nextContent) {
      const template = document.createElement("template");
      template.innerHTML = nextContent;
      patchDomChildren(content, template.content);
      bindCopyButtons(content);
    }
    const retryButton = node.querySelector(".retry-send-button");
    const shouldRetry = sendError && Boolean(message.retry_scope) && Boolean(message.retry_key);
    if (shouldRetry) {
      if (retryButton) {
        retryButton.dataset.retryScope = String(message.retry_scope);
        retryButton.dataset.retryKey = String(message.retry_key);
      } else {
        content.insertAdjacentHTML("afterend", `
          <button type="button"
                  class="retry-send-button"
                  data-retry-scope="${escapeHtml3(message.retry_scope)}"
                  data-retry-key="${escapeHtml3(message.retry_key)}">Retry</button>
        `);
        bindRetryButtons(node);
        bindDeleteButtons(node);
      }
    } else if (retryButton) {
      retryButton.remove();
    }
    const timestamp = node.querySelector(".message-timestamp");
    if (!timestamp)
      return false;
    const nextTimestamp = messageTimestamp(message);
    const clock = timestamp.querySelector(".message-clock");
    if (!clock)
      return false;
    setTextIfChanged2(clock, nextTimestamp.text);
    if (timestamp.dateTime !== nextTimestamp.iso)
      timestamp.dateTime = nextTimestamp.iso;
    if (nextTimestamp.millis === null) {
      delete timestamp.dataset.messageAt;
    } else if (timestamp.dataset.messageAt !== String(nextTimestamp.millis)) {
      timestamp.dataset.messageAt = String(nextTimestamp.millis);
    }
    let age = timestamp.querySelector(".message-age");
    if (nextTimestamp.age) {
      if (!age) {
        timestamp.insertAdjacentHTML("beforeend", '<span class="message-age"></span>');
        age = timestamp.querySelector(".message-age");
      }
      if (age)
        setTextIfChanged2(age, ` · ${nextTimestamp.age}`);
    } else {
      age?.remove();
    }
    const shouldStream = Boolean(message.pending_activity) || allowStreaming && message.status === "streaming";
    const activityLabel = message.pending_activity_label || "writing";
    const indicator = node.querySelector(".streaming-indicator");
    if (shouldStream && !indicator) {
      timestamp.insertAdjacentHTML("beforebegin", `
        <div class="streaming-indicator">
          <span class="streaming-dots"><i></i><i></i><i></i></span>
          ${escapeHtml3(activityLabel)}
        </div>
      `);
    } else if (shouldStream && indicator) {
      const labelNode = indicator.lastChild;
      if (labelNode?.nodeType === Node.TEXT_NODE && labelNode.textContent !== ` ${activityLabel}`)
        labelNode.textContent = ` ${activityLabel}`;
    } else if (!shouldStream && indicator) {
      indicator.remove();
    }
    node.dataset.renderFingerprint = messageNodeFingerprint(message, allowStreaming);
    return true;
  }
  function renderMessageNodes(messages, allowStreaming) {
    const existing = new Map(Array.from(conversation.children).map((node) => [
      node.dataset.messageKey,
      node
    ]));
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
      const currentAtIndex = conversation.children[index];
      if (currentAtIndex !== node) {
        conversation.insertBefore(node, currentAtIndex || null);
      }
    });
    for (const node of Array.from(conversation.children)) {
      if (!desiredKeys.has(node.dataset.messageKey))
        node.remove();
    }
  }
  function renderLoadingState() {
    conversation.innerHTML = `
      <div class="conversation-loading" data-message-key="__loading__" aria-live="polite" aria-label="Loading conversation">
        <div class="conversation-loading-row conversation-loading-user"></div>
        <div class="conversation-loading-row conversation-loading-assistant"></div>
        <div class="conversation-loading-row conversation-loading-assistant short"></div>
      </div>`;
  }
  const CONVERSATION_BOTTOM_SLOP = 24;
  let trackedViewport = null;
  function scrollAnchorCandidates(root) {
    return Array.from(root.querySelectorAll(".message-attachments, .message-content > *, .streaming-indicator, .message-timestamp"));
  }
  function scrollAnchorFingerprint(element) {
    const text = String(element.textContent || "").replace(/\s+/g, " ").trim().slice(0, 160);
    return [element.tagName, element.className, text].join("|");
  }
  function captureConversationViewport() {
    const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    const bottomGap = Math.max(0, maxScrollTop - viewport.scrollTop);
    const pinnedToBottom = bottomGap <= CONVERSATION_BOTTOM_SLOP;
    const snapshot = {
      pinnedToBottom,
      scrollTop: viewport.scrollTop,
      anchorElement: null,
      anchorKey: "",
      anchorIndex: -1,
      anchorFingerprint: "",
      anchorOffset: 0
    };
    if (pinnedToBottom)
      return snapshot;
    const viewportTop = viewport.getBoundingClientRect().top;
    const message = Array.from(conversation.children).find((node) => node.getBoundingClientRect().bottom > viewportTop + 1);
    if (!message)
      return snapshot;
    snapshot.anchorKey = String(message.dataset.messageKey || "");
    const candidates = scrollAnchorCandidates(message);
    const anchor = candidates.find((node) => node.getBoundingClientRect().bottom > viewportTop + 1) || message;
    snapshot.anchorElement = anchor;
    snapshot.anchorIndex = candidates.indexOf(anchor);
    snapshot.anchorFingerprint = scrollAnchorFingerprint(anchor);
    snapshot.anchorOffset = anchor.getBoundingClientRect().top - viewportTop;
    return snapshot;
  }
  function resolveConversationAnchor(snapshot) {
    const direct = snapshot.anchorElement;
    if (direct && direct.isConnected && conversation.contains(direct) && scrollAnchorFingerprint(direct) === snapshot.anchorFingerprint)
      return direct;
    const message = Array.from(conversation.children).find((node) => node.dataset.messageKey === snapshot.anchorKey);
    if (!message)
      return null;
    const candidates = scrollAnchorCandidates(message);
    if (snapshot.anchorFingerprint) {
      const matching = candidates.map((node, index) => ({ node, index })).filter(({ node }) => scrollAnchorFingerprint(node) === snapshot.anchorFingerprint).sort((left, right) => Math.abs(left.index - snapshot.anchorIndex) - Math.abs(right.index - snapshot.anchorIndex));
      if (matching.length)
        return matching[0].node;
    }
    return candidates[snapshot.anchorIndex] || message;
  }
  function restoreConversationViewport(snapshot, forceBottom = false) {
    if (forceBottom || snapshot.pinnedToBottom) {
      viewport.scrollTop = viewport.scrollHeight;
      trackedViewport = captureConversationViewport();
      return;
    }
    const anchor = resolveConversationAnchor(snapshot);
    if (anchor) {
      const viewportTop = viewport.getBoundingClientRect().top;
      const nextOffset = anchor.getBoundingClientRect().top - viewportTop;
      const delta = nextOffset - snapshot.anchorOffset;
      if (Math.abs(delta) > 0.5)
        viewport.scrollTop += delta;
    } else {
      const maxScrollTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
      viewport.scrollTop = Math.min(snapshot.scrollTop, maxScrollTop);
    }
    trackedViewport = captureConversationViewport();
  }
  viewport.addEventListener("scroll", () => {
    trackedViewport = captureConversationViewport();
  }, { passive: true });
  conversation.addEventListener("load", (event) => {
    if (!(event.target instanceof HTMLImageElement) || !trackedViewport)
      return;
    restoreConversationViewport(trackedViewport);
  }, true);
  if ("ResizeObserver" in window) {
    const resizeObserver = new ResizeObserver(() => {
      if (!trackedViewport)
        trackedViewport = captureConversationViewport();
      restoreConversationViewport(trackedViewport);
    });
    resizeObserver.observe(conversation);
    resizeObserver.observe(viewport);
  }
  trackedViewport = captureConversationViewport();
  return {
    renderMessageNodes,
    renderLoadingState,
    messageNodeFingerprint,
    captureConversationViewport,
    restoreConversationViewport
  };
}

// src/prompta/ui/attachmentPicker.ts
function requiredElement4(selector) {
  const element = document.querySelector(selector);
  if (!element)
    throw new Error("Missing required attachment UI element: " + selector);
  return element;
}
function escapeHtml4(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function truncate(value, length = 88) {
  const text = String(value || "");
  return text.length > length ? text.slice(0, Math.max(1, length - 1)).trimEnd() + "…" : text;
}
function patchDomNode(current, next) {
  if (current.nodeType !== next.nodeType) {
    current.replaceWith(next.cloneNode(true));
    return;
  }
  if (current.nodeType === Node.TEXT_NODE) {
    if (current.textContent !== next.textContent)
      current.textContent = next.textContent;
    return;
  }
  if (!(current instanceof Element) || !(next instanceof Element) || current.tagName !== next.tagName) {
    current.replaceWith(next.cloneNode(true));
    return;
  }
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
}
function domPatchKey(node) {
  return node instanceof Element ? node.getAttribute("data-dom-key") || "" : "";
}
function patchDomChildren(currentParent, nextParent) {
  const nextChildren = Array.from(nextParent.childNodes);
  for (let index = 0;index < nextChildren.length; index += 1) {
    const next = nextChildren[index];
    let current = currentParent.childNodes[index];
    const nextKey = domPatchKey(next);
    if (nextKey && domPatchKey(current) !== nextKey) {
      const keyed = Array.from(currentParent.childNodes).slice(index + 1).find((node) => domPatchKey(node) === nextKey);
      if (keyed) {
        currentParent.insertBefore(keyed, current || null);
        current = keyed;
      }
    }
    if (!current) {
      currentParent.appendChild(next.cloneNode(true));
      continue;
    }
    patchDomNode(current, next);
  }
  while (currentParent.childNodes.length > nextChildren.length) {
    currentParent.lastChild?.remove();
  }
}
function patchHtmlChildren(element, html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  patchDomChildren(element, template.content);
}
function createAttachmentPicker({ onChange, setStatus }) {
  const els = {
    button: requiredElement4("#attachmentButton"),
    menu: requiredElement4("#attachmentMenu"),
    fileInput: requiredElement4("#fileUploadInput"),
    photoInput: requiredElement4("#photoUploadInput"),
    cameraInput: requiredElement4("#cameraUploadInput"),
    chips: requiredElement4("#attachmentChips")
  };
  let files = [];
  function render() {
    els.chips.hidden = files.length === 0;
    patchHtmlChildren(els.chips, files.map((file, index) => '<span class="attachment-chip" data-dom-key="attachment:' + index + ":" + escapeHtml4(file.name) + '">' + '<span title="' + escapeHtml4(file.name) + '">' + escapeHtml4(truncate(file.name, 28)) + "</span>" + '<button type="button" data-remove-attachment="' + index + '" aria-label="Remove attachment">×</button>' + "</span>").join(""));
    onChange();
  }
  function clear() {
    files = [];
    els.fileInput.value = "";
    els.photoInput.value = "";
    els.cameraInput.value = "";
    render();
  }
  function setDisabled(disabled) {
    els.button.disabled = disabled;
    if (disabled)
      els.menu.hidden = true;
    for (const button of els.chips.querySelectorAll("button")) {
      button.disabled = disabled;
    }
  }
  function add(nextFiles) {
    const current = [...files];
    for (const file of nextFiles) {
      if (current.length >= 5)
        break;
      const duplicate = current.some((existing) => existing.name === file.name && existing.size === file.size && existing.lastModified === file.lastModified);
      if (!duplicate)
        current.push(file);
    }
    files = current;
    render();
    if (nextFiles.length && current.length >= 5) {
      setStatus("Prompta supports up to 5 attachments per message.");
    }
  }
  async function payload(file) {
    if (file.size > 25 * 1024 * 1024) {
      throw new Error(file.name + " is larger than 25 MB");
    }
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader;
      reader.onerror = () => reject(reader.error || new Error("Could not read " + file.name));
      reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
      reader.readAsDataURL(file);
    });
    const comma = dataUrl.indexOf(",");
    return {
      name: file.name,
      type: file.type || "application/octet-stream",
      data: comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl
    };
  }
  async function serialize() {
    const total = files.reduce((sum, file) => sum + Number(file.size || 0), 0);
    if (total > 25 * 1024 * 1024) {
      throw new Error("Attachments exceed the 25 MB Prompta upload limit");
    }
    return Promise.all(files.map(payload));
  }
  function closeMenu() {
    els.menu.hidden = true;
  }
  els.button.addEventListener("click", () => {
    els.menu.hidden = !els.menu.hidden;
  });
  els.menu.addEventListener("click", (event) => {
    const button = event.target.closest("[data-attachment-kind]");
    if (!button)
      return;
    els.menu.hidden = true;
    const kind = button.dataset.attachmentKind;
    if (kind === "photo")
      els.photoInput.click();
    else if (kind === "camera")
      els.cameraInput.click();
    else
      els.fileInput.click();
  });
  for (const input of [els.fileInput, els.photoInput, els.cameraInput]) {
    input.addEventListener("change", () => {
      const selected = Array.from(input.files || []);
      input.value = "";
      add(selected);
    });
  }
  els.chips.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-attachment]");
    if (!button)
      return;
    const index = Number(button.dataset.removeAttachment);
    if (!Number.isInteger(index))
      return;
    files.splice(index, 1);
    render();
  });
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!els.menu.hidden && !els.menu.contains(target) && !els.button.contains(target)) {
      els.menu.hidden = true;
    }
  });
  return {
    clear,
    closeMenu,
    count: () => files.length,
    serialize,
    setDisabled,
    snapshot: () => [...files]
  };
}

// src/prompta/ui/logsPanel.ts
function requiredElement5(selector) {
  const element = document.querySelector(selector);
  if (!element)
    throw new Error("Missing required logs UI element: " + selector);
  return element;
}
function setTextIfChanged3(element, value) {
  const text = String(value ?? "");
  if (element.textContent !== text)
    element.textContent = text;
}
function createLogsPanel({ fetchJson: fetchJson2, formatRelativeTime }) {
  const els = {
    viewport: requiredElement5("#logsViewport"),
    output: requiredElement5("#logOutput"),
    meta: requiredElement5("#logsMeta"),
    serverTitle: requiredElement5("#logsServerTitle")
  };
  let fingerprint = "";
  let refreshTimer = null;
  let visible = false;
  function render(payload) {
    const lines = Array.isArray(payload.lines) ? payload.lines : [];
    const nextFingerprint = JSON.stringify([payload.updated_at, lines]);
    const wasNearBottom = els.viewport.scrollHeight - els.viewport.scrollTop - els.viewport.clientHeight < 120;
    const isInitial = !fingerprint;
    if (nextFingerprint !== fingerprint) {
      fingerprint = nextFingerprint;
      setTextIfChanged3(els.output, lines.length ? lines.join(`
`) : "No Prompta service logs are available yet.");
      if (isInitial || wasNearBottom) {
        requestAnimationFrame(() => {
          els.viewport.scrollTop = els.viewport.scrollHeight;
        });
      }
    }
    setTextIfChanged3(els.meta, payload.exists ? payload.source === "journal" ? lines.length + " lines · live journal" : lines.length + " lines · synced " + formatRelativeTime(payload.updated_at) : "Waiting for Prompta service logs");
  }
  async function load() {
    try {
      render(await fetchJson2("api/logs?limit=800"));
    } catch (error) {
      setTextIfChanged3(els.meta, "Logs unavailable");
      console.error(error);
    }
  }
  function stopRefresh() {
    if (refreshTimer === null)
      return;
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  function setVisible(nextVisible) {
    visible = Boolean(nextVisible);
    els.viewport.hidden = !visible;
    stopRefresh();
    if (!visible)
      return;
    load();
    refreshTimer = setInterval(() => {
      if (visible && document.visibilityState === "visible")
        load();
    }, 2000);
  }
  function setServerTitle(display) {
    setTextIfChanged3(els.serverTitle, String(display || "") + " · prompta.service");
  }
  return {
    load,
    setServerTitle,
    setVisible
  };
}

// src/prompta/ui/deploymentMonitor.ts
function createDeploymentMonitor({
  onUpdateAvailable = () => {}
} = {}) {
  let head = "";
  let updateAvailable = false;
  let reloading = false;
  async function updateServiceWorker() {
    try {
      if ("serviceWorker" in navigator) {
        const registration = await navigator.serviceWorker.getRegistration();
        await registration?.update();
      }
    } catch (error) {
      console.warn("Could not update Prompta service worker for deployment", error);
    }
  }
  async function applyUpdate() {
    if (reloading)
      return;
    reloading = true;
    await updateServiceWorker();
    window.location.reload();
  }
  function observeHead(value) {
    const nextHead = String(value || "").trim().toLowerCase();
    if (!nextHead)
      return;
    if (!head) {
      head = nextHead;
      return;
    }
    if (nextHead === head)
      return;
    head = nextHead;
    updateAvailable = true;
    onUpdateAvailable(head);
  }
  function handleVisibilityChange() {
    if (updateAvailable)
      onUpdateAvailable(head);
  }
  function registerServiceWorker() {
    if (!("serviceWorker" in navigator))
      return;
    navigator.serviceWorker.register("./sw.js", { updateViaCache: "none" }).catch((error) => {
      console.warn("Could not register Prompta service worker", error);
    });
  }
  return {
    applyUpdate,
    handleVisibilityChange,
    observeHead,
    registerServiceWorker
  };
}

// src/prompta/ui/liveUpdates.ts
function createLiveUpdates({
  loadChats,
  loadServerIdentity,
  setServerStatus,
  observeHead,
  refreshDisplayedTimes,
  onStreamError,
  onPageShow,
  presenceStaleMs = 16000,
  presenceCheckMs = 1000
}) {
  let eventSource = null;
  let fallbackTimer = null;
  let timeRefreshTimer = null;
  let presenceTimer = null;
  let paused = false;
  let refreshRunning = false;
  let refreshAgain = false;
  let lastPresenceAt = 0;
  let lastServer = "";
  async function drainRefreshes() {
    try {
      do {
        refreshAgain = false;
        await loadChats();
      } while (refreshAgain && !paused);
    } finally {
      refreshRunning = false;
      if (refreshAgain && !paused)
        queueRefresh();
    }
  }
  function queueRefresh() {
    if (refreshRunning) {
      refreshAgain = true;
      return;
    }
    refreshRunning = true;
    drainRefreshes();
  }
  function stopTimeRefresh() {
    if (timeRefreshTimer === null)
      return;
    clearInterval(timeRefreshTimer);
    timeRefreshTimer = null;
  }
  function startTimeRefresh() {
    if (timeRefreshTimer !== null)
      return;
    timeRefreshTimer = setInterval(() => refreshDisplayedTimes(), 30000);
  }
  function stopFallbackRefresh() {
    if (fallbackTimer === null)
      return;
    clearInterval(fallbackTimer);
    fallbackTimer = null;
  }
  function startFallbackRefresh() {
    if (fallbackTimer !== null)
      return;
    fallbackTimer = setInterval(() => {
      loadChats();
      loadServerIdentity();
    }, 5000);
  }
  function markPresence(payload) {
    const server = String(payload.server || lastServer || "");
    if (server)
      lastServer = server;
    lastPresenceAt = Date.now();
    if (server && typeof payload.online === "boolean")
      setServerStatus(server, payload.online);
  }
  function markStreamOffline() {
    lastPresenceAt = 0;
    if (lastServer)
      setServerStatus(lastServer, false);
    onStreamError();
  }
  function handleStatusEvent(event, refreshChats) {
    stopFallbackRefresh();
    try {
      const payload = JSON.parse(event.data || "{}");
      markPresence(payload);
      if (payload.head)
        observeHead(payload.head);
    } catch (error) {
      console.warn("Could not parse Prompta SSE status", error);
    }
    if (refreshChats)
      queueRefresh();
  }
  function stopPresenceWatchdog() {
    if (presenceTimer === null)
      return;
    clearInterval(presenceTimer);
    presenceTimer = null;
  }
  function startPresenceWatchdog() {
    if (presenceTimer !== null)
      return;
    presenceTimer = setInterval(() => {
      if (!lastPresenceAt || Date.now() - lastPresenceAt <= presenceStaleMs)
        return;
      markStreamOffline();
      startFallbackRefresh();
    }, presenceCheckMs);
  }
  function stopEventStream() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    stopFallbackRefresh();
  }
  function startEventStream() {
    if (eventSource)
      return;
    if (!("EventSource" in window)) {
      startFallbackRefresh();
      return;
    }
    const events = new EventSource("api/events");
    eventSource = events;
    events.addEventListener("refresh", (event) => {
      handleStatusEvent(event, true);
    });
    events.addEventListener("heartbeat", (event) => {
      handleStatusEvent(event, false);
    });
    events.addEventListener("error", () => {
      markStreamOffline();
      startFallbackRefresh();
    });
  }
  function start() {
    startEventStream();
    startPresenceWatchdog();
    startTimeRefresh();
  }
  function stop() {
    stopEventStream();
    stopPresenceWatchdog();
    stopTimeRefresh();
  }
  window.addEventListener("pagehide", () => {
    paused = true;
    stop();
  });
  window.addEventListener("pageshow", () => {
    onPageShow();
    if (!paused)
      return;
    paused = false;
    loadServerIdentity();
    loadChats();
    start();
  });
  return {
    start,
    stop
  };
}

// src/prompta/ui/completionNotifications.ts
function createCompletionNotifications({ displayServerName, getServerName, chatTitle }) {
  const chatStatuses = new Map;
  const explicitlyActive = new Set;
  const pendingFinishedChats = new Map;
  const notifiedCompletions = new Set;
  let baselineReady = false;
  let permissionRequest = null;
  let flushingNotifications = false;
  function completionKey(chat) {
    return String(chat.id || "") + ":" + String(chat.completed_at ?? chat.updated_at ?? "");
  }
  async function showChatFinished(chat) {
    if (!("Notification" in window) || Notification.permission !== "granted")
      return false;
    const display = displayServerName(getServerName() || location.hostname);
    const title = chatTitle(chat);
    const options = {
      body: title + " finished",
      tag: "prompta-finished-" + chat.id,
      icon: "./icon.svg",
      badge: "./icon.svg",
      data: { url: "./#/" + encodeURIComponent(chat.id) }
    };
    if ("serviceWorker" in navigator) {
      try {
        let registration = typeof navigator.serviceWorker.getRegistration === "function" ? await navigator.serviceWorker.getRegistration() : null;
        if (!registration) {
          registration = await Promise.race([
            navigator.serviceWorker.ready,
            new Promise((resolve) => setTimeout(() => resolve(null), 1500))
          ]);
        }
        if (registration) {
          await registration.showNotification("Prompta · " + display, options);
          return true;
        }
      } catch (error) {
        console.warn("Could not show Prompta service worker notification", error);
      }
    }
    try {
      new Notification("Prompta · " + display, options);
      return true;
    } catch (error) {
      console.warn("Could not show Prompta completion notification", error);
      return false;
    }
  }
  async function flushPendingNotifications() {
    if (flushingNotifications || !("Notification" in window) || Notification.permission !== "granted")
      return;
    flushingNotifications = true;
    try {
      while (pendingFinishedChats.size) {
        const [key, chat] = pendingFinishedChats.entries().next().value;
        if (!await showChatFinished(chat))
          break;
        pendingFinishedChats.delete(key);
        notifiedCompletions.add(key);
      }
    } finally {
      flushingNotifications = false;
    }
  }
  async function requestPermissionFromGesture() {
    if (!("Notification" in window))
      return;
    if (Notification.permission === "granted") {
      await flushPendingNotifications();
      return;
    }
    if (Notification.permission !== "default")
      return;
    if (!permissionRequest) {
      permissionRequest = Notification.requestPermission().catch((error) => {
        console.warn("Could not request notification permission", error);
        return "default";
      }).finally(() => {
        permissionRequest = null;
      });
    }
    const permission = await permissionRequest;
    if (permission === "granted") {
      await flushPendingNotifications();
    }
  }
  function queueFinishedChat(chat) {
    const key = completionKey(chat);
    if (!chat.id || notifiedCompletions.has(key) || pendingFinishedChats.has(key))
      return;
    pendingFinishedChats.set(key, chat);
    flushPendingNotifications();
  }
  function markActive(conversationId) {
    const id = String(conversationId || "");
    if (!id)
      return;
    chatStatuses.set(id, "active");
    explicitlyActive.add(id);
  }
  function trackCompletions(chats) {
    for (const chat of chats) {
      const wasActive = chatStatuses.get(chat.id) === "active" || explicitlyActive.has(chat.id);
      if ((baselineReady || explicitlyActive.has(chat.id)) && wasActive && chat.status === "complete") {
        queueFinishedChat(chat);
        explicitlyActive.delete(chat.id);
      } else if (!["active", "complete"].includes(chat.status)) {
        explicitlyActive.delete(chat.id);
      }
    }
    for (const chat of chats)
      chatStatuses.set(chat.id, chat.status);
    baselineReady = true;
    flushPendingNotifications();
  }
  return {
    markActive,
    requestPermissionFromGesture,
    trackCompletions
  };
}

// src/prompta/ui/changelogDialog.ts
function requiredElement6(selector) {
  const element = document.querySelector(selector);
  if (!element)
    throw new Error("Missing required changelog UI element: " + selector);
  return element;
}
function escapeHtml5(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}
function setTextIfChanged4(element, value) {
  const text = String(value ?? "");
  if (element.textContent !== text)
    element.textContent = text;
}
function createChangelogDialog({ fetchJson: fetchJson2, closeSidebar }) {
  const els = {
    headLabel: requiredElement6("#headLabel"),
    dialog: requiredElement6("#changelogDialog"),
    closeButton: requiredElement6("#closeChangelogDialog"),
    list: requiredElement6("#changelogList"),
    status: requiredElement6("#changelogDialogStatus")
  };
  function close() {
    if (els.dialog.open)
      els.dialog.close();
  }
  async function open() {
    closeSidebar();
    if (!els.dialog.open)
      els.dialog.showModal();
    setTextIfChanged4(els.status, "Loading changelog…");
    els.list.innerHTML = '<li class="changelog-empty">Loading changes…</li>';
    try {
      const payload = await fetchJson2("api/changelog");
      const changes = Array.isArray(payload.changes) ? payload.changes : [];
      els.list.innerHTML = changes.length ? changes.map((change) => '<li class="changelog-entry">' + escapeHtml5(change?.title || "") + "</li>").join("") : '<li class="changelog-empty">No Git commit history is available.</li>';
      setTextIfChanged4(els.status, changes.length + " commit" + (changes.length === 1 ? "" : "s") + " · newest first");
    } catch (error) {
      els.list.innerHTML = '<li class="changelog-empty">Could not load changelog.</li>';
      setTextIfChanged4(els.status, "Changelog unavailable: " + String(error).replace(/^Error:\s*/, ""));
    }
  }
  els.headLabel.addEventListener("click", () => void open());
  els.closeButton.addEventListener("click", close);
  els.dialog.addEventListener("click", (event) => {
    if (event.target === els.dialog)
      close();
  });
  return { open, close };
}

// src/prompta/ui/clientStorage.ts
var PINNED_CHATS_KEY = "prompta:pinned-chats";
var COMPOSER_DRAFTS_KEY = "prompta:composer-drafts";
function loadPinnedIds() {
  try {
    const stored = JSON.parse(localStorage.getItem(PINNED_CHATS_KEY) || "[]");
    return new Set(Array.isArray(stored) ? stored.map((id) => String(id)) : []);
  } catch {
    return new Set;
  }
}
function savePinnedIds(pinnedIds) {
  try {
    localStorage.setItem(PINNED_CHATS_KEY, JSON.stringify(Array.from(pinnedIds)));
  } catch {}
}
function loadComposerDrafts() {
  try {
    const stored = JSON.parse(localStorage.getItem(COMPOSER_DRAFTS_KEY) || "{}");
    if (!stored || Array.isArray(stored) || typeof stored !== "object")
      return new Map;
    return new Map(Object.entries(stored).filter(([, value]) => typeof value === "string" && value).map(([key, value]) => [key, typeof value === "string" ? value : ""]));
  } catch {
    return new Map;
  }
}
function saveComposerDrafts(composerDrafts) {
  try {
    localStorage.setItem(COMPOSER_DRAFTS_KEY, JSON.stringify(Object.fromEntries(composerDrafts)));
  } catch {}
}

// src/prompta/ui/app.ts
var recentChatCache = new RecentChatCache(location.pathname.replace(/\/$/, "") || "/", 20);
function promotePendingConversationPin(pending, nextConversationId) {
  const changed = promotePinnedConversationId(state.pinnedIds, pending, nextConversationId);
  if (changed) {
    savePinnedIds(state.pinnedIds);
    state.sidebarFingerprint = "";
  }
  return changed;
}
function promoteServerPendingPins(chats) {
  let changed = false;
  for (const chat of chats) {
    const clientId = String(chat._client_id || "").trim();
    if (!chat._pending_send || !clientId)
      continue;
    changed = promotePinnedConversationId(state.pinnedIds, { clientId }, String(chat.id || "")) || changed;
  }
  if (changed) {
    savePinnedIds(state.pinnedIds);
    state.sidebarFingerprint = "";
  }
}
var state = {
  chats: [],
  selectedId: null,
  selectedUpdatedAt: null,
  selectedFingerprint: "",
  search: "",
  sidebarFingerprint: "",
  mode: "chats",
  sending: false,
  stopping: false,
  composingNew: false,
  pendingNewId: null,
  pendingNewSend: null,
  pendingReplies: new Map,
  newChatFingerprint: "",
  selectedMetaFingerprint: "",
  chatsRequestId: 0,
  chatOrderScope: null,
  selectedRequestId: 0,
  selectedChat: null,
  selectedVisibleMessageCount: 0,
  renderedConversationId: "",
  conversationViewports: new Map,
  chatSwitchToken: 0,
  optimisticSequence: 0,
  serverName: "",
  serverOnline: null,
  pinnedIds: loadPinnedIds(),
  composerDrafts: loadComposerDrafts(),
  composerDraftTarget: "",
  activityProbes: new Set,
  activityProbeAt: new Map
};
function syncViewportHeight() {
  const viewportHeight = window.visualViewport?.height || window.innerHeight;
  document.documentElement.style.setProperty("--app-height", `${Math.round(viewportHeight)}px`);
}
syncViewportHeight();
window.setTimeout(() => document.documentElement.classList.remove("booting"), 1200);
window.addEventListener("resize", syncViewportHeight);
window.visualViewport?.addEventListener("resize", syncViewportHeight);
function requiredElement7(selector) {
  const element = document.querySelector(selector);
  if (!element)
    throw new Error(`Missing required UI element: ${selector}`);
  return element;
}
var els = {
  chatList: requiredElement7("#chatList"),
  searchInput: requiredElement7("#searchInput"),
  conversation: requiredElement7("#conversation"),
  emptyState: requiredElement7("#emptyState"),
  viewport: requiredElement7("#conversationViewport"),
  chatHeading: requiredElement7("#chatHeading"),
  syncLabel: requiredElement7("#syncLabel"),
  cacheSummary: requiredElement7("#cacheSummary"),
  headLabel: requiredElement7("#headLabel"),
  versionUpdateNotice: requiredElement7("#versionUpdateNotice"),
  globalLiveOrb: requiredElement7("#globalLiveOrb"),
  serverLabel: requiredElement7("#serverLabel"),
  newChatButton: requiredElement7("#newChatButton"),
  pinChatButton: requiredElement7("#pinChatButton"),
  shareChatButton: requiredElement7("#shareChatButton"),
  slashMenu: requiredElement7("#slashMenu"),
  composerFooter: requiredElement7("#composerFooter"),
  messageForm: requiredElement7("#messageForm"),
  messageInput: requiredElement7("#messageInput"),
  sendButton: requiredElement7("#sendButton"),
  composerStatus: requiredElement7("#composerStatus")
};
var sidebarRenderDeferred = false;
var sidebar = createSidebar({
  onMotionEnd: () => {
    if (!sidebarRenderDeferred)
      return;
    sidebarRenderDeferred = false;
    renderSidebar();
  }
});
var jobsDialog = createJobsDialog({
  closeSidebar: sidebar.close,
  resizeComposer,
  syncSendButton
});
var conversationRenderer = createConversationRenderer({
  onRetry: retryFailedSend,
  onDelete: deletePendingSend
});
var attachmentPicker = createAttachmentPicker({
  onChange: syncSendButton,
  setStatus: (message) => setTextIfChanged5(els.composerStatus, message)
});
var logsPanel = createLogsPanel({
  fetchJson: (url, timeoutMs) => fetchJson2(url, timeoutMs),
  formatRelativeTime
});
var deploymentMonitor = createDeploymentMonitor({
  onUpdateAvailable: () => {
    els.versionUpdateNotice.hidden = false;
  }
});
els.versionUpdateNotice.addEventListener("click", () => {
  els.versionUpdateNotice.disabled = true;
  els.versionUpdateNotice.textContent = "Updating Prompta…";
  deploymentMonitor.applyUpdate();
});
createChangelogDialog({
  fetchJson: (url, timeoutMs) => fetchJson2(url, timeoutMs),
  closeSidebar: sidebar.close
});
var completionNotifications = createCompletionNotifications({
  displayServerName,
  getServerName: () => state.serverName,
  chatTitle
});
var liveUpdates = createLiveUpdates({
  loadChats: () => loadChats(),
  loadServerIdentity: () => loadServerIdentity(),
  setServerStatus,
  observeHead: (head) => deploymentMonitor.observeHead(head),
  refreshDisplayedTimes,
  onStreamError: () => els.globalLiveOrb.classList.remove("live"),
  onPageShow: () => deploymentMonitor.handleVisibilityChange()
});
function composerDraftTarget() {
  if (state.composingNew)
    return "new";
  return state.selectedId ? "chat:" + state.selectedId : "";
}
function setStoredComposerDraft(target, value) {
  if (!target)
    return;
  const draft = String(value || "");
  if (draft)
    state.composerDrafts.set(target, draft);
  else
    state.composerDrafts.delete(target);
  saveComposerDrafts(state.composerDrafts);
}
function persistComposerDraft() {
  const target = composerDraftTarget();
  if (!target)
    return;
  state.composerDraftTarget = target;
  setStoredComposerDraft(target, els.messageInput.value);
}
function clearComposerDraft(target = composerDraftTarget()) {
  if (!target)
    return;
  if (state.composerDrafts.delete(target))
    saveComposerDrafts(state.composerDrafts);
}
function syncComposerDraftTarget() {
  const nextTarget = composerDraftTarget();
  if (nextTarget === state.composerDraftTarget)
    return;
  if (state.composerDraftTarget && !state.sending) {
    setStoredComposerDraft(state.composerDraftTarget, els.messageInput.value);
  }
  state.composerDraftTarget = nextTarget;
  const draft = nextTarget ? state.composerDrafts.get(nextTarget) || "" : "";
  if (els.messageInput.value !== draft)
    els.messageInput.value = draft;
  resizeComposer();
  updateSlashMenu();
  syncSendButton();
}
function setTextIfChanged5(element, value) {
  const text = String(value ?? "");
  if (element.textContent !== text)
    element.textContent = text;
}
function setHiddenIfChanged(element, hidden) {
  if (element.hidden !== hidden)
    element.hidden = hidden;
}
function patchDomNode2(current, next) {
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
  const preserveDetailsOpen = current.tagName === "DETAILS" && next.tagName === "DETAILS";
  const detailsOpen = preserveDetailsOpen ? current.open : false;
  for (const attribute of Array.from(current.attributes)) {
    if (preserveDetailsOpen && attribute.name === "open")
      continue;
    if (!next.hasAttribute(attribute.name))
      current.removeAttribute(attribute.name);
  }
  for (const attribute of Array.from(next.attributes)) {
    if (preserveDetailsOpen && attribute.name === "open")
      continue;
    if (current.getAttribute(attribute.name) !== attribute.value) {
      current.setAttribute(attribute.name, attribute.value);
    }
  }
  patchDomChildren2(current, next);
  if (preserveDetailsOpen)
    current.open = detailsOpen;
  return current;
}
function domPatchKey2(node) {
  if (!node || node.nodeType !== Node.ELEMENT_NODE)
    return "";
  return node.dataset.domKey || "";
}
function patchDomChildren2(currentParent, nextParent) {
  let index = 0;
  while (index < nextParent.childNodes.length || index < currentParent.childNodes.length) {
    let current = currentParent.childNodes[index];
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
    const nextKey = domPatchKey2(next);
    if (nextKey && domPatchKey2(current) !== nextKey) {
      const match = Array.from(currentParent.childNodes).slice(index + 1).find((candidate) => domPatchKey2(candidate) === nextKey);
      if (match) {
        currentParent.insertBefore(match, current);
        current = match;
      } else {
        currentParent.insertBefore(next.cloneNode(true), current);
        index += 1;
        continue;
      }
    }
    patchDomNode2(current, next);
    index += 1;
  }
}
function patchHtmlChildren2(element, html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  patchDomChildren2(element, template.content);
}
function setConversationHeading(title, meta) {
  let titleNode = els.chatHeading.querySelector(".heading-title");
  let metaNode = els.chatHeading.querySelector(".heading-meta");
  if (!titleNode) {
    titleNode = document.createElement("div");
    titleNode.className = "heading-title";
    els.chatHeading.prepend(titleNode);
  }
  if (!metaNode) {
    metaNode = document.createElement("div");
    metaNode.className = "heading-meta";
    els.chatHeading.append(metaNode);
  }
  setTextIfChanged5(titleNode, title);
  setTextIfChanged5(metaNode, meta);
}
var SEND_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>';
var STOP_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7.5" y="7.5" width="9" height="9" rx="1.5" fill="currentColor" stroke="none"/></svg>';
function syncSendButton() {
  const waitingNew = state.composingNew && state.pendingNewSend && !["failed", "dead_lettered", "succeeded"].includes(state.pendingNewSend.status);
  const hasTarget = state.composingNew || Boolean(state.selectedId);
  const hasContent = composerHasContent(els.messageInput.value, attachmentPicker.count());
  const canCompose = state.mode === "chats" && !els.messageInput.disabled && hasTarget;
  const stopMode = canCompose && shouldShowStopAction(state.selectedChat?.status, state.composingNew, hasContent);
  const probingActivity = Boolean(state.selectedId && state.activityProbes.has(state.selectedId));
  const action = stopMode ? "stop" : "send";
  if (els.sendButton.dataset.action !== action) {
    els.sendButton.dataset.action = action;
    patchHtmlChildren2(els.sendButton, stopMode ? STOP_ICON : SEND_ICON);
    els.sendButton.setAttribute("aria-label", stopMode ? "Stop response" : "Send message");
    els.sendButton.title = stopMode ? "Stop response" : "Send message";
  }
  els.sendButton.disabled = !canCompose || state.sending || state.stopping || probingActivity || !stopMode && (Boolean(waitingNew) || !hasContent);
}
function updateComposerActionButton() {
  syncSendButton();
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
  setTextIfChanged5(els.serverLabel, knownOnline === false ? `Server · ${display} · offline` : `Server · ${display}`);
  document.title = `Prompta · ${display}`;
  logsPanel.setServerTitle(display);
  const appleTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]');
  if (appleTitle)
    appleTitle.setAttribute("content", `Prompta ${display}`);
  els.globalLiveOrb.classList.toggle("live", knownOnline === true);
  els.globalLiveOrb.title = knownOnline === false ? `${display} is offline` : knownOnline === true ? `${display} is online` : `${display} status unknown`;
}
function escapeHtml6(value) {
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
function truncate2(value, length = 88) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= length ? text : `${text.slice(0, length - 1)}…`;
}
function sidebarGroupAt(chat) {
  return Number(chat?._sidebarGroupAt || chatActivityAt(chat) || 0);
}
function groupChats(chats) {
  const pinned = chats.filter((chat) => state.pinnedIds.has(chat.id));
  const unpinned = chats.filter((chat) => !state.pinnedIds.has(chat.id));
  const groups = [
    ["Pinned", pinned],
    ["Today", unpinned.filter((chat) => sameLocalDay(sidebarGroupAt(chat)))],
    ["Yesterday", unpinned.filter((chat) => sameLocalDay(sidebarGroupAt(chat), 1))],
    [
      "Previous",
      unpinned.filter((chat) => !sameLocalDay(sidebarGroupAt(chat)) && !sameLocalDay(sidebarGroupAt(chat), 1))
    ]
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
  "retrying",
  "failed",
  "dead_lettered",
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
  const knownConversationIds = new Set(state.chats.map((chat) => String(chat.id)));
  const matched = matchingOptimisticConversation(chats, pending, knownConversationIds);
  if (!matched)
    return;
  promotePendingConversationPin(pending, matched.id);
  pending.conversationId = matched.id;
  state.pendingNewId = matched.id;
  if (pending.status === "succeeded" && !matched._pending_send && !state.composingNew && state.selectedId !== matched.id) {
    state.pendingNewSend = null;
    state.pendingNewId = null;
  }
}
function sidebarChats() {
  const chats = state.chats.map((chat) => {
    const pending2 = state.pendingReplies.get(chat.id) || [];
    if (!pending2.length)
      return chat;
    const latest = pending2[pending2.length - 1];
    return {
      ...chat,
      status: ["failed", "dead_lettered"].includes(latest.status || "") ? chat.status : "active",
      preview: latest.message,
      updated_at: Math.max(Number(chat.updated_at || 0), Number(latest.updatedAt || 0)),
      _optimisticReply: true
    };
  });
  chats.unshift(...missingPendingConversationSummaries(chats, state.pendingReplies, state.search));
  const pending = state.pendingNewSend;
  if (!pending)
    return chats;
  const matched = matchingOptimisticConversation(chats, pending);
  if (matched) {
    promotePendingConversationPin(pending, matched.id);
    pending.conversationId = matched.id;
    state.pendingNewId = matched.id;
    return chats;
  }
  const pendingId = pendingConversationDisplayId(pending);
  const optimistic = {
    id: pendingId,
    status: ["failed", "dead_lettered"].includes(pending.status) ? pending.status : "active",
    title: truncate2(pending.message, 72) || "New chat",
    preview: pending.message,
    message_count: 1,
    job_name: "new chat",
    updated_at: pending.updatedAt,
    _optimisticNew: true
  };
  const needle = state.search.trim().toLowerCase();
  if (needle && ![optimistic.title, optimistic.preview, optimistic.job_name].some((value) => String(value || "").toLowerCase().includes(needle))) {
    return chats;
  }
  return [optimistic, ...chats];
}
var boundSidebarItems = new WeakSet;
var boundSidebarPins = new WeakSet;
function renderSidebar(force = false) {
  if (sidebar.isMoving()) {
    sidebarRenderDeferred = true;
    return;
  }
  const chats = sidebarChats();
  const fingerprint = JSON.stringify(chats.map((chat) => [
    chat.id,
    chat.status,
    chat.title,
    sidebarChatPreviewText(chat.preview, chat.prompt),
    chat.message_count,
    chat.job_name,
    chatActivityAt(chat),
    Boolean(chat._optimisticNew),
    Boolean(chat._optimisticReply),
    state.pinnedIds.has(chat.id)
  ])) + state.selectedId + state.composingNew + new Date().toDateString();
  if (!force && fingerprint === state.sidebarFingerprint)
    return;
  state.sidebarFingerprint = fingerprint;
  if (!chats.length) {
    patchHtmlChildren2(els.chatList, `
      <div class="list-empty">
        ${state.search ? "No cached chats match your search." : "No cached conversations yet.<br>Prompta runs will appear here live."}
      </div>`);
    return;
  }
  patchHtmlChildren2(els.chatList, groupChats(chats).map(([label, groupedChats]) => `
    <section class="chat-group" data-dom-key="group:${escapeHtml6(label)}">
      <div class="chat-group-label">${escapeHtml6(label)}</div>
      ${groupedChats.map((chat) => {
    const selected = chat.id === state.selectedId || chat._optimisticNew && state.composingNew;
    return `
        <div class="chat-item ${selected ? "selected" : ""}" data-dom-key="chat:${escapeHtml6(chat.id)}">
          <button type="button"
                  class="chat-item-select"
                  data-chat-id="${escapeHtml6(chat.id)}"
                  data-optimistic-new="${chat._optimisticNew ? "true" : "false"}">
            <div class="chat-item-top">
              ${sidebarStatusDot(chat.status)}
              <span class="chat-title">${escapeHtml6(chatTitle(chat))}</span>
            </div>
            <div class="chat-preview">${escapeHtml6(truncate2(sidebarChatPreviewText(chat.preview, chat.prompt) || "Waiting for messages…"))}</div>
            <div class="chat-meta">
              <span class="chat-job">${escapeHtml6(chat.job_name || `${chat.message_count || 0} messages`)}</span>
              <span class="chat-time" data-activity-at="${escapeHtml6(chatActivityAt(chat))}">${escapeHtml6(formatRelativeTime(chatActivityAt(chat)))}</span>
            </div>
          </button>
          <button type="button"
                  class="chat-row-pin ${state.pinnedIds.has(chat.id) ? "active" : ""}"
                  data-pin-chat-id="${escapeHtml6(chat.id)}"
                  aria-label="${state.pinnedIds.has(chat.id) ? "Unpin chat" : "Pin chat"}"
                  title="${state.pinnedIds.has(chat.id) ? "Unpin chat" : "Pin chat"}"
                  aria-pressed="${String(state.pinnedIds.has(chat.id))}">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l-.8 5 3.3 3.3v1.4H13v7.8l-1 1-1-1v-7.8H6.5v-1.4L9.8 8 9 3z"></path></svg>
          </button>
        </div>`;
  }).join("")}
    </section>
  `).join(""));
  for (const item of els.chatList.querySelectorAll("[data-chat-id]")) {
    if (boundSidebarItems.has(item))
      continue;
    boundSidebarItems.add(item);
    item.addEventListener("click", () => {
      if (item.dataset.optimisticNew === "true" && state.pendingNewSend) {
        renderNewChat();
        sidebar.close();
        return;
      }
      selectChat(item.dataset.chatId);
    });
  }
  for (const pin of els.chatList.querySelectorAll("[data-pin-chat-id]")) {
    if (boundSidebarPins.has(pin))
      continue;
    boundSidebarPins.add(pin);
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
      savePinnedIds(state.pinnedIds);
      state.sidebarFingerprint = "";
      renderSidebar(true);
      updatePinButton();
    });
  }
}
function pendingReplyMessages(conversationId, cachedMessages) {
  const pending = pendingConversationSends(conversationId, state.pendingReplies.get(conversationId) || [], state.pendingNewSend);
  const claimedCachedIndexes = new Set;
  for (const item of pending) {
    const matchedIndex = matchingPendingReplyMessageIndex(cachedMessages, item, claimedCachedIndexes);
    if (matchedIndex >= 0) {
      claimedCachedIndexes.add(matchedIndex);
      item.observedInCache = true;
      item.responseObservedInCache = cachedMessages.slice(matchedIndex + 1).some((message) => message.role === "assistant" && !message.send_error);
      const cachedMessage = cachedMessages[matchedIndex];
      if (cachedMessage && !imageAttachments(cachedMessage).length && imageAttachments(item).length) {
        cachedMessage.attachments = item.attachments;
      }
    }
  }
  const remaining = pending.filter((item) => {
    if (!item.observedInCache)
      return true;
    if (item.responseObservedInCache)
      return false;
    return Boolean(pendingSendActivity(item.status, Boolean(item.sendId), item.retryAfterSeconds, item.retryAt));
  });
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
        attachments: item.attachments || [],
        status: "complete",
        updated_at: item.updatedAt,
        pending_delete_key: item.clientId || item.sendId || ""
      });
    }
    const activity = pendingSendActivity(item.status, Boolean(item.sendId), item.retryAfterSeconds, item.retryAt);
    if (activity) {
      messages.push({
        message_key: `pending-activity-${item.clientId || item.sendId}`,
        role: "assistant",
        content: "",
        status: "pending",
        updated_at: item.updatedAt,
        pending_activity: true,
        pending_activity_label: activity.label
      });
    } else if (["failed", "dead_lettered"].includes(item.status || "")) {
      messages.push({
        message_key: `pending-error-${item.clientId || item.sendId}`,
        role: "assistant",
        content: `Send failed: ${item.error || "Unknown Prompta send error"}`,
        status: "complete",
        updated_at: item.updatedAt,
        send_error: true,
        retry_scope: "reply",
        retry_key: item.clientId || item.sendId || ""
      });
    }
    return messages;
  });
}
function updatePinButton() {
  const chatId = state.selectedId;
  const available = Boolean(chatId) && !state.composingNew;
  const pinned = Boolean(available && chatId && state.pinnedIds.has(chatId));
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
  savePinnedIds(state.pinnedIds);
  state.sidebarFingerprint = "";
  renderSidebar(true);
  updatePinButton();
}
function renderConversationMeta(chat, visibleMessageCount) {
  const title = chatTitle(chat);
  const activityLabel = chat.status === "active" ? "updating live" : chat.status === "interrupted" ? `interrupted · ${formatRelativeTime(chatActivityAt(chat))}` : formatRelativeTime(chatActivityAt(chat));
  const meta = [
    chat.job_name || "one-shot",
    `${visibleMessageCount} message${visibleMessageCount === 1 ? "" : "s"}`,
    activityLabel
  ].join(" · ");
  const metaFingerprint = JSON.stringify([title, meta, chat.status]);
  if (metaFingerprint === state.selectedMetaFingerprint)
    return;
  state.selectedMetaFingerprint = metaFingerprint;
  setConversationHeading(title, meta);
  const syncStatus = chat.status === "active" ? "active" : chat.status === "interrupted" ? "interrupted" : "cached";
  const syncLabel = chat.status === "active" ? "Syncing from SQLite" : chat.status === "interrupted" ? "Last run was interrupted" : "Cached in SQLite";
  setStatusIcon(els.syncLabel, syncStatus, syncLabel, "sync");
}
function rememberConversationViewport(conversationId) {
  if (!conversationId || state.renderedConversationId !== conversationId)
    return;
  const snapshot = {
    ...conversationRenderer.captureConversationViewport(),
    anchorElement: null
  };
  state.conversationViewports.delete(conversationId);
  state.conversationViewports.set(conversationId, snapshot);
  while (state.conversationViewports.size > 20) {
    const oldest = state.conversationViewports.keys().next().value;
    if (!oldest)
      break;
    state.conversationViewports.delete(oldest);
  }
}
function beginChatSwitch() {
  state.chatSwitchToken += 1;
  els.viewport.classList.add("chat-switching");
  els.viewport.setAttribute("aria-busy", "true");
}
function cancelChatSwitch() {
  state.chatSwitchToken += 1;
  els.viewport.classList.remove("chat-switching");
  els.viewport.removeAttribute("aria-busy");
}
function finishChatSwitch(conversationId) {
  if (!els.viewport.classList.contains("chat-switching"))
    return;
  const token = state.chatSwitchToken;
  requestAnimationFrame(() => {
    if (token !== state.chatSwitchToken || state.selectedId !== conversationId)
      return;
    getComputedStyle(els.conversation).opacity;
    els.viewport.classList.remove("chat-switching");
    els.viewport.removeAttribute("aria-busy");
  });
}
function renderConversation(chat) {
  state.selectedChat = chat;
  const messages = Array.isArray(chat.messages) ? chat.messages : [];
  const visibleMessages = [...messages, ...pendingReplyMessages(chat.id, messages)];
  state.selectedVisibleMessageCount = visibleMessages.length;
  const allowStreaming = chat.status === "active";
  const fingerprint = JSON.stringify([
    chat.status,
    visibleMessages.map((message) => [
      message.message_key,
      conversationRenderer.messageNodeFingerprint(message, allowStreaming)
    ])
  ]);
  if (fingerprint !== state.selectedFingerprint) {
    const isInitial = state.renderedConversationId !== chat.id;
    const rememberedViewport = isInitial ? state.conversationViewports.get(chat.id) : null;
    const viewportSnapshot = rememberedViewport || conversationRenderer.captureConversationViewport();
    state.selectedFingerprint = fingerprint;
    conversationRenderer.renderMessageNodes(visibleMessages, allowStreaming);
    state.renderedConversationId = chat.id;
    conversationRenderer.restoreConversationViewport(viewportSnapshot, isInitial && !rememberedViewport);
  }
  finishChatSwitch(chat.id);
  renderConversationMeta(chat, visibleMessages.length);
  setHiddenIfChanged(els.emptyState, true);
  setHiddenIfChanged(els.conversation, false);
  els.messageInput.disabled = false;
  state.composingNew = false;
  syncComposerDraftTarget();
  syncSendButton();
  els.shareChatButton.disabled = false;
  updatePinButton();
  syncSendButton();
  const pendingActivity = [...state.pendingReplies.get(chat.id) || []].reverse().map((item) => pendingSendActivity(item.status, Boolean(item.sendId), item.retryAfterSeconds, item.retryAt)).find(Boolean);
  if (pendingActivity) {
    setTextIfChanged5(els.composerStatus, pendingActivity.statusText);
  } else if (!state.sending) {
    setTextIfChanged5(els.composerStatus, chat.status === "active" ? "Uses the existing live ChatGPT tab." : chat.status === "interrupted" ? "The last run was interrupted. Sending will reopen this chat." : "Sending will reopen this chat once if its retained tab has expired.");
  }
}
function showMode(mode) {
  state.mode = mode === "logs" ? "logs" : "chats";
  const logsMode = state.mode === "logs";
  els.viewport.hidden = logsMode;
  logsPanel.setVisible(logsMode);
  els.composerFooter.hidden = logsMode;
  if (logsMode) {
    cancelChatSwitch();
    state.selectedMetaFingerprint = "";
    const display = displayServerName(state.serverName || location.hostname);
    setConversationHeading(`${display} Prompta logs`, `journalctl · prompta.service · ${display}`);
    setStatusIcon(els.syncLabel, "journal", `${display} journal`, "sync");
    els.messageInput.disabled = true;
    els.sendButton.disabled = true;
    els.shareChatButton.disabled = true;
    setTextIfChanged5(els.composerStatus, "Switch back to chats to send a message.");
    updateComposerActionButton();
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
  cancelChatSwitch();
  state.composingNew = false;
  state.selectedId = null;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedMetaFingerprint = "";
  state.selectedChat = null;
  state.renderedConversationId = "";
  setHiddenIfChanged(els.emptyState, false);
  setHiddenIfChanged(els.conversation, true);
  conversationRenderer.renderMessageNodes([], false);
  setConversationHeading("Prompta", "Local conversation history");
  setStatusIcon(els.syncLabel, "local", "Local cache", "sync");
  els.messageInput.disabled = true;
  els.sendButton.disabled = true;
  els.shareChatButton.disabled = true;
  updatePinButton();
  els.messageInput.placeholder = "Message Prompta…";
  setTextIfChanged5(els.composerStatus, "");
  syncComposerDraftTarget();
  updateComposerActionButton();
}
function renderNewChat() {
  cancelChatSwitch();
  const enteringNewChat = !state.composingNew;
  state.composingNew = true;
  state.selectedId = null;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedChat = null;
  state.renderedConversationId = "";
  state.mode = "chats";
  syncComposerDraftTarget();
  const pending = state.pendingNewSend;
  const waiting = pending && !["failed", "dead_lettered", "succeeded"].includes(pending.status);
  const fingerprint = JSON.stringify([
    pending?.sendId || "",
    pending?.message || "",
    pending?.status || "",
    pending?.error || "",
    pending?.conversationId || "",
    pending?.retryAfterSeconds || 0,
    pending?.retryAt || 0,
    pending?.retryAttempt || 0,
    imageAttachments(pending).map((attachment) => [
      attachment.id || "",
      attachment.name || "",
      attachment.type || "",
      String(attachment.src || "").length
    ])
  ]);
  if (shouldRenderNewChatView(enteringNewChat, fingerprint, state.newChatFingerprint)) {
    state.newChatFingerprint = fingerprint;
    if (pending) {
      const messages = [
        {
          message_key: `pending-user-${pending.clientId || pending.sendId}`,
          role: "user",
          content: pending.message,
          attachments: pending.attachments || [],
          status: "complete",
          updated_at: pending.updatedAt,
          pending_delete_key: pending.clientId || pending.sendId || ""
        }
      ];
      const activity2 = pendingSendActivity(pending.status, Boolean(pending.sendId), pending.retryAfterSeconds, pending.retryAt);
      if (activity2) {
        messages.push({
          message_key: `pending-activity-${pending.clientId || pending.sendId}`,
          role: "assistant",
          content: "",
          status: "pending",
          updated_at: pending.updatedAt,
          pending_activity: true,
          pending_activity_label: activity2.label
        });
      } else if (["failed", "dead_lettered"].includes(pending.status)) {
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
      const viewportSnapshot = conversationRenderer.captureConversationViewport();
      setHiddenIfChanged(els.emptyState, true);
      setHiddenIfChanged(els.conversation, false);
      conversationRenderer.renderMessageNodes(messages, true);
      conversationRenderer.restoreConversationViewport(viewportSnapshot, enteringNewChat);
    } else {
      setHiddenIfChanged(els.emptyState, false);
      setHiddenIfChanged(els.conversation, true);
      conversationRenderer.renderMessageNodes([], false);
    }
    setConversationHeading("New chat", pending ? "Queued through the live Prompta session" : "Starts a fresh ChatGPT conversation");
    setStatusIcon(els.syncLabel, pending ? "queued" : "new", pending ? "Send queued" : "Fresh conversation", "sync");
    els.messageInput.disabled = false;
    syncSendButton();
    els.shareChatButton.disabled = true;
    updatePinButton();
    els.messageInput.placeholder = "Start a new chat…";
    const activity = pending ? pendingSendActivity(pending.status, Boolean(pending.sendId), pending.retryAfterSeconds, pending.retryAt) : null;
    setTextIfChanged5(els.composerStatus, pending ? ["failed", "dead_lettered"].includes(pending.status) ? pending.status === "dead_lettered" ? "Send exhausted its retry budget. Retry to enqueue it again." : "Send failed. The error is shown in the chat." : activity?.statusText || "Sent. Waiting for the cached response…" : "");
  }
  updateComposerActionButton();
  if (enteringNewChat) {
    els.viewport.hidden = false;
    logsPanel.setVisible(false);
    history.replaceState(null, "", `${location.pathname}${location.search}`);
    renderSidebar();
    sidebar.close();
    if (!waiting && matchMedia("(pointer: fine)").matches) {
      requestAnimationFrame(() => els.messageInput.focus());
    }
  }
}
async function fetchJson2(url, timeoutMs = 1e4) {
  const controller = new AbortController;
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal
    });
    if (!response.ok)
      throw new Error(`${response.status} ${response.statusText}`);
    return await response.json();
  } finally {
    window.clearTimeout(timeout);
  }
}
async function hydrateRecentChatCache() {
  let timeout;
  const cached = await Promise.race([
    Promise.all([recentChatCache.warm(), recentChatCache.warmSummaries()]),
    new Promise((resolve) => {
      timeout = window.setTimeout(() => resolve(null), 500);
    })
  ]);
  if (timeout !== undefined)
    window.clearTimeout(timeout);
  if (!cached)
    return false;
  const [cachedChats, cachedSummaries] = cached;
  const sidebarSnapshot = cachedSummaries.length ? cachedSummaries : cachedChats;
  if (!sidebarSnapshot.length || state.search)
    return false;
  const unique = new Map;
  for (const chat of sidebarSnapshot) {
    if (chat?.id && !unique.has(chat.id))
      unique.set(chat.id, chat);
  }
  state.chats = Array.from(unique.values());
  if (!cachedSummaries.length) {
    state.chats.sort((left, right) => chatActivityAt(right) - chatActivityAt(left));
  }
  state.chatOrderScope = cachedSummaries.length ? "" : "__cached__";
  const activeCount = state.chats.filter((chat) => chat.status === "active").length;
  setTextIfChanged5(els.cacheSummary, state.chats.length + " cached · " + activeCount + " active");
  const hashId = conversationIdFromHash(location.hash);
  const initialId = hashId || state.chats[0]?.id || "";
  if (initialId) {
    state.selectedId = initialId;
    const chat = recentChatCache.getMemory(initialId);
    if (chat) {
      state.selectedUpdatedAt = chat.updated_at;
      renderConversation(chat);
    } else {
      conversationRenderer.renderLoadingState();
      setHiddenIfChanged(els.emptyState, true);
      setHiddenIfChanged(els.conversation, false);
    }
  }
  renderSidebar();
  return true;
}
async function loadServerIdentity() {
  try {
    const payload = await fetchJson2("api/health");
    setServerStatus(payload.server, payload.online);
    const head = String(payload.head || "").trim().toLowerCase();
    deploymentMonitor.observeHead(head);
    setTextIfChanged5(els.headLabel, head ? head : "unknown");
    els.headLabel.title = head ? "UI commit " + head : "UI commit unavailable";
  } catch (error) {
    setServerStatus(state.serverName || location.hostname, false);
    console.warn("Could not load Prompta server identity", error);
  }
}
async function hydratePendingSends() {
  try {
    const payload = await fetchJson2("api/sends");
    const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
    for (const job of jobs) {
      const status = String(job.status || "queued");
      const sendId = String(job.send_id || "");
      if (!sendId || ["succeeded", "failed", "dead_lettered"].includes(status))
        continue;
      const conversationId = String(job.conversation_id || "");
      const pending = {
        sendId,
        clientId: String(job.client_id || ""),
        message: String(job.message || ""),
        status,
        error: String(job.error || ""),
        conversationId,
        createdAt: Number(job.created_at || Date.now() / 1000),
        updatedAt: Number(job.updated_at || Date.now() / 1000),
        retryAfterSeconds: Number(job.retry_after_seconds || 0),
        retryAt: Number(job.retry_at || 0),
        retryAttempt: Number(job.retry_attempt || 0),
        attachmentNames: Array.isArray(job.attachment_names) ? job.attachment_names.map((value) => String(value)) : []
      };
      if (job.operation === "reply" && conversationId) {
        const items = state.pendingReplies.get(conversationId) || [];
        if (!items.some((item) => item.sendId === sendId)) {
          items.push(pending);
          items.sort((left, right) => Number(left.createdAt || 0) - Number(right.createdAt || 0));
          state.pendingReplies.set(conversationId, items);
        }
        watchSend(sendId, false, conversationId);
      } else if (job.operation === "once" && !conversationId && !state.pendingNewSend) {
        state.pendingNewSend = pending;
        state.composingNew = true;
        watchSend(sendId, true, "");
      }
    }
  } catch (error) {
    console.warn("Could not hydrate pending Prompta sends", error);
  }
}
async function loadChats(forceSelectedRefresh = false) {
  const requestId = ++state.chatsRequestId;
  try {
    const query = state.search ? `?q=${encodeURIComponent(state.search)}` : "";
    const payload = await fetchJson2(`api/chats${query}`);
    if (requestId !== state.chatsRequestId)
      return;
    const chats = payload.chats || [];
    promoteServerPendingPins(chats);
    reconcileOptimisticNew(chats);
    if (!state.search)
      recentChatCache.rememberSummaries(chats);
    completionNotifications.trackCompletions(chats);
    const orderScope = state.search;
    const preserveOrder = state.chatOrderScope === orderScope;
    const previousChats = preserveOrder ? state.chats : [];
    const groupAnchors = new Map(previousChats.map((chat) => [chat.id, sidebarGroupAt(chat)]));
    state.chats = preserveSidebarChatOrder(previousChats, chats).map((chat) => ({
      ...chat,
      _sidebarGroupAt: groupAnchors.get(chat.id) || chatActivityAt(chat)
    }));
    state.chatOrderScope = orderScope;
    const activeCount = state.chats.filter((chat) => chat.status === "active").length;
    setTextIfChanged5(els.cacheSummary, `${state.chats.length} cached · ${activeCount} active`);
    const hashId = conversationIdFromHash(location.hash);
    if (!state.selectedId && hashId) {
      state.selectedId = hashId;
    }
    if (!state.selectedId && state.chats.length && !state.composingNew) {
      state.selectedId = state.chats[0].id;
    }
    if (state.selectedId && !state.composingNew && state.pendingNewId !== state.selectedId && !state.chats.some((chat) => chat.id === state.selectedId) && !state.search && hashId !== state.selectedId) {
      state.selectedId = state.chats[0]?.id || null;
      state.selectedFingerprint = "";
    }
    renderSidebar();
    if (state.mode === "chats") {
      if (state.selectedId) {
        const summary = state.chats.find((chat) => chat.id === state.selectedId);
        const shouldRefresh = shouldRefreshSelectedChat(summary, state.selectedUpdatedAt, state.selectedFingerprint, forceSelectedRefresh);
        if (shouldRefresh)
          await loadSelectedChat();
      } else if (!state.composingNew) {
        clearConversation();
      }
    } else {
      await logsPanel.load();
    }
  } catch (error) {
    if (requestId !== state.chatsRequestId)
      return;
    if (els.globalLiveOrb.classList.contains("live")) {
      els.globalLiveOrb.classList.remove("live");
    }
    setTextIfChanged5(els.cacheSummary, "Cache unavailable");
    console.error(error);
  }
}
var HISTORICAL_ACTIVITY_PROBE_TTL_MS = 30000;
async function probeHistoricalActivity(conversationId) {
  if (!conversationId || !shouldProbeHistoricalActivity(state.selectedChat?.status))
    return;
  const now = Date.now();
  const lastProbeAt = Number(state.activityProbeAt.get(conversationId) || 0);
  if (state.activityProbes.has(conversationId) || now - lastProbeAt < HISTORICAL_ACTIVITY_PROBE_TTL_MS)
    return;
  state.activityProbeAt.set(conversationId, now);
  state.activityProbes.add(conversationId);
  if (state.selectedId === conversationId) {
    setTextIfChanged5(els.composerStatus, "Checking whether ChatGPT is still running…");
    syncSendButton();
  }
  try {
    const payload = await postJsonRequest("api/chats/" + encodeURIComponent(conversationId) + "/probe", {}, 1, 30000);
    if (state.selectedId !== conversationId || state.mode !== "chats")
      return;
    const chat = payload?.chat;
    if (!chat || chat.id !== conversationId)
      return;
    state.selectedUpdatedAt = chat.updated_at;
    recentChatCache.remember(chat);
    renderConversation(chat);
    await loadChats();
  } catch (error) {
    if (state.selectedId === conversationId) {
      setTextIfChanged5(els.composerStatus, "Could not verify whether this interrupted chat is still running.");
    }
    console.warn("Could not probe historical chat activity", error);
  } finally {
    state.activityProbes.delete(conversationId);
    if (state.selectedId === conversationId)
      syncSendButton();
  }
}
function renderRecentChatSnapshot(conversationId) {
  if (!conversationId || state.mode !== "chats")
    return;
  const memoryChat = recentChatCache.getMemory(conversationId);
  if (memoryChat) {
    state.selectedUpdatedAt = memoryChat.updated_at;
    renderConversation(memoryChat);
    return;
  }
  if (!state.renderedConversationId) {
    conversationRenderer.renderLoadingState();
    setHiddenIfChanged(els.emptyState, true);
    setHiddenIfChanged(els.conversation, false);
  }
  recentChatCache.get(conversationId).then((chat) => {
    if (!chat || state.mode !== "chats" || state.selectedId !== conversationId || state.selectedChat?.id === conversationId)
      return;
    state.selectedUpdatedAt = chat.updated_at;
    renderConversation(chat);
  });
}
async function loadSelectedChat() {
  if (!state.selectedId || state.mode !== "chats")
    return;
  const selectedId = state.selectedId;
  if (!state.selectedChat || state.selectedChat.id !== selectedId) {
    renderRecentChatSnapshot(selectedId);
  }
  const requestId = ++state.selectedRequestId;
  try {
    const chat = await fetchJson2(`api/chats/${encodeURIComponent(selectedId)}`);
    if (requestId !== state.selectedRequestId || selectedId !== state.selectedId || chat.id !== state.selectedId)
      return;
    if (state.pendingNewId === chat.id && !state.pendingNewSend) {
      state.pendingNewId = null;
    }
    state.selectedUpdatedAt = chat.updated_at;
    recentChatCache.remember(chat);
    renderConversation(chat);
    if (shouldProbeHistoricalActivity(chat.status)) {
      probeHistoricalActivity(chat.id);
    }
  } catch (error) {
    if (requestId !== state.selectedRequestId || selectedId !== state.selectedId)
      return;
    const missing = String(error).startsWith("Error: 404");
    if (missing && state.pendingNewId !== state.selectedId) {
      recentChatCache.remove(selectedId);
      if (conversationIdFromHash(location.hash) === selectedId) {
        history.replaceState(null, "", `${location.pathname}${location.search}`);
      }
      clearConversation();
    }
    if (!missing || state.pendingNewId !== state.selectedId)
      console.error(error);
    finishChatSwitch(selectedId);
  }
}
async function selectChat(id) {
  if (!id)
    return;
  if (state.mode !== "chats")
    showMode("chats");
  sidebar.close();
  if (id === state.selectedId) {
    if (!state.selectedChat || state.selectedChat.id !== id) {
      await loadSelectedChat();
    }
    return;
  }
  rememberConversationViewport(state.selectedId);
  beginChatSwitch();
  const pendingNew = state.pendingNewSend?.conversationId === id ? state.pendingNewSend : null;
  state.composingNew = false;
  state.pendingNewId = pendingNew ? id : null;
  els.messageInput.placeholder = "Message Prompta…";
  state.selectedId = id;
  state.selectedUpdatedAt = null;
  state.selectedFingerprint = "";
  state.selectedMetaFingerprint = "";
  state.selectedChat = null;
  history.replaceState(null, "", `#/${encodeURIComponent(id)}`);
  renderSidebar();
  await loadSelectedChat();
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
    attachmentPicker.closeMenu();
    els.slashMenu.hidden = true;
    jobsDialog.close();
    els.searchInput.blur();
    sidebar.close();
  }
});
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
async function runScheduleSlashCommand(command, originalMessage) {
  state.sending = true;
  els.messageInput.disabled = true;
  els.sendButton.disabled = true;
  attachmentPicker.setDisabled(true);
  clearComposerDraft();
  els.messageInput.value = "";
  resizeComposer();
  updateComposerActionButton();
  setTextIfChanged5(els.composerStatus, "Saving schedule…");
  try {
    const result = await postJsonRequest("api/schedule", {
      interval_minutes: command.intervalMinutes,
      prompt: command.prompt
    });
    const server = displayServerName(result.server || state.serverName || location.hostname);
    const interval = formatScheduleInterval(Number(result.interval_minutes));
    const prefix = result.created === false ? "Already scheduled" : "Scheduled";
    setTextIfChanged5(els.composerStatus, `${prefix} on ${server}: every ${interval} · ${command.prompt}`);
  } catch (error) {
    els.messageInput.value = originalMessage;
    persistComposerDraft();
    resizeComposer();
    updateSlashMenu();
    setTextIfChanged5(els.composerStatus, `Schedule failed: ${String(error).replace(/^Error:\s*/, "")}`);
    console.error(error);
  } finally {
    state.sending = false;
    els.messageInput.disabled = false;
    attachmentPicker.setDisabled(false);
    syncSendButton();
    if (matchMedia("(pointer: fine)").matches)
      els.messageInput.focus();
  }
}
async function runAtSlashCommand(command, originalMessage) {
  state.sending = true;
  els.messageInput.disabled = true;
  els.sendButton.disabled = true;
  attachmentPicker.setDisabled(true);
  clearComposerDraft();
  els.messageInput.value = "";
  resizeComposer();
  updateSlashMenu();
  setTextIfChanged5(els.composerStatus, "Saving one-time schedule…");
  try {
    const result = await postJsonRequest("api/schedule-at", {
      run_at_epoch: command.runAtEpoch,
      prompt: command.prompt
    });
    const server = displayServerName(result.server || state.serverName || location.hostname);
    setTextIfChanged5(els.composerStatus, `Scheduled on ${server}: ${command.runAtLabel} · ${command.prompt}`);
  } catch (error) {
    els.messageInput.value = originalMessage;
    persistComposerDraft();
    resizeComposer();
    updateSlashMenu();
    setTextIfChanged5(els.composerStatus, `Schedule failed: ${String(error).replace(/^Error:\s*/, "")}`);
    console.error(error);
  } finally {
    state.sending = false;
    els.messageInput.disabled = false;
    attachmentPicker.setDisabled(false);
    syncSendButton();
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
  const previous = JSON.stringify([
    item.status || "",
    item.error || "",
    item.retryAfterSeconds || 0,
    item.retryAt || 0,
    item.retryAttempt || 0
  ]);
  Object.assign(item, updates);
  const changed = JSON.stringify([
    item.status || "",
    item.error || "",
    item.retryAfterSeconds || 0,
    item.retryAt || 0,
    item.retryAttempt || 0
  ]) !== previous;
  if (changed)
    item.updatedAt = Date.now() / 1000;
  return changed;
}
async function deletePendingSend(deleteKey) {
  let pending = null;
  let creatingNew = false;
  const conversationId = state.selectedId || "";
  if (state.pendingNewSend && (state.pendingNewSend.clientId === deleteKey || state.pendingNewSend.sendId === deleteKey)) {
    pending = state.pendingNewSend;
    creatingNew = true;
    state.pendingNewSend = null;
    state.pendingNewId = null;
    state.newChatFingerprint = "";
  } else if (conversationId) {
    const items = state.pendingReplies.get(conversationId) || [];
    pending = items.find((item) => item.clientId === deleteKey || item.sendId === deleteKey) || null;
    if (pending) {
      const remaining = items.filter((item) => item !== pending);
      if (remaining.length)
        state.pendingReplies.set(conversationId, remaining);
      else
        state.pendingReplies.delete(conversationId);
      state.selectedFingerprint = "";
    }
  }
  if (!pending)
    return;
  const sendId = String(pending.sendId || "");
  if (sendId) {
    try {
      const response = await fetch(`api/sends/${encodeURIComponent(sendId)}`, {
        method: "DELETE",
        cache: "no-store"
      });
      if (!response.ok && response.status !== 404)
        throw new Error(`${response.status}`);
    } catch (error) {
      console.warn("Could not delete pending Prompta send", error);
      setTextIfChanged5(els.composerStatus, "Could not delete the pending message.");
    }
  }
  if (creatingNew)
    renderNewChat();
  else if (state.selectedChat?.id === conversationId)
    renderConversation(state.selectedChat);
  renderSidebar();
}
async function watchSend(sendId, creatingNew, conversationId) {
  let statusFailures = 0;
  while (true) {
    await new Promise((resolve) => setTimeout(resolve, 400));
    let job;
    try {
      job = await fetchJson2(`api/sends/${encodeURIComponent(sendId)}`);
      statusFailures = 0;
    } catch {
      statusFailures += 1;
      if (statusFailures >= 3) {
        await loadChats();
        if (creatingNew) {
          const pending = state.pendingNewSend;
          if (!pending || pending.sendId !== sendId)
            return;
          if (pending.conversationId) {
            state.composingNew = false;
            state.selectedId = pending.conversationId;
            state.pendingNewId = pending.conversationId;
            history.replaceState(null, "", `#/${encodeURIComponent(pending.conversationId)}`);
            await loadSelectedChat();
            return;
          }
        } else {
          if (!pendingReply(conversationId, sendId))
            return;
          if (state.selectedId === conversationId)
            await loadSelectedChat();
          if (!pendingReply(conversationId, sendId))
            return;
        }
        setTextIfChanged5(els.composerStatus, "Send status unavailable. Prompta may still be running it; reconnecting…");
      }
      await new Promise((resolve) => setTimeout(resolve, Math.min(5000, 250 * statusFailures)));
      continue;
    }
    const status = job.status || "running";
    if (creatingNew) {
      const pendingNewSend = state.pendingNewSend;
      if (!pendingNewSend || pendingNewSend.sendId !== sendId)
        return;
      const nextError = job.error || "";
      const nextConversationId = job.conversation_id || pendingNewSend.conversationId || "";
      const nextRetryAfterSeconds = Number(job.retry_after_seconds || 0);
      const nextRetryAt = Number(job.retry_at || 0);
      const nextRetryAttempt = Number(job.retry_attempt || 0);
      if (nextConversationId) {
        completionNotifications.markActive(nextConversationId);
        promotePendingConversationPin(pendingNewSend, nextConversationId);
      }
      const changed2 = pendingNewSend.status !== status || pendingNewSend.error !== nextError || pendingNewSend.conversationId !== nextConversationId || pendingNewSend.retryAfterSeconds !== nextRetryAfterSeconds || pendingNewSend.retryAt !== nextRetryAt || pendingNewSend.retryAttempt !== nextRetryAttempt;
      Object.assign(pendingNewSend, {
        status,
        error: nextError,
        conversationId: nextConversationId,
        retryAfterSeconds: nextRetryAfterSeconds,
        retryAt: nextRetryAt,
        retryAttempt: nextRetryAttempt
      });
      if (changed2)
        pendingNewSend.updatedAt = Date.now() / 1000;
      if (status === "succeeded") {
        const newId = job.conversation_id;
        if (!newId) {
          pendingNewSend.status = "failed";
          pendingNewSend.error = "Prompta reported success without a conversation id";
          if (state.composingNew)
            renderNewChat();
          return;
        }
        const completedPending = pendingNewSend;
        promotePendingConversationPin(completedPending, newId);
        completedPending.conversationId = newId;
        state.pendingNewId = newId;
        const pendingReplies = state.pendingReplies.get(newId) || [];
        if (!pendingReplies.some((item) => item.clientId === completedPending.clientId)) {
          pendingReplies.push(completedPending);
          state.pendingReplies.set(newId, pendingReplies);
        }
        state.pendingNewSend = null;
        const stillViewingPending = state.composingNew && state.mode === "chats";
        if (!stillViewingPending) {
          renderSidebar();
          await loadChats();
          return;
        }
        state.composingNew = false;
        state.selectedId = newId;
        history.replaceState(null, "", `#/${encodeURIComponent(newId)}`);
        els.messageInput.placeholder = "Message Prompta…";
        setTextIfChanged5(els.composerStatus, "Sent. Waiting for the cached response…");
        state.selectedUpdatedAt = null;
        await loadChats();
        await loadSelectedChat();
        return;
      }
      if (["failed", "dead_lettered"].includes(status)) {
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
      error: job.error || "",
      retryAfterSeconds: Number(job.retry_after_seconds || 0),
      retryAt: Number(job.retry_at || 0),
      retryAttempt: Number(job.retry_attempt || 0)
    });
    if (changed)
      renderSidebar();
    if (state.selectedId === conversationId)
      await loadSelectedChat();
    if (status === "succeeded") {
      setTextIfChanged5(els.composerStatus, "Sent. Waiting for the cached response…");
      await loadChats();
      return;
    }
    if (["failed", "dead_lettered"].includes(status)) {
      setTextIfChanged5(els.composerStatus, status === "dead_lettered" ? "Send exhausted its retry budget. Retry to enqueue it again." : "Send failed. The error is shown in the chat.");
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
    const selectedId = state.selectedId;
    const items = state.pendingReplies.get(selectedId) || [];
    pending = items.find((item) => item.clientId === retryKey || item.sendId === retryKey) || null;
    if (pending) {
      const remaining = items.filter((item) => item !== pending);
      if (remaining.length)
        state.pendingReplies.set(selectedId, remaining);
      else
        state.pendingReplies.delete(selectedId);
      state.selectedFingerprint = "";
      if (state.selectedChat?.id === state.selectedId)
        renderConversation(state.selectedChat);
    }
  }
  if (!pending)
    return;
  els.messageInput.value = pending.message || "";
  resizeComposer();
  syncSendButton();
  if ((pending.attachmentNames || []).length) {
    setTextIfChanged5(els.composerStatus, "Reattach the files, then send again.");
    els.messageInput.focus();
    return;
  }
  await sendSelectedMessage();
}
async function stopSelectedChat() {
  const conversationId = state.selectedId;
  if (!conversationId || state.mode !== "chats" || state.stopping)
    return;
  state.stopping = true;
  syncSendButton();
  setTextIfChanged5(els.composerStatus, "Stopping response…");
  try {
    await postJsonRequest("api/chats/" + encodeURIComponent(conversationId) + "/stop", {});
    setTextIfChanged5(els.composerStatus, "Stopped.");
    state.selectedFingerprint = "";
    state.selectedUpdatedAt = null;
    await loadSelectedChat();
    await loadChats();
  } catch (error) {
    setTextIfChanged5(els.composerStatus, "Stop failed: " + String(error).replace(/^Error:\s*/, ""));
    console.error(error);
  } finally {
    state.stopping = false;
    syncSendButton();
  }
}
async function sendSelectedMessage() {
  const message = els.messageInput.value.trim();
  const creatingNew = state.composingNew;
  const conversationId = state.selectedId;
  const attachments = attachmentPicker.snapshot();
  if (!message || state.mode !== "chats" || state.sending)
    return;
  if (message.toLowerCase() === "/logs") {
    clearComposerDraft();
    els.messageInput.value = "";
    els.slashMenu.hidden = true;
    resizeComposer();
    showMode("logs");
    return;
  }
  if (["/list", "/jobs"].includes(message.toLowerCase())) {
    await jobsDialog.open(true);
    return;
  }
  completionNotifications.requestPermissionFromGesture();
  const scheduleCommand = parseScheduleSlashCommand(message);
  if (scheduleCommand) {
    if (attachments.length) {
      setTextIfChanged5(els.composerStatus, "Scheduled prompts do not include attachments.");
      return;
    }
    if ("error" in scheduleCommand) {
      setTextIfChanged5(els.composerStatus, scheduleCommand.error);
      return;
    }
    await runScheduleSlashCommand(scheduleCommand, message);
    return;
  }
  const atCommand = parseAtSlashCommand(message);
  if (atCommand) {
    if (attachments.length) {
      setTextIfChanged5(els.composerStatus, "Scheduled prompts do not include attachments.");
      return;
    }
    if ("error" in atCommand) {
      setTextIfChanged5(els.composerStatus, atCommand.error);
      return;
    }
    await runAtSlashCommand(atCommand, message);
    return;
  }
  if (!creatingNew && !conversationId)
    return;
  let serializedAttachments = [];
  if (attachments.length) {
    state.sending = true;
    els.messageInput.disabled = true;
    els.sendButton.disabled = true;
    attachmentPicker.setDisabled(true);
    setTextIfChanged5(els.composerStatus, "Preparing attachments…");
    try {
      serializedAttachments = await attachmentPicker.serialize();
    } catch (error) {
      state.sending = false;
      els.messageInput.disabled = false;
      attachmentPicker.setDisabled(false);
      syncSendButton();
      setTextIfChanged5(els.composerStatus, "Attachment failed: " + String(error).replace(/^Error:\s*/, ""));
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
    attachmentNames: attachments.map((file) => file.name),
    attachments: pendingImageAttachments(serializedAttachments)
  };
  state.sending = true;
  els.sendButton.disabled = true;
  clearComposerDraft();
  els.messageInput.value = "";
  resizeComposer();
  if (creatingNew) {
    state.pendingNewSend = pending;
    state.newChatFingerprint = "";
    renderNewChat();
    renderSidebar();
  } else {
    const targetConversationId = conversationId || "";
    const items = state.pendingReplies.get(targetConversationId) || [];
    items.push(pending);
    state.pendingReplies.set(targetConversationId, items);
    state.selectedFingerprint = "";
    if (state.selectedChat?.id === targetConversationId)
      renderConversation(state.selectedChat);
    renderSidebar();
  }
  try {
    const result = creatingNew ? await postJsonRequest("api/chats", { message, attachments: serializedAttachments, client_id: pending.clientId }, attachments.length ? 1 : 3) : await postJsonRequest(`api/chats/${encodeURIComponent(conversationId || "")}/messages`, { message, attachments: serializedAttachments, client_id: pending.clientId }, attachments.length ? 1 : 3);
    if (!result.send_id)
      throw new Error("Prompta did not return a send id");
    if (!creatingNew)
      completionNotifications.markActive(conversationId);
    pending.sendId = result.send_id;
    pending.status = result.status || "queued";
    pending.updatedAt = Date.now() / 1000;
    if (attachments.length)
      attachmentPicker.clear();
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
    if (attachments.length)
      attachmentPicker.setDisabled(false);
    if (!creatingNew && state.selectedId && state.mode === "chats") {
      els.messageInput.disabled = false;
      syncSendButton();
      if (matchMedia("(pointer: fine)").matches)
        els.messageInput.focus();
    } else if (creatingNew && state.pendingNewSend?.status === "failed" && state.mode === "chats") {
      els.messageInput.disabled = false;
      syncSendButton();
      if (matchMedia("(pointer: fine)").matches)
        els.messageInput.focus();
    }
    updateComposerActionButton();
  }
}
async function copySelectedChatUrl() {
  if (!state.selectedId)
    return;
  const url = new URL(location.href);
  url.hash = `/${encodeURIComponent(state.selectedId)}`;
  try {
    await navigator.clipboard.writeText(url.toString());
    setTextIfChanged5(els.composerStatus, "Chat link copied.");
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = url.toString();
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    setTextIfChanged5(els.composerStatus, copied ? "Chat link copied." : "Could not copy the chat link.");
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
  syncSendButton();
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
  if (els.sendButton.dataset.action === "stop")
    stopSelectedChat();
  else
    sendSelectedMessage();
});
els.messageInput.addEventListener("input", () => {
  persistComposerDraft();
  resizeComposer();
  updateSlashMenu();
  syncSendButton();
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
  const mobileInput = matchMedia("(max-width: 780px)").matches || matchMedia("(pointer: coarse)").matches;
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !mobileInput) {
    event.preventDefault();
    if (els.sendButton.dataset.action === "stop")
      stopSelectedChat();
    else
      sendSelectedMessage();
  }
});
window.addEventListener("hashchange", () => {
  const id = conversationIdFromHash(location.hash);
  if (id && id !== state.selectedId)
    selectChat(id);
});
function refreshDisplayedTimes() {
  if (state.composingNew && ["rate_limited", "retrying"].includes(state.pendingNewSend?.status || "")) {
    state.newChatFingerprint = "";
    renderNewChat();
  } else if (state.selectedId && (state.pendingReplies.get(state.selectedId) || []).some((item) => ["rate_limited", "retrying"].includes(item.status || ""))) {
    state.selectedFingerprint = "";
    loadSelectedChat();
  }
  renderSidebar();
  for (const time of els.chatList.querySelectorAll(".chat-time[data-activity-at]")) {
    setTextIfChanged5(time, formatRelativeTime(Number(time.dataset.activityAt || 0)));
  }
  for (const time of els.conversation.querySelectorAll(".message-timestamp[data-message-at]")) {
    const age = time.querySelector(".message-age");
    if (!age)
      continue;
    const ageText = messageAgeText(Number(time.dataset.messageAt || 0));
    setTextIfChanged5(age, ageText ? ` · ${ageText}` : "");
  }
  if (state.mode === "chats" && state.selectedChat && state.selectedChat.id === state.selectedId && !state.composingNew) {
    renderConversationMeta(state.selectedChat, state.selectedVisibleMessageCount);
  }
}
async function startApp() {
  deploymentMonitor.registerServiceWorker();
  loadServerIdentity();
  await hydratePendingSends();
  resizeComposer();
  const hydrated = await hydrateRecentChatCache();
  if (!hydrated) {
    conversationRenderer.renderLoadingState();
    setHiddenIfChanged(els.emptyState, true);
    setHiddenIfChanged(els.conversation, false);
  }
  document.documentElement.classList.remove("booting");
  await loadChats(true);
  liveUpdates.start();
}
startApp();
