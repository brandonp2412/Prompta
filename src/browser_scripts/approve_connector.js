(async () => {
  const visible = el => el.isConnected && el.getClientRects().length > 0 &&
    getComputedStyle(el).visibility !== 'hidden';
  const normalize = value => (value || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const label = el => {
    const copy = el.cloneNode(true);
    copy.querySelectorAll('kbd, [aria-hidden="true"]').forEach(hint => hint.remove());
    const labelled = (el.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => document.getElementById(id)?.textContent || '').join(' ');
    return normalize(el.getAttribute('aria-label') || labelled.trim() || copy.textContent);
  };
  const enabled = el => !el.disabled && el.getAttribute('aria-disabled') !== 'true';
  const controls = root => [...root.querySelectorAll('button, [role="button"]')];
  const isAlways = el => visible(el) && label(el) === 'always allow';
  const state = window.__promptaConnectorApproval ||= new WeakMap();
  const candidateAttribute = 'data-prompta-approval-candidate';
  const hasOnceFallback = button => {
    for (let group = button.parentElement; group && group !== document.body; group = group.parentElement) {
      if (group.matches('main, article, [data-message-author-role]')) break;
      const peers = controls(group).filter(visible);
      if (peers.some(el => label(el) === 'allow once') &&
          (group.matches('[role="dialog"], [role="alertdialog"]') ||
           peers.some(el => ['deny', 'decline'].includes(label(el))))) return true;
    }
    return false;
  };
  const approve = async (button, checkbox) => {
    if (!enabled(button) || (checkbox && !enabled(checkbox))) return false;
    const previous = state.get(button) || { attempts: 0, at: -Infinity };
    // ChatGPT can display controls before their event handlers hydrate.
    // Never permanently blacklist a still-visible permission after two misses.
    const retryAfter = Math.min(30000, 3000 * (2 ** Math.min(previous.attempts - 1, 4)));
    const checkboxChecked = checkbox &&
      (checkbox.checked || checkbox.getAttribute('aria-checked') === 'true');
    if (!(previous.checkboxPending && checkboxChecked) &&
        performance.now() - previous.at < retryAfter) return false;
    const next = { attempts: previous.attempts + 1, at: performance.now(), checkboxPending: false };
    state.set(button, next);
    document.querySelectorAll(`[${candidateAttribute}]`).forEach(el =>
      el.removeAttribute(candidateAttribute));
    if (checkbox && !checkboxChecked) {
      next.checkboxPending = true;
      checkbox.setAttribute(candidateAttribute, 'checkbox');
      checkbox.click();
      if (!(checkbox.checked || checkbox.getAttribute('aria-checked') === 'true')) return 'stuck';
    }
    next.checkboxPending = false;
    button.setAttribute(candidateAttribute, 'button');
    button.click();
    for (let i = 0; i < 5; i++) {
      await new Promise(resolve => setTimeout(resolve, 100));
      if (!visible(button)) return true;
    }
    return 'stuck';
  };
  for (const button of controls(document)) {
    if (!isAlways(button) || !enabled(button)) continue;
    // If the persistent action remains unresponsive, try the scoped one-time option.
    if ((state.get(button)?.attempts || 0) >= 3 && hasOnceFallback(button)) continue;
    // Locate the smallest permission group despite arbitrary wrapper depth.
    for (let group = button.parentElement; group && group !== document.body; group = group.parentElement) {
      if (group.matches('[role="dialog"], [role="alertdialog"]') ||
          controls(group).some(el => visible(el) && ['allow once', 'deny', 'decline'].includes(label(el)))) {
        return await approve(button);
      }
      if (group.matches('main, article, [data-message-author-role]')) break;
    }
  }
  for (const dialog of document.querySelectorAll('[role="dialog"], [role="alertdialog"]')) {
    if (!visible(dialog)) continue;
    const checkbox = [...dialog.querySelectorAll('input[type="checkbox"], [role="checkbox"]')]
      .find(el => visible(el) && normalize(el.getAttribute('aria-label') ||
        el.labels?.[0]?.textContent || el.parentElement?.textContent) === 'always allow');
    const allow = controls(dialog).find(el => visible(el) && label(el) === 'allow');
    if (checkbox && allow) return await approve(allow, checkbox);
  }
  // One-time approvals are permitted only inside a recognizable permission group,
  // and only when no visible persistent grant exists in that group.
  for (const button of controls(document)) {
    if (!visible(button) || !enabled(button) || label(button) !== 'allow once') continue;
    for (let group = button.parentElement; group && group !== document.body; group = group.parentElement) {
      if (group.matches('main, article, [data-message-author-role]')) break;
      const peers = controls(group).filter(visible);
      const permission = group.matches('[role="dialog"], [role="alertdialog"]') ||
        peers.some(el => ['deny', 'decline'].includes(label(el)));
      if (permission) {
        if (peers.some(el => isAlways(el) && enabled(el) &&
            (state.get(el)?.attempts || 0) < 3)) break;
        return await approve(button);
      }
    }
  }
  return false;
})()
