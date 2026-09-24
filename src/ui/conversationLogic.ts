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

const LIVE_GENERIC_TOOL_PLACEHOLDER =
  /```(?:tool|tool-call|function|function-call):\s*tool[^\n]*\n\s*Called tool\s*\n```/gi;

export function messageDisplayContent(message: Record<string, any> | null | undefined) {
  const fallback = String(message?.content || "");

  if (message?.role !== "assistant") return fallback;

  const toolDiffs = new Map<string, unknown>();
  if (Array.isArray(message.tool_calls)) {
    for (const call of message.tool_calls) {
      const callKey = String(call?.call_key || "");
      if (callKey && call?.code_diff) toolDiffs.set(callKey, call.code_diff);
    }
  }

  const liveToolParts = Array.isArray(message.parts)
    ? message.parts
        .map((part: any, index: number) => ({
          content: String(part?.content || "").trim(),
          index,
          kind: String(part?.kind || ""),
          ordinal: Number.isFinite(Number(part?.ordinal)) ? Number(part.ordinal) : index,
          toolCallKey: String(part?.tool_call_key || ""),
        }))
        .filter(
          (part: { content: string; kind: string }) =>
            part.kind === "tool_call" && Boolean(part.content),
        )
        .sort(
          (left: { ordinal: number; index: number }, right: { ordinal: number; index: number }) =>
            left.ordinal - right.ordinal || left.index - right.index,
        )
    : [];

  let liveToolIndex = 0;
  const enrichedFallback = fallback.replace(LIVE_GENERIC_TOOL_PLACEHOLDER, (placeholder) => {
    const part = liveToolParts[liveToolIndex];
    if (!part) return placeholder;
    liveToolIndex += 1;

    return part.toolCallKey && toolDiffs.has(part.toolCallKey)
      ? injectToolCodeDiff(part.content, toolDiffs.get(part.toolCallKey))
      : part.content;
  });

  if (message?.parts_renderable !== true) return enrichedFallback;
  if (!Array.isArray(message.parts)) return enrichedFallback;

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

  if (!ordered.length) return enrichedFallback;

  const rendered = ordered
    .map((part: { content: string }) => part.content)
    .join("\n\n")
    .trim();

  return rendered || enrichedFallback;
}
