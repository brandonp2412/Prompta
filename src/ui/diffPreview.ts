export const TOOL_CODE_DIFF_FIELD = "__prompta_code_diff";

export type ToolCodeDiff = {
  patchText: string;
  changedFileCount: number;
  additions: number;
  deletions: number;
  truncated: boolean;
};

export type UnifiedDiffHunk = {
  header: string;
  body: string;
};

export type UnifiedDiffFile = {
  path: string;
  metadata: string;
  hunks: UnifiedDiffHunk[];
};

export type UnifiedDiffPresentation = {
  files: UnifiedDiffFile[];
  highlight: boolean;
};

const DIFF_HIGHLIGHT_MAX_CHARS = 24 * 1024;

function nonNegativeInteger(value: unknown) {
  const number = Number(value);

  return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0;
}

export function normalizeToolCodeDiff(value: unknown): ToolCodeDiff | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;

  const raw = value as Record<string, unknown>;
  const patchValue = raw.patch_text ?? raw.patchText;
  const diff = {
    patchText: typeof patchValue === "string" ? patchValue : "",
    changedFileCount: nonNegativeInteger(raw.changed_file_count ?? raw.changedFileCount),
    additions: nonNegativeInteger(raw.additions),
    deletions: nonNegativeInteger(raw.deletions),
    truncated: Boolean(raw.truncated),
  };

  if (
    !diff.patchText &&
    !diff.changedFileCount &&
    !diff.additions &&
    !diff.deletions &&
    !diff.truncated
  ) {
    return null;
  }

  return diff;
}

export function toolCodeDiffSummary(diff: ToolCodeDiff) {
  const noun = diff.changedFileCount === 1 ? "file" : "files";
  return (
    String(diff.changedFileCount) + " " + noun + " · +" + diff.additions + " −" + diff.deletions
  );
}

function toolFenceParts(content: string) {
  const firstNewline = content.indexOf("\n");
  if (firstNewline < 0) return null;

  const opening = content.slice(0, firstNewline);
  const fence = opening.match(
    /^ {0,3}(\x60{3}|~~~)(?:tool|tool-call|function|function-call)(?::.*)?$/i,
  )?.[1];
  if (!fence) return null;

  const closing = "\n" + fence;
  const closingAt = content.lastIndexOf(closing);
  if (closingAt <= firstNewline) return null;

  return {
    opening,
    body: content.slice(firstNewline + 1, closingAt),
    closing: content.slice(closingAt),
  };
}

export function injectToolCodeDiff(content: string, value: unknown) {
  const diff = normalizeToolCodeDiff(value);
  if (!diff) return content;

  const parts = toolFenceParts(content);
  if (!parts) return content;

  try {
    const parsed = JSON.parse(parts.body);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return content;

    return [
      parts.opening,
      JSON.stringify({ ...parsed, [TOOL_CODE_DIFF_FIELD]: diff }, null, 2),
      parts.closing.slice(1),
    ].join("\n");
  } catch {
    return content;
  }
}

export function extractToolCodeDiff(code: string) {
  if (!code.includes(TOOL_CODE_DIFF_FIELD)) {
    return { code, diff: null as ToolCodeDiff | null };
  }

  try {
    const parsed = JSON.parse(code);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { code, diff: null as ToolCodeDiff | null };
    }

    const payload = parsed as Record<string, unknown>;
    const diff = normalizeToolCodeDiff(payload[TOOL_CODE_DIFF_FIELD]);
    if (!diff) return { code, diff: null as ToolCodeDiff | null };

    const visible = { ...payload };
    delete visible[TOOL_CODE_DIFF_FIELD];

    return {
      code: Object.keys(visible).length ? JSON.stringify(visible, null, 2) : "",
      diff,
    };
  } catch {
    return { code, diff: null as ToolCodeDiff | null };
  }
}

function diffFilePath(line: string) {
  const quoted = line.match(/^diff --git "(?:a\/)?(.+)" "(?:b\/)?(.+)"$/);
  if (quoted) return quoted[2];

  const marker = line.lastIndexOf(" b/");
  if (marker >= 0) return line.slice(marker + 3).trim();

  return line.slice("diff --git ".length).trim();
}

export function unifiedDiffPresentation(diff: ToolCodeDiff): UnifiedDiffPresentation {
  const files: UnifiedDiffFile[] = [];
  let file: {
    path: string;
    metadata: string[];
    hunks: Array<{ header: string; lines: string[] }>;
  } | null = null;
  let hunk: { header: string; lines: string[] } | null = null;

  const flushFile = () => {
    if (!file) return;

    files.push({
      path: file.path || "Patch",
      metadata: file.metadata.join("\n"),
      hunks: file.hunks.map((entry) => ({
        header: entry.header,
        body: entry.lines.join("\n"),
      })),
    });
  };

  for (const line of diff.patchText.split("\n")) {
    if (line.startsWith("diff --git ")) {
      flushFile();
      file = { path: diffFilePath(line), metadata: [], hunks: [] };
      hunk = null;
      continue;
    }

    if (!file) {
      file = { path: "Patch", metadata: [], hunks: [] };
    }

    if (line.startsWith("@@")) {
      hunk = { header: line, lines: [] };
      file.hunks.push(hunk);
      continue;
    }

    if (hunk) hunk.lines.push(line);
    else file.metadata.push(line);
  }

  flushFile();

  return {
    files: files.filter(
      (entry) =>
        entry.metadata || entry.hunks.some((entryHunk) => entryHunk.header || entryHunk.body),
    ),
    highlight: diff.patchText.length <= DIFF_HIGHLIGHT_MAX_CHARS,
  };
}
