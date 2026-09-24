from __future__ import annotations

from .browser_script_loader import render_browser_script

# CSS is limited to DOM state and hidden file inputs. Playwright interactions use
# accessible roles, names and visible text in playwright_driver.py.
FILE_INPUT_SELECTORS = (
    'form[data-type="unified-composer"] input[type="file"]',
    '[data-composer-surface] input[type="file"]',
    'input[type="file"]',
)

STOP_BUTTON_SELECTORS = (
    'button[aria-label="Stop answering"]',
    'button[aria-label="Stop generating"]',
    'button[aria-label*="stop" i]',
)

FILE_INPUT_SELECTORS = (
    'form[data-type="unified-composer"] input[type="file"]',
    '[data-composer-surface] input[type="file"]',
    'input[type="file"]',
)

MESSAGE_ROLE_SELECTOR = "[data-message-author-role]"
ASSISTANT_MESSAGE_SELECTOR = '[data-message-author-role="assistant"]'

# Stable turn markers are kept separate from legacy layout fallbacks so callers
# cannot accidentally make styling classes part of their primary discovery path.
SEMANTIC_TURN_SELECTORS = ('[data-testid^="conversation-turn-"]',)
LEGACY_TURN_SELECTORS = (
    ".agent-turn",
    "article",
)
TURN_SELECTORS = SEMANTIC_TURN_SELECTORS + LEGACY_TURN_SELECTORS

PROSE_BLOCK_SELECTORS = (
    "p",
    "pre",
    "blockquote",
    "ul",
    "ol",
    "table",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
)

# Styling-class selectors are legacy-only. Primary rich-text discovery uses
# semantic HTML blocks and author/turn structure.
LEGACY_RICH_TEXT_SELECTORS = (
    ".markdown",
    ".markdown-new-styling",
    '[class*="markdown"]',
)

STREAMING_SELECTORS = (
    '[data-streaming="active"]',
    '[data-is-streaming="true"]',
    '[aria-busy="true"][data-testid*="turn" i]',
)

CONVERSATION_HISTORY_RATE_LIMIT_SELECTOR = '[data-testid="modal-conversation-history-rate-limit"]'

RATE_LIMIT_SELECTORS = ('[data-testid*="rate-limit" i]',)


def css_union(selectors: tuple[str, ...]) -> str:
    return ",".join(selectors)


STOP_BUTTON_SELECTOR = css_union(STOP_BUTTON_SELECTORS)
SEMANTIC_TURN_SELECTOR = css_union(SEMANTIC_TURN_SELECTORS)
LEGACY_TURN_SELECTOR = css_union(LEGACY_TURN_SELECTORS)
TURN_SELECTOR = css_union(TURN_SELECTORS)
PROSE_BLOCK_SELECTOR = css_union(PROSE_BLOCK_SELECTORS)
LEGACY_RICH_TEXT_SELECTOR = css_union(LEGACY_RICH_TEXT_SELECTORS)
STREAMING_SELECTOR = css_union(STREAMING_SELECTORS)
RATE_LIMIT_SELECTOR = css_union(RATE_LIMIT_SELECTORS)

MESSAGE_DISCOVERY_SCRIPT = render_browser_script(
    "message_discovery.js",
    message_role_selector=MESSAGE_ROLE_SELECTOR,
    assistant_selector=ASSISTANT_MESSAGE_SELECTOR,
    semantic_turn_selector=SEMANTIC_TURN_SELECTOR,
    legacy_turn_selector=LEGACY_TURN_SELECTOR,
)
