# Svelte architecture

Prompta's application UI is fully owned by Svelte 5. `src/prompta/ui/app.ts`
contains data loading, reconciliation, persistence, and command orchestration; Svelte
components and rune modules own view state, markup, interactions, and reactive updates.

## Architecture

- Shared UI state lives in `.svelte.ts` rune modules using `$state` and
  `$derived`, not `svelte/store`.
- Application markup is rendered by `.svelte` components with stable keyed
  conversation/sidebar lists.
- Components use Svelte 5 event properties, class arrays/objects, snippets,
  `$props()`, `MediaQuery`, and `{@attach}`.
- Imperative element behavior such as focus, textarea sizing, selection, scrolling,
  click-outside handling, and native dialog methods is isolated in
  `browserAttachments.svelte.ts`.
- Markdown is parsed by Marked into tokens and rendered recursively by
  `MarkdownContent.svelte`. Syntax highlighting uses Lowlight/highlight.js HAST
  nodes. No Markdown or message content is injected with `{@html}`.
- Raw HTML embedded in Markdown is displayed as text rather than injected into the
  document.
- Clipboard, EventSource, service-worker, IndexedDB, and bootstrap APIs remain in
  narrow non-component browser/service modules.

## Required invariants

1. `app.ts` stays an orchestration module. It must not query or mutate rendered UI
   DOM.
2. Svelte components must not use `{@html}`, `bind:this`, legacy `on:` or
   `class:` directives, `use:V actions, `export let`, legacy slots,
   `svelte/store`, `$:`, or old lifecycle hooks.
3. Components must not call `document`/`window`, `matchMedia`, selectors,
   DOM-construction/mutation APIs, manual event listeners, or imperative
  focus/selection/scroll/dialog methods.
4. If a browser element API is genuinely required, add or extend a typed Svelte
   attachment in `browserAttachments.svelte.ts`; do not add an ad-hoc component
  exception.
5. Use `MediaQuery` from `svelte/reactivity` for responsive behavioral state.
6. Keep Markdown and syntax highlighting structured: parser/highlighter output must
   remain tokens/HAST rendered by Svelte rather than HTML strings.
7. Keep stable keys for conversation messages, sidebar chats, and other live lists.
8. Prefer established libraries for general parsing/highlighting behavior rather
   than maintaining custom parsers when a suitable dependency exists.

## Regression guards

`bun run check` enforces these rules with:

- `lint` / `lint:tests`: Oxlint and type-aware linting.
- `lint:dom`: the existing DOM rebuild guard.
- `lint:svelte-idioms`: rejects legacy Svelte syntax and direct component DOM
  access, and applies the no-view-DOM rule to `app.ts`.
- `check:svelte`: Svelte diagnostics with zero warnings/errors.
- `test:ui`: unit tests for UI logic, Markdown AST/highlighting behavior, DOM
  rebuild rules, and the Svelte idiom guard.
- `build`: the production Vite bundle.

The only source file intentionally allowed to contain imperative element APIs for
Svelte UI behavior is `browserAttachments.svelte.ts`. Other browser-specific
service modules should stay narrow and must not render or mutate application UI.
