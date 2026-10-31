(() => {
  "use strict";
  // Exact read-only recovery; a claimed reply is never resent.
  const conversation = __CONVERSATION__;
  const originalPrompt = __ORIGINAL_PROMPT__;
  const replyText = __REPLY_TEXT__;
  const parent = __PARENT__;
  /* PROMPTA_MARKDOWN_FROM_DOM */
  /* PROMPTA_REPLY_TURN_SCAN */
  return scanExactReplyTurn(conversation, originalPrompt, replyText, parent, true);
})();
