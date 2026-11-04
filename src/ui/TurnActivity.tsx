import type { CapturedToolCall, LocalTurn } from "./resultFormatting";
import ResultMarkdown from "./ResultMarkdown";
import ToolCalls from "./ToolCalls";

type Activity =
  | { kind: "text"; id: string; text: string }
  | { kind: "tools"; id: string; calls: CapturedToolCall[] };

/** Preserve the visible assistant/tool chronology, including commentary before calls. */
export function orderedActivity(turn: LocalTurn, captureSource = "dom"): Activity[] {
  const calls = turn.tool_calls ?? [];
  const blocks = turn.display_blocks ?? [];
  if (!blocks.some((block) => block.kind === "text")) {
    return [
      ...(calls.length ? [{ kind: "tools" as const, id: "tools", calls }] : []),
      ...(turn.assistant_text
        ? [{ kind: "text" as const, id: "answer", text: turn.assistant_text }]
        : []),
    ];
  }
  const claimed = new Set<string>();
  const activity: Activity[] = [];
  const textBlocks = blocks.filter((block) => block.kind === "text");
  // DOM headings can summarize dozens of invocations. Structured tool events
  // have stable timestamps; live prose blocks retain their first-seen time.
  // Reconcile those actual event times instead of assigning one call per heading
  // and dumping all other calls together before the conclusion.
  const timedDom =
    captureSource === "dom" &&
    textBlocks.length > 0 &&
    textBlocks.every(
      (block) =>
        block.id.startsWith("text-") && block.seen_at && Number.isFinite(Number(block.seen_at)),
    ) &&
    calls.some((call) => !call.id.startsWith("dom-tool-")) &&
    calls.every(
      (call) =>
        typeof call.observed_at === "number" &&
        Number.isFinite(call.observed_at) &&
        call.observed_at > 0,
    );
  if (timedDom) {
    const chronologicalCalls = calls
      .map((call, index) => ({ call, index }))
      .sort((a, b) => (a.call.observed_at ?? 0) - (b.call.observed_at ?? 0) || a.index - b.index);
    let next = 0;
    const addCall = (call: CapturedToolCall) => {
      claimed.add(call.id);
      const last = activity.at(-1);
      if (last?.kind === "tools") last.calls.push(call);
      else activity.push({ kind: "tools", id: `tools-${call.id}`, calls: [call] });
    };
    for (const block of textBlocks) {
      while (
        next < chronologicalCalls.length &&
        (chronologicalCalls[next].call.observed_at ?? 0) < Number(block.seen_at)
      ) {
        addCall(chronologicalCalls[next++].call);
      }
      activity.push({ kind: "text", id: block.id, text: block.text });
    }
    while (next < chronologicalCalls.length) addCall(chronologicalCalls[next++].call);
  } else
    for (const block of blocks) {
      if (block.kind === "text") {
        activity.push({ kind: "text", id: block.id, text: block.text });
        continue;
      }
      const index = Number(block.id.replace(/^dom-tool-/, ""));
      const call =
        calls.find((candidate) => candidate.id === (block.tool_id ?? block.id)) ??
        (block.id.startsWith("dom-tool-") ? calls[index] : undefined);
      if (!call || claimed.has(call.id)) continue;
      claimed.add(call.id);
      const last = activity.at(-1);
      if (last?.kind === "tools") last.calls.push(call);
      else activity.push({ kind: "tools", id: block.id, calls: [call] });
    }
  const remaining = calls.filter((call) => !claimed.has(call.id));
  if (remaining.length) {
    const lastText = activity.findLastIndex((item) => item.kind === "text");
    const insertAt = lastText > 0 ? lastText : activity.length;
    activity.splice(insertAt, 0, { kind: "tools", id: "unplaced-tools", calls: remaining });
  }
  // The passive DOM observer can end before the final SSE text lands. Retain
  // the streamed answer if the ordered snapshot contains only earlier blocks.
  const rendered = blocks
    .filter((block) => block.kind === "text")
    .map((block) => block.text)
    .join("\n\n")
    .trim();
  const answer = turn.assistant_text.trim();
  if (answer && !rendered.includes(answer)) {
    if (answer.startsWith(rendered)) {
      const tail = answer.slice(rendered.length).trim();
      if (tail) activity.push({ kind: "text", id: "answer-tail", text: tail });
    } else if (rendered && answer.endsWith(rendered)) {
      const head = answer.slice(0, -rendered.length).trim();
      if (head) activity.unshift({ kind: "text", id: "answer-head", text: head });
    } else {
      // A refreshed SSE answer can share opening or intermediate commentary
      // with an older DOM snapshot without matching the full concatenation.
      // Adding the complete answer here would display that commentary twice.
      const parts = (value: string) =>
        value
          .split(/\n\s*\n/)
          .map((part) => part.trim())
          .filter(Boolean);
      const shown = parts(rendered);
      const incoming = parts(answer);
      const sharedPrefix = (left: string[], right: string[]) => {
        let count = 0;
        while (count < left.length && count < right.length && left[count] === right[count]) count++;
        return count;
      };
      const opening = sharedPrefix(shown, incoming);
      const continuation =
        Array.from(
          { length: Math.min(shown.length, incoming.length) },
          (_, index) => Math.min(shown.length, incoming.length) - index,
        ).find((count) => sharedPrefix(shown.slice(-count), incoming) === count) ?? 0;
      const ending = sharedPrefix([...shown].reverse(), [...incoming].reverse());
      if (opening > 0 && opening < incoming.length) {
        activity.push({
          kind: "text",
          id: "answer-tail",
          text: incoming.slice(opening).join("\n\n"),
        });
      } else if (continuation > 0 && continuation < incoming.length) {
        activity.push({
          kind: "text",
          id: "answer-tail",
          text: incoming.slice(continuation).join("\n\n"),
        });
      } else if (ending > 0 && ending < incoming.length) {
        activity.unshift({
          kind: "text",
          id: "answer-head",
          text: incoming.slice(0, -ending).join("\n\n"),
        });
      } else {
        activity.push({ kind: "text", id: "answer-fallback", text: answer });
      }
    }
  }
  return activity;
}

