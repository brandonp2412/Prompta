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
  created_at: number;
  updated_at: number;
  finished_at: number;
};

export type RunDetail = RunSummary & {
  user_text: string;
  assistant_text: string;
  source: string;
  accepted_at: number;
  images: { name: string; url: string }[];
};

export type LocalTurn = {
  reply_id: string;
  user_text: string;
  assistant_text: string;
  status: ResultStatus | "prepared" | "dispatching" | "outcome_unknown";
  created_at: number;
  updated_at: number;
};

export function turnStatus(status: LocalTurn["status"]): string {
  switch (status) {
    case "prepared":
      return "Reply saved locally · not sent";
    case "dispatching":
      return "Sending · confirmation pending";
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
