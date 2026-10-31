import { expect, test } from "bun:test";
import {
  formatDate,
  jobFilter,
  jobStateText,
  sameJob,
  scheduleText,
  type Job,
} from "../src/ui/jobView";

const job: Job = {
  images: [],
  name: "daily check",
  created_order: 2,
  prompt: "Check",
  status: "healthy",
  status_message: "",
  paused: false,
  run_at_epoch: null,
  pin_chat: false,
  daily_at: null,
  interval_minutes: 60,
  exact_interval: false,
  source_revision: "rev1",
  next_due_at_epoch: 123,
  last_sent_at: 100,
  last_uncertain_send_at: 0,
};

test("schedule descriptions keep their time units and mode", () => {
  expect(formatDate(0)).toBe("—");
  expect(scheduleText(job)).toBe("every 1 hour");
  expect(scheduleText({ ...job, interval_minutes: 120, exact_interval: true })).toBe(
    "every 2 hours · exact",
  );
  expect(scheduleText({ ...job, interval_minutes: 1 })).toBe("every 1 minute");
  expect(scheduleText({ ...job, interval_minutes: 31 })).toBe("every 31 minutes");
  expect(scheduleText({ ...job, daily_at: "08:15" })).toBe("daily · 08:15");
  expect(scheduleText({ ...job, run_at_epoch: 100 })).toStartWith("once · ");
});

test("filter and status labels retain uncertain-send semantics", () => {
  expect(jobFilter(job)).toBe("healthy");
  expect(jobFilter({ ...job, paused: true })).toBe("paused");
  expect(jobFilter({ ...job, last_uncertain_send_at: 101 })).toBe("unhealthy");
  expect(jobFilter({ ...job, status: "rate-limited" })).toBe("unhealthy");
  expect(jobFilter({ ...job, status: "queued" })).toBe("pending");
  expect(jobStateText({ ...job, paused: true })).toBe("paused");
  expect(jobStateText({ ...job, last_uncertain_send_at: 101 })).toBe("unconfirmed");
  expect(
    jobStateText({
      ...job,
      status: "failing",
      status_message: "Lost send confirmation after dispatch",
    }),
  ).toBe("unconfirmed");
});

test("job refresh equality detects changes to every rendered or operational field", () => {
  expect(sameJob(job, { ...job })).toBe(true);
  const changes: Partial<Job>[] = [
    { name: "other" },
    { created_order: 3 },
    { prompt: "Other" },
    { images: [{ ref: "image-ref", name: "image.png", url: "local" }] },
    { status: "queued" },
    { status_message: "error" },
    { paused: true },
    { run_at_epoch: 99 },
    { pin_chat: true },
    { daily_at: "09:00" },
    { interval_minutes: 30 },
    { exact_interval: true },
    { source_revision: "rev2" },
    { next_due_at_epoch: 200 },
    { last_sent_at: 200 },
    { last_uncertain_send_at: 200 },
  ];
  for (const changed of changes) {
    expect(sameJob(job, { ...job, ...changed })).toBe(false);
  }
});
