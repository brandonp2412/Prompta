export type ChatSummary = {
  id: string;
  prompt?: string;
  created_at?: number;
  _pending_send?: boolean;
  _client_id?: string;
};

export function chatListRequestUrl(search: string, pinnedIds: Iterable<string>): string {
  const params = new URLSearchParams();
  const query = search.trim();

  if (query) {
    params.set("q", search);
  } else {
    const seen = new Set<string>();

    for (const rawId of pinnedIds) {
      const id = String(rawId || "").trim();

      if (!id || seen.has(id)) continue;

      seen.add(id);
      params.append("include", id);
    }
  }

  const suffix = params.toString();

  return suffix ? `api/chats?${suffix}` : "api/chats";
}

export function sidebarChatCountSummary(
  chatCount: number,
  activeCount: number,
  search: string,
): string {
  const scope = search.trim()
    ? `${chatCount} ${chatCount === 1 ? "result" : "results"}`
    : `${chatCount} cached`;

  return `${scope} · ${activeCount} active`;
}

export type SidebarOrderChat = {
  id: string;
  created_at?: unknown;
  last_user_at?: unknown;
  _pending_send?: unknown;
  _optimisticNew?: unknown;
  _optimisticReply?: unknown;
};

export function sidebarChatCreatedAt(chat: SidebarOrderChat | null | undefined): number {
  const createdAt = Number(chat?.created_at || 0);

  return Number.isFinite(createdAt) && createdAt > 0 ? createdAt : 0;
}

export function sidebarChatLastUserAt(chat: SidebarOrderChat | null | undefined): number {
  const lastUserAt = Number(chat?.last_user_at || 0);

  if (Number.isFinite(lastUserAt) && lastUserAt > 0) return lastUserAt;

  return sidebarChatCreatedAt(chat);
}

export function sidebarChatIsPending(chat: SidebarOrderChat | null | undefined): boolean {
  return Boolean(chat?._pending_send || chat?._optimisticNew || chat?._optimisticReply);
}

export const BROKEN_CHAT_AFTER_SECONDS = 40 * 60;

type ChatHealthMessage = {
  role?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
  activity_at?: unknown;
};

type ChatHealth = SidebarOrderChat & {
  status?: unknown;
  last_assistant_at?: unknown;
  last_user_at?: unknown;
  messages?: readonly ChatHealthMessage[];
};

function positiveEpoch(value: unknown): number {
  const epoch = Number(value || 0);

  return Number.isFinite(epoch) && epoch > 0 ? epoch : 0;
}

function roleActivityAt(chat: ChatHealth | null | undefined, role: "assistant" | "user"): number {
  if (!chat) return 0;

  const summaryValue = role === "assistant" ? chat.last_assistant_at : chat.last_user_at;
  let latest = positiveEpoch(summaryValue);

  for (const message of chat.messages || []) {
    const messageRole = typeof message?.role === "string" ? message.role : "";

    if (messageRole !== role) continue;

    latest = Math.max(
      latest,
      positiveEpoch(message.activity_at),
      positiveEpoch(message.created_at),
    );
  }

  return latest;
}

export function chatLastAssistantAt(chat: ChatHealth | null | undefined): number {
  return roleActivityAt(chat, "assistant");
}

export function chatBrokenReferenceAt(chat: ChatHealth | null | undefined): number {
  if (!chat) return 0;

  return Math.max(
    chatLastAssistantAt(chat),
    roleActivityAt(chat, "user"),
    positiveEpoch(chat.created_at),
  );
}

export function chatIsBroken(
  chat: ChatHealth | null | undefined,
  nowSeconds = Date.now() / 1000,
): boolean {
  if (!chat || sidebarChatIsPending(chat)) return false;

  const status = typeof chat.status === "string" ? chat.status : "";

  if (status !== "active" && status !== "interrupted") return false;

  const referenceAt = chatBrokenReferenceAt(chat);

  if (!referenceAt) return false;

  return nowSeconds - referenceAt >= BROKEN_CHAT_AFTER_SECONDS;
}

