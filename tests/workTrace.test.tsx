import { expect, test } from "bun:test";
import { fireEvent, render } from "@testing-library/react";
import TurnActivity from "../src/ui/TurnActivity";
import type { CapturedToolCall, LocalTurn } from "../src/ui/resultFormatting";

function call(id: string): CapturedToolCall {
  return {
    id,
    connector: "Glass",
    action: "execute_python",
    status: "completed",
    arguments: "",
    result: "ok",
    error: "",
  };
}

function turn(status: LocalTurn["status"] = "completed"): LocalTurn {
  return {
    reply_id: "reply",
    user_text: "Review it",
    assistant_text: "Opening\n\nProgress\n\nFinal answer",
    status,
    created_at: 100,
    updated_at: 400,
    tool_calls: [call("first"), call("second"), call("third")],
    display_blocks: [
      { kind: "text", id: "text-0", text: "Opening" },
      { kind: "tool", id: "tool-0", tool_id: "first" },
      { kind: "text", id: "text-1", text: "Progress" },
      { kind: "tool", id: "tool-1", tool_id: "second" },
      { kind: "tool", id: "tool-2", tool_id: "third" },
      { kind: "text", id: "text-2", text: "Final answer" },
    ],
  };
}

test("completed response hides its long chronological work trace but not the final answer", () => {
  const { container, unmount } = render(
    <TurnActivity
      turn={turn()}
      captureSource="sse"
      turnTimestamp={100}
      workedDuration="Worked for 5m"
    />,
  );
  const trace = container.querySelector<HTMLDetailsElement>(".work-trace");
  expect(trace?.open).toBe(false);
  expect(trace?.querySelector(".work-trace-title")?.textContent).toBe("Worked for 5m");
  expect(trace?.querySelector(".work-trace-count")?.textContent).toContain("3 calls");
  expect(trace?.querySelectorAll(".tool-timeline").length).toBe(2);
  const traceText = trace?.textContent ?? "";
  expect(traceText.indexOf("Opening")).toBeLessThan(traceText.indexOf("Glass"));
  expect(traceText.indexOf("Glass")).toBeLessThan(traceText.indexOf("Progress"));
  expect(traceText).not.toContain("Final answer");
  expect(container.lastElementChild?.textContent).toContain("Final answer");

  fireEvent.click(trace!.querySelector("summary")!);
  expect(trace?.open).toBe(true);
  unmount();
});

test("generating responses keep visible streaming chronology and have no work collapse", () => {
  const { container, unmount } = render(
    <TurnActivity turn={turn("generating")} captureSource="sse" turnTimestamp={100} />,
  );
  expect(container.querySelector(".work-trace")).toBeNull();
  expect(container.querySelectorAll(".tool-timeline").length).toBe(2);
  expect(container.textContent).toContain("Opening");
  expect(container.textContent).toContain("Final answer");
  unmount();
});

test("completed tool history without trustworthy timing does not invent a duration", () => {
  const { container, unmount } = render(
    <TurnActivity turn={turn()} captureSource="history_dom" turnTimestamp={100} />,
  );
  expect(container.querySelector(".work-trace-title")?.textContent).toBe("Work details");
  expect(container.querySelector(".work-trace-count")?.textContent).toContain("3 calls");
  unmount();
});

test("completed text-only replies never get an empty work disclosure", () => {
  const plain = { ...turn(), tool_calls: [], display_blocks: undefined };
  const { container, unmount } = render(
    <TurnActivity
      turn={plain}
      captureSource="sse"
      turnTimestamp={100}
      workedDuration="Worked for 5m"
    />,
  );
  expect(container.querySelector(".work-trace")).toBeNull();
  expect(container.textContent).toContain("Final answer");
  unmount();
});
