<script lang="ts">
  import { marked, type Token, type Tokens } from "marked";
  import { formatStoredResponse, isFlattenedDomResponse, legacyLabelList, legacyMetricSummary, safeHref } from "./resultFormatting";

  let { source, captureSource = "" }: { source: string; captureSource?: string } = $props();
  let displaySource = $derived(formatStoredResponse(source, captureSource));
  let flattened = $derived(isFlattenedDomResponse(displaySource, captureSource));
  // The token tree is rendered as Svelte text/elements. Untrusted HTML is never injected.
  let tokens = $derived(marked.lexer(displaySource, { gfm: true, breaks: false }));
  let copiedCode = $state("");
  let copyStatus = $state<"idle" | "copied" | "failed">("idle");
  let feedbackTimer: ReturnType<typeof setTimeout> | undefined;
  let copyGeneration = 0;

  $effect(() => {
    // A copied-code toast belongs to this response, never the next chat.
    void displaySource;
    copyGeneration += 1;
    copiedCode = "";
    copyStatus = "idle";
    return () => clearTimeout(feedbackTimer);
  });

  async function copyCode(text: string, index: number) {
    const generation = ++copyGeneration;
    clearTimeout(feedbackTimer);
    const key = index + ":" + text;
    try {
      await navigator.clipboard.writeText(text);
      if (generation !== copyGeneration) return;
      copiedCode = key;
      copyStatus = "copied";
    } catch {
      if (generation !== copyGeneration) return;
      copiedCode = key;
      copyStatus = "failed";
    }
    feedbackTimer = setTimeout(() => {
      if (generation === copyGeneration) {
        copiedCode = "";
        copyStatus = "idle";
      }
    }, 2200);
  }

  function children(token: Token): Token[] {
    return "tokens" in token && Array.isArray(token.tokens) ? token.tokens : [];
  }
</script>

{#snippet inline(items: Token[])}
  {#each items as token}
    {#if token.type === "text"}
      {#if children(token).length}{@render inline(children(token))}{:else}{token.text}{/if}
    {:else if token.type === "strong"}
      <strong>{@render inline(children(token))}</strong>
    {:else if token.type === "em"}
      <em>{@render inline(children(token))}</em>
    {:else if token.type === "del"}
      <del>{@render inline(children(token))}</del>
    {:else if token.type === "codespan"}
      <code>{token.text}</code>
    {:else if token.type === "link"}
      {#if safeHref(token.href)}
        <a href={safeHref(token.href) ?? undefined} target="_blank" rel="noopener noreferrer">{@render inline(children(token))}</a>
      {:else}
        {@render inline(children(token))}
      {/if}
    {:else if token.type === "br"}
      <br />
    {:else if token.type === "escape" || token.type === "html" || token.type === "image"}
      {token.type === "image" ? token.text : token.text}
    {/if}
  {/each}
{/snippet}

{#snippet blocks(items: Token[])}
  {#each items as token, index}
    {#if token.type === "heading"}
      {#if token.depth === 1}<h1>{@render inline(children(token))}</h1>
      {:else if token.depth === 2}<h2>{@render inline(children(token))}</h2>
      {:else}<h3>{@render inline(children(token))}</h3>{/if}
    {:else if token.type === "paragraph" || token.type === "text"}
      {@const metrics = legacyMetricSummary(token.text)}
      {@const labelList = legacyLabelList(token.text, captureSource)}
      {#if metrics}
        <div class="response-metrics" role="group" aria-label="Response metrics">
          {#each metrics as metric}
            <div class="response-metric">
              <strong class={"response-metric-value tone-" + metric.tone}>{metric.value}</strong>
              <span>{metric.label}</span>
            </div>
          {/each}
        </div>
      {:else if labelList}
        <ul class="result-recovered-list">{#each labelList as item}<li>{item}</li>{/each}</ul>
      {:else}
        <p>{@render inline(children(token).length ? children(token) : [token])}</p>
      {/if}
    {:else if token.type === "code"}
      <div class="code-snippet">
        <div class="code-toolbar"><span>{token.lang || "Code"}</span><button type="button" aria-label="Copy code" aria-live="polite" onclick={() => copyCode(token.text, index)}>{copiedCode === index + ":" + token.text ? (copyStatus === "copied" ? "Copied" : "Copy failed") : "Copy code"}</button></div>
        <pre><code class={token.lang ? "language-" + token.lang.split(/\s+/)[0] : ""}>{token.text}</code></pre>
      </div>
    {:else if token.type === "list"}
      {#if token.ordered}
        <ol start={token.start || 1}>{#each token.items as item}<li>{@render blocks(item.tokens)}</li>{/each}</ol>
      {:else}
        <ul>{#each token.items as item}<li>{@render blocks(item.tokens)}</li>{/each}</ul>
      {/if}
    {:else if token.type === "blockquote"}
      <blockquote>{@render blocks(token.tokens ?? [])}</blockquote>
    {:else if token.type === "table"}
      <div class="result-table-scroll"><table>
        <thead><tr>{#each token.header as cell}<th>{@render inline(cell.tokens)}</th>{/each}</tr></thead>
        <tbody>{#each token.rows as row}<tr>{#each row as cell}<td>{@render inline(cell.tokens)}</td>{/each}</tr>{/each}</tbody>
      </table></div>
    {:else if token.type === "hr"}
      <hr />
    {:else if token.type === "html"}
      <p>{token.text}</p>
    {/if}
  {/each}
{/snippet}

<div class:flattened class="result-markdown">{@render blocks(tokens)}</div>
