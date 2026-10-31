import { expect, test } from "bun:test";
import { recoverVisibleTurns } from "../src/ui/turnRecovery";
import type { LocalTurn } from "../src/ui/resultFormatting";

const original: LocalTurn = {
  reply_id: "",
  user_text: "First",
  assistant_text: "Original answer",
  status: "completed",
  created_at: 1,
  updated_at: 2,
};
const reply: LocalTurn = {
  reply_id: "reply-1",
  user_text: "Follow-up",
  assistant_text: "Second answer",
  status: "completed",
  created_at: 3,
  updated_at: 4,
};

test("an unavailable local turns endpoint keeps the last confirmed transcript", () => {
  expect(recoverVisibleTurns(null, [original, reply], original, true)).toEqual([original, reply]);
  expect(recoverVisibleTurns(null, [], original, true)).toEqual([original]);
  expect(recoverVisibleTurns(null, [original, reply], original, false)).toEqual([original]);
});

test("fresh confirmed turns replace stale local turns, including empty server records", () => {
  expect(recoverVisibleTurns([original, reply], [original], original, true)).toEqual([
    original,
    reply,
  ]);
  expect(recoverVisibleTurns([], [original, reply], original, true)).toEqual([original]);
});
test("a newer original detail repairs a stale original without dropping follow-ups", () => {
  const older = {
    ...original,
    status: "generating" as const,
    assistant_text: "Still writing",
    updated_at: 2,
  };
  const newer = { ...original, assistant_text: "Final answer from detail", updated_at: 8 };
  expect(recoverVisibleTurns(null, [older, reply], newer, true)).toEqual([newer, reply]);
  expect(recoverVisibleTurns(null, [newer, reply], older, true)).toEqual([newer, reply]);
});

test("partial fallback text cannot erase richer confirmed turns", () => {
  const previous = { ...original, assistant_text: "A longer confirmed answer", updated_at: 4 };
  const interrupted = {
    ...original,
    status: "interrupted" as const,
    assistant_text: "A",
    updated_at: 5,
  };
  expect(recoverVisibleTurns(null, [previous, reply], interrupted, true)).toEqual([
    previous,
    reply,
  ]);
  expect(
    recoverVisibleTurns(null, [{ ...previous, status: "generating" }, reply], interrupted, true),
  ).toEqual([{ ...interrupted, assistant_text: previous.assistant_text }, reply]);
  expect(
    recoverVisibleTurns(
      null,
      [original, reply],
      { ...original, status: "generating", updated_at: 7 },
      true,
    ),
  ).toEqual([original, reply]);
});
