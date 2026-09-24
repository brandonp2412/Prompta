export const MAX_ATTACHMENTS = 5;

export function attachmentMenuTargetIndex(key: string, currentIndex: number, itemCount: number) {
  if (itemCount <= 0) return null;

  if (key === "Home") return 0;
  if (key === "End") return itemCount - 1;
  if (key === "ArrowDown") return currentIndex < 0 ? 0 : (currentIndex + 1) % itemCount;
  if (key === "ArrowUp") {
    return currentIndex < 0 ? itemCount - 1 : (currentIndex - 1 + itemCount) % itemCount;
  }

  return null;
}

type AttachmentIdentity = {
  name: string;
  size: number;
  lastModified: number;
};

function sameAttachment(left: AttachmentIdentity, right: AttachmentIdentity) {
  return (
    left.name === right.name && left.size === right.size && left.lastModified === right.lastModified
  );
}

export function mergeAttachments<T extends AttachmentIdentity>(
  current: readonly T[],
  incoming: readonly T[],
  max = MAX_ATTACHMENTS,
) {
  const files = [...current];
  let omitted = 0;

  for (const file of incoming) {
    if (files.some((item) => sameAttachment(item, file))) continue;

    if (files.length >= max) {
      omitted += 1;
      continue;
    }

    files.push(file);
  }

  return { files, omitted };
}
