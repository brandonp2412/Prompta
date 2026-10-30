(() => {
  const verify = () => (__VERIFY__);
  if (verify()) return Promise.resolve(true);
  // A composer can hydrate before the previous assistant messages.
  // Observe this one explicitly reopened tab; never poll or fetch history.
  return new Promise((resolve) => {
    const observer = new MutationObserver(() => {
      if (verify()) finish(true);
    });
    // Allow slow conversation hydration while staying below the 30-second
    // Playwright evaluation bound. This check never submits a message.
    const timeout = setTimeout(() => finish(false), 24000);
    const finish = (matched) => {
      observer.disconnect();
      clearTimeout(timeout);
      resolve(matched);
    };
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["data-message-id", "data-chatgpt-search-message-ids", "data-content-search-message-ids"],
    });
    if (verify()) finish(true);
  });
})()
