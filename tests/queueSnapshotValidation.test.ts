import { expect, test } from "bun:test";
import { isQueueSnapshot, queueEtaText } from "../src/ui/queueStatus";

const valid = () => ({
  max_workers: 3,
  occupied_slots: 2,
  estimated_run_seconds: 180,
  estimate_samples: 4,
  waiting: [
    {
      name: "scheduled-job",
      one_time: true,
      position: 1,
      reason: "global",
      occupied: 2,
      limit: 3,
      eta_seconds: 180,
    },
  ],
});

test("only finite, coherent queue counts and estimates reach the UI", () => {
  expect(isQueueSnapshot(valid())).toBe(true);
  expect(isQueueSnapshot({ ...valid(), max_workers: null })).toBe(true);
  for (const [key, value] of [
    ["max_workers", 0],
    ["max_workers", 1.5],
    ["occupied_slots", -1],
    ["occupied_slots", Infinity],
    ["estimated_run_seconds", NaN],
    ["estimated_run_seconds", -3],
    ["estimate_samples", 0.5],
  ] as const) {
    expect(isQueueSnapshot({ ...valid(), [key]: value })).toBe(false);
  }
});

test("queued chat estimates require a valid send ID and finite ETA", () => {
  expect(
    isQueueSnapshot({ ...valid(), waiting_runs: [{ send_id: "manual-chat", eta_seconds: 75 }] }),
  ).toBe(true);
  for (const waiting_runs of [
    [{ send_id: "", eta_seconds: 60 }],
    [{ send_id: "manual-chat", eta_seconds: -1 }],
    [{ send_id: "manual-chat", eta_seconds: Infinity }],
    [{ send_id: "manual-chat", eta_seconds: NaN }],
    [{ eta_seconds: 60 }],
  ]) {
    expect(isQueueSnapshot({ ...valid(), waiting_runs })).toBe(false);
  }
});

test("malformed waiting rows cannot produce nonsensical positions or ETAs", () => {
  for (const row of [
    { position: -1 },
    { position: 2.5 },
    { position: Number.MAX_SAFE_INTEGER + 1 },
    { occupied: -2 },
    { occupied: Infinity },
    { limit: 0 },
    { eta_seconds: -1 },
    { eta_seconds: Infinity },
    { eta_seconds: NaN },
    { name: "" },
    { one_time: "yes" },
  ]) {
    const original = valid();
    expect(
      isQueueSnapshot({
        ...original,
        waiting: [{ ...original.waiting[0], ...row }],
      }),
    ).toBe(false);
  }
  expect(queueEtaText(valid().waiting[0])).toBe("ETA ~3 min");
});
