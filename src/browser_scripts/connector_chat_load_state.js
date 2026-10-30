(() => {
  // Return structural status only; never expose chat text to the watcher.
  const main = document.querySelector('main');
  const messages = main?.querySelectorAll('[data-message-author-role], [data-chatgpt-search-unit-key], [data-testid^="conversation-turn-"]') || [];
  const notices = [...document.querySelectorAll('[role="alert"], [role="status"], [role="region"]')]
    .filter(node => main?.contains(node) && (node.textContent || '').trim().length < 200);
  const limited = notices.some(node => /too many requests|rate limit|try again in|wait a few minutes/i.test(node.textContent || ''));
  const failed = notices.some(node => /could not load (?:this )?chatgpt conversation|unable to load (?:this )?conversation/i.test(node.textContent || ''));
  return { loaded: messages.length > 0, failed, limited };
})()
