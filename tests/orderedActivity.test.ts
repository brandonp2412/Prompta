import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import TurnActivity, { orderedActivity } from "../src/ui/TurnActivity";
import type { LocalTurn } from "../src/ui/resultFormatting";

test("assistant commentary displays before a tool and later answer", () => {
  const turn: LocalTurn = {
    reply_id: "", user_text: "Hi", assistant_text: "First\n\nFinal", status: "completed",
    created_at: 1, updated_at: 1,
    tool_calls: [{ id: "dom-tool-0", connector: "", action: "Used Search", status: "completed",
      arguments: "", result: "", error: "" }],
    display_blocks: [
      { kind: "text", id: "text-0", text: "First" },
      { kind: "tool", id: "dom-tool-0" },
      { kind: "text", id: "text-1", text: "Final" },
    ],
  };
  expect(orderedActivity(turn).map((item) => item.kind)).toEqual(["text", "tools", "text"]);
  expect(orderedActivity(turn)[0]).toEqual({ kind: "text", id: "text-0", text: "First" });
  const html = renderToStaticMarkup(createElement(TurnActivity, {
    turn, captureSource: "dom", turnTimestamp: 1,
  }));
  expect(html.indexOf("First")).toBeLessThan(html.indexOf("tool-timeline"));
  expect(html.indexOf("tool-timeline")).toBeLessThan(html.indexOf("Final"));
});
