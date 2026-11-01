(() => {
  "use strict";
  // Inspect only the exact owned conversation after one explicit send.
  const conversation = __CONVERSATION__;
  const parent = __PARENT__;
  const targetReply = __REPLY__;
  /* PROMPTA_MARKDOWN_FROM_DOM */
  /* PROMPTA_REPLY_TURN_SCAN */
  // The verified parent may belong to the second or a later manual reply.
  // Require only one new user turn after that exact parent.
  const result = scanExactReplyTurn(conversation, "", targetReply, parent, true);
  const visible = (node) => node.isConnected && node.getClientRects().length > 0 &&
    getComputedStyle(node).visibility !== "hidden";
  const generating = [...document.querySelectorAll(
    'button[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"]'
  )].some(visible);
  const error_visible = [...document.querySelectorAll('[role="alert"], [role="status"]')]
    .filter(visible).some((node) =>
      /something went wrong|unable to load|an error occurred|failed to load/i
        .test(node.textContent || ""));
  return { verified: result.verified, complete: result.complete,
    message_id: result.branch_message_id, text: result.text,
    has_assistant: !!result.message_id, generating, error_visible };
})();
