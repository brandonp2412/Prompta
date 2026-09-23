from __future__ import annotations

import json

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

# Stable turn markers are kept separate from legacy layout fallbacks so callers
# cannot accidentally make styling classes part of their primary discovery path.
SEMANTIC_TURN_SELECTORS = ('[data-testid^="conversation-turn-"]',)
LEGACY_TURN_SELECTORS = (
    ".agent-turn",
    "article",
)
TURN_SELECTORS = SEMANTIC_TURN_SELECTORS + LEGACY_TURN_SELECTORS

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

CONVERSATION_HISTORY_RATE_LIMIT_SELECTOR = '[data-testid="modal-conversation-history-rate-limit"]'

RATE_LIMIT_SELECTORS = ('[data-testid*="rate-limit" i]',)


def css_union(selectors: tuple[str, ...]) -> str:
    return ",".join(selectors)


STOP_BUTTON_SELECTOR = css_union(STOP_BUTTON_SELECTORS)
SEMANTIC_TURN_SELECTOR = css_union(SEMANTIC_TURN_SELECTORS)
LEGACY_TURN_SELECTOR = css_union(LEGACY_TURN_SELECTORS)
TURN_SELECTOR = css_union(TURN_SELECTORS)
MARKDOWN_SELECTOR = css_union(MARKDOWN_SELECTORS)
STREAMING_SELECTOR = css_union(STREAMING_SELECTORS)
RATE_LIMIT_SELECTOR = css_union(RATE_LIMIT_SELECTORS)

MESSAGE_DISCOVERY_SCRIPT = (
    r"""
  const messageRoleSelector=__MESSAGE_ROLE_SELECTOR__;
  const assistantSelector=__ASSISTANT_SELECTOR__;
  const semanticTurnSelector=__SEMANTIC_TURN_SELECTOR__;
  const legacyTurnSelector=__LEGACY_TURN_SELECTOR__;
  const messageRole=node=>String(node?.getAttribute?.('data-message-author-role')||'');
  const messageId=node=>String(
    node?.getAttribute?.('data-message-id')
    ||node?.getAttribute?.('data-message-uuid')
    ||''
  );
  const authorNodes=role=>[...document.querySelectorAll(messageRoleSelector)]
    .filter(node=>!role||messageRole(node)===role);
  const authorNode=(root,role='')=>{
    if(!root)return null;
    if(messageRole(root)&&(!role||messageRole(root)===role))return root;
    return [...root.querySelectorAll(messageRoleSelector)]
      .find(node=>!role||messageRole(node)===role)||null;
  };
  const semanticTurnRoot=node=>node?.closest?.(semanticTurnSelector)||null;
  const structuralTurnRoot=node=>{
    if(!node)return null;
    let candidate=null;
    for(let parent=node.parentElement;parent&&parent!==document.body;parent=parent.parentElement){
      if(parent.tagName==='MAIN'||parent.getAttribute?.('role')==='main')break;
      const authors=[...parent.querySelectorAll(messageRoleSelector)];
      if(authors.length!==1||authors[0]!==node)break;
      candidate=parent;
    }
    return candidate;
  };
  const legacyTurnRoot=node=>node?.closest?.(legacyTurnSelector)||null;
  const turnRoot=node=>semanticTurnRoot(node)
    ||structuralTurnRoot(node)
    ||legacyTurnRoot(node)
    ||node
    ||null;
  const turnMessageId=(turn,role='')=>messageId(turn)
    ||messageId(authorNode(turn,role))
    ||messageId(turn?.querySelector?.('[data-message-id],[data-message-uuid]'))
    ||'';
""".replace("__MESSAGE_ROLE_SELECTOR__", json.dumps(MESSAGE_ROLE_SELECTOR))
    .replace("__ASSISTANT_SELECTOR__", json.dumps(ASSISTANT_MESSAGE_SELECTOR))
    .replace("__SEMANTIC_TURN_SELECTOR__", json.dumps(SEMANTIC_TURN_SELECTOR))
    .replace("__LEGACY_TURN_SELECTOR__", json.dumps(LEGACY_TURN_SELECTOR))
)
