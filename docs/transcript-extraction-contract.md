# Transcript extraction contract

This document is the target contract for Prompta's ChatGPT transcript extraction redesign. It records the current extraction surfaces and the invariants later chunks must preserve while the implementation is moved away from styling-dependent selectors.

## Current extraction inventory

- `conversation_snapshot.py` owns the primary in-page snapshot script. It discovers visible user/assistant messages, reconstructs assistant prose and tool blocks, collects sanitized React-backed source events for the latest turn, derives stable/synthetic IDs, and reports streaming state. `parse_conversation_snapshot` is intentionally only a JSON boundary.
- `webdriver.py` is the browser-independent caller. `conversation_snapshot()` executes the snapshot script. `conversation_activity()` separately derives completion/streaming/failure state, and `conversation_final_event()` can read the authenticated conversation API to recover a completed final assistant event.
- `chromium.py` is read-only Chromium/CDP enrichment. Its React probe recovers structured tool-call metadata for the latest assistant turn, then `tool_blocks_from_messages()` / `ordered_assistant_content_from_messages()` / `merge_tool_blocks()` enrich assistant content without discarding non-tool text.
- `chatgpt_dom.py` centralizes ChatGPT DOM selectors. Stable role/data/test attributes are listed before structural or class-based compatibility fallbacks.

These paths overlap today. The redesign should converge them on the contract below rather than adding another independent extractor.

## Precedence

Extraction should use the strongest observable contract available, in this order:

1. **Semantic DOM relationships.** Author-role elements and document relationships determine user/assistant ownership and visible order. Visible text remains authoritative for what the user can actually see.
2. **Stable data/ARIA attributes.** `data-testid`, `data-message-id`, `data-message-uuid`, tool data attributes, streaming data attributes, and semantic ARIA state enrich identity and state. They must not reorder visible turns independently of DOM order.
3. **Narrow structural compatibility fallbacks.** Generic structural containers or known legacy classes may keep older DOM shapes working, but are fallback-only and must be labelled as such. Styling classes are never the primary contract.
4. **React/private-state fallback and enrichment.** React internals may recover hidden tool/reasoning events or a transcript when the public DOM is incomplete. React data must not replace visible assistant prose unless the replacement demonstrably contains the visible prose. Private property names are a last-resort compatibility mechanism, not a stable selector contract.

Backend conversation API recovery is a completion/reconciliation source, not a replacement for the visible transcript snapshot.

## Canonical snapshot model

A snapshot has:

- `path: str`
- `title: str`
- `messages: list[Turn]`
- `source_events: list[SourceEvent]` for the active/latest assistant turn
- `streaming: bool`

### Turn

A canonical visible turn contains:

- `id: str`: ChatGPT's stable message ID/UUID when available; deterministic Prompta synthetic ID only when no stable ID exists.
- `role: "user" | "assistant"`
- `content: str`: visible user text or reconstructed assistant content.
- `ordinal: int`: contiguous zero-based visible transcript order.

Tool and reasoning events do not become top-level turns.

### SourceEvent

Source events preserve the hidden/structured event stream needed to render one assistant turn faithfully. The sanitized shape is:

- identity/order: `id`, `parent_id`, `create_time`, `update_time`
- completion: `end_turn`, `status`
- routing: `role`, `recipient`, `content_type`
- content: `text`, `parts`
- tool/reasoning metadata: `connector_tool_payload`, `reasoning_title`, `reasoning_titles`, `invoked_resource`, `connector_name`
- provenance: `model_slug`, `request_id`
- rich references: `attachments`, `citations`, `content_references`

Source-event ordering should follow the message parent chain where present, using source time only as a tie-breaker/fallback. Tool invocation position is the canonical position for a tool call; completion wrappers/results enrich that call rather than moving it later.

## Invariants

1. **Visible text:** every visible user turn is represented once, and visible assistant prose is not lost when React/private state is incomplete or tool-only.
2. **Role isolation:** explicit user turns can never be promoted to assistant fallback turns.
3. **Ordering:** visible turns remain in DOM order. Within an assistant turn, prose, reasoning/activity, tool calls, and final prose retain canonical event order rather than being grouped by type.
4. **Tool calls:** invocation identity/order is preserved; results enrich the matching invocation. Tool UI chrome and buttons are not transcript text.
5. **Reasoning/activity:** reasoning titles/activity may be represented as structured source events/derived message parts, but must not overwrite final assistant prose.
6. **Streaming:** `streaming` is true when a visible stop control or stable streaming marker is active, or when the latest trustworthy assistant event explicitly has `end_turn == false`. A trustworthy `end_turn == true` is completion evidence, not a reason to drop visible content.
7. **IDs:** prefer `data-message-id` / `data-message-uuid` or source-event IDs. Ignore request-placeholder IDs. Synthetic live IDs must be deterministic for the same turn seed and must not collide with real IDs.
8. **Deduplication:** the same stable role+ID is emitted once. Streaming growth updates an existing turn/event instead of appending duplicate partials.
9. **Ordinals:** visible message ordinals are contiguous and match emitted order. Structured event/part ordinals preserve canonical event order.
10. **Fallback safety:** React/private-state fallback may fill missing information, but it cannot silently override stronger semantic DOM evidence.
11. **Noise:** controls, copy/regenerate affordances, transient connection banners, and tool-list chrome are excluded from transcript content.
12. **Compatibility:** legacy class selectors may remain while migrations are in progress, but fixture coverage must distinguish them from class-free semantic/data-attribute cases.

## Fixture baseline

`tests/fixtures/transcript_extraction/` contains small DOM shapes that exercise this contract:

- a class-free semantic/data-attribute transcript covering role ownership, IDs, visible ordering, and stable streaming markers;
- a legacy tool-order shape covering the currently unavoidable markdown compatibility selector while using stable tool attributes;
- a React-only fallback shape proving parent-chain ordering and source-event preservation when public message nodes are absent.

The fixture harness executes the production `CONVERSATION_SNAPSHOT_SCRIPT` in headless Chromium. New extractor implementations should continue to satisfy these fixtures, and new ChatGPT DOM shapes should be captured as minimal fixtures before adding selectors.