export function sidebarSelectedConversationId(
  selectedId: string | null | undefined,
  composingNew: boolean,
  pendingNewDisplayId: string | null | undefined,
): string {
  const pendingId = String(pendingNewDisplayId || "");

  if (composingNew && pendingId) return pendingId;

  return String(selectedId || "");
}

export function sidebarChatIsSelected(
  chat: SidebarOrderChat | null | undefined,
  selectedId: string | null | undefined,
  composingNew: boolean,
  pendingNewDisplayId: string | null | undefined,
): boolean {
  const chatId = String(chat?.id || "");

  if (!chatId) return false;

  return chatId === sidebarSelectedConversationId(selectedId, composingNew, pendingNewDisplayId);
}

export function selectedConversationAfterChatRefresh<T extends { id: string }>(
  selectedId: string | null | undefined,
  composingNew: boolean,
  chats: readonly T[],
): string | null {
  const current = String(selectedId || "").trim();

  if (current) return current;

  if (composingNew) return null;

  const first = String(chats[0]?.id || "").trim();

  return first || null;
}

export function clientIdBelongsToSession(
  clientId: string | null | undefined,
  sessionId: string | null | undefined,
): boolean {
  const client = String(clientId || "").trim();
  const session = String(sessionId || "").trim();

  return Boolean(client && session && client.startsWith(`${session}:`));
}

export function sortSidebarChats<T extends SidebarOrderChat>(
  chats: readonly T[],
  pinnedIds: ReadonlySet<string>,
): T[] {
  const pinnedOrder = new Map(Array.from(pinnedIds, (id, index) => [id, index]));

  return [...chats].sort((left, right) => {
    const leftPinnedIndex = pinnedOrder.get(left.id);
    const rightPinnedIndex = pinnedOrder.get(right.id);

    if (leftPinnedIndex !== undefined || rightPinnedIndex !== undefined) {
      if (leftPinnedIndex === undefined) return 1;

      if (rightPinnedIndex === undefined) return -1;

      return leftPinnedIndex - rightPinnedIndex;
    }

    const userActivityDelta = sidebarChatLastUserAt(right) - sidebarChatLastUserAt(left);

    if (userActivityDelta) return userActivityDelta;

    return left.id.localeCompare(right.id);
  });
}

export type PendingNewSend = {
  clientId?: string;
  conversationId?: string;
  message?: string;
  status?: string;
  createdAt?: number;
};

export type PendingReply = {
  clientId?: string;
  sendId?: string;
  conversationId?: string;
  origin?: "new" | "reply";
  message?: string;
  status?: string;
  error?: string;
  retryAfterSeconds?: number;
  retryAt?: number;
  retryAttempt?: number;
  queuePosition?: number;
  queueEtaAt?: number;
  observedInCache?: boolean;
  responseObservedInCache?: boolean;
  createdAt?: number;
  updatedAt?: number;
  attachments?: Array<{
    id?: string;
    name?: string;
    type?: string;
    src?: string;
  }>;
};

export type CachedMessage = {
  role?: string;
  content?: string;
  created_at?: number;
  updated_at?: number;
};

export type ScheduleSlashCommand =
  | null
  | { error: string }
  | { intervalMinutes: number; prompt: string };

export type AtSlashCommand =
  | null
  | { error: string }
  | { runAtEpoch: number; runAtLabel: string; prompt: string };

export type PendingSendActivity = {
  label: string;
  statusText: string;
};

export type PendingConversationSummary = {
  id: string;
  status: string;
  title: string;
  preview: string;
  message_count: number;
  job_name: string;
  created_at: number;
  updated_at: number;
  last_user_at: number;
  _optimisticReply: true;
};

const CHATGPT_RICH_START = "\uE200";

const CHATGPT_RICH_END = "\uE201";

const CHATGPT_RICH_SEPARATOR = "\uE202";

