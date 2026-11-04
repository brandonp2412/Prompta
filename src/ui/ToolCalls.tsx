import { chatMessageTime, dateGroup, nzTime } from "./resultFormatting";
import type { CapturedToolCall } from "./resultFormatting";
import { highlightedCode } from "./CodeHighlight";
import { toolPayload } from "./ToolCallFormatting";

function ToolContent({
  value,
  call,
  input,
}: {
  value: string;
  call: CapturedToolCall;
  input: boolean;
}) {
  const { text, language } = toolPayload(value, call, input);
  return (
    <pre>
      <code className={language ? "language-" + language : ""}>
        {highlightedCode(text, language)}
      </code>
    </pre>
  );
}

const statusMark: Record<string, string> = {
  Failed: "!",
  Running: "…",
  Observed: "·",
  Completed: "✓",
};

function title(call: CapturedToolCall): string {
  const connector = call.connector.trim();
  if (connector.toLowerCase() === "web")
    return `Web · ${call.status === "running" ? "Searching" : "Searched"} the web`;
  if (connector.toLowerCase() === "python")
    return `Python · ${call.status === "running" ? "Analyzing" : "Analyzed"} data`;
  const action = call.action
    .trim()
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^\w/, (initial) => initial.toUpperCase())
    .replace(/\bpython\b/gi, "Python");
  const knownConnector = connector.toLowerCase() === "tool" ? "" : connector;
  return [knownConnector, action].filter(Boolean).join(" · ") || "Tool call";
}

function status(call: CapturedToolCall): string {
  if (call.status === "error" || call.error) return "Failed";
  if (call.status === "running") return "Running";
  if (call.status === "observed") return "Observed";
  return "Completed";
}

function groupObservedTimes(calls: CapturedToolCall[], turnTimestamp?: number) {
  const timestamps = calls
    .map((call) => call.observed_at || turnTimestamp || 0)
    .filter((value) => Number.isFinite(value) && value > 0);
  if (!timestamps.length) return null;
  return { first: Math.min(...timestamps), last: Math.max(...timestamps) };
}

function clockTime(epoch: number): string {
  return new Intl.DateTimeFormat("en-NZ", {
    timeZone: "Pacific/Auckland",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(epoch * 1000);
}

export default function ToolCalls({
  calls,
  turnTimestamp,
}: {
  calls: CapturedToolCall[];
  turnTimestamp?: number;
}) {
  if (!calls.length) return null;
  // Collapse adjacent identical actions only; A → B → A must stay A → B → A.
  const groups: { key: string; calls: CapturedToolCall[] }[] = [];
  for (const call of calls) {
    const key = JSON.stringify([call.connector, call.action]);
    const last = groups.at(-1);
    if (last?.key === key) last.calls.push(call);
    else groups.push({ key, calls: [call] });
  }
  const failures = calls.filter((call) => call.status === "error" || call.error).length;
  return (
    <section className="tool-timeline" aria-label="Tool activity">
      <div className="tool-timeline-summary">
        <span className="tool-timeline-icon" aria-hidden="true">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="3" width="7" height="7" rx="2" />
            <rect x="14" y="3" width="7" height="7" rx="2" />
            <rect x="3" y="14" width="7" height="7" rx="2" />
            <rect x="14" y="14" width="7" height="7" rx="2" />
          </svg>
        </span>
        <span>
          {calls.length} tool {calls.length === 1 ? "call" : "calls"}
        </span>
        {failures > 0 && <span className="tool-failure-count">{failures} failed</span>}
      </div>
      <div className="tool-call-list">
        {groups.map(({ key, calls: group }, groupIndex) => {
          const times = groupObservedTimes(group, turnTimestamp);
          const firstLabel = times ? chatMessageTime(times.first) : "";
          const lastLabel = times ? chatMessageTime(times.last) : "";
          return (
            <details className="tool-type-group" key={`${key}-${groupIndex}`}>
              <summary>
                <span className="tool-type-label">
                  {title(group[0])} · {group.length} {group.length === 1 ? "call" : "calls"}
                  {group.some((call) => status(call) === "Running") && " · Running"}
                  {group.some((call) => status(call) === "Failed") && " · Failed"}
                </span>
                {times && (
                  <span
                    className="tool-type-time"
                    title={`First observed: ${nzTime(times.first)}${firstLabel !== lastLabel ? `; last observed: ${nzTime(times.last)}` : ""}`}
                  >
                    <time dateTime={new Date(times.first * 1000).toISOString()}>{firstLabel}</time>
                    {firstLabel !== lastLabel && (
                      <>
                        {" – "}
                        <time dateTime={new Date(times.last * 1000).toISOString()}>
                          {dateGroup(times.first) === dateGroup(times.last)
                            ? clockTime(times.last)
                            : lastLabel}
                        </time>
                      </>
                    )}
                  </span>
                )}
              </summary>
              {group.map((call, index) => (
                <details
                  key={call.id || index}
                  className={
                    "tool-call" +
                    (status(call) === "Failed" ? " failed" : "") +
                    (status(call) === "Running" ? " running" : "")
                  }
                >
                  <summary className="tool-call-summary">
                    <span className="tool-call-mark" aria-hidden="true">
                      {statusMark[status(call)]}
                    </span>
                    <span className="tool-call-name">{title(call)}</span>
                    {call.observed_at || turnTimestamp ? (
                      <time
                        className="tool-call-time"
                        dateTime={new Date(
                          (call.observed_at || turnTimestamp || 0) * 1000,
                        ).toISOString()}
                        title={
                          (call.observed_at ? "First observed: " : "Conversation turn: ") +
                          nzTime(call.observed_at || turnTimestamp || 0)
                        }
                      >
                        {chatMessageTime(call.observed_at || turnTimestamp || 0)}
                      </time>
                    ) : null}
                    <span className="tool-call-status">{status(call)}</span>
                  </summary>
                  {(call.arguments || call.result || call.error) && (
                    <div className="tool-call-body">
                      {call.arguments && (
                        <section>
                          <h4>Input / code</h4>
                          <ToolContent value={call.arguments} call={call} input={true} />
                        </section>
                      )}
                      {call.result && (
                        <section>
                          <h4>Output</h4>
                          <ToolContent value={call.result} call={call} input={false} />
                        </section>
                      )}
                      {call.error && (
                        <section>
                          <h4>Error</h4>
                          <ToolContent value={call.error} call={call} input={false} />
                        </section>
                      )}
                    </div>
                  )}
                  {!call.arguments && !call.result && !call.error && (
                    <div className="tool-call-body">
                      <p>Only the tool label was available for this call.</p>
                    </div>
                  )}
                </details>
              ))}
            </details>
          );
        })}
      </div>
    </section>
  );
}
