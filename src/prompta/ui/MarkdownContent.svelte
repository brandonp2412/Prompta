<script lang="ts">
  import type { Element, RootContent } from "hast";
  import type { Token, Tokens } from "marked";

  import { copyText } from "./clipboard";
  import { codePresentation, parseMarkdown, safeLinkHref } from "./markdown";

  let { source, streaming = false }: { source: unknown; streaming?: boolean } = $props();

  let copiedKey = $state("");
  let expandedTools = $state.raw(new Set<string>());

  const tokens = $derived(parseMarkdown(source, { renderIncompleteFence: streaming }));

  function tokenKey(token: Token, index: number) {
    return token.type + ":" + index + ":" + token.raw.slice(0, 80);
  }

  function childTokens(token: Token) {
    return "tokens" in token && Array.isArray(token.tokens) ? token.tokens : [];
  }

  function elementClasses(node: Element) {
    const value = node.properties.className;

    return Array.isArray(value) ? value.map(String) : typeof value === "string" ? value : "";
  }

  function setToolOpen(key: string, open: boolean) {
    const next = new Set(expandedTools);

    if (open) next.add(key);
    else next.delete(key);

    expandedTools = next;
  }

  async function copyCode(key: string, code: string) {
    copiedKey = (await copyText(code)) ? key : "";

    if (copiedKey) {
      setTimeout(() => {
        if (copiedKey === key) copiedKey = "";
      }, 1000);
    }
  }
</script>

