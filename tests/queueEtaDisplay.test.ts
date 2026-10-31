import { expect, test } from "bun:test";
import { queueEtaText, type WaitingJob } from "../src/ui/queueStatus";

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

test("invalid queue estimates never render NaN or Infinity", () => {
  for (const eta_seconds of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -20]) {
    expect(queueEtaText({ ...waiting, eta_seconds })).toBe("ETA unavailable");
  }
});
