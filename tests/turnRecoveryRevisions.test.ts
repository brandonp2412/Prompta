import { expect, test } from "bun:test";
import { recoverVisibleTurns } from "../src/ui/turnRecovery";
import type { LocalTurn } from "../src/ui/resultFormatting";

const first: LocalTurn = {
  reply_id: "",
  user_text: "First question",
  assistant_text: "Work in progress",
  status: "generating",
  created_at: 1,
  updated_at: 2,
};
const reply: LocalTurn = {
  reply_id: "follow-up-1",
  user_text: "Follow-up",
  assistant_text: "Reply",
  status: "completed",
  created_at: 3,
  updated_at: 4,
};

test("out-of-order turns GET cannot overwrite a newer final detail", () => {
  const final = {
    ...first,
    assistant_text: "Final and verified answer",
    status: "completed" as const,
    updated_at: 8,
  };
  expect(recoverVisibleTurns([first, reply], [], final, false)).toEqual([final, reply]);
  expect(recoverVisibleTurns([first], [], final, true)).toEqual([final]);
});

test("stale detail cannot regress a final answer from the turns endpoint", () => {
  const final = {
    ...first,
    assistant_text: "Final and verified answer",
    status: "completed" as const,
    updated_at: 8,
  };
  expect(recoverVisibleTurns([final, reply], [], first, false)).toEqual([final, reply]);
  expect(recoverVisibleTurns([final], [], { ...first, updated_at: 9 }, false)).toEqual([final]);
});

test("stale original repair retains richer tool summaries and manual replies", () => {
  const tool = {
    id: "tool-1",
    connector: "example",
    action: "read",
    status: "completed",
    arguments: "",
    result: "Done",
    error: "",
  };
  const withTools = { ...first, tool_calls: [tool] };
  const final = {
    ...first,
    assistant_text: "Final and verified answer",
    status: "completed" as const,
    updated_at: 8,
  };
  expect(recoverVisibleTurns([withTools, reply], [], final, false)).toEqual([
    { ...final, tool_calls: [tool] },
    reply,
  ]);
});

test("primary detail hydration preserves the verified exact-reply branch", () => {
  const confirmed = {
    ...first,
    conversation_id: "verified-conversation",
    parent_id: "verified-user",
    message_id: "verified-assistant",
  };
  const laterDetail = {
    ...first,
    assistant_text: "Final and verified answer",
    status: "completed" as const,
    updated_at: 8,
  };
  const expected = {
    ...laterDetail,
    conversation_id: confirmed.conversation_id,
    parent_id: confirmed.parent_id,
    message_id: confirmed.message_id,
  };
  expect(recoverVisibleTurns([confirmed, reply], [], laterDetail, false)).toEqual([
    expected,
    reply,
  ]);
  expect(recoverVisibleTurns(null, [confirmed, reply], laterDetail, true)).toEqual([
    expected,
    reply,
  ]);
});
