import { Fragment } from "react";
import Prism from "prismjs";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-python";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-json";

export function highlightedCode(value: string, language: string): React.ReactNode {
  const grammar = Prism.languages[language];
  if (!grammar) return value;

  function render(stream: Prism.TokenStream): React.ReactNode {
    if (typeof stream === "string") return stream;
    if (!Array.isArray(stream))
      return <span className={"token " + stream.type}>{render(stream.content)}</span>;
    return stream.map((part, i) => <Fragment key={i}>{render(part)}</Fragment>);
  }

  return render(Prism.tokenize(value, grammar));
}
