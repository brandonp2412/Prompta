export type ImageRef = { ref: string; name: string; url: string };

export type Job = {
  images: ImageRef[];
  name: string;
  created_order: number;
  prompt: string;
  status: string;
  status_message: string;
  paused: boolean;
  run_at_epoch: number | null;
  pin_chat: boolean;
  daily_at: string | null;
  interval_minutes: number;
  exact_interval: boolean;
  source_revision: string;
  next_due_at_epoch: number;
  last_sent_at: number;
  last_uncertain_send_at: number;
};

export type JobFilter = "pending" | "healthy" | "paused" | "unhealthy";

export function formatDate(epoch: number) {
  if (!epoch) return "—";
  return new Date(epoch * 1000).toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function scheduleText(job: Job) {
  if (job.run_at_epoch) return "once · " + formatDate(job.run_at_epoch);
  if (job.daily_at) return "daily · " + job.daily_at;

  const minutes = Number(job.interval_minutes);
  const amount =
    minutes >= 60 && minutes % 60 === 0
      ? String(minutes / 60) + " hour" + (minutes === 60 ? "" : "s")
      : String(minutes) + " minute" + (minutes === 1 ? "" : "s");
  return "every " + amount + (job.exact_interval ? " · exact" : "");
}

export function jobFilter(job: Job): JobFilter {
  if (job.paused) return "paused";
  if (
    job.last_uncertain_send_at > job.last_sent_at ||
    job.status === "failing" ||
    job.status === "rate-limited"
  )
    return "unhealthy";
  if (job.status === "healthy") return "healthy";
  return "pending";
}

export function jobStateText(job: Job) {
  if (job.paused) return "paused";
  if (
    job.last_uncertain_send_at > job.last_sent_at ||
    (job.status === "failing" && /lost send confirmation after dispatch/i.test(job.status_message))
  )
    return "unconfirmed";
  return job.status || "pending";
}

export function sameJob(left: Job, right: Job) {
  return (
    left.name === right.name &&
    left.created_order === right.created_order &&
    left.prompt === right.prompt &&
    JSON.stringify(left.images) === JSON.stringify(right.images) &&
    left.status === right.status &&
    left.status_message === right.status_message &&
    left.paused === right.paused &&
    left.run_at_epoch === right.run_at_epoch &&
    left.pin_chat === right.pin_chat &&
    left.daily_at === right.daily_at &&
    left.interval_minutes === right.interval_minutes &&
    left.exact_interval === right.exact_interval &&
    left.source_revision === right.source_revision &&
    left.next_due_at_epoch === right.next_due_at_epoch &&
    left.last_sent_at === right.last_sent_at &&
    left.last_uncertain_send_at === right.last_uncertain_send_at
  );
}