{#snippet highlightNodes(nodes: RootContent[])}
  {#each nodes as node}
    {#if node.type === "text"}
      {node.value}
    {:else if node.type === "element"}
      <span class={elementClasses(node)}>{@render highlightNodes(node.children)}</span>
    {/if}
  {/each}
{/snippet}

{#snippet inline(items: Token[])}
  {#each items as token, index (tokenKey(token, index))}
    {#if token.type === "text"}
      {#if childTokens(token)?.length}
        {@render inline(childTokens(token))}
      {:else}
        {token.text}
      {/if}
    {:else if token.type === "escape"}
      {token.text}
    {:else if token.type === "strong"}
      <strong>{@render inline(childTokens(token))}</strong>
    {:else if token.type === "em"}
      <em>{@render inline(childTokens(token))}</em>
    {:else if token.type === "del"}
      <del>{@render inline(childTokens(token))}</del>
    {:else if token.type === "codespan"}
      <code class="inline-code">{token.text}</code>
    {:else if token.type === "br"}
      <br />
    {:else if token.type === "link"}
      {#if safeLinkHref(token.href)}
        <a href={safeLinkHref(token.href)} target="_blank" rel="noreferrer noopener">
          {@render inline(childTokens(token))}
        </a>
      {:else}
        {@render inline(childTokens(token))}
      {/if}
    {:else if token.type === "image"}
      {token.text}
    {:else if token.type === "html"}
      {token.text}
    {/if}
  {/each}
{/snippet}

{#snippet blocks(items: Token[])}
  {#each items as token, index (tokenKey(token, index))}
    {#if token.type === "paragraph"}
      <p>{@render inline(childTokens(token))}</p>
    {:else if token.type === "heading"}
      {#if token.depth === 1}
        <h1>{@render inline(childTokens(token))}</h1>
      {:else if token.depth === 2}
        <h2>{@render inline(childTokens(token))}</h2>
      {:else if token.depth === 3}
        <h3>{@render inline(childTokens(token))}</h3>
      {:else if token.depth === 4}
        <h4>{@render inline(childTokens(token))}</h4>
      {:else if token.depth === 5}
        <h5>{@render inline(childTokens(token))}</h5>
      {:else}
        <h6>{@render inline(childTokens(token))}</h6>
      {/if}
    {:else if token.type === "hr"}
      <hr />
    {:else if token.type === "blockquote"}
      <blockquote>{@render blocks(childTokens(token))}</blockquote>
    {:else if token.type === "list"}
      {#if token.ordered}
        <ol start={typeof token.start === "number" ? token.start : undefined}>
          {#each token.items as item, itemIndex (item.raw + ":" + itemIndex)}
            <li class={{ "task-item": item.task }}>
              {#if item.task}
                <input type="checkbox" disabled checked={Boolean(item.checked)} />
              {/if}
              {@render blocks(item.tokens)}
            </li>
          {/each}
        </ol>
      {:else}
        <ul>
          {#each token.items as item, itemIndex (item.raw + ":" + itemIndex)}
            <li class={{ "task-item": item.task }}>
              {#if item.task}
                <input type="checkbox" disabled checked={Boolean(item.checked)} />
              {/if}
              {@render blocks(item.tokens)}
            </li>
          {/each}
        </ul>
      {/if}
    {:else if token.type === "table"}
      <div class={["table-scroll", { "table-scroll-wide": token.header.length >= 3 }]}>
        <table>
          <thead>
            <tr>
              {#each token.header as cell, cellIndex (cellIndex)}
                <th style:text-align={cell.align ?? undefined}>{@render inline(cell.tokens)}</th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each token.rows as row, rowIndex (rowIndex)}
              <tr>
                {#each row as cell, cellIndex (cellIndex)}
                  <td style:text-align={cell.align ?? undefined}>{@render inline(cell.tokens)}</td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {:else if token.type === "code"}
      {const presentation = codePresentation(token as Tokens.Code)}
      {const key = tokenKey(token, index)}
      {#if presentation}
        {#if presentation.tool}
          <details
            class={[
              "code-block",
              "tool-call-block",
              {
                "tool-has-summary": Boolean(presentation.tool.summary),
                "tool-has-meta": presentation.tool.hasMeta,
              },
            ]}
            ontoggle={(event) => setToolOpen(key, event.currentTarget.open)}
          >
            <summary class="code-header">
              {#if presentation.tool.summary}
                <span class="tool-summary">{presentation.tool.summary}</span>
                {#if presentation.tool.action}
                  <span class="tool-inline-meta">
                    <span class="tool-expanded-separator">|</span>
                    <span class="tool-expanded-action">{presentation.tool.action}</span>
                    {#if presentation.tool.connector}
                      <span class="tool-expanded-separator">|</span>
                      <span class="tool-expanded-connector">{presentation.tool.connector}</span>
                    {/if}
                  </span>
                {/if}
              {:else}
                <span class={presentation.tool.name ? "tool-primary-name" : "code-language"}>
                  {presentation.tool.name || presentation.label}
                </span>
              {/if}
              {#if presentation.tool.time}
                <time class="tool-time" datetime={presentation.tool.time.iso}>
                  {presentation.tool.time.text}
                </time>
              {/if}
            </summary>
            {#if presentation.tool.hasMeta}
              <div class="tool-expanded-meta">
                <span class="tool-expanded-action">{presentation.tool.action}</span>
                {#if presentation.tool.connector}
                  <span class="tool-expanded-separator">|</span>
                  <span class="tool-expanded-connector">{presentation.tool.connector}</span>
                {/if}
              </div>
            {/if}
            {#if presentation.code && expandedTools.has(key)}
              <pre><code class={"language-" + presentation.language}>{@render highlightNodes(presentation.highlighted)}</code></pre>
            {/if}
          </details>
        {:else}
          <div class="code-block">
            <div class="code-header">
              <span class="code-language">{presentation.label}</span>
              {#if presentation.code}
                <button type="button" class="copy-code" onclick={() => void copyCode(key, presentation.code)}>
                  {copiedKey === key ? "copied" : "copy"}
                </button>
              {/if}
            </div>
            {#if presentation.code}
              <pre><code class={"language-" + presentation.language}>{@render highlightNodes(presentation.highlighted)}</code></pre>
            {/if}
          </div>
        {/if}
      {/if}
    {:else if token.type === "html"}
      <p>{token.text}</p>
    {:else if token.type === "text"}
      <p>{@render inline([token])}</p>
    {/if}
  {/each}
{/snippet}

{@render blocks(tokens)}
