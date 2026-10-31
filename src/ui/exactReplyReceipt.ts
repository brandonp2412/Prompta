import { localGet } from "./localRead";

export type ExactReplyPayload = {
  reply_id: string;
  conversation_id: string;
  parent_id: string;
  text: string;
};

export type ExactReplyReceiptState = "accepted" | "uncertain" | "not_sent" | "invalid";

// A 202 alone is not proof that this exact immutable reply was queued.
// Confirm every identity and payload field before clearing a saved receipt.
export function exactReplyReceiptState(
  turn: unknown,
  expected: ExactReplyPayload,
  sendId: string,
): ExactReplyReceiptState {
  if (!turn || typeof turn !== "object") return "invalid";
  if (
    !("reply_id" in turn) ||
    turn.reply_id !== expected.reply_id ||
    !("send_id" in turn) ||
    turn.send_id !== sendId ||
    !("conversation_id" in turn) ||
    turn.conversation_id !== expected.conversation_id ||
    !("parent_id" in turn) ||
    turn.parent_id !== expected.parent_id ||
    !("user_text" in turn) ||
    turn.user_text !== expected.text ||
    !("status" in turn) ||
    typeof turn.status !== "string"
  )
    return "invalid";
  if (turn.status === "outcome_unknown") return "uncertain";
  if (turn.status === "preflight_failed") return "not_sent";
  if (turn.status === "prepared") {
    return "queued_by_user" in turn && turn.queued_by_user === true ? "accepted" : "not_sent";
  }
  return ["dispatching", "accepted", "generating", "completed", "interrupted"].includes(turn.status)
    ? "accepted"
    : "invalid";
}

// Only a local, read-only database lookup. No ChatGPT navigation or resubmission.
export async function findExactReplyReceiptState(
  sendId: string,
  expected: ExactReplyPayload,
): Promise<ExactReplyReceiptState | null> {
  try {
    const response = await localGet("./api/results/" + encodeURIComponent(sendId) + "/turns");
    if (!response.ok) return null;
    const body: unknown = await response.json();
    if (!body || typeof body !== "object" || !("turns" in body) || !Array.isArray(body.turns)) {
      return null;
    }
    const found: unknown = body.turns.find(
      (turn: unknown) =>
        turn !== null &&
        typeof turn === "object" &&
        "reply_id" in turn &&
        turn.reply_id === expected.reply_id,
    );
    return found === undefined ? null : exactReplyReceiptState(found, expected, sendId);
  } catch {
    return null;
  }
}
