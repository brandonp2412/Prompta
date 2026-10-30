import { expect, test } from "bun:test";
import { recoverVisibleTurns } from "../src/ui/turnRecovery";
import type { LocalTurn } from "../src/ui/resultFormatting";

const original: LocalTurn = {
  reply_id: "", user_text: "First", assistant_text: "Original answer",
  status: "completed", created_at: 1, updated_at: 2,
};
const reply: LocalTurn = {
  reply_id: "reply-1", user_text: "Follow-up", assistant_text: "Second answer",
  status: "completed", created_at: 3, updated_at: 4,
};

test("an unavailable local turns endpoint keeps the last confirmed transcript", () => {
  expect(recoverVisibleTurns(null, [original, reply], original, true)).toEqual([original, reply]);
  expect(recoverVisibleTurns(null, [], original, true)).toEqual([original]);
  expect(recoverVisibleTurns(null, [original, reply], original, false)).toEqual([original]);
});

test("fresh confirmed turns replace stale local turns, including empty server records", () => {
  expect(recoverVisibleTurns([original, reply], [original], original, true)).toEqual([original, reply]);
  expect(recoverVisibleTurns([], [original, reply], original, true)).toEqual([original]);
});
