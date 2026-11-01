import { expect, test } from "bun:test";
import {
  queuedChatEtaText,
  queueEtaText,
  type QueueSnapshot,
  type WaitingJob,
} from "../src/ui/queueStatus";

const waiting: WaitingJob = {
  name: "Prompta",
  position: 2,
  reason: "global",
  occupied: 1,
  limit: 1,
  eta_seconds: 120,
};

test("queue waits show readable minutes and hours", () => {
  expect(queueEtaText(waiting)).toBe("ETA ~2 min");
  expect(queueEtaText({ ...waiting, eta_seconds: 0 })).toBe("ETA ~1 min");
  expect(queueEtaText({ ...waiting, eta_seconds: 3720 })).toBe("ETA ~1h 2m");
});

test("queued chat subtitle shows its own ETA, not another chat's", () => {
  const snapshot: QueueSnapshot = {
    max_workers: 1,
    occupied_slots: 1,
    estimated_run_seconds: 120,
    estimate_samples: 4,
    waiting: [],
    waiting_runs: [
      { send_id: "manual-first", eta_seconds: 60 },
      { send_id: "manual-second", eta_seconds: 240 },
    ],
  };
  expect(queuedChatEtaText("manual-second", snapshot)).toBe("Queued · ETA ~4 min");
  expect(queuedChatEtaText("not-in-queue", snapshot)).toBe("Queued · ETA unavailable");
});

test("invalid queue estimates never render NaN or Infinity", () => {
  for (const eta_seconds of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -20]) {
    expect(queueEtaText({ ...waiting, eta_seconds })).toBe("ETA unavailable");
  }
});
