import { expect, test } from "bun:test";
import { sortJobs, type SortableJob } from "../src/ui/jobSorting";

function job(
  name: string,
  created_order: number,
  interval_minutes: number,
  daily_at: string | null = null,
  run_at_epoch: number | null = null,
): SortableJob {
  return { name, created_order, interval_minutes, daily_at, run_at_epoch };
}

test("sorts by highest recurrence frequency, then newest creation first", () => {
  const original = [
    job("daily-new", 9, 0, "09:00"),
    job("forty-new", 5, 40),
    job("one-off", 20, 0, null, 2000),
    job("forty-old", 2, 40),
    job("daily-old", 1, 0, "18:00"),
    job("hourly", 7, 60),
    job("one-off-old", 3, 0, null, 1000),
    job("fast", 4, 10),
  ];
  expect(sortJobs(original).map((item) => item.name)).toEqual([
    "fast",
    "forty-new",
    "forty-old",
    "hourly",
    "daily-new",
    "daily-old",
    "one-off",
    "one-off-old",
  ]);
  expect(original[0]?.name).toBe("daily-new");
});

test("uses name to break otherwise identical ties", () => {
  expect(sortJobs([job("z", 0, 40), job("a", 0, 40)]).map((item) => item.name)).toEqual(["a", "z"]);
});
