export type SortableJob = {
  name: string;
  created_order: number;
  interval_minutes: number;
  daily_at: string | null;
  run_at_epoch: number | null;
};

function frequencyMinutes(job: SortableJob): number {
  if (job.run_at_epoch) return Number.POSITIVE_INFINITY;
  if (job.daily_at) return 24 * 60;
  return job.interval_minutes;
}

function compareJobs(left: SortableJob, right: SortableJob): number {
  const leftFrequency = frequencyMinutes(left);
  const rightFrequency = frequencyMinutes(right);
  if (leftFrequency !== rightFrequency) return leftFrequency < rightFrequency ? -1 : 1;
  return right.created_order - left.created_order || left.name.localeCompare(right.name);
}

export function sortJobs<T extends SortableJob>(jobs: T[]): T[] {
  return [...jobs].sort(compareJobs);
}
