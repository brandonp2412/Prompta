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

export type ScheduleSlashCommand =
  | null
  | { error: string }
  | { intervalMinutes: number; prompt: string };

export type AtSlashCommand =
  | null
  | { error: string }
  | { runAtEpoch: number; runAtLabel: string; prompt: string };

export function sidebarPreviewText(value: unknown): string {
  return String(value || "")
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
  return chats.find((chat) => {
    if (String(chat.prompt || "").trim() !== prompt) return false;
    const chatCreatedAt = Number(chat.created_at || 0);
    return !createdAt || !chatCreatedAt || Math.abs(chatCreatedAt - createdAt) <= 30;
  }) || null;
}

export function parseScheduleSlashCommand(message: string): ScheduleSlashCommand {
  if (!message.startsWith("/every")) return null;

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


export function parseAtSlashCommand(message: string, now = new Date()): AtSlashCommand {
  if (!message.startsWith("/at")) return null;

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
  if (dateToken === "today" || dateToken === "tomorrow") {
    target = new Date(now);
    if (dateToken === "tomorrow") target.setDate(target.getDate() + 1);
    target.setHours(hour, minute, 0, 0);
  } else {
    const parts = dateToken.split("-").map(Number);
    target = new Date(parts[0], parts[1] - 1, parts[2], hour, minute, 0, 0);
    if (
      target.getFullYear() !== parts[0]
      || target.getMonth() !== parts[1] - 1
      || target.getDate() !== parts[2]
    ) {
      return { error: "Schedule date is invalid." };
    }
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
