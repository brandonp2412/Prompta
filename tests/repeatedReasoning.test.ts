import { expect, test } from "bun:test";
import { orderedActivity } from "../src/ui/TurnActivity";
import type { LocalTurn } from "../src/ui/resultFormatting";

function turn(answer: string, prose: string[]): LocalTurn {
  return {
    reply_id: "reply",
    user_text: "Fix the duplication",
    assistant_text: answer,
    status: "generating",
    created_at: 1,
    updated_at: 2,
    tool_calls: [],
    display_blocks: prose.map((text, index) => ({
      kind: "text",
      id: `text-${index}`,
      text,
    })),
  };
}

function visibleText(value: LocalTurn): string[] {
  return orderedActivity(value)
    .filter((item) => item.kind === "text")
    .map((item) => item.text);
}

test("a refreshed answer does not repeat opening commentary when its conclusion changed", () => {
  const shown = ["I’ll investigate the capture.", "The first check is complete."];
  const answer = "I’ll investigate the capture.\n\nThe conclusion has arrived.";
  expect(visibleText(turn(answer, shown))).toEqual([...shown, "The conclusion has arrived."]);
});

test("a refreshed answer does not repeat intermediate reasoning across tool calls", () => {
  const shown = ["I’ll check Glass.", "Glass was offline; Nox is ready."];
  const answer = "Glass was offline; Nox is ready.\n\nThe fix is deployed.";
  const value = turn(answer, shown);
  value.tool_calls = [
    {
      id: "dom-tool-0",
      connector: "Glass",
      action: "execute_python",
      status: "completed",
      arguments: "",
      result: "",
      error: "",
    },
  ];
  value.display_blocks?.splice(1, 0, { kind: "tool", id: "dom-tool-0" });
  expect(orderedActivity(value).map((item) => item.kind)).toEqual([
    "text",
    "tools",
    "text",
    "text",
  ]);
  expect(visibleText(value)).toEqual([...shown, "The fix is deployed."]);
});

test("an independent final answer remains visible after an early commentary capture", () => {
  const shown = ["I’ll check Glass.", "Testing in progress."];
  expect(visibleText(turn("All tests passed.", shown))).toEqual([...shown, "All tests passed."]);
});

test("a complete captured answer is not appended again", () => {
  const shown = ["Opening reasoning.", "The final answer."];
  expect(visibleText(turn("The final answer.", shown))).toEqual(shown);
});
