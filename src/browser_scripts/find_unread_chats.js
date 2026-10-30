(() => {
  // Only inspect rendered sidebar rows. Never fetch account history or chat content.
  const paths = [];
  const markers = [
    '[data-unread="true"]',
    '[data-is-unread="true"]',
    '[data-state="unread"]',
    '[data-testid*="unread" i]',
    '[aria-label*="unread" i]',
    '[title*="unread" i]',
    '[aria-label*="new response" i]',
    '[title*="new response" i]',
    '[class~="unread"]',
    '[class~="is-unread"]',
  ].join(', ');
  const isUnread = el => {
    if (el.matches('[data-unread="true"], [data-is-unread="true"], [data-state="unread"], [class~="unread"], [class~="is-unread"]')) return true;
    const testid = (el.getAttribute('data-testid') || '').toLowerCase();
    if (/^unread(?:[-_]|$)|^(?:chat|conversation)[-_]unread(?:[-_]|$)/.test(testid)) return true;
    const label = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim().toLowerCase();
    return /^(unread|unread chat|unread response|unread replies|new response|new replies)(\s+\d+)?$/.test(label);
  };
  for (const link of document.querySelectorAll('a[href^="/c/"]')) {
    const row = link.closest('[data-sidebar-cycle-item], [data-testid="conversation-list-item"], li');
    if (!row) continue;
    const href = link.getAttribute('href') || '';
    if (!/^\/c\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(href)) continue;
    if ([row, ...row.querySelectorAll(markers)].some(el => isUnread(el))) paths.push(href);
    if (paths.length >= 8) break;
  }
  return paths;
})()
