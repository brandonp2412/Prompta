from __future__ import annotations

# Keep ChatGPT DOM knowledge in one place. Selectors are ordered from the most
# semantic/stable contract to progressively broader structural fallbacks.
COMPOSER_SELECTORS = (
    'textarea[name="prompt-textarea"]',
    "#prompt-textarea",
    "[data-composer-surface] textarea",
    'form[data-type="unified-composer"] textarea',
    '[data-composer-surface] [contenteditable="true"][role="textbox"]',
    'form[data-type="unified-composer"] [contenteditable="true"][role="textbox"]',
    '[contenteditable="true"][role="textbox"]',
    'div[role="textbox"].ProseMirror',
    "textarea#mobile-composer-prompt",
    'main textarea[aria-label*="Chat" i]',
    'main textarea[placeholder*="Ask" i]',
)

SEND_BUTTON_SELECTORS = (
    '[data-testid="send-button"]',
    "#composer-submit-button",
    'button[aria-label="Send prompt"]',
    'button[aria-label*="send" i]',
    'button[type="submit"]',
)

STOP_BUTTON_SELECTORS = (
    '[data-testid="stop-button"]',
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
TURN_SELECTORS = (
    '[data-testid^="conversation-turn-"]',
    ".agent-turn",
    "article",
)

MARKDOWN_SELECTORS = (
    ".markdown",
    ".markdown-new-styling",
    '[class*="markdown"]',
)

STREAMING_SELECTORS = (
    '[data-streaming="active"]',
    '[data-is-streaming="true"]',
    '[aria-busy="true"][data-testid*="turn" i]',
)

RATE_LIMIT_SELECTORS = (
    '[data-testid="modal-conversation-history-rate-limit"]',
    '[data-testid="conversation-fetch-error-toaster"]',
    '[data-testid*="rate-limit" i]',
    '[role="alert"]',
    '[aria-live="assertive"]',
    '[aria-live="polite"]',
)


def css_union(selectors: tuple[str, ...]) -> str:
    return ",".join(selectors)


STOP_BUTTON_SELECTOR = css_union(STOP_BUTTON_SELECTORS)
TURN_SELECTOR = css_union(TURN_SELECTORS)
MARKDOWN_SELECTOR = css_union(MARKDOWN_SELECTORS)
STREAMING_SELECTOR = css_union(STREAMING_SELECTORS)
RATE_LIMIT_SELECTOR = css_union(RATE_LIMIT_SELECTORS)
