import { expect, test } from "bun:test";
import { messageDisplayContent } from "./conversationLogic";

test("refresh preserves text-tool-text order and tool details", () => {
  const tool = '```tool:Glass · execute_python\n{"code":"print(1 + 1)","result":2}\n```';
  const message = {
    role: "assistant",
    parts_renderable: true,
    content: "Finished",
    parts: [
      { ordinal: 3, kind: "final_text", content: "Finished" },
      { ordinal: 1, kind: "tool_call", content: tool },
      { ordinal: 0, kind: "assistant_text", content: "First update" },
      { ordinal: 2, kind: "assistant_text", content: "Middle update" },
    ],
  };
  const expected = ["First update", tool, "Middle update", "Finished"].join("\n\n");
  expect(messageDisplayContent(message)).toBe(expected);
  expect(messageDisplayContent(JSON.parse(JSON.stringify(message)))).toBe(expected);
});
