export interface ChatProgress {
  phase: string;
  last_activity_at?: number;
  retry_at?: number;
  queue_position?: number;
}

export function chatProgressLabel(progress: ChatProgress, now = Date.now() / 1000): string {
  const labels: Record<string, string> = {
    queued: "Queued",
    running: "Sending to ChatGPT",
    confirmed: "Confirmed received · waiting for response",
    succeeded: "Confirmed received · waiting for response",
    responding: "Responding",
    recovering: "Recovering connection",
    retrying: "Waiting to retry delivery",
    rate_limited: "Waiting for account cooldown",
    complete: "Complete",
    completed: "Complete",
    interrupted: "Interrupted",
    failed: "Delivery failed",
    dead_lettered: "Delivery needs attention",
  };
  let label = labels[progress.phase] || "Waiting for status";
  if (progress.phase === "queued" && Number(progress.queue_position) > 0) {
    label += ` · #${progress.queue_position}`;
  }
  if (["retrying", "rate_limited"].includes(progress.phase) && Number(progress.retry_at) > 0) {
    const seconds = Math.max(0, Number(progress.retry_at) - now);
    label += seconds > 0 ? ` · next retry in ${Math.ceil(seconds / 60)}m` : " · retry due";
  }
  return label;
}
