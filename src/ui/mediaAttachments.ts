export const attachmentAccept =
  "image/png,image/jpeg,image/gif,image/webp,video/mp4,video/quicktime,video/webm";

const types: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  mp4: "video/mp4",
  mov: "video/quicktime",
  webm: "video/webm",
};

export function isVideoAttachment(name: string): boolean {
  return /\.(mp4|mov|webm)$/i.test(name);
}

export function attachmentSelectionError(files: File[], count: number, context: string): string {
  if (count + files.length > 4) return "At most four attachments per " + context + ".";
  for (const file of files) {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    const expected = types[extension];
    if (!expected || (file.type && file.type !== expected))
      return "Supported files: PNG, JPEG, GIF, WebP, MP4, MOV and WebM.";
    if (file.size === 0) return "Attachments must not be empty.";
    if (file.size > (isVideoAttachment(file.name) ? 50 : 8) * 1024 * 1024)
      return isVideoAttachment(file.name)
        ? "Videos must be 50 MiB or smaller."
        : "Images must be 8 MiB or smaller.";
  }
  return "";
}
