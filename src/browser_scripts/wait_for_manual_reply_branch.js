(() => {
  const verify = () => (__VERIFY__);
  if (verify()) return Promise.resolve(true);
  // A composer can hydrate before the previous assistant messages.
  // Observe this one explicitly reopened tab; never poll or fetch history.
  return new Promise((resolve) => {
    const observer = new MutationObserver(() => {
      if (verify()) finish(true);
    });
    const timeout = setTimeout(() => finish(false), 12000);
    const finish = (matched) => {
      observer.disconnect();
      clearTimeout(timeout);
      resolve(matched);
    };
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["data-message-id", "data-chatgpt-search-message-ids"],
    });
    if (verify()) finish(true);
  });
})()
