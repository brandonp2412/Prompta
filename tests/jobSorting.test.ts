import { expect, test } from "bun:test";
import { isRepeatingJob, sortJobs, type SortableJob } from "../src/ui/jobSorting";

function job(
  name: string,
  created_order: number,
  next_due_at_epoch: number,
  schedule: Partial<Omit<SortableJob, "name" | "created_order" | "next_due_at_epoch">> = {},
): SortableJob {
  return {
    name,
    created_order,
    next_due_at_epoch,
    paused: false,
    interval_minutes: 40,
    daily_at: null,
    run_at_epoch: null,
    ...schedule,
  };
}

test("sorts by next actual run across one-off, daily and interval jobs", () => {
  const original = [
    job("daily-later", 9, 5000, { daily_at: "09:00", interval_minutes: 0 }),
    job("forty-new", 5, 2000),
    job("one-off-soonest", 20, 900, { interval_minutes: 0, run_at_epoch: 900 }),
    job("forty-old", 2, 2000),
    job("daily-earlier", 1, 1500, { daily_at: "18:00", interval_minutes: 0 }),
    job("hourly", 7, 3000, { interval_minutes: 60 }),
    job("overdue", 3, 700, { interval_minutes: 10 }),
    job("fast-but-later", 4, 4000, { interval_minutes: 1 }),
  ];
  expect(sortJobs(original).map((item) => item.name)).toEqual([
    "overdue",
    "one-off-soonest",
    "daily-earlier",
    "forty-new",
    "forty-old",
    "hourly",
    "fast-but-later",
    "daily-later",
  ]);
  expect(original[0]?.name).toBe("daily-later");
});

test("repeating jobs include daily and interval schedules, but exclude one-offs", () => {
  expect(isRepeatingJob(job("daily", 1, 2000, { daily_at: "09:00", interval_minutes: 0 }))).toBe(
    true,
  );
  expect(isRepeatingJob(job("every-ten-minutes", 2, 2000, { interval_minutes: 10 }))).toBe(true);
  expect(isRepeatingJob(job("every-day", 3, 2000, { interval_minutes: 1440 }))).toBe(true);
  expect(isRepeatingJob(job("every-week", 4, 2000, { interval_minutes: 7 * 1440 }))).toBe(true);
  expect(isRepeatingJob(job("once", 5, 2000, { run_at_epoch: 2000, interval_minutes: 0 }))).toBe(
    false,
  );
  expect(isRepeatingJob(job("no-schedule", 6, 0, { interval_minutes: 0 }))).toBe(false);
});

test("uses name to break otherwise identical ties", () => {
  expect(sortJobs([job("z", 0, 2000), job("a", 0, 2000)]).map((item) => item.name)).toEqual([
    "a",
    "z",
  ]);
});

test("puts paused and unscheduled jobs after runnable jobs", () => {
  expect(
    sortJobs([
      job("paused", 4, 100, { paused: true }),
      job("missing-due", 3, 0),
      job("future", 2, 3000),
      job("invalid-due", 1, Number.NaN),
      job("sooner", 0, 2000),
    ]).map((item) => item.name),
  ).toEqual(["sooner", "future", "paused", "missing-due", "invalid-due"]);
});
