import { useEffect, useMemo, useRef, useState } from "react";
import { marked, type Token, type Tokens } from "marked";
import {
  formatStoredResponse,
  isFlattenedDomResponse,
  legacyLabelList,
  legacyMetricSummary,
  safeHref,
} from "./resultFormatting";

function children(token: Token): Token[] {
  return "tokens" in token && Array.isArray(token.tokens) ? token.tokens : [];
}

export default function ResultMarkdown({
  source,
  captureSource = "",
}: {
  source: string;
  captureSource?: string;
}) {
  const displaySource = useMemo(
    () => formatStoredResponse(source, captureSource),
    [source, captureSource],
  );
  const flattened = useMemo(
    () => isFlattenedDomResponse(displaySource, captureSource),
    [displaySource, captureSource],
  );
  // Tokens are rendered by React as text and elements. No untrusted HTML is injected.
  const tokens = useMemo(
    () => marked.lexer(displaySource, { gfm: true, breaks: false }),
    [displaySource],
  );
  const [copiedCode, setCopiedCode] = useState("");
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle");
  const generation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    generation.current += 1;
    setCopiedCode("");
    setCopyStatus("idle");
    return () => clearTimeout(timer.current);
  }, [displaySource]);

  async function copyCode(text: string, index: number) {
    const current = ++generation.current;
    clearTimeout(timer.current);
    const key = index + ":" + text;
    try {
      await navigator.clipboard.writeText(text);
      if (generation.current !== current) return;
      setCopiedCode(key);
      setCopyStatus("copied");
    } catch {
      if (generation.current !== current) return;
      setCopiedCode(key);
      setCopyStatus("failed");
    }
    timer.current = setTimeout(() => {
      if (generation.current === current) {
        setCopiedCode("");
        setCopyStatus("idle");
      }
    }, 2200);
  }

  function inline(items: Token[]): React.ReactNode {
    return items.map((token, index) => {
      const key = index;
      switch (token.type) {
        case "text":
          return (
            <span key={key}>{children(token).length ? inline(children(token)) : token.text}</span>
          );
        case "strong":
          return <strong key={key}>{inline(children(token))}</strong>;
        case "em":
          return <em key={key}>{inline(children(token))}</em>;
        case "del":
          return <del key={key}>{inline(children(token))}</del>;
        case "codespan":
          return <code key={key}>{token.text}</code>;
        case "link": {
          const href = safeHref(token.href);
          return href ? (
            <a key={key} href={href} target="_blank" rel="noopener noreferrer">
              {inline(children(token))}
            </a>
          ) : (
            <span key={key}>{inline(children(token))}</span>
          );
        }
        case "br":
          return <br key={key} />;
        case "escape":
        case "html":
        case "image":
          return <span key={key}>{token.text}</span>;
        default:
          return null;
      }
    });
  }

  function blocks(items: Token[]): React.ReactNode {
    return items.map((token, index) => {
      switch (token.type) {
        case "heading":
          if (token.depth === 1) return <h1 key={index}>{inline(children(token))}</h1>;
          if (token.depth === 2) return <h2 key={index}>{inline(children(token))}</h2>;
          return <h3 key={index}>{inline(children(token))}</h3>;
        case "paragraph":
        case "text": {
          const metrics = legacyMetricSummary(token.text);
          const labelList = legacyLabelList(token.text, captureSource);
          if (metrics)
            return (
              <div
                key={index}
                className="response-metrics"
                role="group"
                aria-label="Response metrics"
              >
                {metrics.map((metric, i) => (
                  <div key={i} className="response-metric">
                    <strong className={"response-metric-value tone-" + metric.tone}>
                      {metric.value}
                    </strong>
                    <span>{metric.label}</span>
                  </div>
                ))}
              </div>
            );
          if (labelList)
            return (
              <ul key={index} className="result-recovered-list">
                {labelList.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            );
          return <p key={index}>{inline(children(token).length ? children(token) : [token])}</p>;
        }
        case "code": {
          let copyLabel = "Copy code";
          if (copiedCode === index + ":" + token.text)
            copyLabel = copyStatus === "copied" ? "Copied" : "Copy failed";
          return (
            <div key={index} className="code-snippet">
              <div className="code-toolbar">
                <span>{token.lang || "Code"}</span>
                <button
                  type="button"
                  aria-label="Copy code"
                  aria-live="polite"
                  onClick={() => void copyCode(token.text, index)}
                >
                  {copyLabel}
                </button>
              </div>
              <pre>
                <code className={token.lang ? "language-" + token.lang.split(/\s+/)[0] : ""}>
                  {token.text}
                </code>
              </pre>
            </div>
          );
        }
        case "list":
          return token.ordered ? (
            <ol key={index} start={token.start || 1}>
              {token.items.map((item: Tokens.ListItem, i: number) => (
                <li key={i}>{blocks(item.tokens)}</li>
              ))}
            </ol>
          ) : (
            <ul key={index}>
              {token.items.map((item: Tokens.ListItem, i: number) => (
                <li key={i}>{blocks(item.tokens)}</li>
              ))}
            </ul>
          );
        case "blockquote":
          return <blockquote key={index}>{blocks(token.tokens ?? [])}</blockquote>;
        case "table":
          return (
            <div key={index} className="result-table-scroll">
              <table>
                <thead>
                  <tr>
                    {token.header.map((cell: Tokens.TableCell, i: number) => (
                      <th key={i}>{inline(cell.tokens)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {token.rows.map((row: Tokens.TableCell[], i: number) => (
                    <tr key={i}>
                      {row.map((cell: Tokens.TableCell, j: number) => (
                        <td key={j}>{inline(cell.tokens)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        case "hr":
          return <hr key={index} />;
        case "html":
          return <p key={index}>{token.text}</p>;
        default:
          return null;
      }
    });
  }

  return (
    <div className={"result-markdown" + (flattened ? " flattened" : "")}>
      {blocks(tokens as Token[])}
    </div>
  );
}
