(() => {
  const observer = window.__promptaPassiveResponseObserver;
  return observer?.read?.() || { message_id: "", text: "", complete: false, ambiguous: false };
})()