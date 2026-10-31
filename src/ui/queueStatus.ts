export type WaitingJob = {
  name: string;
  position: number;
  reason: "global" | "stage";
  occupied: number;
  limit: number;
  eta_seconds: number;
};

export type QueueSnapshot = {
  max_workers: number | null;
  occupied_slots: number;
  estimated_run_seconds: number;
  estimate_samples: number;
  waiting: WaitingJob[];
};

export const emptyQueueSnapshot: QueueSnapshot = {
  max_workers: null,
  occupied_slots: 0,
  estimated_run_seconds: 600,
  estimate_samples: 0,
  waiting: [],
};

export function isQueueSnapshot(value: unknown): value is QueueSnapshot {
  if (!value || typeof value !== "object") return false;
  if (
    !("waiting" in value) ||
    !Array.isArray(value.waiting) ||
    !("occupied_slots" in value) ||
    typeof value.occupied_slots !== "number" ||
    !Number.isFinite(value.occupied_slots) ||
    !("max_workers" in value) ||
    (value.max_workers !== null && typeof value.max_workers !== "number") ||
    !("estimated_run_seconds" in value) ||
    typeof value.estimated_run_seconds !== "number" ||
    !("estimate_samples" in value) ||
    typeof value.estimate_samples !== "number"
  )
    return false;
  return value.waiting.every(
    (job: unknown) =>
      job !== null &&
      typeof job === "object" &&
      "name" in job &&
      typeof job.name === "string" &&
      "position" in job &&
      typeof job.position === "number" &&
      "reason" in job &&
      (job.reason === "global" || job.reason === "stage") &&
      "occupied" in job &&
      typeof job.occupied === "number" &&
      "limit" in job &&
      typeof job.limit === "number" &&
      "eta_seconds" in job &&
      typeof job.eta_seconds === "number",
  );
}

export function queueEtaText(waiting: WaitingJob): string {
  if (!Number.isFinite(waiting.eta_seconds) || waiting.eta_seconds < 0) return "ETA unavailable";
  const minutes = Math.max(1, Math.ceil(waiting.eta_seconds / 60));
  if (minutes < 60) return "ETA ~" + minutes + " min";
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return "ETA ~" + hours + "h" + (remainder ? " " + remainder + "m" : "");
}

export function queueEtaExplanation(snapshot: QueueSnapshot): string {
  return snapshot.estimate_samples >= 3
    ? "Approximate time to start, based on recent completed jobs. Rate limits and long-running jobs can shift it."
    : "Initial approximate time to start while recent job-duration data accumulates. Rate limits can shift it.";
}
