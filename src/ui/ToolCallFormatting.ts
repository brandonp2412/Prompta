import type { CapturedToolCall } from "./resultFormatting";

export type ToolPayload = { text: string; language: string };
type ToolIdentity = Pick<CapturedToolCall, "connector" | "action">;

function asObject(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value))
    : null;
}

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
}

function nestedArguments(value: unknown): Record<string, unknown>[] {
  const root = asObject(value);
  if (!root) return [];
  const candidates = [root];
  for (const key of ["arguments", "input", "parameters"]) {
    const wrapped = root[key];
    const nested = asObject(typeof wrapped === "string" ? parseJson(wrapped) : wrapped);
    if (nested) candidates.push(nested);
  }
  return candidates;
}

function codeFromArguments(value: unknown, call: ToolIdentity): ToolPayload | null {
  const identity = `${call.connector} ${call.action}`.toLowerCase();
  const python = /python|execute_python/.test(identity);
  const shell =
    /serena|shell|bash|terminal|exec_command|run_command|execute_command|command|exec|bash/.test(
      identity,
    );
  const javascript = /javascript|run_code|browser_evaluate/.test(identity);
  if (!python && !shell && !javascript) return null;

  for (const args of nestedArguments(value)) {
    const language = typeof args.language === "string" ? args.language.toLowerCase() : "";
    if (python || language === "python") {
      const code = args.code ?? args.python_code ?? args.script;
      if (typeof code === "string" && code.trim()) return { text: code, language: "python" };
    }
    if (shell || language === "bash" || language === "shell") {
      const code = args.command ?? args.cmd ?? args.shell_command ?? args.script ?? args.code;
      if (typeof code === "string" && code.trim()) return { text: code, language: "bash" };
    }
    if (javascript || language === "javascript") {
      const code = args.code ?? args.script;
      if (typeof code === "string" && code.trim()) return { text: code, language: "javascript" };
    }
  }
  return null;
}

export function toolPayload(value: string, call: ToolIdentity, input: boolean): ToolPayload {
  const parsed = parseJson(value);
  if (parsed !== undefined) {
    if (input) {
      const code = codeFromArguments(parsed, call);
      if (code) return code;
    }
    return { text: JSON.stringify(parsed, null, 2), language: "json" };
  }
  if (input) {
    const identity = `${call.connector} ${call.action}`.toLowerCase();
    if (/python|execute_python/.test(identity)) return { text: value, language: "python" };
    if (
      /serena|shell|bash|terminal|exec_command|run_command|execute_command|command|exec|bash/.test(
        identity,
      )
    )
      return { text: value, language: "bash" };
    if (/javascript|run_code|browser_evaluate/.test(identity))
      return { text: value, language: "javascript" };
  }
  return { text: value, language: "" };
}
