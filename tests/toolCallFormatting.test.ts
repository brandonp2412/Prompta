import { expect, test } from "bun:test";
import { toolPayload } from "../src/ui/ToolCallFormatting";

test("Python MCP JSON arguments render actual Python rather than the wrapper", () => {
  const input = JSON.stringify({
    code: "from pathlib import Path\nprint(Path.cwd())",
    timeout_seconds: 20,
  });
  expect(
    toolPayload(input, { connector: "Glass Python MCP", action: "execute_python" }, true),
  ).toEqual({ text: "from pathlib import Path\nprint(Path.cwd())", language: "python" });
});

test("Serena shell commands render as Bash, including nested arguments", () => {
  const input = JSON.stringify({
    name: "mcp__serena__execute_shell_command",
    arguments: { command: "rg -n 'hello' src | head -10", cwd: "/repo" },
  });
  expect(
    toolPayload(input, { connector: "Nox Serena", action: "execute_shell_command" }, true),
  ).toEqual({ text: "rg -n 'hello' src | head -10", language: "bash" });
});

test("plain JSON arguments and JSON outputs stay JSON", () => {
  const tool = { connector: "Search", action: "lookup" };
  const input = '{"query":"kiwi","limit":2}';
  expect(toolPayload(input, tool, true)).toEqual({
    text: '{\n  "query": "kiwi",\n  "limit": 2\n}',
    language: "json",
  });
  expect(toolPayload('{"count":2}', tool, false)).toEqual({
    text: '{\n  "count": 2\n}',
    language: "json",
  });
});

test("unrelated JSON code fields remain JSON, not executable snippets", () => {
  const input = '{"code":"print(1)","description":"not a Python tool"}';
  expect(toolPayload(input, { connector: "Search", action: "lookup" }, true).language).toBe("json");
});

test("embedded code is treated as text and retains literal markup", () => {
  const source = "print('<script>alert(1)</script>')\n# do not execute";
  expect(
    toolPayload(
      JSON.stringify({ code: source }),
      {
        connector: "Nox Python",
        action: "execute_python",
      },
      true,
    ),
  ).toEqual({ text: source, language: "python" });
});

test("raw code, malformed JSON, and a nested JSON argument string", () => {
  const tool = { connector: "Nox Python", action: "execute_python" };
  expect(toolPayload("print(1)", tool, true)).toEqual({
    text: "print(1)",
    language: "python",
  });
  expect(toolPayload('{"code":', tool, true)).toEqual({
    text: '{"code":',
    language: "python",
  });
  const nested = JSON.stringify({ arguments: JSON.stringify({ code: "print(42)" }) });
  expect(toolPayload(nested, tool, true)).toEqual({
    text: "print(42)",
    language: "python",
  });
});

test("JavaScript browser code and non-JSON output retain their content", () => {
  expect(
    toolPayload(
      '{"code":"return document.title"}',
      {
        connector: "Patchright",
        action: "browser_run_code",
      },
      true,
    ),
  ).toEqual({ text: "return document.title", language: "javascript" });
  expect(toolPayload("no results", { connector: "Search", action: "lookup" }, false)).toEqual({
    text: "no results",
    language: "",
  });
});
