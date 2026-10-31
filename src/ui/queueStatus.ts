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

export function queueEtaText(waiting: WaitingJob): string {
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
