(() => {
  "use strict";
  // Read-only recovery of the latest manual reply on one exact stored branch.
  const conversation = __CONVERSATION__;
  const parent = __PARENT__;
  const userText = __USER_TEXT__;
  const savedAnswer = __ASSISTANT_TEXT__;
  const turnCount = __TURN_COUNT__;
  /* PROMPTA_MARKDOWN_FROM_DOM */
  /* PROMPTA_REPLY_TURN_SCAN */
  if (turnCount < 2) return null;
  const result = scanExactReplyTurn(conversation, "", userText, parent, true);
  if (!result.verified || result.ambiguous ||
      !result.latest_branch_message_id) return null;
  const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();
  if (savedAnswer && !normalize(result.text).startsWith(normalize(savedAnswer))) return null;
  const main = document.querySelector("main");
  const users = main?.querySelectorAll(
    '[data-message-author-role="user"], [data-chatgpt-search-unit-key$=":user"], [data-content-search-unit-key$=":user"]'
  );
  return users?.length === turnCount ? result.latest_branch_message_id : null;
})();
