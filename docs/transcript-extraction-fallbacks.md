# Transcript extraction fallbacks

The primary transcript path uses semantic author/turn attributes and semantic HTML content. The following fallbacks remain intentional after the live rollout:

- **Legacy turn roots (.agent-turn, then article)** remain because the live ChatGPT UI can render assistant turns without data-message-author-role or data-testid conversation-turn markers.
- **Legacy rich-text class selectors** remain secondary-only recovery for older/current markup that does not expose semantic prose blocks cleanly.
- **React-private introspection** remains for structured tool/source events and end_turn state that the visible DOM does not reliably expose. It is best-effort, provenance-labelled, and bounded by a shared extraction time budget plus node/object limits; budget exhaustion is surfaced through conversation-worker diagnostics.
- **Visible DOM prose synthesis** remains when React source events omit assistant prose that is visibly rendered.
- **Backend final-text recovery** remains a completion fallback when the browser DOM cannot supply the authoritative completed answer.

These fallbacks must stay out of the normal UI transcript as diagnostics; extraction provenance, fallback use, truncation/errors, and unreconciled expected content belong in conversation-worker logs.
