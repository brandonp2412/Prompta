export type ResultStatus =
  | "queued"
  | "accepted"
  | "generating"
  | "completed"
  | "interrupted"
  | "unavailable";

export type RunSummary = {
  send_id: string;
  job_name: string;
  title: string;
  preview: string;
  status: ResultStatus;
  has_response: boolean;
  last_reply_revision: string;
  last_read_revision: string;
  last_reply_at: number;
  created_at: number;
  updated_at: number;
  finished_at: number;
};

export type RunDetail = RunSummary & {
  user_text: string;
  assistant_text: string;
  tool_calls?: CapturedToolCall[];
  source: string;
  accepted_at: number;
  images: { name: string; url: string }[];
};

export type CapturedToolCall = {
  id: string;
  connector: string;
  action: string;
  status: string;
  arguments: string;
  result: string;
  error: string;
};

export type LocalTurn = {
  reply_id: string;
  conversation_id?: string;
  parent_id?: string;
  message_id?: string;
  user_text: string;
  assistant_text: string;
  tool_calls?: CapturedToolCall[];
  status: ResultStatus | "prepared" | "preflight_failed" | "dispatching" | "outcome_unknown";
  created_at: number;
  updated_at: number;
};

export function turnStatus(status: LocalTurn["status"]): string {
  switch (status) {
    case "prepared":
      return "Pending";
    case "preflight_failed":
      return "Not sent · browser verification failed. Tap Send to retry.";
    case "dispatching":
      return "Sending…";
    case "outcome_unknown":
      return "Send outcome unknown · no automatic retry";
    case "accepted":
      return "Awaiting captured response";
    case "generating":
      return "Response is generating";
    case "interrupted":
      return "Response capture interrupted";
    case "unavailable":
      return "Response unavailable";
    case "queued":
      return "Waiting for job dispatch";
    case "completed":
      return "Completed";
  }
}

const dateOptions: Intl.DateTimeFormatOptions = {
  timeZone: "Pacific/Auckland",
  day: "numeric",
  month: "short",
  year: "numeric",
};

export function dateGroup(epoch: number): string {
  return new Intl.DateTimeFormat("en-NZ", dateOptions).format(epoch * 1000);
}

export function nzTime(epoch: number): string {
  if (epoch <= 0) return "Time unavailable";
  return new Intl.DateTimeFormat("en-NZ", {
    ...dateOptions,
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(epoch * 1000);
}

export function statusLabel(status: ResultStatus): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "accepted":
      return "Accepted";
    case "generating":
      return "Generating";
    case "completed":
      return "Completed";
    case "interrupted":
      return "Interrupted";
    case "unavailable":
      return "Unavailable";
  }
}

export function safeHref(href: string): string | null {
  try {
    const url = new URL(href);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

export function plainPreview(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/```[^\n]*\n?/g, " ")
    .replace(/^[#>]+\s*/gm, "")
    .replace(/\*\*|__|~~|[`*_]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

// Early DOM captures stored ChatGPT's rendered table innerText rather than
// Markdown. Tabs still delimit cells, and 3+ newlines still delimit rows.
// Repair the presentation only: retain raw text for reply-parent verification.
type LegacyTableRow = { cells: string[]; before: string; after: string };

function legacyTableRow(chunk: string): LegacyTableRow | null {
  if (!/\n[ \r\n]*\t[ \r\n]*\n/.test(chunk)) return null;
  const raw = chunk.split(/\n[ \r\n]*\t[ \r\n]*\n/);
  if (raw.length < 2 || raw.length > 6) return null;
  const before = raw[0].split(/\n[ \t]*\n/);
  const last = raw.length - 1;
  const after = raw[last].split(/\n[ \t]*\n/);
  raw[0] = before.at(-1) ?? "";
  raw[last] = after[0];
  const cells = raw.map((cell) => cell.trim());
  if (cells.some((cell) => !cell || cell.includes("\n"))) return null;
  return {
    cells,
    before: before.slice(0, -1).join("\n\n"),
    after: after.slice(1).join("\n\n"),
  };
}

export function formatStoredResponse(text: string, captureSource: string): string {
  if (captureSource === "sse" || !text.includes("\t")) return text;
  const parts = text.split(/(\n{3,})/);
  let output = "";
  for (let i = 0; i < parts.length;) {
    const first = legacyTableRow(parts[i]);
    if (!first) {
      output += parts[i] + (parts[i + 1] ?? "");
      i += 2;
      continue;
    }

    const rows = [first];
    let end = i + 2;
    while (end < parts.length) {
      const next = legacyTableRow(parts[end]);
      if (!next || next.cells.length !== first.cells.length || next.before) break;
      rows.push(next);
      end += 2;
    }
    // Leave an isolated tabbed line or an ambiguous block untouched.
    if (rows.length < 2 || rows.slice(0, -1).some((row) => row.after)) {
      output += parts[i] + (parts[i + 1] ?? "");
      i += 2;
      continue;
    }
    const row = (cells: string[]) =>
      "| " + cells.map((cell) => cell.replace(/\|/g, "\\|")).join(" | ") + " |";
    const table = [
      row(first.cells),
      row(first.cells.map(() => "---")),
      ...rows.slice(1).map((item) => row(item.cells)),
    ].join("\n");
    output +=
      (first.before ? first.before.trimEnd() + "\n\n" : "") +
      table +
      (rows.at(-1)?.after ? "\n\n" + rows.at(-1)?.after.trimStart() : "") +
      (parts[end - 1] ?? "");
    i = end;
  }
  return output;
}

// Older DOM captures contain plain innerText with every heading, list item and
// table cell separated as a paragraph. Keep those archived answers compact;
// new semantic captures and genuine Markdown retain normal formatting.
export function isFlattenedDomResponse(text: string, captureSource: string): boolean {
  if (captureSource !== "dom") return false;
  if (/^\s*(?:#{1,6}\s|[-*+]\s|\d+\.\s|>|\|\s|`{3})/m.test(text)) return false;
  const blocks = text
    .split(/\n\s*\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  if (blocks.length < 10) return false;
  const shortLabels = blocks.filter(
    (item) => item.length <= 80 && !/[.!?:]$/.test(item) && !item.includes("\n"),
  );
  return shortLabels.length >= 7 && shortLabels.length >= blocks.length * 0.45;
}

export function groupRuns(items: RunSummary[]): { date: string; items: RunSummary[] }[] {
  const groups: { date: string; items: RunSummary[] }[] = [];
  for (const item of items) {
    const date = dateGroup(item.updated_at || item.created_at);
    const last = groups[groups.length - 1];
    if (last?.date === date) last.items.push(item);
    else groups.push({ date, items: [item] });
  }
  return groups;
}
