import type { CapturedToolCall } from "./resultFormatting";

const statusMark: Record<string, string> = {
  Failed: "!",
  Running: "…",
  Observed: "·",
  Completed: "✓",
};

function title(call: CapturedToolCall): string {
  if (call.connector === "web")
    return call.status === "running" ? "Searching the web" : "Searched the web";
  if (call.connector === "python")
    return call.status === "running" ? "Analyzing data" : "Analyzed data";
  const name = [call.connector, call.action].filter(Boolean).join(" · ") || "Tool call";
  if (!call.connector) return name;
  return `${call.status === "running" ? "Using" : "Used"} ${name}`;
}

function status(call: CapturedToolCall): string {
  if (call.status === "error" || call.error) return "Failed";
  if (call.status === "running") return "Running";
  if (call.status === "observed") return "Observed";
  return "Completed";
}

export default function ToolCalls({ calls }: { calls: CapturedToolCall[] }) {
  if (!calls.length) return null;
  const failures = calls.filter((call) => call.status === "error" || call.error).length;
  return (
    <details className="tool-timeline" open>
      <summary className="tool-timeline-summary">
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
        <span className="tool-timeline-toggle" aria-hidden="true">
          ⌄
        </span>
      </summary>
      <div className="tool-call-list">
        {calls.map((call, index) => (
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
              <span className="tool-call-status">{status(call)}</span>
              <span className="tool-call-chevron" aria-hidden="true">
                ⌄
              </span>
            </summary>
            <div className="tool-call-body">
              {call.arguments && (
                <section>
                  <h4>Input</h4>
                  <pre>{call.arguments}</pre>
                </section>
              )}
              {call.result && (
                <section>
                  <h4>Output</h4>
                  <pre>{call.result}</pre>
                </section>
              )}
              {call.error && (
                <section>
                  <h4>Error</h4>
                  <pre>{call.error}</pre>
                </section>
              )}
              {!call.arguments && !call.result && !call.error && (
                <p>No additional details captured.</p>
              )}
            </div>
          </details>
        ))}
      </div>
    </details>
  );
}
