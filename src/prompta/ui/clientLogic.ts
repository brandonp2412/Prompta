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
