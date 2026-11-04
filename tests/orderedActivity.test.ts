import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import TurnActivity, { orderedActivity } from "../src/ui/TurnActivity";
import type { LocalTurn } from "../src/ui/resultFormatting";

test("assistant commentary displays before a tool and later answer", () => {
  const turn: LocalTurn = {
    reply_id: "",
    user_text: "Hi",
    assistant_text: "First\n\nFinal",
    status: "completed",
    created_at: 1,
    updated_at: 1,
    tool_calls: [
      {
        id: "dom-tool-0",
        connector: "",
        action: "Used Search",
        status: "completed",
        arguments: "",
        result: "",
        error: "",
      },
    ],
    display_blocks: [
      { kind: "text", id: "text-0", text: "First" },
      { kind: "tool", id: "dom-tool-0" },
      { kind: "text", id: "text-1", text: "Final" },
    ],
  };
  expect(orderedActivity(turn).map((item) => item.kind)).toEqual(["text", "tools", "text"]);
  expect(orderedActivity(turn)[0]).toEqual({ kind: "text", id: "text-0", text: "First" });
  const html = renderToStaticMarkup(
    createElement(TurnActivity, {
      turn,
      captureSource: "dom",
      turnTimestamp: 1,
    }),
  );
  expect(html.indexOf("First")).toBeLessThan(html.indexOf("tool-timeline"));
  expect(html.indexOf("tool-timeline")).toBeLessThan(html.indexOf("Final"));
});

test("a later final SSE answer is not lost after an early DOM commentary block", () => {
  const turn: LocalTurn = {
    reply_id: "",
    user_text: "Hi",
    assistant_text: "Checking first.\n\nFinal result.",
    status: "completed",
    created_at: 1,
    updated_at: 1,
    display_blocks: [{ kind: "text", id: "text-0", text: "Checking first." }],
  };
  expect(orderedActivity(turn)).toEqual([
    { kind: "text", id: "text-0", text: "Checking first." },
    { kind: "text", id: "answer-tail", text: "Final result." },
  ]);
});

test("streamed prose and tool markers interleave with their real invocation ids", () => {
  const turn: LocalTurn = {
    reply_id: "stream-ordered",
    user_text: "Check",
    assistant_text: "FINISH",
    status: "completed",
    created_at: 1,
    updated_at: 1,
    tool_calls: [
      {
        id: "call-1",
        connector: "python",
        action: "execute",
        status: "completed",
        arguments: "",
        result: "",
        error: "",
      },
      {
        id: "call-2",
        connector: "python",
        action: "execute",
        status: "completed",
        arguments: "",
        result: "",
        error: "",
      },
    ],
    display_blocks: [
      { kind: "text", id: "sse-text-000000000000000000000001", text: "OPENING" },
      { kind: "tool", id: "sse-tool-000000000000000000000001", tool_id: "call-1" },
      { kind: "text", id: "sse-text-000000000000000000000002", text: "MIDDLE" },
      { kind: "tool", id: "sse-tool-000000000000000000000002", tool_id: "call-2" },
      { kind: "text", id: "sse-text-000000000000000000000003", text: "FINISH" },
    ],
  };
  const activity = orderedActivity(turn);
  expect(activity.map((item) => item.kind)).toEqual(["text", "tools", "text", "tools", "text"]);
  expect(activity[1]).toMatchObject({ kind: "tools", calls: [{ id: "call-1" }] });
  expect(activity[3]).toMatchObject({ kind: "tools", calls: [{ id: "call-2" }] });
  const html = renderToStaticMarkup(
    createElement(TurnActivity, {
      turn,
      captureSource: "sse",
      turnTimestamp: 1,
    }),
  );
  const opening = html.indexOf("OPENING");
  const firstTool = html.indexOf("tool-timeline", opening);
  const middle = html.indexOf("MIDDLE", firstTool);
  const secondTool = html.indexOf("tool-timeline", middle);
  const finish = html.indexOf("FINISH", secondTool);
  expect([opening, firstTool, middle, secondTool, finish].every((index) => index >= 0)).toBe(true);
  expect(opening).toBeLessThan(firstTool);
  expect(firstTool).toBeLessThan(middle);
  expect(middle).toBeLessThan(secondTool);
  expect(secondTool).toBeLessThan(finish);
});

test("nonadjacent identical tools remain separate in chronological order", () => {
  const turn: LocalTurn = {
    reply_id: "order",
    user_text: "Check",
    assistant_text: "",
    status: "generating",
    created_at: 1,
    updated_at: 1,
    tool_calls: [
      {
        id: "a1",
        connector: "A",
        action: "check",
        status: "completed",
        arguments: "",
        result: "",
        error: "",
      },
      {
        id: "b1",
        connector: "B",
        action: "check",
        status: "completed",
        arguments: "",
        result: "",
        error: "",
      },
      {
        id: "a2",
        connector: "A",
        action: "check",
        status: "completed",
        arguments: "",
        result: "",
        error: "",
      },
    ],
  };
  const html = renderToStaticMarkup(
    createElement(TurnActivity, {
      turn,
      captureSource: "sse",
      turnTimestamp: 1,
    }),
  );
  expect(html.match(/class="tool-type-group"/g)?.length).toBe(3);
  const firstA = html.indexOf("A · Check");
  const b = html.indexOf("B · Check", firstA);
  const secondA = html.indexOf("A · Check", b);
  expect(firstA).toBeGreaterThan(-1);
  expect(firstA).toBeLessThan(b);
  expect(b).toBeLessThan(secondA);
});

test("tools remain visible when no assistant text has arrived", () => {
  const turn: LocalTurn = {
    reply_id: "",
    user_text: "Hi",
    assistant_text: "",
    status: "generating",
    created_at: 1,
    updated_at: 1,
    tool_calls: [
      {
        id: "dom-tool-0",
        connector: "",
        action: "Used Search",
        status: "running",
        arguments: "",
        result: "",
        error: "",
      },
    ],
  };
  expect(orderedActivity(turn).map((item) => item.kind)).toEqual(["tools"]);
});