export default function TurnActivity({
  turn,
  captureSource,
  turnTimestamp,
  workedDuration,
}: {
  turn: LocalTurn;
  captureSource: string;
  turnTimestamp: number;
  workedDuration?: string | null;
}) {
  const activity = orderedActivity(turn, captureSource);
  const lastToolIndex = activity.findLastIndex((item) => item.kind === "tools");
  const collapsible = turn.status === "completed" && lastToolIndex !== -1;
  const calls = activity
    .filter((item): item is Extract<Activity, { kind: "tools" }> => item.kind === "tools")
    .flatMap((item) => item.calls);
  const failures = calls.filter((call) => call.status === "error" || call.error).length;
  const renderItem = (item: Activity) =>
    item.kind === "text" ? (
      <ResultMarkdown key={item.id} source={item.text} captureSource={captureSource} />
    ) : (
      <ToolCalls key={item.id} calls={item.calls} turnTimestamp={turnTimestamp} />
    );

  return collapsible ? (
    <>
      <details className="work-trace">
        <summary className="work-trace-summary">
          <span className="work-trace-chevron" aria-hidden="true">
            <svg
              viewBox="0 0 24 24"
              width="17"
              height="17"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m9 6 6 6-6 6" />
            </svg>
          </span>
          <span className="work-trace-title">{workedDuration ?? "Work details"}</span>
          <span className="work-trace-count">
            {calls.length} {calls.length === 1 ? "call" : "calls"}
          </span>
          {failures > 0 && <span className="work-trace-failures">{failures} failed</span>}
        </summary>
        <div className="work-trace-content">
          {activity.slice(0, lastToolIndex + 1).map(renderItem)}
        </div>
      </details>
      {activity.slice(lastToolIndex + 1).map(renderItem)}
    </>
  ) : (
    <>{activity.map(renderItem)}</>
  );
}
