import { expect, test } from "bun:test";
import { nextResultPageOffset, reconcileResultPage } from "../src/ui/resultListRefresh";
import type { RunSummary } from "../src/ui/resultFormatting";

function item(
  send_id: string,
  status: RunSummary["status"],
  created_at: number,
  updated_at = created_at,
): RunSummary {
  return {
    send_id,
    status,
    created_at,
    updated_at,
    job_name: "",
    title: send_id,
    preview: "",
    has_response: false,
    last_reply_revision: "",
    last_read_revision: "",
    last_reply_at: 0,
    finished_at: 0,
  };
}

test("an authoritative first page removes entries no longer in the result", () => {
  const prior = [item("queued-one", "queued", 1), item("queued-two", "queued", 2)];
  expect(reconcileResultPage(prior, [], 0, 20, "queued")).toEqual([]);
  expect(
    reconcileResultPage(prior, [item("queued-two", "queued", 2)], 1, 20, "queued").map(
      (row) => row.send_id,
    ),
  ).toEqual(["queued-two"]);
});

test("refreshing a filtered long list drops transitioned runs but retains older matching pages", () => {
  const prior = [
    item("old-queued", "queued", 1),
    item("now-completed", "completed", 2),
    item("recent-queued", "queued", 3),
  ];
  const next = reconcileResultPage(prior, [item("recent-queued", "queued", 3, 10)], 3, 1, "queued");
  expect(next.map((row) => row.send_id)).toEqual(["recent-queued", "old-queued"]);
  expect(next[0]?.updated_at).toBe(10);
});

test("attention refresh retains only older chats that still need recovery", () => {
  const unresolved = { ...item("uncertain-reply", "completed", 1), needs_attention: true };
  const repaired = { ...item("repaired", "completed", 2), needs_attention: false };
  const current = { ...item("recent", "interrupted", 3, 8), needs_attention: true };
  const next = reconcileResultPage([unresolved, repaired, current], [current], 3, 1, "needs_attention");
  expect(next.map((row) => row.send_id)).toEqual(["recent", "uncertain-reply"]);
});

test("a new first page updates rows without duplicates and respects the server total", () => {
  const prior = [item("older", "completed", 1), item("same", "generating", 2)];
  const next = reconcileResultPage(
    prior,
    [item("newer", "completed", 3), item("same", "completed", 2, 4)],
    2,
    2,
    "",
  );
  expect(next.map((row) => row.send_id)).toEqual(["same", "newer"]);
  expect(next.find((row) => row.send_id === "same")?.status).toBe("completed");
});

test("stalled pagination halts automatic refetch until an explicit retry", () => {
  expect(nextResultPageOffset(20, 0, 45)).toBeNull();
  expect(nextResultPageOffset(20, 20, 45)).toBe(40);
  expect(nextResultPageOffset(40, 10, 45)).toBe(45);
  expect(nextResultPageOffset(45, 0, 45)).toBe(45);
  expect(nextResultPageOffset(20, 0, 18)).toBe(18);
});
