export type ChatSummary = {
  id: string;
  prompt?: string;
  created_at?: number;
};

export type PendingNewSend = {
  conversationId?: string;
  message?: string;
  createdAt?: number;
};

export type PendingReply = {
  clientId?: string;
  sendId?: string;
  conversationId?: string;
  message?: string;
  status?: string;
  error?: string;
  retryAfterSeconds?: number;
  retryAttempt?: number;
  observedInCache?: boolean;
  responseObservedInCache?: boolean;
  createdAt?: number;
  updatedAt?: number;
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


const CHATGPT_RICH_START = "\uE200";
const CHATGPT_RICH_END = "\uE201";
const CHATGPT_RICH_SEPARATOR = "\uE202";

function readableRichMarkerFallback(parts: string[]): string {
  return parts.find((part) => {
    const value = part.trim();
    return Boolean(value)
      && value.length <= 200
      && !/^turn\d+[a-z]+\d+$/i.test(value)
      && !/^https?:\/\//i.test(value)
      && !/^[{[]/.test(value);
  })?.trim() || "";
}

export function replaceChatGptRichMarkers(
  value: unknown,
  renderUrl: (label: string, url: string) => string = (label) => label,
): string {
  const source = String(value || "");
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
): PendingSendActivity | null {
  const normalized = String(status || "queued").trim().toLowerCase();
  if (normalized === "failed") return null;
  if (!hasSendId) return { label: "sending", statusText: "Sending…" };
  if (normalized === "queued") return { label: "queued", statusText: "Queued in Prompta…" };
  if (normalized === "rate_limited") {
    const delay = retryDelayText(retryAfterSeconds);
    return {
      label: `rate limited · retry in ${delay}`,
      statusText: `Rate limited — backing off; retrying automatically in ${delay}.`,
    };
  }
  return { label: "waiting", statusText: "Waiting for ChatGPT…" };
}

export function conversationIdFromHash(hash: unknown): string {
  const encoded = String(hash || "").replace(/^#\/?/, "").trim();
  if (!encoded) return "";
  try {
    return decodeURIComponent(encoded);
  } catch {
    return "";
  }
}

const TOOL_UI_NOISE = /^(?:open tool call list|close tool call list|tool|tool call|expand|collapse|cot-v5-[\w-]+)$/i;

export function toolCallDisplayName(value: unknown): string {
  const name = String(value || "").replace(/\s+/g, " " ).trim();
  return name && !TOOL_UI_NOISE.test(name) ? name : "";
}

export function toolCallIsInvocationPlaceholder(value: unknown): boolean {
  return /^called tool$/i.test(String(value || "").trim());
}

export function toolCallHasUsefulDetail(value: unknown): boolean {
  return String(value || "")
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

export function pythonToolCallCode(toolName: unknown, value: unknown): string {
  const name = String(toolName || "").trim().toLowerCase();
  const pythonTool = name.includes("execute_python")
    || (name.includes("python") && (name.includes("nox") || name.includes("glass") || name.includes("mcp")));
  if (!pythonTool) return "";

  const payload = parsedToolPayload(value);
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";
  const record = payload as Record<string, unknown>;
  const argumentPayload = parsedToolPayload(record.arguments ?? record.args ?? record);
  if (!argumentPayload || typeof argumentPayload !== "object" || Array.isArray(argumentPayload)) return "";
  const code = (argumentPayload as Record<string, unknown>).code;
  return typeof code === "string" ? code.replace(/^(?:[ \t]*\r?\n)+/, "") : "";
}

export function sidebarPreviewText(value: unknown): string {
  return replaceChatGptRichMarkers(value)
    .replace(
      /```(?:tool|tool-call|function|function-call)(?::[^\n\x60]*)?\n?[\s\S]*?```/gi,
      " ",
    )
    .replace(/\s+/g, " ")
    .trim();
}

export function matchingOptimisticConversation(
  chats: ChatSummary[],
  pending: PendingNewSend | null | undefined,
): ChatSummary | null {
  if (!pending) return null;

  if (pending.conversationId) {
    const exact = chats.find((chat) => chat.id === pending.conversationId);
    if (exact) return exact;
  }

  const prompt = String(pending.message || "").trim();
  if (!prompt) return null;

  const createdAt = Number(pending.createdAt || 0);
  if (!Number.isFinite(createdAt) || createdAt <= 0) return null;

  let best: ChatSummary | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const chat of chats) {
    if (String(chat.prompt || "").trim() !== prompt) continue;
    const chatCreatedAt = Number(chat.created_at || 0);
    if (!Number.isFinite(chatCreatedAt) || chatCreatedAt <= 0) continue;
    const distance = Math.abs(chatCreatedAt - createdAt);
    if (distance > 30 || distance >= bestDistance) continue;
    best = chat;
    bestDistance = distance;
  }
  return best;
}

export function messageTimestampMillis(
  createdAt: unknown,
  updatedAt: unknown,
): number | null {
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

  const duplicate = replies.some((item) => (
    item === pendingNew
    || (pendingNew.clientId && item.clientId === pendingNew.clientId)
    || (pendingNew.sendId && item.sendId === pendingNew.sendId)
  ));
  return duplicate ? replies : [...replies, pendingNew];
}

export function matchingPendingReplyMessageIndex(
  messages: CachedMessage[],
  pending: PendingReply,
  claimedIndexes: ReadonlySet<number> = new Set(),
): number {
  const content = String(pending.message || "").trim();
  const pendingAt = Number(pending.createdAt || pending.updatedAt || 0);
  if (!content || !Number.isFinite(pendingAt) || pendingAt <= 0) return -1;

  const earliestMatch = pendingAt - 3;
  let bestIndex = -1;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (claimedIndexes.has(index)) continue;
    const message = messages[index];
    if (message.role !== "user" || String(message.content || "").trim() !== content) continue;
    const messageTime = Number(message.created_at || message.updated_at || 0);
    if (!Number.isFinite(messageTime) || messageTime < earliestMatch) continue;
    const distance = Math.abs(messageTime - pendingAt);
    if (distance >= bestDistance) continue;
    bestIndex = index;
    bestDistance = distance;
  }
  return bestIndex;
}

export function parseScheduleSlashCommand(message: string): ScheduleSlashCommand {
  if (!/^\/every(?:\s|$)/i.test(message)) return null;

  const match = message.match(
    /^\/every\s+(\d+(?:\.\d+)?)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours)?\s+([\s\S]+)$/i,
  );
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

export function formatScheduleInterval(minutes: number): string {
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
      } catch (error) {
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
    const errorMessage = (
      typeof data === "object"
      && data !== null
      && "error" in data
      && typeof data.error === "string"
    ) ? data.error : "";
    lastError = new Error(errorMessage || `${response.status} ${response.statusText}`);
    if (response.status < 500 || attempt + 1 >= attempts) throw lastError;
    await new Promise((resolve) => globalThis.setTimeout(resolve, 350 * (attempt + 1)));
  }
  throw lastError;
}

export function composerHasContent(message: string, attachmentCount: number): boolean {
  return Boolean(String(message || "").trim()) || attachmentCount > 0;
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
    if (target.getFullYear() !== expectedYear || target.getMonth() !== expectedMonth || target.getDate() !== expectedDay) {
      return { error: "Schedule date is invalid." };
    }
  }
  if (target.getFullYear() !== expectedYear || target.getMonth() !== expectedMonth || target.getDate() !== expectedDay || target.getHours() !== hour || target.getMinutes() !== minute) {
    return { error: "Schedule time does not exist in the local timezone." };
  }

  if (!prompt) return { error: "Schedule prompt is required." };
  const runAtEpoch = target.getTime() / 1000;
  if (!Number.isFinite(runAtEpoch) || runAtEpoch <= now.getTime() / 1000) {
    return { error: "Schedule time must be in the future." };
  }

  const runAtLabel = target.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return { runAtEpoch, runAtLabel, prompt };
}
