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

test("fresh confirmed turns extend local turns without dropping known replies", () => {
  expect(recoverVisibleTurns([original, reply], [original], original, true)).toEqual([
    original,
    reply,
  ]);
  expect(recoverVisibleTurns([], [original, reply], original, true)).toEqual([original, reply]);
});
test("a delayed shorter turns snapshot cannot erase a completed reply or text", () => {
  const newer = { ...reply, assistant_text: "Completed answer with details", updated_at: 40 };
  const stale = { ...reply, status: "generating" as const, assistant_text: "Completed", updated_at: 4 };
  expect(recoverVisibleTurns([original, stale], [original, newer], original, true)).toEqual([original, newer]);
  expect(recoverVisibleTurns([original], [original, newer], original, true)).toEqual([original, newer]);
});
test("a newer shorter live frame preserves rich text and verified completion", () => {
  const previous = { ...reply, assistant_text: "Long verified answer", updated_at: 10 };
  const incoming = { ...reply, assistant_text: "Short", status: "interrupted" as const, updated_at: 11 };
  expect(recoverVisibleTurns([original, incoming], [original, previous], original, true)).toEqual([
    original, { ...incoming, assistant_text: previous.assistant_text, status: "completed" },
  ]);
});
test("new replies append, but different verified identities never merge", () => {
  const first = { ...reply, message_id: "verified-A" };
  const conflicting = { ...reply, message_id: "verified-B", updated_at: 100 };
  const extra = { ...reply, reply_id: "reply-2", created_at: 5, updated_at: 6 };
  expect(recoverVisibleTurns([original, conflicting, extra], [original, first], original, true))
    .toEqual([original, first, extra]);
});
test("a delayed tool-empty snapshot keeps previously captured tool summaries", () => {
  const captured = {
    id: "tool-1", connector: "connector", action: "lookup", status: "completed",
    arguments: "", result: "bounded summary", error: "",
  };
  const previous = { ...reply, tool_calls: [captured], updated_at: 6 };
  const incoming = { ...reply, tool_calls: [], updated_at: 7 };
  expect(recoverVisibleTurns([original, incoming], [original, previous], original, true)).toEqual([
    original, { ...incoming, tool_calls: [captured] },
  ]);
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