function textValue(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;

  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }

  return fallback;
}

function readableRichMarkerFallback(parts: string[]): string {
  return (
    parts
      .find((part) => {
        const value = part.trim();

        return (
          Boolean(value) &&
          value.length <= 200 &&
          !/^turn\d+[a-z]+\d+$/i.test(value) &&
          !/^https?:\/\//i.test(value) &&
          !/^[{[]/.test(value)
        );
      })
      ?.trim() || ""
  );
}

export function replaceChatGptRichMarkers(
  value: unknown,
  renderUrl: (label: string, url: string) => string = (label) => label,
): string {
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
      // Streaming responses can expose a marker before its closing delimiter.
      // Hide the private marker until the next snapshot completes it.
      break;
    }

    const body = source.slice(start + CHATGPT_RICH_START.length, end);
    const [rawType, ...parts] = body.split(CHATGPT_RICH_SEPARATOR);
    const type = rawType.trim().toLowerCase();
    let replacement = "";

    if (type === "url") {
      const label = String(parts[0] || parts[1] || "").trim();
      const url = String(parts[1] || "").trim();
      replacement = /^https?:\/\//i.test(url)
        ? renderUrl(label || url, url)
        : label || readableRichMarkerFallback(parts);
    } else if (type !== "cite" && type !== "memcite") {
      replacement = readableRichMarkerFallback(parts);
    }

    output += replacement;
    cursor = end + CHATGPT_RICH_END.length;
  }

  return output;
}

function queueEtaText(seconds: unknown): string {
  const value = Number(seconds);

  if (!Number.isFinite(value) || value <= 0) return "<1m";

  const minutes = Math.max(1, Math.ceil(value / 60));

  if (minutes < 60) return String(minutes) + "m";

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  if (hours < 24) return remainingMinutes ? hours + "h " + remainingMinutes + "m" : hours + "h";

  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;

  return remainingHours ? days + "d " + remainingHours + "h" : days + "d";
}

function retryDelayText(seconds: unknown): string {
  const value = Number(seconds);

  if (!Number.isFinite(value) || value <= 0) return "soon";

  if (value < 60) return "<1m";

  const minutes = Math.ceil(value / 60);

  if (minutes < 60) return `${minutes}m`;

  const hours = Math.ceil(minutes / 60);

  return `${hours}h`;
}

export function pendingSendActivity(
  status: unknown,
  hasSendId: boolean,
  retryAfterSeconds: unknown = 0,
  retryAtEpoch: unknown = 0,
  nowEpoch: unknown = Date.now() / 1000,
  queuePosition: unknown = 0,
  queueEtaAtEpoch: unknown = 0,
): PendingSendActivity | null {
  const normalized = textValue(status, "queued").trim().toLowerCase();

  if (["failed", "dead_lettered"].includes(normalized)) return null;

  if (!hasSendId) return { label: "sending", statusText: "Sending…" };

  if (normalized === "queued") {
    const position = Number(queuePosition);

    if (Number.isFinite(position) && position > 0) {
      const queueLabel = "queued · #" + Math.floor(position);
      const statusLabel = "Queued in Prompta · #" + Math.floor(position);
      const etaAt = Number(queueEtaAtEpoch);
      const now = Number(nowEpoch);
      const etaRemaining =
        Number.isFinite(etaAt) && etaAt > 0 && Number.isFinite(now) ? Math.max(0, etaAt - now) : 0;
      const eta = etaRemaining > 0 ? " · ETA ~" + queueEtaText(etaRemaining) : "";

      return {
        label: queueLabel + eta,
        statusText: statusLabel + eta,
      };
    }

    return { label: "queued", statusText: "Queued in Prompta…" };
  }

  if (normalized === "retrying") {
    const deadline = Number(retryAtEpoch);
    const now = Number(nowEpoch);
    const remaining =
      Number.isFinite(deadline) && deadline > 0 && Number.isFinite(now)
        ? Math.max(0, deadline - now)
        : Number(retryAfterSeconds);

    if (remaining <= 0) {
      return { label: "retrying now", statusText: "Retry backoff elapsed; retrying now…" };
    }

    const delay = retryDelayText(remaining);

    return {
      label: `retrying · ${delay}`,
      statusText: `Send failed transiently — retrying automatically in ${delay}.`,
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
        statusText: "Rate limited — backoff elapsed; retrying now…",
      };
    }

    const delay = retryDelayText(remaining);

    return {
      label: `rate limited · retry in ${delay}`,
      statusText: `Rate limited — backing off; retrying automatically in ${delay}.`,
    };
  }

  return { label: "waiting", statusText: "Waiting for ChatGPT…" };
}

