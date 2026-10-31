export type ResultStatus =
  | "queued"
  | "accepted"
  | "generating"
  | "completed"
  | "interrupted"
  | "unavailable";

export type ChatListStatus = ResultStatus | "needs_attention" | "";

export type RunSummary = {
  send_id: string;
  job_name: string;
  title: string;
  preview: string;
  status: ResultStatus;
  has_response: boolean;
  needs_attention?: boolean;
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
  conversation_id?: string;
  accepted_at: number;
  recovery?: {
    attempt_count: number;
    last_attempt_at: number;
    next_attempt_at: number;
    eligible: boolean;
  };
  images: { name: string; url: string }[];
};

export function recoveryProgress(recovery: RunDetail["recovery"], now: number): string | null {
  if (!recovery) return null;
  if (!recovery.eligible) return "No verified conversation ID for automatic recovery.";
  if (recovery.attempt_count === 0) return "Awaiting first read-only recovery check.";
  const attempts = recovery.attempt_count;
  const checked = `Read-only recovery checked ${attempts} ${attempts === 1 ? "time" : "times"}.`;
  if (recovery.next_attempt_at > now) {
    const minutes = Math.ceil((recovery.next_attempt_at - now) / 60);
    return `${checked} Next eligible check in about ${minutes} min; account pacing may delay it.`;
  }
  return `${checked} Awaiting next available recovery slot.`;
}

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
  queued_by_user?: boolean;
  created_at: number;
  updated_at: number;
};

export function responseBadge(status: LocalTurn["status"]): string {
  switch (status) {
    case "completed":
      return "Final";
    case "generating":
      return "Live";
    case "interrupted":
      return "Interrupted";
    case "unavailable":
      return "Unavailable";
    case "outcome_unknown":
      return "Uncertain";
    case "preflight_failed":
      return "Not sent";
    case "dispatching":
      return "Sending";
    case "accepted":
      return "Waiting";
    case "queued":
      return "Queued";
    case "prepared":
      return "Pending";
  }
}

export function exactConversationUrl(conversationId: string | undefined): string | null {
  return conversationId && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(conversationId)
    ? "https://chatgpt.com/c/" + conversationId
    : null;
}

export function partialResponseLabel(status: LocalTurn["status"]): string {
  switch (status) {
    case "generating":
      return "Live partial response · still generating";
    case "interrupted":
      return "Saved partial answer · capture interrupted; read-only recovery may complete it";
    case "unavailable":
      return "Saved partial answer · capture unavailable";
    case "outcome_unknown":
      return "Saved partial answer · send outcome uncertain; no automatic resend";
    default:
      return turnStatus(status);
  }
}

export function turnStatus(status: LocalTurn["status"]): string {
  switch (status) {
    case "prepared":
      return "Pending";
    case "preflight_failed":
      return "Not sent · preflight check failed. Tap Send to retry.";
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

// Use the same relative day labels as a chat transcript, in Auckland time.
export function chatMessageTime(epoch: number, nowEpoch = Date.now() / 1000): string {
  if (epoch <= 0) return "Time unavailable";
  const dayParts = (value: number) => {
    const parts = new Intl.DateTimeFormat("en-NZ", {
      timeZone: "Pacific/Auckland",
      year: "numeric",
      month: "numeric",
      day: "numeric",
    }).formatToParts(value * 1000);
    const read = (type: string) => Number(parts.find((part) => part.type === type)?.value);
    return Date.UTC(read("year"), read("month") - 1, read("day")) / 86_400_000;
  };
  const difference = dayParts(nowEpoch) - dayParts(epoch);
  let day: string;
  if (difference === 0) day = "Today";
  else if (difference === 1) day = "Yesterday";
  else day = dateGroup(epoch);
  const time = new Intl.DateTimeFormat("en-NZ", {
    timeZone: "Pacific/Auckland",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(epoch * 1000);
  return day + " " + time;
}

export type ResponseMetric = {
  value: string;
  label: string;
  tone: "neutral" | "success" | "error";
};

// Early DOM text captures flatten ChatGPT's compact numeric cards into six
// newline-separated values. Recognise only a complete three-metric paragraph.
export function legacyMetricSummary(text: string): ResponseMetric[] | null {
  const lines = text
    .trim()
    .split(/\r?\n/)
    .map((line) => line.trim());
  if (lines.length !== 6) return null;
  const metrics: ResponseMetric[] = [];
  for (let i = 0; i < 6; i += 2) {
    const value = lines[i];
    const label = lines[i + 1];
    if (!/^[+-]?[$£€]?\d[\d,.]*%?$/.test(value) || !/^[\p{L}][\p{L}\p{N} /&-]{0,30}$/u.test(label))
      return null;
    const lower = label.toLowerCase();
    let tone: ResponseMetric["tone"] = "neutral";
    if (/^(completed|passed|success(?:ful)?|healthy)$/.test(lower)) tone = "success";
    else if (/^(failed|interrupted|errors?)$/.test(lower)) tone = "error";
    metrics.push({ value, label, tone });
  }
  return metrics;
}

// Reconstruct lists only where legacy DOM text has several short, label/value
// lines. Do not guess at prose, code, genuine Markdown or SSE captures.
export function legacyLabelList(text: string, captureSource: string): string[] | null {
  if (captureSource !== "dom") return null;
  const lines = text
    .trim()
    .split(/\r?\n/)
    .map((line) => line.trim());
  if (lines.length < 4 || lines.length > 12 || lines.some((line) => !line || line.length > 110))
    return null;
  if (lines.filter((line) => /^[^:]{2,55}:\s+\S/.test(line)).length < lines.length * 0.6)
    return null;
  return lines;
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
