import { expect, test } from "bun:test";
import {
  dateGroup,
  groupRuns,
  isFlattenedDomResponse,
  nzTime,
  plainPreview,
  safeHref,
  statusLabel,
  type RunSummary,
} from "../src/ui/resultFormatting";

test("timestamps use Auckland 12-hour clock and DST", () => {
  expect(nzTime(Date.UTC(2026, 9, 26, 10, 15) / 1000)).toContain("11:15 pm");
  expect(dateGroup(Date.UTC(2026, 9, 26, 10, 15) / 1000)).toContain("26 Oct 2026");
  expect(nzTime(Date.UTC(2026, 5, 26, 12, 15) / 1000)).toContain("12:15 am");
});

test("sidebar groups actual runs without global history", () => {
  const run = (id: string, created_at: number): RunSummary => ({
    send_id: id,
    created_at,
    job_name: "job",
    title: "job",
    preview: "",
    status: "queued",
    has_response: false,
    updated_at: created_at,
    finished_at: 0,
  });
  const groups = groupRuns([run("1", 100), run("2", 120), run("3", 100_000)]);
  expect(groups.map((group) => group.items.map((item) => item.send_id))).toEqual([
    ["1", "2"],
    ["3"],
  ]);
  expect(statusLabel("generating")).toBe("Generating");
  expect(statusLabel("interrupted")).toBe("Interrupted");
});

test("markdown hyperlinks cannot execute script schemes", () => {
  expect(safeHref("javascript:alert(1)")).toBeNull();
  expect(safeHref("data:text/html,hi")).toBeNull();
  expect(safeHref("/backend-api/conversation")).toBeNull();
  expect(safeHref("https://example.com/path")).toBe("https://example.com/path");
});

test("list previews remove markdown syntax without interpreting it", () => {
  expect(plainPreview("**Answer**\n\n```py\nprint(1)\n```")).toBe("Answer print(1)");
  expect(plainPreview("[documentation](https://example.com)")).toBe("documentation");
});
test("legacy flattened DOM answers render densely without changing real Markdown", () => {
  const cells = [
    "Status",
    "Result",
    "Mobile",
    "Passed",
    "Desktop",
    "Passed",
    "Ruff",
    "Passed",
    "Ty",
    "Passed",
    "Build",
    "Passed",
    "Summary",
  ];
  const archived = cells.join("\n\n");
  expect(isFlattenedDomResponse(archived, "dom")).toBe(true);
  expect(isFlattenedDomResponse(archived, "sse")).toBe(false);
  expect(isFlattenedDomResponse("## Status\n\n- Mobile\n- Desktop", "dom")).toBe(false);
  expect(isFlattenedDomResponse("A paragraph.\n\nAnother paragraph.", "dom")).toBe(false);
});