export function conversationIdFromHash(hash: unknown): string {
  const encoded = textValue(hash).replace(/^#\/?/, "").trim();

  if (!encoded) return "";

  try {
    return decodeURIComponent(encoded);
  } catch {
    return "";
  }
}

const TOOL_UI_NOISE =
  /^(?:open tool call list|close tool call list|tool|tool call|expand|collapse|cot-v5-[\w-]+)$/i;

export function toolCallDisplayName(value: unknown): string {
  const name = textValue(value).replace(/\s+/g, " ").trim();

  return name && !TOOL_UI_NOISE.test(name) ? name : "";
}

export function toolCallIsInvocationPlaceholder(value: unknown): boolean {
  return /^called tool$/i.test(textValue(value).trim());
}

export function toolCallHasUsefulDetail(value: unknown): boolean {
  return textValue(value)
    .split(/\n+/)
    .map((line) => line.trim())
    .some((line) => Boolean(toolCallDisplayName(line)));
}

function parsedToolPayload(value: unknown): unknown {
  let current: unknown = value;

  for (let depth = 0; depth < 3; depth += 1) {
    if (typeof current !== "string") return current;

    const trimmed = current.trim();

    if (!trimmed || !/^[{[]/.test(trimmed)) return current;

    try {
      current = JSON.parse(trimmed);
    } catch {
      return current;
    }
  }

  return current;
}

export function toolCallSummary(value: unknown): string {
  const payload = parsedToolPayload(value);

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";

  const record = payload as Record<string, unknown>;

  for (const candidate of [record.summary, record.reasoning_title, record.title]) {
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }

  return "";
}

export function toolCallTimestampMillis(value: unknown): number | null {
  const payload = parsedToolPayload(value);

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;

  const record = payload as Record<string, unknown>;

  for (const candidate of [record.created_at, record.createdAt, record.timestamp, record.time]) {
    const numeric = Number(candidate);

    if (!Number.isFinite(numeric) || numeric <= 0) continue;

    const millis = numeric > 1_000_000_000_000 ? numeric : numeric * 1000;

    if (Number.isNaN(new Date(millis).getTime())) continue;

    return millis;
  }

  return null;
}

export function pythonToolCallCode(toolName: unknown, value: unknown): string {
  const name = textValue(toolName).trim().toLowerCase();
  const pythonTool =
    name.includes("execute_python") ||
    (name.includes("python") &&
      (name.includes("nox") || name.includes("glass") || name.includes("mcp")));

  if (!pythonTool) return "";

  const payload = parsedToolPayload(value);

  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";

  const record = payload as Record<string, unknown>;
  const argumentPayload = parsedToolPayload(record.arguments ?? record.args ?? record);

  if (!argumentPayload || typeof argumentPayload !== "object" || Array.isArray(argumentPayload))
    return "";

  const code = (argumentPayload as Record<string, unknown>).code;

  return typeof code === "string" ? code.replace(/^(?:[ \t]*\r?\n)+/, "") : "";
}

export function sidebarPreviewText(value: unknown): string {
  return replaceChatGptRichMarkers(value)
    .replace(/```(?:tool|tool-call|function|function-call)(?::[^\n\x60]*)?\n?[\s\S]*?```/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function sidebarChatPreviewText(preview: unknown, prompt: unknown): string {
  return sidebarPreviewText(preview) || sidebarPreviewText(prompt);
}

export function missingPendingConversationSummaries(
  chats: readonly { id: string }[],
  pendingReplies: ReadonlyMap<string, PendingReply[]>,
  query = "",
): PendingConversationSummary[] {
  const existingIds = new Set(chats.map((chat) => String(chat.id)));
  const needle = query.trim().toLowerCase();
  const summaries: PendingConversationSummary[] = [];

  for (const [conversationId, replies] of pendingReplies) {
    if (!conversationId || existingIds.has(conversationId) || !replies.length) continue;

    const latest = replies[replies.length - 1];
    const message = textValue(latest.message).trim();
    const title = message.slice(0, 72) || "New chat";
    const status = ["failed", "dead_lettered"].includes(textValue(latest.status))
      ? textValue(latest.status)
      : "active";

    if (
      needle &&
      ![title, message, "new chat"].some((value) => value.toLowerCase().includes(needle))
    ) {
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
      last_user_at: Number.isFinite(createdAt) ? createdAt : 0,
      _optimisticReply: true,
    });
  }

  return summaries.sort((left, right) => right.updated_at - left.updated_at);
}

export function pendingConversationDisplayId(pending: PendingNewSend | null | undefined): string {
  if (!pending) return "";

  if (pending.conversationId) return String(pending.conversationId);

  const clientId = String(pending.clientId || "").trim();

  return clientId ? `pending-new-${clientId}` : "";
}

export function isUnresolvedPendingNewConversation(
  pending: PendingNewSend | null | undefined,
  conversationId: string | null | undefined,
): boolean {
  if (!pending || !conversationId) return false;

  const status = String(pending.status || "")
    .trim()
    .toLowerCase();

  return status !== "succeeded" && pendingConversationDisplayId(pending) === conversationId;
}

export function promotePinnedConversationId(
  pinnedIds: Set<string>,
  pending: PendingNewSend | null | undefined,
  nextConversationId: string,
): boolean {
  const nextId = String(nextConversationId || "").trim();

  if (!nextId) return false;

  const previousId = pendingConversationDisplayId(pending);

  if (!previousId || previousId === nextId || !pinnedIds.has(previousId)) return false;

  pinnedIds.delete(previousId);
  pinnedIds.add(nextId);

  return true;
}

function comparableTimestampSeconds(value: unknown): number {
  const timestamp = Number(value);

  if (!Number.isFinite(timestamp) || timestamp <= 0) return 0;

  return timestamp >= 1e12 ? timestamp / 1000 : timestamp;
}

function comparablePrompt(value: unknown): string {
  return textValue(value).trim().replace(/\s+/g, " ");
}

export function matchingOptimisticConversation(
  chats: ChatSummary[],
  pending: PendingNewSend | null | undefined,
  knownConversationIds: ReadonlySet<string> = new Set(),
): ChatSummary | null {
  if (!pending) return null;

  const clientId = textValue(pending.clientId).trim();

  if (clientId) {
    const exactClient = chats.find((chat) => textValue(chat._client_id).trim() === clientId);

    if (exactClient) return exactClient;
  }

  if (pending.conversationId) {
    const exact = chats.find((chat) => chat.id === pending.conversationId);

    if (exact) return exact;
  }

  const prompt = comparablePrompt(pending.message);

  if (!prompt) return null;

  const createdAt = comparableTimestampSeconds(pending.createdAt);
  let best: ChatSummary | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;

  if (createdAt > 0) {
    for (const chat of chats) {
      if (comparablePrompt(chat.prompt) !== prompt) continue;

      const chatCreatedAt = comparableTimestampSeconds(chat.created_at);

      if (chatCreatedAt <= 0) continue;

      const distance = Math.abs(chatCreatedAt - createdAt);

      if (distance > 30 || distance >= bestDistance) continue;

      best = chat;
      bestDistance = distance;
    }
  }

  if (best) return best;

  if (!knownConversationIds.size) return null;

  const unseenMatches = chats.filter(
    (chat) => !knownConversationIds.has(chat.id) && comparablePrompt(chat.prompt) === prompt,
  );

  return unseenMatches.length === 1 ? unseenMatches[0] : null;
}

export function messageTimestampMillis(createdAt: unknown, updatedAt: unknown): number | null {
  for (const candidate of [createdAt, updatedAt]) {
    const raw = Number(candidate);

    if (!Number.isFinite(raw) || raw <= 0) continue;

    const millis = raw < 1e12 ? raw * 1000 : raw;

    if (!Number.isFinite(millis)) continue;

    const date = new Date(millis);

    if (!Number.isNaN(date.getTime())) return millis;
  }

  return null;
}

export function formatClockTime12Hour(value: Date | number, includeSeconds = false): string {
  const date = value instanceof Date ? value : new Date(value);

  if (Number.isNaN(date.getTime())) return "";

  const hour24 = date.getHours();
  const hour12 = hour24 % 12 || 12;
  const minutes = String(date.getMinutes()).padStart(2, "0");
  const seconds = includeSeconds ? `:${String(date.getSeconds()).padStart(2, "0")}` : "";

  return `${hour12}:${minutes}${seconds}${hour24 < 12 ? "am" : "pm"}`;
}

export function formatDailyTime12Hour(value: unknown): string {
  const raw = textValue(value);
  const match = raw.match(/^([01]\d|2[0-3]):([0-5]\d)$/);

  if (!match) return raw;

  const hour24 = Number(match[1]);
  const hour12 = hour24 % 12 || 12;

  return `${hour12}:${match[2]}${hour24 < 12 ? "am" : "pm"}`;
}

export function messageAgeText(timestampMillis: unknown, nowMillis = Date.now()): string {
  const timestamp = Number(timestampMillis);
  const now = Number(nowMillis);

  if (!Number.isFinite(timestamp) || timestamp <= 0 || !Number.isFinite(now)) return "";

  const elapsed = Math.max(0, now - timestamp);

  if (elapsed < 45_000) return "now";

  if (elapsed < 3_600_000) return `${Math.max(1, Math.floor(elapsed / 60_000))}m ago`;

  if (elapsed < 86_400_000) return `${Math.max(1, Math.floor(elapsed / 3_600_000))}h ago`;

  if (elapsed < 604_800_000) return `${Math.max(1, Math.floor(elapsed / 86_400_000))}d ago`;

  if (elapsed < 2_592_000_000) return `${Math.max(1, Math.floor(elapsed / 604_800_000))}w ago`;

  if (elapsed < 31_536_000_000) return `${Math.max(1, Math.floor(elapsed / 2_592_000_000))}mo ago`;

  return `${Math.max(1, Math.floor(elapsed / 31_536_000_000))}y ago`;
}

export function shouldRenderNewChatView(
  enteringNewChat: boolean,
  fingerprint: string,
  previousFingerprint: string,
): boolean {
  return enteringNewChat || fingerprint !== previousFingerprint;
}

export function pendingConversationSends(
  conversationId: string,
  replies: PendingReply[],
  pendingNew: PendingReply | null | undefined,
): PendingReply[] {
  if (!pendingNew || pendingNew.conversationId !== conversationId) return replies;

  const duplicate = replies.some(
    (item) =>
      item === pendingNew ||
      (pendingNew.clientId && item.clientId === pendingNew.clientId) ||
      (pendingNew.sendId && item.sendId === pendingNew.sendId),
  );

  return duplicate ? replies : [...replies, pendingNew];
}

export function matchingPendingReplyMessageIndex(
  messages: CachedMessage[],
  pending: PendingReply,
  claimedIndexes: ReadonlySet<number> = new Set(),
): number {
  const content = comparablePrompt(pending.message);

  if (!content) return -1;

  if (pending.origin === "new") {
    const firstDurableUserIndex = messages.findIndex(
      (message, index) =>
        !claimedIndexes.has(index) &&
        message.role === "user" &&
        comparablePrompt(message.content) === content,
    );

    if (firstDurableUserIndex >= 0) return firstDurableUserIndex;
  }

  const pendingTimes = [pending.createdAt, pending.updatedAt]
    .map(comparableTimestampSeconds)
    .filter((timestamp) => timestamp > 0);

  if (!pendingTimes.length) return -1;

  let bestIndex = -1;
  let bestDistance = Number.POSITIVE_INFINITY;
  const delayedCandidates: number[] = [];
  const earliestPendingTime = Math.min(...pendingTimes);

  for (let index = 0; index < messages.length; index += 1) {
    if (claimedIndexes.has(index)) continue;

    const message = messages[index];

    if (message.role !== "user" || comparablePrompt(message.content) !== content) continue;

    const messageTime = comparableTimestampSeconds(message.created_at || message.updated_at);

    if (messageTime <= 0) continue;

    const distance = Math.min(
      ...pendingTimes.map((pendingTime) => Math.abs(messageTime - pendingTime)),
    );

    if (distance <= 30 && distance < bestDistance) {
      bestIndex = index;
      bestDistance = distance;
    }

    // Cached message timestamps are observation times, not ChatGPT source
    // timestamps. A long-running response can therefore first persist its user
    // row well after the 30-second optimistic-send window. It is still safe to
    // reconcile when the durable row was observed after this pending send.
    if (messageTime >= earliestPendingTime - 30) delayedCandidates.push(index);
  }

  if (bestIndex >= 0) return bestIndex;

  return delayedCandidates[0] ?? -1;
}

export function parseScheduleSlashCommand(message: string): ScheduleSlashCommand {
  if (!/^\/(?:add|every)(?:\s|$)/i.test(message)) return null;

  const match = message.match(
    /^\/(?:add|every)\s+(\d+(?:\.\d+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)?\s+([\s\S]+)$/i,
  );

  if (!match) {
    return {
      error:
        "Use /add <interval> <prompt>, for example: /add 30 fix bugs or /add 2h review failures",
    };
  }

  const amount = Number(match[1]);
  const unit = String(match[2] || "m").toLowerCase();
  const multiplier = unit.startsWith("s")
    ? 1 / 60
    : unit.startsWith("h")
      ? 60
      : unit.startsWith("d")
        ? 1440
        : 1;
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

export function formatScheduleInterval(minutes: number): string {
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

export async function postJsonRequest(
  url: string,
  payload: unknown,
  attempts = 1,
  timeoutMs = 45_000,
  fetchImpl: typeof fetch = fetch,
): Promise<any> {
  let lastError = new Error("Request failed");

  for (let attempt = 0; attempt < Math.max(1, attempts); attempt += 1) {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
    let response: Response;
    let data: any = {};

    try {
      response = await fetchImpl(url, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      try {
        data = await response.json();
      } catch {
        if (controller.signal.aborted) throw new Error("Request timed out");

        if (response.ok) throw new Error("Prompta returned an invalid response");
      }
    } catch (error) {
      lastError = controller.signal.aborted
        ? new Error("Request timed out")
        : error instanceof Error
          ? error
          : new Error(String(error));

      if (attempt + 1 >= attempts) throw lastError;

      await new Promise((resolve) => globalThis.setTimeout(resolve, 350 * (attempt + 1)));
      continue;
    } finally {
      globalThis.clearTimeout(timeout);
    }

    if (response.ok) return data;

    const errorMessage =
      typeof data === "object" && data !== null && "error" in data && typeof data.error === "string"
        ? data.error
        : "";
    lastError = new Error(errorMessage || `${response.status} ${response.statusText}`);

    if (response.status < 500 || attempt + 1 >= attempts) throw lastError;

    await new Promise((resolve) => globalThis.setTimeout(resolve, 350 * (attempt + 1)));
  }

  throw lastError;
}

export async function deleteRequest(
  url: string,
  timeoutMs = 10_000,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetchImpl(url, {
      method: "DELETE",
      cache: "no-store",
      signal: controller.signal,
    });

    if (!response.ok && response.status !== 404) {
      throw new Error((String(response.status) + " " + response.statusText).trim());
    }
  } catch (error) {
    if (controller.signal.aborted) throw new Error("Request timed out");

    throw error instanceof Error ? error : new Error(String(error));
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export function nextSlashCommandIndex(
  itemCount: number,
  currentIndex: number,
  direction: number,
): number {
  const count = Math.max(0, Math.trunc(itemCount));

  if (count === 0) return -1;

  const step = direction < 0 ? -1 : 1;

  if (currentIndex < 0 || currentIndex >= count) return step < 0 ? count - 1 : 0;

  return (currentIndex + step + count) % count;
}

export function composerHasContent(message: string, attachmentCount: number): boolean {
  return Boolean(String(message || "").trim()) || attachmentCount > 0;
}

export function shouldShowStopAction(
  chatStatus: unknown,
  composingNew: boolean,
  hasComposerContent = false,
): boolean {
  return (
    !hasComposerContent && !composingNew && textValue(chatStatus).trim().toLowerCase() === "active"
  );
}

export function shouldProbeHistoricalActivity(chatStatus: unknown): boolean {
  return textValue(chatStatus).trim().toLowerCase() === "interrupted";
}

export function shouldRefreshSelectedChat(
  summary: { status?: unknown; updated_at?: unknown } | null | undefined,
  selectedUpdatedAt: unknown,
  selectedFingerprint: unknown,
  force = false,
): boolean {
  return (
    force ||
    !summary ||
    summary.status === "active" ||
    selectedUpdatedAt !== summary.updated_at ||
    !selectedFingerprint
  );
}

export function parseAtSlashCommand(message: string, now = new Date()): AtSlashCommand {
  if (!/^\/at(?:\s|$)/i.test(message)) return null;

  const match = message.match(
    /^\/at\s+(today|tomorrow|\d{4}-\d{2}-\d{2})(?:[T\s]+)([01]\d|2[0-3]):([0-5]\d)\s+([\s\S]+)$/i,
  );

  if (!match) {
    return {
      error: "Use /at <date> <time> <prompt>, for example: /at 2026-09-21 09:30 review failures",
    };
  }

  const dateToken = match[1].toLowerCase();
  const hour = Number(match[2]);
  const minute = Number(match[3]);
  const prompt = match[4].trim();

  let target: Date;
  let expectedYear: number;
  let expectedMonth: number;
  let expectedDay: number;

  if (dateToken === "today" || dateToken === "tomorrow") {
    target = new Date(now);

    if (dateToken === "tomorrow") target.setDate(target.getDate() + 1);

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

    if (
      target.getFullYear() !== expectedYear ||
      target.getMonth() !== expectedMonth ||
      target.getDate() !== expectedDay
    ) {
      return { error: "Schedule date is invalid." };
    }
  }

  if (
    target.getFullYear() !== expectedYear ||
    target.getMonth() !== expectedMonth ||
    target.getDate() !== expectedDay ||
    target.getHours() !== hour ||
    target.getMinutes() !== minute
  ) {
    return { error: "Schedule time does not exist in the local timezone." };
  }

  if (!prompt) return { error: "Schedule prompt is required." };

  const runAtEpoch = target.getTime() / 1000;

  if (!Number.isFinite(runAtEpoch) || runAtEpoch <= now.getTime() / 1000) {
    return { error: "Schedule time must be in the future." };
  }

  const runAtLabel = `${target.toLocaleDateString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
  })} ${formatClockTime12Hour(target)}`;

  return { runAtEpoch, runAtLabel, prompt };
}
