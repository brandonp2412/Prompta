export const MAX_ATTACHMENTS = 5;

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
