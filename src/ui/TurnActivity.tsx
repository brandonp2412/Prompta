import type { CapturedToolCall, LocalTurn } from "./resultFormatting";
import ResultMarkdown from "./ResultMarkdown";
import ToolCalls from "./ToolCalls";

type Activity =
  | { kind: "text"; id: string; text: string }
  | { kind: "tools"; id: string; calls: CapturedToolCall[] };

/** Preserve the visible assistant/tool chronology, including commentary before calls. */
export function orderedActivity(turn: LocalTurn): Activity[] {
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
  for (const block of blocks) {
    if (block.kind === "text") {
      activity.push({ kind: "text", id: block.id, text: block.text });
      continue;
    }
    const index = Number(block.id.replace(/^dom-tool-/, ""));
    const call = calls.find((candidate) => candidate.id === block.id) ?? calls[index];
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
  return activity;
}

export default function TurnActivity({
  turn,
  captureSource,
  turnTimestamp,
}: {
  turn: LocalTurn;
  captureSource: string;
  turnTimestamp: number;
}) {
  return (
    <>
      {orderedActivity(turn).map((item) =>
        item.kind === "text" ? (
          <ResultMarkdown key={item.id} source={item.text} captureSource={captureSource} />
        ) : (
          <ToolCalls key={item.id} calls={item.calls} turnTimestamp={turnTimestamp} />
        ),
      )}
    </>
  );
}
