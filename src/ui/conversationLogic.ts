import { injectToolCodeDiff } from "./diffPreview";

export function canMorphPendingMessageNode(messageKey: unknown, role: string, sendError = false) {
  if (sendError) return false;

  return role === "user"
    ? String(messageKey).startsWith("pending-user-")
    : String(messageKey).startsWith("pending-activity-");
}

export function imageAttachments(message: Record<string, any> | null | undefined) {
  const attachments = Array.isArray(message?.attachments) ? message.attachments : [];

  return attachments.filter(
    (attachment) =>
      attachment &&
      typeof attachment === "object" &&
      String(attachment.type || "").startsWith("image/") &&
      (Boolean(attachment.id) || String(attachment.src || "").startsWith("data:image/")),
  );
}

export function pendingImageAttachments(
  serializedAttachments: Array<{ name: string; type: string; data: string }>,
) {
  return serializedAttachments
    .filter((attachment) => attachment.type.startsWith("image/"))
    .map((attachment) => ({
      name: attachment.name,
      type: attachment.type,
      src: "data:" + attachment.type + ";base64," + attachment.data,
    }));
}

export function shouldHandlePendingLongPress(pointerType: string, coarsePointer: boolean) {
  return pointerType !== "mouse" || coarsePointer;
}

export function pendingLongPressMoved(
  startX: number,
  startY: number,
  currentX: number,
  currentY: number,
  tolerance = 8,
) {
  return Math.max(Math.abs(currentX - startX), Math.abs(currentY - startY)) > tolerance;
}

export function messageDisplayContent(message: Record<string, any> | null | undefined) {
  const fallback = String(message?.content || "");

  if (message?.role !== "assistant" || message?.parts_renderable !== true) return fallback;
  if (!Array.isArray(message.parts)) return fallback;

  const toolDiffs = new Map<string, unknown>();
  if (Array.isArray(message.tool_calls)) {
    for (const call of message.tool_calls) {
      const callKey = String(call?.call_key || "");
      if (callKey && call?.code_diff) toolDiffs.set(callKey, call.code_diff);
    }
  }

  const ordered = message.parts
    .map((part: any, index: number) => {
      const content = String(part?.content || "").trim();
      const callKey = String(part?.tool_call_key || "");

      return {
        content:
          String(part?.kind || "") === "tool_call" && callKey && toolDiffs.has(callKey)
            ? injectToolCodeDiff(content, toolDiffs.get(callKey))
            : content,
        index,
        ordinal: Number.isFinite(Number(part?.ordinal)) ? Number(part.ordinal) : index,
      };
    })
    .filter((part: { content: string }) => Boolean(part.content))
    .sort(
      (left: { ordinal: number; index: number }, right: { ordinal: number; index: number }) =>
        left.ordinal - right.ordinal || left.index - right.index,
    );

  if (!ordered.length) return fallback;

  const rendered = ordered
    .map((part: { content: string }) => part.content)
    .join("\n\n")
    .trim();

  return rendered || fallback;
}
