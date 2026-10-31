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
  return { verified: result.verified, complete: result.complete,
    message_id: result.branch_message_id, text: result.text };
})();
