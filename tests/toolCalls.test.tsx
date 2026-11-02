import { expect, test } from "bun:test";
import { render } from "@testing-library/react";
import ToolCalls from "../src/ui/ToolCalls";
import { chatMessageTime, nzTime } from "../src/ui/resultFormatting";
import type { CapturedToolCall } from "../src/ui/resultFormatting";

function call(id: string, observed_at?: number): CapturedToolCall {
  return {
    id,
    observed_at,
    connector: "Glass",
    action: "execute_python",
    status: "completed",
    arguments: "",
    result: "ok",
    error: "",
  };
}

test("collapsed tool type shows first and last observed timestamps in Auckland time", () => {
  const first = Date.UTC(2026, 10, 2, 2, 0) / 1000;
  const last = first + 900;
  const { container, unmount } = render(
    <ToolCalls calls={[call("latest", last), call("earliest", first)]} />,
  );
  const group = container.querySelector<HTMLDetailsElement>(".tool-type-group");
  expect(group?.open).toBe(false);
  const times = group?.querySelectorAll(":scope > summary .tool-type-time time");
  expect(times?.length).toBe(2);
  expect(times?.[0]?.getAttribute("datetime")).toBe(new Date(first * 1000).toISOString());
  expect(times?.[1]?.getAttribute("datetime")).toBe(new Date(last * 1000).toISOString());
  expect(times?.[0]?.textContent).toBe(chatMessageTime(first));
  expect(times?.[1]?.textContent).toBe("3:15 pm");
  expect(group?.querySelector(".tool-type-time")?.getAttribute("title")).toBe(
    `First observed: ${nzTime(first)}; last observed: ${nzTime(last)}`,
  );
  unmount();
});

test("same-minute calls show a single collapsed timestamp without a false range", () => {
  const first = Date.UTC(2026, 10, 2, 2, 0) / 1000;
  const { container, unmount } = render(
    <ToolCalls calls={[call("a", first), call("b", first + 20)]} />,
  );
  const times = container.querySelectorAll(".tool-type-group > summary .tool-type-time time");
  expect(times.length).toBe(1);
  expect(times[0]?.textContent).toBe(chatMessageTime(first));
  unmount();
});

test("legacy calls use the turn timestamp, but no timestamp is invented when absent", () => {
  const turnTimestamp = Date.UTC(2026, 10, 1, 2, 0) / 1000;
  const { container, rerender, unmount } = render(
    <ToolCalls calls={[call("legacy")]} turnTimestamp={turnTimestamp} />,
  );
  expect(container.querySelector(".tool-type-group > summary time")?.textContent).toBe(
    chatMessageTime(turnTimestamp),
  );
  rerender(<ToolCalls calls={[call("legacy")]} />);
  expect(container.querySelector(".tool-type-group > summary time")).toBeNull();
  unmount();
});
