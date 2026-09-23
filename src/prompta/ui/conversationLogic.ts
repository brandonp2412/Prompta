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
  tolerance = 12,
) {
  return Math.hypot(currentX - startX, currentY - startY) > tolerance;
}
