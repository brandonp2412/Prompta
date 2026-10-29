export type SortableJob = {
  name: string;
  created_order: number;
  interval_minutes: number;
  daily_at: string | null;
  run_at_epoch: number | null;
  next_due_at_epoch: number;
  paused: boolean;
};

export function isRepeatingJob(job: SortableJob): boolean {
  return job.run_at_epoch === null && (job.daily_at !== null || job.interval_minutes > 0);
}

function nextRunEpoch(job: SortableJob): number {
  const nextDue = job.next_due_at_epoch;
  return !job.paused && Number.isFinite(nextDue) && nextDue > 0
    ? nextDue
    : Number.POSITIVE_INFINITY;
}

function compareJobs(left: SortableJob, right: SortableJob): number {
  const leftNextRun = nextRunEpoch(left);
  const rightNextRun = nextRunEpoch(right);
  if (leftNextRun !== rightNextRun) return leftNextRun < rightNextRun ? -1 : 1;
  return right.created_order - left.created_order || left.name.localeCompare(right.name);
}

export function sortJobs<T extends SortableJob>(jobs: T[]): T[] {
  return [...jobs].sort(compareJobs);
}
